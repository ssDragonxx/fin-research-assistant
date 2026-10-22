"""统一 JSON 契约。

所有命令共用同一信封，LLM 只从 data 取数、从 warnings 读缺陷、从 sources 做引用。
"""

from __future__ import annotations

from typing import Any, Iterable

from .config import now_cst


def _iso_now() -> str:
    return now_cst().isoformat(timespec="seconds")


def source(name: str, endpoint: str, url: str = "") -> dict:
    return {"name": name, "endpoint": endpoint, "url": url}


def ok(
    cmd: str,
    data: Any,
    *,
    sources: Iterable[dict] = (),
    warnings: Iterable[str] = (),
    cache: str = "miss",
    as_of: str | None = None,
) -> dict:
    return {
        "ok": True,
        "cmd": cmd,
        "as_of": as_of or _iso_now(),
        "data": data,
        "sources": list(sources),
        "warnings": list(warnings),
        "cache": cache,
    }


def fail(cmd: str, message: str, *, code: str = "error", hint: str = "") -> dict:
    payload = {"ok": False, "cmd": cmd, "as_of": _iso_now(), "error": message, "code": code}
    if hint:
        payload["hint"] = hint
    return payload
