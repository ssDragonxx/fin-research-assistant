"""日报数据骨架拼装。LLM 只负责在 narrative_slots 处填写解读。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .. import envelope, symbols
from ..config import DATA_DIR, today_cst
from . import market, news

BRIEF_DIR = DATA_DIR / "briefs"


def assemble(offline: bool = False, date: str | None = None) -> dict:
    date = date or today_cst()
    warns: list[str] = []
    states: list[str] = []
    blocks: dict = {}

    snap, st, w = market.market_snapshot(offline=offline)
    blocks["market"] = snap
    states.append(st)
    warns.extend(w)

    try:
        n, st, w = news.fast_news(limit=20, offline=offline)
        blocks["news"] = n
        states.append(st)
        warns.extend(w)
    except Exception as exc:
        blocks["news"] = None
        warns.append(f"资讯获取失败：{exc}")

    try:
        cal, st, w = news.calendar(code=None, offline=offline)
        blocks["calendar"] = cal
        states.append(st)
        warns.extend(w)
    except Exception as exc:
        blocks["calendar"] = None
        warns.append(f"日程获取失败：{exc}")

    prev = load_brief(date, offset=-1)
    narrative_slots = {
        "market_comment": "【待 LLM 填写：用一段话概括今日行情冷暖，数字必须来自 blocks.market】",
        "sector_comment": "【待 LLM 填写：哪些板块领涨领跌、资金流向何处，引用 blocks.market.sector】",
        "news_comment": "【待 LLM 填写：从 blocks.news 中挑 3-5 条最重要的，说明与市场的关联】",
        "tomorrow_watch": "【待 LLM 填写：引用 blocks.calendar 与 market 数据，列出次日关注项】",
        "yesterday_review": "【待 LLM 填写：逐条对照 previous_brief.predictions，标注 已验证/未验证/不成立】",
    }

    data = {
        "date": date,
        "blocks": blocks,
        "previous_brief": prev,
        "narrative_slots": narrative_slots,
        "rules": [
            "所有数字必须来自 blocks，不得跨日期拼接",
            "每段结论末尾标注来源键，如 [market.indexes]",
            "数据缺失写「暂无数据」，不得推断",
            "不预测涨跌，不给买卖建议",
        ],
    }
    state = "hit" if states and all(x == "hit" for x in states) else "miss"
    return envelope.ok("brief.assemble", data, sources=[envelope.source("东方财富", "多接口聚合")],
                        warnings=warns, cache=state, as_of=f"{date}T15:30:00+08:00")


def _brief_path(date: str) -> Path:
    return BRIEF_DIR / f"{date}.md"


def _date_offset(date: str, offset: int) -> str:
    from datetime import datetime, timedelta

    d = datetime.strptime(date, "%Y-%m-%d") + timedelta(days=offset)
    return d.strftime("%Y-%m-%d")


def load_brief(date: str, offset: int = 0) -> dict | None:
    """读取某日的简报文件；不存在则返回 None。"""
    target = _date_offset(date, offset)
    path = _brief_path(target)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return {"date": target, "markdown": text}


def save_brief(date: str, markdown: str) -> str:
    BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    path = _brief_path(date)
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def latest_brief() -> dict | None:
    if not BRIEF_DIR.exists():
        return None
    files = sorted(BRIEF_DIR.glob("*.md"))
    if not files:
        return None
    p = files[-1]
    return {"date": p.stem, "markdown": p.read_text(encoding="utf-8")}
