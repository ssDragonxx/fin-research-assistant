"""行情与市场宽度。"""

from __future__ import annotations

import time

from .. import envelope
from ..config import INDEXES, TTL, today_cst
from ..sources import eastmoney, tencent

# ulist.np 字段：f2 最新价 f3 涨跌幅 f4 涨跌额 f6 成交额 f12 代码 f14 名称
INDEX_FIELDS = "f2,f3,f4,f6,f12,f14"
# ulist.np 字段：f12 代码 f104 涨 f105 跌 f106 平 f107 停牌
BREADTH_FIELDS = "f12,f104,f105,f106,f107"

# 板块字段：f3 涨跌幅 f12 板块代码 f14 名称 f62 主力净流入 f104 涨 f105 跌 f128 领涨股
SECTOR_FIELDS = "f12,f14,f3,f62,f104,f105,f128,f136"
INDUSTRY_FS = "m:90+t:2"  # 东财行业板块（含 Ⅱ/Ⅲ 层级）


def _index_map() -> dict[str, dict]:
    return {i["secid"]: i for i in INDEXES}


def quotes(offline: bool = False) -> tuple[dict, str, list[str]]:
    """主要指数行情。东财优先，push2 限流时降级到腾讯。"""
    warns: list[str] = []
    codes = [i["code"] for i in INDEXES]
    by_code = {i["code"]: i for i in INDEXES}
    items: list[dict] = []
    state = "miss"

    try:
        secids = [i["secid"] for i in INDEXES]
        payload, state, warns = eastmoney.quotes(secids, INDEX_FIELDS)
        for row in ((payload.get("data") or {}).get("diff")) or []:
            code = row.get("f12")
            meta = by_code.get(code, {})
            items.append(
                {
                    "name": row.get("f14") or meta.get("name") or "?",
                    "code": code,
                    "price": row.get("f2"),
                    "change_pct": row.get("f3"),
                    "change": row.get("f4"),
                    "amount_yuan": row.get("f6"),
                }
            )
        if items:
            warns = [w for w in warns if not w.startswith("上游请求失败")]
    except Exception as exc:
        warns.append(f"东财行情不可用，切换腾讯数据源：{exc}")

    if not items:
        rows, state, w = tencent.quotes(codes, kinds="index")
        warns.extend(w)
        for r in rows:
            items.append(
                {
                    "name": by_code.get(r["code"], {}).get("name") or r["name"],
                    "code": r["code"],
                    "price": r["price"],
                    "change_pct": r["change_pct"],
                    "change": r["change"],
                    "amount_yuan": r["amount_yuan"],
                }
            )
        if items:
            warns.append("行情来源：腾讯（东财 push2 不可用）")

    if not items:
        raise ValueError("所有行情源均不可用")

    total_amount = sum(i["amount_yuan"] or 0 for i in items)
    up = sum(1 for i in items if (i.get("change_pct") or 0) > 0)
    data = {
        "date": time.strftime("%Y-%m-%d", time.localtime()),
        "indexes": items,
        "summary": {
            "up_indexes": up,
            "down_indexes": len(items) - up,
            "total_amount_yi": round(total_amount / 1e8, 1),
            "weekday": time.strftime("%A", time.localtime()),
        },
    }
    return data, state, warns


def breadth(offline: bool = False) -> tuple[dict, str, list[str]]:
    """指数级涨跌家数。

    坑：stock/get 的 f104/f105 恒为 0，必须走 ulist.np 且带 f12 才拿得到；
    ulist.np 限流时该指标直接缺失，不能用 0 冒充。
    """
    secids = [i["secid"] for i in INDEXES]
    payload, state, warns = eastmoney.quotes(secids, BREADTH_FIELDS)
    diff = ((payload.get("data") or {}).get("diff")) or []

    by_code = {i["code"]: i["name"] for i in INDEXES}
    rows = []
    for row in diff:
        code = row.get("f12")
        up, down = row.get("f104"), row.get("f105")
        if not isinstance(up, (int, float)):
            continue
        rows.append(
            {
                "index": by_code.get(code, code),
                "code": code,
                "up": int(up),
                "down": int(down or 0),
                "flat": int(row.get("f106") or 0),
                "halt": int(row.get("f107") or 0),
            }
        )

    merged = {
        "as_of_date": time.strftime("%Y-%m-%d", time.localtime()),
        "scope": "指数级口径：沪指=沪市，深成指=深市，创业板/科创50 为子集，不可相加",
        "by_index": rows,
        "market_total": None,
    }
    if not rows:
        merged["unavailable"] = True
        merged["reason"] = "涨跌家数接口不可用（东财 ulist.np 限流），该指标缺省"
        return merged, "miss", warns + ["涨跌家数暂无数据：数据源不可用，报告中不得推测"]

    sh = next((r for r in rows if r["code"] == "000001"), None)
    sz = next((r for r in rows if r["code"] == "399001"), None)
    if sh and sz:
        merged["market_total"] = {
            "up": sh["up"] + sz["up"],
            "down": sh["down"] + sz["down"],
            "flat": sh["flat"] + sz["flat"],
            "halt": sh["halt"] + sz["halt"],
            "note": "沪指 + 深成指，覆盖沪深两市全部个股（创业板/科创板已含在内）",
        }
    return merged, state, warns


