"""通用参数与路径。"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

DATA_DIR = Path(os.environ.get("FIN_DATA_DIR", Path.home() / ".fin-data"))
DB_PATH = DATA_DIR / "fin.db"
FIXTURE_DIR = Path(__file__).parent / "fixtures"

# 频率要保守：东财 WAF 对高频请求直接断 TLS，恢复需数分钟
MIN_INTERVAL_SECONDS = 1.0
HTTP_TIMEOUT = 12
HTTP_RETRIES = 1

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 主要指数：secid 规则 = 1.代码 表示沪市，0.代码 表示深市
INDEXES = [
    {"code": "000001", "name": "上证指数", "secid": "1.000001", "sh": True},
    {"code": "399001", "name": "深证成指", "secid": "0.399001", "sh": False},
    {"code": "399006", "name": "创业板指", "secid": "0.399006", "sh": False},
    {"code": "000688", "name": "科创50", "secid": "1.000688", "sh": True},
]

# 全市场筛选：沪深主板/创业板/科创板/北交所
MARKET_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

# 缓存 TTL（秒）
TTL = {
    "quote": 120,
    "kline": 3600,
    "financials": 43200,
    "news": 600,
    "announce": 7200,
    "peers": 3600,
    "sectors": 600,
    "symbols": 86400,
    "calendar": 7200,
    "limitup": 600,
}


def now_cst() -> datetime:
    return datetime.now(CST)


def today_cst() -> str:
    return now_cst().strftime("%Y-%m-%d")


def is_trading_day(d: datetime | None = None) -> bool:
    """粗判：周末不是交易日。法定节假日返回 True，调用方需用行情数据兜底判断。"""
    d = d or now_cst()
    return d.weekday() < 5
