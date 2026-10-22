"""股票代码与 secid 换算、符号表刷新、名称解析。"""

from __future__ import annotations

import time

from . import store
from .config import TTL
from .sources import eastmoney


class ResolveError(ValueError):
    pass


def normalize_code(text: str) -> str | None:
    """去掉 sh/sz 前缀和 .SH/.SZ 后缀，返回 6 位代码。"""
    raw = text.strip().upper().replace("SH", "").replace("SZ", "").replace("BJ", "")
    raw = raw.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    raw = raw.replace(".", "").strip()
    if raw.isdigit() and len(raw) == 6:
        return raw
    return None


def secid_of(code: str) -> str:
    """6 位代码 → 东财 secid。北交所 4/8 开头用 0. 前缀（部分接口不认，属已知限制）。"""
    if code.startswith(("60", "68", "90")):
        return f"1.{code}"
    if code.startswith(("4", "8")):
        return f"0.{code}"
    return f"0.{code}"


def secucode_of(code: str) -> str:
    """6 位代码 → 财报用 secucode，如 300750.SZ"""
    if code.startswith(("60", "68", "90")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def market_of(code: str) -> str:
    if code.startswith(("60", "68", "90")):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SZ"


# ------------------------------------------------------------ 符号表


def refresh_symbols(force: bool = False, offline: bool = False) -> tuple[int, str, list[str]]:
    updated = store.symbols_updated_at()
    if not force and updated and time.time() - updated < TTL["symbols"]:
        return store.symbols_count(), "hit", []
    rows, state, warns = eastmoney.market_universe()
    if not rows:
        raise ResolveError("未能获取全市场股票列表")
    count = store.symbols_replace(rows)
    return count, state, warns


def ensure_symbols(offline: bool = False) -> list[str]:
    warns: list[str] = []
    try:
        _, _, w = refresh_symbols(offline=offline)
        warns.extend(w)
    except Exception as exc:  # 符号表失败不阻断，降级为代码直查
        if store.symbols_count() == 0:
            warns.append(f"股票列表未就绪：{exc}")
    return warns


def resolve(query: str) -> dict:
    """名称/代码 → {code, name, candidates}。歧义时 exact 为 None。

    路径：6 位代码直查 → 本地符号表 → 东财搜索建议（不依赖 push2）。
    """
    code = normalize_code(query)
    if code:
        row = store.symbol_get(code)
        return {
            "query": query,
            "exact": code,
            "name": row["name"] if row else None,
            "candidates": [],
            "mode": "code",
        }

    hits = store.symbols_search(query, limit=8) if store.symbols_count() else []
    source = "symbols"
    if not hits:
        hits = _suggest_search(query)
        source = "suggest"

    if not hits:
        raise ResolveError(f"未找到与「{query}」匹配的股票")

    exact = next((h for h in hits if h["name"] == query), None)
    target = exact or (hits[0] if len(hits) == 1 else None)
    return {
        "query": query,
        "exact": target["code"] if target else None,
        "name": target["name"] if target else None,
        "candidates": hits if (len(hits) > 1 and not exact) else [],
        "mode": "name",
        "source": source,
    }


def _suggest_search(keyword: str, limit: int = 8) -> list[dict]:
    try:
        payload, _, _ = eastmoney.suggest(keyword, count=limit)
    except Exception:
        return []
    rows = ((payload.get("QuotationCodeTable") or {}).get("Data")) or []
    out: list[dict] = []
    seen: set[str] = set()
    # 只保留 A 股：深A/沪A/京A
    for r in rows:
        sec_type = r.get("SecurityTypeName") or ""
        if sec_type not in {"深A", "沪A", "京A"}:
            continue
        code = r.get("Code")
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": r.get("Name"), "market": market_of(code)})
    return out[:limit]