def limit_up(date: str | None = None, offline: bool = False) -> tuple[dict, str, list[str]]:
    d = (date or today_cst()).replace("-", "")
    payload, state, warns = eastmoney.limit_up_pool(d)
    data = payload.get("data") or {}
    total = data.get("tc")
    pool = data.get("pool") or []
    sample = [
        {"code": p.get("c"), "name": p.get("n"), "change_pct": p.get("zdp"),
         "boards": (p.get("zttj") or {}).get("ct"), "industry": p.get("hybk")}
        for p in pool[:5]
    ]
    return (
        {"date": d, "count": total if total is not None else None, "sample": sample},
        state,
        warns + ([] if total is not None else ["涨停池当日无数据（非交易日或未开盘）"]),
    )


def sentiment(date: str | None = None, offline: bool = False) -> tuple[dict, str, list[str]]:
    """涨跌停与强势股统计。涨跌家数接口不可用时的替代情绪指标。"""
    d = (date or today_cst()).replace("-", "")
    warns: list[str] = []
    states: list[str] = []
    out: dict = {"date": d}

    for kind, label in (("zt", "涨停"), ("dt", "跌停"), ("qs", "强势")):
        try:
            payload, st, w = eastmoney.limit_pool(kind, d)
            states.append(st)
            warns.extend(w)
            data = payload.get("data") or {}
            pool = data.get("pool") or []
            out[label] = {
                "count": data.get("tc"),
                "sample": [
                    {"code": p.get("c"), "name": p.get("n"),
                     "change_pct": p.get("zdp"), "industry": p.get("hybk")}
                    for p in pool[:3]
                ],
            }
        except Exception as exc:
            out[label] = None
            warns.append(f"{label}统计获取失败：{exc}")

    zt = (out.get("涨停") or {}).get("count")
    dt = (out.get("跌停") or {}).get("count")
    if isinstance(zt, int) and isinstance(dt, int):
        out["ratio_note"] = f"涨停 {zt} / 跌停 {dt}，比值 {round(zt / dt, 2) if dt else '∞'}"
        if zt >= 50 and dt <= 5:
            warns.append("涨停家数偏多且跌停极少，市场情绪偏强（参考口径，非直接结论）")
        elif dt >= 30:
            warns.append("跌停家数偏多，市场情绪偏弱（参考口径）")
    state = "hit" if states and all(s == "hit" for s in states) else "miss"
    return out, state, warns


def _fetch_all_sectors(offline: bool = False) -> tuple[list[dict], str, list[str]]:
    """行业板块。优先 clist（含涨跌家数），失败则用数据中心资金流表（不含涨跌家数）。"""
    rows: list[dict] = []
    state = "miss"
    warns: list[str] = []
    page = 1
    try:
        while page <= 10:
            payload, st, w = eastmoney.clist(
                INDUSTRY_FS, SECTOR_FIELDS, page=page, page_size=100, fid="f3", ttl=TTL["sectors"]
            )
            if st == "hit":
                state = "hit"
            warns.extend(w)
            data = payload.get("data") or {}
            diff = data.get("diff") or []
            for r in diff:
                name = r.get("f14") or ""
                rows.append(
                    {
                        "code": r.get("f12"),
                        "name": name,
                        "change_pct": r.get("f3"),
                        "main_net_inflow": r.get("f62"),
                        "up": r.get("f104"),
                        "down": r.get("f105"),
                        "leader": r.get("f128"),
                        "level": "sub" if ("Ⅱ" in name or "Ⅲ" in name) else "primary",
                    }
                )
            total = data.get("total") or 0
            if len(diff) < 100 or page * 100 >= total:
                break
            page += 1
    except Exception as exc:
        warns.append(f"clist 板块接口不可用，切换数据中心资金流表：{exc}")

    if rows:
        return rows, state, warns

    # 兜底：数据中心资金流（无涨跌家数、无层级字段靠名称判断）
    payload, st, w = eastmoney.industry_fundflow()
    state = st
    warns.extend(w)
    warns.append("板块数据来自资金流表：不含涨跌家数，涨跌幅与主力净流入可用")
    items = ((payload.get("result") or {}).get("data")) or []
    for r in items:
        name = r.get("BOARD_NAME") or ""
        rows.append(
            {
                "code": r.get("BOARD_CODE"),
                "name": name,
                "change_pct": r.get("CHANGE_RATE"),
                "main_net_inflow": r.get("NET_INFLOW"),
                "up": None,
                "down": None,
                "leader": r.get("MAX_NETINFLOW_SEC"),
                "level": "sub" if ("Ⅱ" in name or "Ⅲ" in name) else "primary",
            }
        )
    return rows, state, warns


