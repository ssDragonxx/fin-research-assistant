"""个股：行情估值、财务、同业。"""

from __future__ import annotations

from .. import symbols
from ..config import TTL
from ..sources import eastmoney, tencent

# 东财补充字段：f58 名称 f162 PE动态 f164 PE-TTM f173 ROE f184 营收同比
# f127 行业 f198 板块代码 f100 行业(备选)
EASTMONEY_EXTRA = "f43,f57,f58,f116,f117,f162,f164,f167,f173,f184,f127,f198,f100"

PEER_FIELDS = "f12,f14,f2,f3,f9,f20,f23,f100"


def quote(code: str, offline: bool = False) -> tuple[dict, str, list[str]]:
    """个股行情估值。腾讯为主（稳定、一次一股份），东财只补 ROE 与行业。"""
    warns: list[str] = []
    data: dict = {"code": code}

    rows, state, w = tencent.quotes([code], kinds="stock")
    warns.extend(w)
    t = next((r for r in rows if r["code"] == code), None)
    if t:
        data.update(
            {
                "name": t["name"],
                "price": t["price"],
                "change": t["change"],
                "change_pct": t["change_pct"],
                "market_cap_yi": t["market_cap_yi"],
                "float_cap_yi": t["float_cap_yi"],
                "pe_ttm": t["pe_ttm"],
                "pb": t["pb"],
                "source": "腾讯",
            }
        )
    else:
        warns.append("腾讯行情未返回该股票，尝试东财")

    # 东财补充：ROE、行业、PE 交叉校验。失败不影响主结果。
    try:
        secid = symbols.secid_of(code)
        payload, st, w = eastmoney.stock_quote(secid, EASTMONEY_EXTRA)
        warns.extend(w)
        d = payload.get("data") or {}
        if d:
            data.setdefault("name", d.get("f58"))
            data["roe"] = d.get("f173")
            data["revenue_yoy"] = d.get("f184")
            data["industry"] = d.get("f127") or d.get("f100")
            data["board_code"] = d.get("f198")
            em_pe = d.get("f164")
            if isinstance(em_pe, (int, float)) and isinstance(data.get("pe_ttm"), (int, float)):
                if abs(em_pe - data["pe_ttm"]) / max(abs(em_pe), 1e-9) > 0.15:
                    warns.append(
                        f"两个数据源的 PE-TTM 差异较大：腾讯 {data['pe_ttm']} / 东财 {em_pe}，需人工核对"
                    )
            if not data.get("pe_ttm") and isinstance(em_pe, (int, float)):
                data["pe_ttm"] = em_pe
                data["pe_source"] = "东财"
            warns.append(
                f"PE 存在多个口径：动态 {d.get('f162')} / TTM {d.get('f164')} / 腾讯 {data.get('pe_ttm')}，报告统一使用 PE-TTM"
            )
    except Exception as exc:
        warns.append(f"东财补充字段（ROE/行业）暂不可用：{exc}")

    missing = [k for k in ("price", "market_cap_yi", "pe_ttm", "pb") if data.get(k) is None]
    if missing:
        warns.append(f"以下字段暂无数据：{'、'.join(missing)}")

    return data, state, warns


FIN_FIELDS = [
    ("REPORT_DATE_NAME", "报告期"),
    ("EPSJB", "基本每股收益"),
    ("BPS", "每股净资产"),
    ("TOTALOPERATEREVE", "营业总收入"),
    ("PARENTNETPROFIT", "归母净利润"),
    ("TOTALOPERATEREVETZ", "营收同比%"),
    ("PARENTNETPROFITTZ", "归母净利同比%"),
    ("ROEJQ", "加权ROE%"),
    ("XSMLL", "销售毛利率%"),
    ("ZCFZL", "资产负债率%"),
    ("MGJYXJJE", "每股经营现金流"),
]


def financials(code: str, periods: int = 4, offline: bool = False) -> tuple[dict, str, list[str]]:
    secucode = symbols.secucode_of(code)
    payload, state, warns = eastmoney.main_financials(secucode, periods)
    result = payload.get("result") or {}
    rows = result.get("data") or []
    if not rows:
        warns.append("未获取到财务数据（可能为新股或数据源未覆盖）")
    out = []
    for r in rows:
        item = {}
        for key, label in FIN_FIELDS:
            v = r.get(key)
            if key == "TOTALOPERATEREVE" and isinstance(v, (int, float)):
                v = round(v / 1e8, 2)
                label = "营业总收入(亿)"
            elif key == "PARENTNETPROFIT" and isinstance(v, (int, float)):
                v = round(v / 1e8, 2)
                label = "归母净利润(亿)"
            item[label] = v
        out.append(item)
    return {"code": code, "periods": out}, state, warns


