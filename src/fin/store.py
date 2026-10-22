"""SQLite 缓存与符号表存储。

两张表：
  cache   —— 通用 KV，key 由 endpoint+参数生成
  symbols —— 全市场股票代码/名称，用于名称解析
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from .config import DATA_DIR, DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    ttl        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS symbols (
    code      TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    market    TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn, conn:
        conn.executescript(_SCHEMA)


def make_key(*parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- cache


def cache_get(key: str, *, allow_stale: bool = False) -> tuple[Any, str] | None:
    """返回 (payload, state)，state ∈ {hit, stale}；未命中返回 None。"""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT payload, fetched_at, ttl FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    age = time.time() - row["fetched_at"]
    if age <= row["ttl"]:
        return json.loads(row["payload"]), "hit"
    if allow_stale:
        return json.loads(row["payload"]), "stale"
    return None


def cache_put(key: str, payload: Any, ttl: int) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, payload, fetched_at, ttl) VALUES (?, ?, ?, ?)",
            (key, json.dumps(payload, ensure_ascii=False), time.time(), ttl),
        )


def cache_fetched_at(key: str) -> float | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT fetched_at FROM cache WHERE key = ?", (key,)).fetchone()
    return row["fetched_at"] if row else None


# -------------------------------------------------------------- symbols


def symbols_replace(rows: list[dict]) -> int:
    """整表替换。rows = [{code, name, market}]"""
    stamp = time.time()
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM symbols")
        conn.executemany(
            "INSERT OR REPLACE INTO symbols (code, name, market, updated_at) VALUES (?, ?, ?, ?)",
            [(r["code"], r["name"], r["market"], stamp) for r in rows],
        )
    return len(rows)


def symbols_count() -> int:
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM symbols").fetchone()["n"]


def symbols_updated_at() -> float | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT MAX(updated_at) AS t FROM symbols").fetchone()
    return row["t"] if row and row["t"] else None


def symbols_all() -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT code, name, market FROM symbols").fetchall()
    return [dict(r) for r in rows]


def symbols_search(keyword: str, limit: int = 10) -> list[dict]:
    """精确名 → 前缀 → 包含，三级匹配。"""
    kw = keyword.strip()
    if not kw:
        return []
    with closing(_connect()) as conn:
        exact = conn.execute(
            "SELECT code, name, market FROM symbols WHERE name = ?", (kw,)
        ).fetchall()
        prefix = conn.execute(
            "SELECT code, name, market FROM symbols WHERE name LIKE ? AND name != ? LIMIT ?",
            (kw + "%", kw, limit),
        ).fetchall()
        contains = conn.execute(
            "SELECT code, name, market FROM symbols WHERE name LIKE ? AND name NOT LIKE ? LIMIT ?",
            ("%" + kw + "%", kw + "%", limit),
        ).fetchall()
    seen: set[str] = set()
    out: list[dict] = []
    for group in (exact, prefix, contains):
        for row in group:
            if row["code"] in seen:
                continue
            seen.add(row["code"])
            out.append(dict(row))
            if len(out) >= limit:
                return out
    return out


def symbol_get(code: str) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT code, name, market FROM symbols WHERE code = ?", (code,)
        ).fetchone()
    return dict(row) if row else None


def db_size_bytes() -> int:
    p = Path(DB_PATH)
    return p.stat().st_size if p.exists() else 0