def _dedupe_primary(rows: list[dict]) -> list[dict]:
    """一级板块去重。

    只有在能拿到涨跌家数时才可去重（父子板块涨跌家数完全相同）；
    没有涨跌家数时无法判断层级，直接按名称过滤，不做合并——否则会把所有板块并成 1 个。
    """
    primaries = [r for r in rows if r["level"] == "primary"]
    has_counts = all(
        isinstance(r.get("up"), int) and isinstance(r.get("down"), int) for r in primaries
    )
    if not has_counts:
        return primaries

    seen: dict[tuple, dict] = {}
    out: list[dict] = []
    for r in primaries:
        key = (r.get("up"), r.get("down"))
        holder = seen.get(key)
        if holder is None:
            seen[key] = r
            out.append(r)
            continue
        if len(r["name"]) < len(holder["name"]):
            out[out.index(holder)] = r
            seen[key] = r
    return out


def sector(limit: int = 10, offline: bool = False) -> tuple[dict, str, list[str]]:
    rows, state, warns = _fetch_all_sectors(offline=offline)
    if not rows:
        raise ValueError("板块数据为空")

    primary = _dedupe_primary(rows)
    mixed_warn = f"行业板块共 {len(rows)} 个（含二级/三级），按一级去重后 {len(primary)} 个"
    ordered = sorted(primary, key=lambda x: x["change_pct"] or -999, reverse=True)
    top = ordered[:limit]
    bottom = [r for r in sorted(primary, key=lambda x: x["change_pct"] or 999)[:limit]
              if r["code"] not in {t["code"] for t in top}]
    data = {
        "total_boards": len(rows),
        "primary_boards": len(primary),
        "top": top,
        "bottom": bottom,
    }
    return data, state, warns + [mixed_warn]


def market_snapshot(offline: bool = False) -> dict:
    """日报用的行情骨架。任何子项失败都不阻断整体。"""
    warns: list[str] = []
    states: list[str] = []
    data: dict = {}

    try:
        q, st, w = quotes(offline=offline)
        data["indexes"] = q
        states.append(st)
        warns.extend(w)
    except Exception as exc:
        data["indexes"] = None
        warns.append(f"指数行情获取失败：{exc}")

    try:
        b, st, w = breadth(offline=offline)
        data["breadth"] = b
        states.append(st)
        warns.extend(w)
        if b.get("unavailable"):
            try:
                s, st2, w2 = sentiment(offline=offline)
                data["sentiment"] = s
                states.append(st2)
                warns.extend(w2)
                warns.append("涨跌家数不可用，已用涨跌停统计替代情绪指标")
            except Exception as exc:
                data["sentiment"] = None
                warns.append(f"情绪指标也获取失败：{exc}")
    except Exception as exc:
        data["breadth"] = None
        warns.append(f"涨跌家数获取失败：{exc}")

    try:
        zt, st, w = limit_up(offline=offline)
        data["limit_up"] = zt
        states.append(st)
        warns.extend(w)
    except Exception as exc:
        data["limit_up"] = None
        warns.append(f"涨停池获取失败：{exc}")

    try:
        s, st, w = sector(offline=offline)
        data["sector"] = s
        states.append(st)
        warns.extend(w)
    except Exception as exc:
        data["sector"] = None
        warns.append(f"板块行情获取失败：{exc}")

    state = "hit" if states and all(x == "hit" for x in states) else ("miss" if states else "miss")
    return data, state, warns