def industry_of(code: str, offline: bool = False) -> tuple[dict | None, str, list[str]]:
    """所属行业板块。走数据中心核心题材表，避开 push2。

    返回 {"board_code": "BK1033", "board_name": "电池", "numeric": "1033", "levels": [...]}
    偏好二级行业（电池），因为一级行业（电力设备）太宽，同业对比参考价值低。
    """
    secucode = symbols.secucode_of(code)
    payload, state, warns = eastmoney.stock_boards(secucode)
    rows = ((payload.get("result") or {}).get("data")) or []
    industries = [
        {
            "board_code": r.get("NEW_BOARD_CODE") or f"BK{r.get('BOARD_CODE')}",
            "board_name": r.get("BOARD_NAME"),
            "numeric": str(r.get("BOARD_CODE")),
            "rank": r.get("BOARD_RANK"),
        }
        for r in rows
        if r.get("BOARD_TYPE") == "行业"
    ]
    if not industries:
        return None, state, warns + ["未找到该股票的行业板块（BOARD_TYPE=行业）"]

    # BOARD_RANK 越大越细分：电池(2) 比 电力设备(1) 更具体
    industries.sort(key=lambda x: x.get("rank") or 0, reverse=True)
    primary = dict(industries[0])
    primary["levels"] = [dict(x) for x in industries]
    return primary, state, warns


def peers(code: str, industry_code: str | None = None, limit: int = 5,
          offline: bool = False) -> tuple[dict, str, list[str]]:
    """同业对比。

    成员来自数据中心成分股表（含净利润与 PE 分位），价格与 PE-TTM 用腾讯批量补齐。
    不依赖 push2 的 clist。
    """
    warns: list[str] = []
    states: list[str] = []

    info = None
    if not industry_code:
        try:
            info, st, w = industry_of(code, offline=offline)
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"行业识别失败：{exc}")

    numeric = (info or {}).get("numeric")
    if industry_code and industry_code.startswith("BK"):
        numeric = industry_code[2:]
    if not numeric:
        raise ValueError("无法确定所属行业（行业字段不可用），暂无法做同业对比")

    payload, state, w = eastmoney.board_constituents(numeric, page_size=max(limit + 5, 30))
    states.append(state)
    warns.extend(w)
    rows = ((payload.get("result") or {}).get("data")) or []
    if not rows:
        raise ValueError("行业成分股为空")

    members = []
    for r in rows:
        profit = r.get("ACCUM_NETPROFIT")
        members.append(
            {
                "code": r.get("SECURITY_CODE"),
                "name": None,  # 该表无简称字段，稍后用腾讯行情补
                "net_profit_yi": round(profit / 1e8, 2) if isinstance(profit, (int, float)) else None,
                "profit_yoy": r.get("NETPROFIT_RATIO_1Y"),
                "pe_ttm_percentile": r.get("PE_TTM_PERCENTILE"),
                "dividend_yield": r.get("DIVIDEND_RATIO"),
                "is_st": r.get("IS_ST") == 1,
            }
        )
    members.sort(key=lambda x: x["net_profit_yi"] or -1e18, reverse=True)

    target_idx = next((i for i, m in enumerate(members) if m["code"] == code), None)
    target = members[target_idx] if target_idx is not None else None
    # 取净利润最接近的同业（含前后），排除 ST
    others = [m for m in members if m["code"] != code and not m["is_st"]]
    if target and target["net_profit_yi"]:
        others.sort(key=lambda m: abs((m["net_profit_yi"] or 0) - target["net_profit_yi"]))
    others = others[:limit]

    # 腾讯补齐名称/价格/PE/PB/市值
    if others:
        try:
            trows, _, tw = tencent.quotes([m["code"] for m in others], kinds="stock")
            warns.extend(tw)
            tmap = {r["code"]: r for r in trows}
            for m in others:
                t = tmap.get(m["code"])
                if t:
                    m.update(
                        {
                            "name": t["name"],
                            "price": t["price"],
                            "change_pct": t["change_pct"],
                            "pe_ttm": t["pe_ttm"],
                            "pb": t["pb"],
                            "market_cap_yi": t["market_cap_yi"],
                        }
                    )
        except Exception as exc:
            warns.append(f"同业行情补齐失败：{exc}")

    if target is not None:
        try:
            trows, _, _ = tencent.quotes([code], kinds="stock")
            t = next((r for r in trows if r["code"] == code), None)
            if t:
                target.update({"name": t["name"], "price": t["price"], "pe_ttm": t["pe_ttm"],
                               "pb": t["pb"], "market_cap_yi": t["market_cap_yi"]})
        except Exception:
            pass

    data = {
        "industry": info or {"board_code": f"BK{numeric}"},
        "member_count": len(members),
        "target_rank_by_profit": (target_idx + 1) if target_idx is not None else None,
        "target": target,
        "peers": others,
        "pe_basis": "pe_ttm（腾讯）",
    }
    valid_pe = [m["pe_ttm"] for m in others if isinstance(m.get("pe_ttm"), (int, float)) and m["pe_ttm"] > 0]
    data["peer_median_pe"] = sorted(valid_pe)[len(valid_pe) // 2] if valid_pe else None

    # 个股 PE 相对行业中位数的偏离，供风险规则「估值溢价」使用
    target_pe = (target or {}).get("pe_ttm")
    if (
        isinstance(target_pe, (int, float))
        and target_pe > 0
        and data["peer_median_pe"]
    ):
        data["pe_vs_peer_median_pct"] = round(
            (target_pe / data["peer_median_pe"] - 1) * 100, 1
        )

    warns.append("同业按净利润规模最接近筛选，不含 ST；价格与 PE 来自腾讯")

    state_out = "hit" if states and all(s == "hit" for s in states) else "miss"
    return data, state_out, warns
