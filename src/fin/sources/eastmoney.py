"""东方财富接口薄封装。只返回上游原始 JSON，不做语义加工。

每个函数返回 (payload, cache_state, warnings)。
"""

from __future__ import annotations

from urllib.parse import quote

from .. import http
from ..config import MARKET_FS, TTL

PUSH2 = "https://push2.eastmoney.com/api/qt"
PUSH2_FALLBACK = "https://82.push2.eastmoney.com/api/qt"
PUSH2HIS = "https://push2his.eastmoney.com/api/qt"
PUSH2EX = "https://push2ex.eastmoney.com"
DATACENTER = "https://datacenter.eastmoney.com/securities/api/data/get"
DATACENTER_WEB = "https://datacenter-web.eastmoney.com/api/data/v1/get"
NEWS_LIST = "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
NEWS_SEARCH = "https://search-api-web.eastmoney.com/search/jsonp"
ANNOUNCE = "https://np-anotice-stock.eastmoney.com/api/security/ann"
REPORT = "https://reportapi.eastmoney.com/report/list"
SUGGEST = "https://searchapi.eastmoney.com/api/suggest/get"
_SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"

_TTL_QUOTE = TTL["quote"]


# ------------------------------------------------------------- 行情


def quotes(secids: list[str], fields: str) -> tuple[dict, str, list[str]]:
    """批量行情。secid 形如 1.000001 / 0.399001。"""
    url = f"{PUSH2}/ulist.np/get"
    payload, state, warning = http.get_json(
        url,
        params={"fltt": 2, "secids": ",".join(secids), "fields": fields},
        ttl=_TTL_QUOTE,
        cache_key=f"quotes:{','.join(secids)}:{fields}",
    )
    return payload, state, [warning] if warning else []


def stock_quote(secid: str, fields: str) -> tuple[dict, str, list[str]]:
    url = f"{PUSH2}/stock/get"
    payload, state, warning = http.get_json(
        url,
        params={"fltt": 2, "secid": secid, "fields": fields},
        ttl=_TTL_QUOTE,
        cache_key=f"stock:{secid}:{fields}",
    )
    return payload, state, [warning] if warning else []


def clist(
    fs: str,
    fields: str,
    *,
    page: int = 1,
    page_size: int = 100,
    fid: str = "f3",
    ttl: int = TTL["quote"],
    extra_params: dict | None = None,
) -> tuple[dict, str, list[str]]:
    """列表类接口：股票列表、板块列表、板块成分股。单页上限 100。"""
    url = f"{PUSH2}/clist/get"
    params = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": fid,
        "fs": fs,
        "fields": fields,
    }
    if extra_params:
        params.update(extra_params)
    payload, state, warning = http.get_json(
        url,
        params=params,
        ttl=ttl,
        cache_key=f"clist:{fs}:{fields}:{page}:{page_size}:{fid}:{extra_params}",
    )
    return payload, state, [warning] if warning else []


