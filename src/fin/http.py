"""HTTP 会话：串行限速、重试、统一 UA。故意不用 ThreadPoolExecutor 并发取数。"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import requests

from . import store
from .config import HTTP_RETRIES, HTTP_TIMEOUT, MIN_INTERVAL_SECONDS, UA

_lock = threading.Lock()
_last_call = 0.0


class FetchError(RuntimeError):
    def __init__(self, message: str, *, endpoint: str = "", hint: str = ""):
        super().__init__(message)
        self.endpoint = endpoint
        self.hint = hint


def _throttle() -> None:
    global _last_call
    with _lock:
        wait = MIN_INTERVAL_SECONDS - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept": "*/*"})


def _call(method: str, url: str, **kwargs) -> requests.Response:
    endpoint = url.split("://", 1)[-1].split("?", 1)[0]
    last_err: Exception | None = None
    for attempt in range(HTTP_RETRIES + 1):
        if attempt:
            time.sleep(0.5 * (2 ** (attempt - 1)))
        _throttle()
        try:
            resp = _session.request(method, url, timeout=HTTP_TIMEOUT, **kwargs)
            if resp.status_code >= 500:
                last_err = FetchError(f"上游返回 HTTP {resp.status_code}", endpoint=endpoint)
                continue
            return resp
        except requests.RequestException as exc:
            last_err = exc  # type: ignore[assignment]
    raise FetchError(
        f"请求失败：{last_err}", endpoint=endpoint, hint="检查网络或稍后重试"
    )


def _mojibake_score(text: str) -> int:
    """中文乱码特征计数。GBK 字节被当 UTF-8 解码后，常出现拉丁扩展/西里尔/希腊字母。"""
    score = 0
    for ch in text:
        cp = ord(ch)
        if 0xFFFD == cp:
            score += 2
        elif 0x80 <= cp <= 0x24F:      # Latin-1 补充 / 拉丁扩展
            score += 1
        elif 0x370 <= cp <= 0x52F:     # 希腊 / 西里尔
            score += 1
        elif 0x2E80 <= cp <= 0x9FFF:   # CJK，正常中文，扣分
            score -= 1
    return score


def _decode(resp: requests.Response) -> str:
    """东财财务接口声明 UTF-8 实际返回 GBK，且 UTF-8 解码不报错——只能靠乱码特征判断。"""
    raw = resp.content
    try:
        utf8 = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gb18030", errors="replace")

    score = _mojibake_score(utf8)
    if score > 0:
        gbk = raw.decode("gb18030", errors="replace")
        if _mojibake_score(gbk) < score:
            return gbk
    return utf8


def _strip_jsonp(text: str) -> str:
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text
    # 形如 x({...}) 或 cb({...});
    start = text.find("(")
    end = text.rfind(")")
    if start != -1 and end > start:
        return text[start + 1 : end]
    return text


def get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    ttl: int | None = None,
    cache_key: str | None = None,
    offline: bool = False,
) -> tuple[Any, str, str | None]:
    """返回 (payload, cache_state, warning)。

    cache_state: hit | miss | stale | offline
    warning: 降级或字段异常的可读说明，供 envelope.warnings 使用。
    """
    key = cache_key or store.make_key("GET", url, params or {})

    if offline:
        cached = store.cache_get(key, allow_stale=True)
        if cached is None:
            raise FetchError("离线模式下无可用快照", endpoint=url, hint="先联网运行一次以生成快照")
        return cached[0], "offline", None

    if ttl is not None:
        cached = store.cache_get(key)
        if cached is not None:
            return cached[0], "hit", None

    try:
        resp = _call("GET", url, params=params, headers=headers)
        text = _strip_jsonp(_decode(resp))
        payload = json.loads(text)
    except (FetchError, json.JSONDecodeError) as exc:
        cached = store.cache_get(key, allow_stale=True)
        fetched = store.cache_fetched_at(key)
        if cached is not None:
            age_note = ""
            if fetched:
                age_note = time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched))
            return cached[0], "stale", f"上游请求失败，使用 {age_note} 的缓存数据：{exc}"
        raise FetchError(str(exc), endpoint=url, hint="检查网络后重试") from exc

    if ttl is not None:
        store.cache_put(key, payload, ttl)
    return payload, "miss", None


def post_form(
    url: str,
    *,
    data: dict,
    headers: dict | None = None,
    ttl: int | None = None,
    cache_key: str | None = None,
    offline: bool = False,
) -> tuple[Any, str, str | None]:
    key = cache_key or store.make_key("POST", url, data)

    if offline:
        cached = store.cache_get(key, allow_stale=True)
        if cached is None:
            raise FetchError("离线模式下无可用快照", endpoint=url)
        return cached[0], "offline", None

    if ttl is not None:
        cached = store.cache_get(key)
        if cached is not None:
            return cached[0], "hit", None

    try:
        resp = _call("POST", url, data=data, headers=headers)
        payload = json.loads(_strip_jsonp(_decode(resp)))
    except (FetchError, json.JSONDecodeError) as exc:
        cached = store.cache_get(key, allow_stale=True)
        if cached is not None:
            return cached[0], "stale", f"上游请求失败，使用缓存数据：{exc}"
        raise FetchError(str(exc), endpoint=url) from exc

    if ttl is not None:
        store.cache_put(key, payload, ttl)
    return payload, "miss", None
