"""腾讯行情接口。仅作东财 push2 限流时的行情兜底。

返回 GBK 文本：v_sh000001="1~上证指数~000001~3658.03~...~";  字段以 ~ 分隔。
"""

from __future__ import annotations

import requests

from .. import store
from ..config import HTTP_TIMEOUT, TTL, UA

BASE = "https://qt.gtimg.cn/q="

I_NAME, I_CODE, I_PRICE, I_PREV = 1, 2, 3, 4
I_CHANGE, I_CHANGE_PCT = 31, 32
I_AMOUNT_WAN = 37
I_PE_TTM = 39
I_FLOAT_CAP_YI = 44
I_MARKET_CAP_YI = 45
I_PB = 46
MIN_FIELDS = 47


def _symbol(code: str) -> str:
    return f"sh{code}" if code.startswith(("60", "68", "90")) else f"sz{code}"


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.split(";"):
        line = line.strip()
        if "=" not in line or '"' not in line:
            continue
        body = line.split("=", 1)[1].strip().strip('";')
        vals = body.split("~")
        if len(vals) < MIN_FIELDS:
            continue
        amount_wan = _num(vals[I_AMOUNT_WAN]) or 0
        rows.append(
            {
                "symbol": line.split("=", 1)[0].strip().removeprefix("v_"),
                "code": vals[I_CODE],
                "name": vals[I_NAME],
                "price": _num(vals[I_PRICE]),
                "change": _num(vals[I_CHANGE]),
                "change_pct": _num(vals[I_CHANGE_PCT]),
                "amount_yuan": amount_wan * 1e4,
                "pe_ttm": _num(vals[I_PE_TTM]),
                "pb": _num(vals[I_PB]),
                "market_cap_yi": _num(vals[I_MARKET_CAP_YI]),
                "float_cap_yi": _num(vals[I_FLOAT_CAP_YI]),
            }
        )
    return rows


def quotes(codes: list[str], kinds: str = "stock") -> tuple[list[dict], str, list[str]]:
    """批量行情。codes 为 6 位代码；失败时自动降级到过期缓存。"""
    key = f"tx:{kinds}:{','.join(codes)}"
    hit = store.cache_get(key)
    if hit is not None:
        return hit[0], "hit", []

    url = BASE + ",".join(_symbol(c) for c in codes)
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": UA})
        rows = _parse(resp.content.decode("gbk", errors="replace"))
        if not rows:
            raise ValueError("腾讯接口返回内容无法解析")
    except Exception as exc:
        stale = store.cache_get(key, allow_stale=True)
        if stale is not None:
            return stale[0], "stale", [f"腾讯行情不可用，使用缓存数据：{exc}"]
        raise

    store.cache_put(key, rows, TTL["quote"])
    return rows, "miss", []
