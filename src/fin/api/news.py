"""资讯、公告、研报、日程。"""

from __future__ import annotations

import re

from .. import symbols
from ..config import TTL, today_cst
from ..sources import eastmoney

_TAG = re.compile(r"<[^>]+>")
_EM = re.compile(r"</?em>")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _TAG.sub("", _EM.sub("", text)).strip()


def _http_url(u: str | None) -> str | None:
    if not u:
        return None
    return u.replace("http://", "https://", 1)


def fast_news(limit: int = 20, offline: bool = False) -> tuple[dict, str, list[str]]:
    payload, state, warns = eastmoney.fast_news(page_size=limit)
    items = ((payload.get("data") or {}).get("fastNewsList")) or []
    rows = []
    for it in items[:limit]:
        rows.append(
            {
                "time": it.get("showTime"),
                "title": _clean(it.get("title")) or _clean(it.get("summary"))[:40],
                "summary": _clean(it.get("summary")),
                # 快讯接口不返回原文链接，只有内容 id
                "id": it.get("code"),
                "tags": it.get("stockList"),
            }
        )
    if rows:
        warns.append("快讯接口不提供原文链接，仅能展示标题与摘要")
    return {"count": len(rows), "items": rows}, state, warns


def stock_news(name_or_code: str, limit: int = 8, offline: bool = False) -> tuple[dict, str, list[str]]:
    payload, state, warns = eastmoney.news_search(name_or_code, page_size=limit)
    # jsonp 已剥离，但 JSONP 回调套壳已被 http._strip_jsonp 处理
    result = payload.get("result") or {}
    items = result.get("cmsArticleWebOld") or []
    rows = []
    for it in items[:limit]:
        rows.append(
            {
                "date": it.get("date"),
                "title": _clean(it.get("title")),
                "summary": _clean(it.get("content"))[:120],
                "url": _http_url(it.get("url")),
                "media": it.get("mediaName"),
            }
        )
    return {"keyword": name_or_code, "count": len(rows), "items": rows}, state, warns


def announcements(code: str, limit: int = 10, offline: bool = False) -> tuple[dict, str, list[str]]:
    payload, state, warns = eastmoney.announcements(code, page_size=limit)
    items = ((payload.get("data") or {}).get("list")) or []
    rows = []
    for it in items[:limit]:
        art = it.get("art_code")
        rows.append(
            {
                "date": (it.get("notice_date") or "")[:10],
                "title": it.get("title_ch") or it.get("title"),
                "type": ",".join(c.get("column_name", "") for c in (it.get("columns") or [])),
                "url": f"https://data.eastmoney.com/notices/detail/{code}/{art}.html" if art else None,
            }
        )
    return {"code": code, "count": len(rows), "items": rows}, state, warns


def research_reports(code: str, limit: int = 5, offline: bool = False) -> tuple[dict, str, list[str]]:
    begin = f"{today_cst()[:4]}-01-01"
    payload, state, warns = eastmoney.research_reports(code, begin, today_cst(), page_size=limit)
    items = payload.get("data") or []
    rows = []
    for it in items[:limit]:
        rows.append(
            {
                "date": (it.get("publishDate") or "")[:10],
                "title": it.get("title"),
                "org": it.get("orgSName"),
                "rating": it.get("emRatingName"),
                "eps_next2y": it.get("predictNextTwoYearEps"),
                "pe_next2y": it.get("predictNextTwoYearPe"),
            }
        )
    return {"code": code, "count": payload.get("hits"), "items": rows}, state, warns


def calendar(code: str | None = None, offline: bool = False) -> tuple[dict, str, list[str]]:
    """解禁 + 披露预约。不给 code 时返回今天之后 7 天的披露预约。"""
    from datetime import timedelta

    from ..config import now_cst

    warns: list[str] = []
    data: dict = {}
    state = "miss"

    if code:
        secucode = symbols.secucode_of(code)
        try:
            payload, state, w = eastmoney.lift_schedule(secucode)
            warns.extend(w)
            rows = ((payload.get("result") or {}).get("data")) or []
            data["lift"] = [
                {
                    "date": (r.get("FREE_DATE") or "")[:10],
                    "market_cap_yi": round((r.get("LIFT_MARKET_CAP") or 0) / 1e4, 2)
                    if isinstance(r.get("LIFT_MARKET_CAP"), (int, float)) else None,
                    "shares_wan": r.get("CURRENT_FREE_SHARES"),
                    "type": r.get("FREE_SHARES_TYPE"),
                }
                for r in rows
            ]
            if not rows:
                warns.append("该股票无历史解禁记录")
        except Exception as exc:
            data["lift"] = None
            warns.append(f"解禁数据获取失败：{exc}")

    today = now_cst()
    try:
        payload, state, w = eastmoney.disclosure_schedule(
            today.strftime("%Y-%m-%d"), (today + timedelta(days=7)).strftime("%Y-%m-%d"), page_size=20
        )
        warns.extend(w)
        rows = ((payload.get("result") or {}).get("data")) or []
        data["disclosure_next_7d"] = [
            {"date": (r.get("FIRST_APPOINT_DATE") or "")[:10],
             "code": r.get("SECURITY_CODE"),
             "name": r.get("SECURITY_NAME_ABBR")}
            for r in rows
        ]
        data["disclosure_note"] = "上游接口未返回报告期字段（REPORT_TYPE 编码需映射），仅列公司与日期"
    except Exception as exc:
        data["disclosure_next_7d"] = None
        warns.append(f"披露预约获取失败：{exc}")

    return data, state, warns
