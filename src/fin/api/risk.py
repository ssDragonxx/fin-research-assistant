"""风险规则引擎（确定性）。

输出命中项 + 证据 + 来源。LLM 只负责解释与排序，不得增删命中项。
"""

from __future__ import annotations

import statistics

from .. import symbols
from ..sources import eastmoney

ANNOUNCE_KEYWORDS = {
    "减持": "股东减持", "质押": "股权质押", "诉讼": "诉讼仲裁",
    "立案": "立案调查", "问询": "监管问询", "预亏": "业绩预亏",
    "退市": "退市风险", "担保": "对外担保", "冻结": "股份冻结",
    "违规": "违规处罚", "重整": "重整事项",
}

RULE_LEVELS = {"高": 3, "中": 2, "低": 1}


def _hit(rule: str, level: str, evidence: str, source: str) -> dict:
    return {"rule": rule, "level": level, "evidence": evidence, "source": source}


def scan(code: str, offline: bool = False) -> tuple[dict, str, list[str]]:
    warns: list[str] = []
    states: list[str] = []
    hits: list[dict] = []

    # 1. 股价异动：近 20 个交易日
    try:
        secid = symbols.secid_of(code)
        payload, st, w = eastmoney.kline(secid, limit=25)
        states.append(st)
        warns.extend(w)
        klines = ((payload.get("data") or {}).get("klines")) or []
        recent = klines[-20:]
        parsed = []
        for k in recent:
            parts = k.split(",")
            if len(parts) >= 8:
                parsed.append({"date": parts[0], "close": float(parts[2]),
                               "change_pct": float(parts[8]) if len(parts) > 8 else None,
                               "volume_ratio": float(parts[10]) if len(parts) > 10 else None})
        big_drop = [p for p in parsed if p["change_pct"] is not None and p["change_pct"] <= -7]
        for p in big_drop[-3:]:
            hits.append(_hit("股价异动", "高" if p["change_pct"] <= -9 else "中",
                             f"{p['date']} 单日下跌 {p['change_pct']}%", "push2his/kline"))
        high_vol = [p for p in parsed if p["volume_ratio"] and p["volume_ratio"] >= 2.5]
        for p in high_vol[-2:]:
            hits.append(_hit("成交量异动", "中",
                             f"{p['date']} 量比 {p['volume_ratio']}", "push2his/kline"))
        if parsed:
            closes = [p["close"] for p in parsed]
            drawdown = (closes[-1] / max(closes) - 1) * 100
            if drawdown <= -15:
                hits.append(_hit("区间回撤", "中", f"近20日区间回撤 {drawdown:.1f}%", "push2his/kline"))
    except Exception as exc:
        warns.append(f"K线数据获取失败，股价异动规则跳过：{exc}")

    # 2. 财务质量
    try:
        from . import stock

        fin, st, w = stock.financials(code, periods=5)
        states.append(st)
        warns.extend(w)
        periods = fin.get("periods") or []
        if periods:
            latest = periods[0]
            debt = latest.get("资产负债率%")
            if isinstance(debt, (int, float)) and debt > 70:
                hits.append(_hit("高负债率", "高" if debt > 85 else "中",
                                 f"{latest.get('报告期')} 资产负债率 {debt}%", "datacenter/financials"))
            gross = [p.get("销售毛利率%") for p in periods[:5] if isinstance(p.get("销售毛利率%"), (int, float))]
            if len(gross) >= 2 and gross[0] - gross[1] <= -5:
                hits.append(_hit("毛利率下滑", "中",
                                 f"毛利率由 {gross[1]}% 降至 {gross[0]}%，降幅 {gross[1] - gross[0]:.1f} 个百分点",
                                 "datacenter/financials"))
            profit = latest.get("归母净利润(亿)")
            if isinstance(profit, (int, float)) and profit < 0:
                hits.append(_hit("亏损", "高", f"{latest.get('报告期')} 归母净利润 {profit} 亿元",
                                 "datacenter/financials"))
    except Exception as exc:
        warns.append(f"财务数据获取失败，财务规则跳过：{exc}")

    # 3. 估值异常
    try:
        from . import stock

        q, st, w = stock.quote(code, offline=offline)
        states.append(st)
        warns.extend(w)
        pe = q.get("pe_ttm")
        if isinstance(pe, (int, float)) and pe < 0:
            hits.append(_hit("估值异常", "中", f"PE-TTM 为负（{pe}），公司处于亏损状态", "push2/stock"))
        try:
            peer, st2, w2 = stock.peers(code, industry_code=q.get("board_code"), offline=offline)
            states.append(st2)
            warns.extend(w2)
            diff = peer.get("pe_vs_peer_median_pct")
            if isinstance(diff, (int, float)) and diff > 150:
                hits.append(_hit("估值溢价", "中", f"PE 高于同业中位数 {diff}%", "push2/clist"))
        except Exception:
            pass
    except Exception as exc:
        warns.append(f"估值数据获取失败，估值规则跳过：{exc}")

    # 4. 重大公告关键词
    try:
        from . import news

        ann, st, w = news.announcements(code, limit=15, offline=offline)
        states.append(st)
        warns.extend(w)
        for item in ann.get("items") or []:
            title = item.get("title") or ""
            for kw, label in ANNOUNCE_KEYWORDS.items():
                if kw in title:
                    hits.append(_hit("重大公告", "高" if kw in {"立案", "退市", "预亏", "减持"} else "中",
                                     f"{item.get('date')} {label}：{title}", "np-anotice-stock"))
                    break
    except Exception as exc:
        warns.append(f"公告数据获取失败，公告规则跳过：{exc}")

    # 5. 解禁压力：只看未来，历史解禁不是风险
    try:
        from datetime import timedelta

        from ..config import now_cst
        from . import news

        cal, st, w = news.calendar(code=code, offline=offline)
        states.append(st)
        warns.extend(w)
        today = now_cst().strftime("%Y-%m-%d")
        horizon = (now_cst() + timedelta(days=90)).strftime("%Y-%m-%d")
        upcoming = [
            x for x in (cal.get("lift") or [])
            if x.get("date") and today <= x["date"] <= horizon
        ]
        for x in upcoming[:2]:
            hits.append(_hit("解禁压力", "中" if upcoming else "低",
                             f"{x['date']} 解禁市值约 {x.get('market_cap_yi')} 亿元，"
                             f"类型：{x.get('type') or '未标注'}",
                             "datacenter/RPT_LIFT_STAGE"))
        if not upcoming:
            warns.append("未来 90 天内无解禁记录")
    except Exception as exc:
        warns.append(f"解禁数据获取失败，解禁规则跳过：{exc}")

    hits.sort(key=lambda h: RULE_LEVELS.get(h["level"], 0), reverse=True)
    data = {
        "code": code,
        "hit_count": len(hits),
        "max_level": hits[0]["level"] if hits else "无",
        "hits": hits,
        "note": "规则命中为确定性判定，由 LLM 解释与排序，不得增删",
    }
    state = "hit" if states and all(s == "hit" for s in states) else "miss"
    return data, state, warns