def kline(secid: str, limit: int = 60, klt: int = 101, fqt: int = 1) -> tuple[dict, str, list[str]]:
    url = f"{PUSH2HIS}/stock/kline/get"
    payload, state, warning = http.get_json(
        url,
        params={
            "secid": secid,
            "klt": klt,
            "fqt": fqt,
            "lmt": limit,
            "end": "20500101",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
        ttl=TTL["kline"],
        cache_key=f"kline:{secid}:{klt}:{fqt}:{limit}",
    )
    return payload, state, [warning] if warning else []


def limit_up_pool(date: str) -> tuple[dict, str, list[str]]:
    """date 形如 20261022。"""
    url = f"{PUSH2EX}/getTopicZTPool"
    payload, state, warning = http.get_json(
        url,
        params={
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.ztzt",
            "Pageindex": 0,
            "pagesize": 1,
            "sort": "fbt:asc",
            "date": date,
        },
        ttl=TTL["limitup"],
        cache_key=f"ztpool:{date}",
    )
    return payload, state, [warning] if warning else []


def stock_fund_flow(secid: str) -> tuple[dict, str, list[str]]:
    url = f"{PUSH2}/stock/fflow/kline/get"
    payload, state, warning = http.get_json(
        url,
        params={
            "lmt": 1,
            "klt": 101,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "secid": secid,
        },
        ttl=_TTL_QUOTE,
        cache_key=f"fflow:{secid}",
    )
    return payload, state, [warning] if warning else []


# ------------------------------------------------------------- 财务


def main_financials(secucode: str, periods: int = 4) -> tuple[dict, str, list[str]]:
    """secucode 形如 300750.SZ。返回最近 N 期主要财务指标。

    不要把 filter 预先 quote()——requests 会再编码一次，变成 %2528 导致上游返回空。
    """
    filt = f'(SECUCODE="{secucode}")'
    payload, state, warning = http.get_json(
        DATACENTER,
        params={
            "type": "RPT_F10_FINANCE_MAINFINADATA",
            "sty": "APP_F10_MAINFINADATA",
            "filter": filt,
            "p": 1,
            "ps": periods,
            "sr": -1,
            "st": "REPORT_DATE",
            "source": "HSF10",
            "client": "PC",
        },
        ttl=TTL["financials"],
        cache_key=f"fin:{secucode}:{periods}",
    )
    return payload, state, [warning] if warning else []


def owner_structure(secucode: str) -> tuple[dict, str, list[str]]:
    """股东结构（十大股东、股东户数等）。"""
    filt = f'(SECUCODE="{secucode}")'
    payload, state, warning = http.get_json(
        DATACENTER,
        params={
            "type": "RPT_F10_EH_HOLDERNUM",
            "sty": "ALL",
            "filter": filt,
            "p": 1,
            "ps": 4,
            "sr": -1,
            "st": "END_DATE",
            "source": "HSF10",
            "client": "PC",
        },
        ttl=TTL["financials"],
        cache_key=f"holder:{secucode}",
    )
    return payload, state, [warning] if warning else []


def lift_schedule(secucode: str, page_size: int = 6) -> tuple[dict, str, list[str]]:
    """限售解禁。列名是 SECURITY_CODE，写错上游会返回 "列不存在"。"""
    payload, state, warning = http.get_json(
        DATACENTER_WEB,
        params={
            "reportName": "RPT_LIFT_STAGE",
            "columns": "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,FREE_DATE,LIFT_MARKET_CAP,CURRENT_FREE_SHARES,FREE_SHARES_TYPE",
            "filter": f'(SECUCODE="{secucode}")',
            "pageSize": page_size,
            "sortColumns": "FREE_DATE",
            "sortTypes": -1,
        },
        ttl=TTL["calendar"],
        cache_key=f"lift:{secucode}",
    )
    return payload, state, [warning] if warning else []


def disclosure_schedule(start: str, end: str, page_size: int = 50) -> tuple[dict, str, list[str]]:
    """业绩预约披露。start/end 形如 2026-10-22。"""
    filt = f"(FIRST_APPOINT_DATE>='{start}')(FIRST_APPOINT_DATE<='{end}')"
    payload, state, warning = http.get_json(
        DATACENTER_WEB,
        params={
            "reportName": "RPT_PUBLIC_BS_APPOIN",
            "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,FIRST_APPOINT_DATE,REPORT_TYPE",
            "filter": filt,
            "pageSize": page_size,
            "sortColumns": "FIRST_APPOINT_DATE",
            "sortTypes": 1,
        },
        ttl=TTL["calendar"],
        cache_key=f"appoint:{start}:{end}:{page_size}",
    )
    return payload, state, [warning] if warning else []


# ------------------------------------------------------------- 资讯


def fast_news(page_size: int = 30, column: int = 102) -> tuple[dict, str, list[str]]:
    """7x24 快讯。column 102 = 全部。缺 req_trace 会返回空列表。"""
    import time as _time

    payload, state, warning = http.get_json(
        NEWS_LIST,
        params={
            "client": "web",
            "biz": "web_724",
            "fastColumn": column,
            "sortEnd": "",
            "pageSize": page_size,
            "req_trace": str(int(_time.time() * 1000)),
        },
        ttl=TTL["news"],
        cache_key=f"news:{column}:{page_size}",
    )
    return payload, state, [warning] if warning else []


def news_search(keyword: str, page_size: int = 10) -> tuple[dict, str, list[str]]:
    import json as _json

    param = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    payload, state, warning = http.get_json(
        NEWS_SEARCH,
        params={"cb": "finjsonp", "param": _json.dumps(param, ensure_ascii=False)},
        headers={"Referer": "https://so.eastmoney.com/"},
        ttl=TTL["news"],
        cache_key=f"newssearch:{keyword}:{page_size}",
    )
    return payload, state, [warning] if warning else []


def announcements(code: str, page_size: int = 10) -> tuple[dict, str, list[str]]:
    payload, state, warning = http.get_json(
        ANNOUNCE,
        params={
            "sr": -1,
            "page_size": page_size,
            "page_index": 1,
            "ann_type": "A",
            "client_source": "web",
            "stock_list": code,
            "f_node": 0,
        },
        ttl=TTL["announce"],
        cache_key=f"ann:{code}:{page_size}",
    )
    return payload, state, [warning] if warning else []


def research_reports(code: str, begin: str, end: str, page_size: int = 5) -> tuple[dict, str, list[str]]:
    payload, state, warning = http.get_json(
        REPORT,
        params={
            "industryCode": "*",
            "pageSize": page_size,
            "pageNo": 1,
            "qType": 0,
            "code": code,
            "beginTime": begin,
            "endTime": end,
        },
        ttl=TTL["announce"],
        cache_key=f"report:{code}:{begin}:{end}:{page_size}",
    )
    return payload, state, [warning] if warning else []


def industry_fundflow(page_size: int = 200) -> tuple[dict, str, list[str]]:
    """行业板块行情与资金流（不走 push2，clist 限流时的主路径）。

    字段：BOARD_CODE / BOARD_NAME / CHANGE_RATE / NET_INFLOW / MAX_NETINFLOW_SEC
    注意：包含 Ⅱ/Ⅲ 层级，且无涨跌家数。
    """
    payload, state, warning = http.get_json(
        DATACENTER_WEB,
        params={
            "reportName": "RPT_INDUSTRY_FUNDFLOW",
            "columns": "BOARD_CODE,BOARD_NAME,CHANGE_RATE,NET_INFLOW,NET_INFLOW_RATIO,MAX_NETINFLOW_SEC,TRADE_DATE",
            "pageSize": page_size,
            "pageNumber": 1,
            "sortColumns": "TRADE_DATE,CHANGE_RATE",
            "sortTypes": "-1,-1",
        },
        ttl=TTL["sectors"],
        cache_key=f"indflow:{page_size}",
    )
    return payload, state, [warning] if warning else []


def limit_pool(kind: str, date: str) -> tuple[dict, str, list[str]]:
    """涨停/跌停/强势池。kind ∈ zt / dt / qs。date 形如 20261022。"""
    endpoint = {"zt": "getTopicZTPool", "dt": "getTopicDTPool", "qs": "getTopicQSPool"}[kind]
    sort = {"zt": "fbt:asc", "dt": "fund:asc", "qs": "zdp:asc"}[kind]
    payload, state, warning = http.get_json(
        f"{PUSH2EX}/{endpoint}",
        params={
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.ztzt",
            "Pageindex": 0,
            "pagesize": 200,
            "sort": sort,
            "date": date,
        },
        ttl=TTL["limitup"],
        cache_key=f"pool:{kind}:{date}",
    )
    return payload, state, [warning] if warning else []


def stock_boards(secucode: str) -> tuple[dict, str, list[str]]:
    """股票所属板块（含 BOARD_TYPE='行业' 的行业板块）。不依赖 push2。"""
    payload, state, warning = http.get_json(
        DATACENTER_WEB,
        params={
            "reportName": "RPT_F10_CORETHEME_BOARDTYPE",
            "columns": "BOARD_CODE,BOARD_NAME,BOARD_RANK,BOARD_TYPE,NEW_BOARD_CODE",
            "filter": f'(SECUCODE="{secucode}")',
            "pageSize": 50,
            "sortColumns": "BOARD_RANK",
            "sortTypes": 1,
        },
        ttl=TTL["peers"],
        cache_key=f"boards:{secucode}",
    )
    return payload, state, [warning] if warning else []


def board_constituents(board_code: str, page_size: int = 60) -> tuple[dict, str, list[str]]:
    """板块成分股与基本面。board_code 为纯数字（如 1033），不是 BK1033。

    该表没有股票简称字段（SECURITY_NAME_ABBR 不存在），名称需由调用方补。
    """
    payload, state, warning = http.get_json(
        DATACENTER_WEB,
        params={
            "reportName": "RPT_BOARD_CONSTITUENT",
            "columns": "BOARD_CODE,BOARD_NAME,SECURITY_CODE,SECUCODE,"
                       "ACCUM_NETPROFIT,NETPROFIT_RATIO_1Y,PE_TTM_PERCENTILE,"
                       "DIVIDEND_RATIO,MAIN_BUSINESS_INCOME,MBI_RATIO,IS_ST,TOTAL_COUNT",
            "filter": f'(BOARD_CODE="{board_code}")(IS_VALID="1")',
            "pageSize": page_size,
            "pageNumber": 1,
            "sortColumns": "ACCUM_NETPROFIT",
            "sortTypes": -1,
        },
        ttl=TTL["peers"],
        cache_key=f"constituents:{board_code}:{page_size}",
    )
    return payload, state, [warning] if warning else []


def suggest(keyword: str, count: int = 10) -> tuple[dict, str, list[str]]:
    """名称/拼音/代码搜索。不依赖 push2，是名称解析的主路径。"""
    payload, state, warning = http.get_json(
        SUGGEST,
        params={"input": keyword, "type": 14, "token": _SUGGEST_TOKEN, "count": count},
        ttl=TTL["symbols"],
        cache_key=f"suggest:{keyword}:{count}",
    )
    return payload, state, [warning] if warning else []


def market_universe() -> tuple[list[dict], str, list[str]]:
    """全市场股票列表。单页上限 100，需翻页。约 14 秒。"""
    fields = "f12,f13,f14"
    rows: list[dict] = []
    state = "miss"
    warning: str | None = None
    page = 1
    total = None
    while True:
        payload, st, warn = clist(
            MARKET_FS, fields, page=page, page_size=100, fid="f12", ttl=TTL["symbols"]
        )
        if st == "hit":
            state = "hit"
        if warn:
            warning = warn
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        if total is None:
            total = data.get("total") or 0
        for item in diff:
            code = item.get("f12") or ""
            name = item.get("f14") or ""
            market = "SH" if item.get("f13") == 1 else "SZ"
            if code and name:
                rows.append({"code": code, "name": name, "market": market})
        if len(diff) < 100 or (total and page * 100 >= total):
            break
        page += 1
        if page > 80:  # 安全上限
            break
    return rows, state, [warning] if warning else []
