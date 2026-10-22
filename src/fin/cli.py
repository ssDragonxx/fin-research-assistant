"""fin 命令行入口。输出统一 JSON，供 Hermes 技能解析。"""

from __future__ import annotations

import argparse
import io
import json
import sys

from . import envelope, store, symbols
from .api import brief as brief_api
from .api import market, news, risk, stock


def _emit(payload: dict) -> int:
    # Windows 终端默认 GBK，强制 UTF-8 保证中文不乱码
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                                      newline="\n", line_buffering=True, write_through=True)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0 if payload.get("ok") else 1


def _run(cmd: str, fn, *args, **kwargs) -> dict:
    try:
        data, state, warns = fn(*args, **kwargs)
        return envelope.ok(cmd, data, sources=[envelope.source("东方财富", cmd)], warnings=warns, cache=state)
    except symbols.ResolveError as exc:
        return envelope.fail(cmd, str(exc), code="resolve_error", hint="输入 6 位代码可跳过解析")
    except Exception as exc:
        return envelope.fail(cmd, f"{type(exc).__name__}: {exc}", hint="加 --offline 使用本地快照或稍后重试")


# ------------------------------------------------------------------ market


def cmd_market(args) -> dict:
    if args.part == "quote":
        return _run("market.quote", market.quotes, offline=args.offline)
    if args.part == "breadth":
        return _run("market.breadth", market.breadth, offline=args.offline)
    if args.part == "sector":
        return _run("market.sector", market.sector, limit=args.limit, offline=args.offline)
    if args.part == "limitup":
        return _run("market.limitup", market.limit_up, date=args.date, offline=args.offline)
    if args.part == "snapshot":
        return _run("market.snapshot", market.market_snapshot, offline=args.offline)
    return envelope.fail("market", f"未知子命令 {args.part}")


def cmd_resolve(args) -> dict:
    try:
        data = symbols.resolve(args.query)
        return envelope.ok("resolve", data, sources=[envelope.source("本地符号表", "symbols")], cache="hit")
    except symbols.ResolveError as exc:
        return envelope.fail("resolve", str(exc), code="resolve_error")
    except Exception as exc:
        return envelope.fail("resolve", f"{type(exc).__name__}: {exc}")


def cmd_symbols(args) -> dict:
    try:
        count, state, warns = symbols.refresh_symbols(force=args.force, offline=args.offline)
        return envelope.ok("symbols", {"count": count}, warnings=warns, cache=state)
    except Exception as exc:
        return envelope.fail("symbols", f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------- stock


def _target(args) -> str:
    """接受代码或名称，统一解析为 6 位代码。

    news 子命令把标的放在位置参数 keyword，其余命令用 target。
    """
    raw = getattr(args, "target", None) or getattr(args, "keyword", None)
    if not raw:
        raise symbols.ResolveError("未提供股票代码或名称，例如 300750 或 宁德时代")
    res = symbols.resolve(raw)
    if not res.get("exact"):
        cands = res.get("candidates") or []
        names = "、".join(f"{c['name']}({c['code']})" for c in cands[:5])
        raise symbols.ResolveError(
            f"「{raw}」有多个候选，请指定：{names}" if names else f"未找到「{raw}」"
        )
    return res["exact"]


def cmd_stock(args) -> dict:
    try:
        code = _target(args)
    except symbols.ResolveError as exc:
        return envelope.fail("stock", str(exc), code="resolve_error")

    parts = [p.strip() for p in args.parts.split(",") if p.strip()]
    wanted = set(parts) | {"quote"}
    if "all" in wanted:
        wanted = {"quote", "financials", "peers"}

    warns: list[str] = []
    states: list[str] = []
    data: dict = {"code": code}

    if "quote" in wanted:
        try:
            d, st, w = stock.quote(code, offline=args.offline)
            data["quote"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"行情获取失败：{exc}")

    if "financials" in wanted:
        try:
            d, st, w = stock.financials(code, periods=args.periods, offline=args.offline)
            data["financials"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"财务获取失败：{exc}")

    if "peers" in wanted:
        try:
            d, st, w = stock.peers(code, offline=args.offline)
            data["peers"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"同业获取失败：{exc}")

    if "risk" in wanted:
        try:
            d, st, w = risk.scan(code, offline=args.offline)
            data["risk"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"风险扫描失败：{exc}")

    if "news" in wanted:
        name = (data.get("quote") or {}).get("name") or code
        try:
            d, st, w = news.stock_news(name, offline=args.offline)
            data["news"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"新闻获取失败：{exc}")

    if "announce" in wanted:
        try:
            d, st, w = news.announcements(code, offline=args.offline)
            data["announcements"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"公告获取失败：{exc}")

    if "reports" in wanted:
        try:
            d, st, w = news.research_reports(code, offline=args.offline)
            data["reports"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"研报获取失败：{exc}")

    if "calendar" in wanted:
        try:
            d, st, w = news.calendar(code=code, offline=args.offline)
            data["calendar"] = d
            states.append(st)
            warns.extend(w)
        except Exception as exc:
            warns.append(f"日程获取失败：{exc}")

    state = "hit" if states and all(s == "hit" for s in states) else "miss"
    return envelope.ok(f"stock.{','.join(parts)}", data,
                       sources=[envelope.source("东方财富", "多接口")], warnings=warns, cache=state)


# ------------------------------------------------------------------- misc


def cmd_news(args) -> dict:
    if args.part == "list":
        return _run("news.list", news.fast_news, limit=args.limit, offline=args.offline)
    if args.part == "search":
        return _run("news.search", news.stock_news, name_or_code=args.keyword,
                    limit=args.limit, offline=args.offline)
    if args.part == "announce":
        return _run("news.announce", news.announcements, code=_target(args),
                    limit=args.limit, offline=args.offline)
    if args.part == "reports":
        return _run("news.reports", news.research_reports, code=_target(args),
                    limit=args.limit, offline=args.offline)
    return envelope.fail("news", f"未知子命令 {args.part}")


def cmd_risk(args) -> dict:
    try:
        code = _target(args)
    except symbols.ResolveError as exc:
        return envelope.fail("risk", str(exc), code="resolve_error")
    return _run("risk.rules", risk.scan, code, offline=args.offline)


def cmd_calendar(args) -> dict:
    code = None
    if args.target:
        try:
            code = _target(args)
        except symbols.ResolveError as exc:
            return envelope.fail("calendar", str(exc), code="resolve_error")
    return _run("calendar", news.calendar, code=code, offline=args.offline)


def cmd_brief(args) -> dict:
    if args.part == "assemble":
        return brief_api.assemble(offline=args.offline, date=args.date)
    if args.part == "save":
        payload = brief_api.assemble(offline=args.offline, date=args.date)
        md = args.markdown
        if md is None:
            md = sys.stdin.read()
        path = brief_api.save_brief(payload["data"]["date"], md)
        return envelope.ok("brief.save", {"path": path, "date": payload["data"]["date"]})
    if args.part == "show":
        data = brief_api.load_brief(args.date) if args.date else brief_api.latest_brief()
        if data is None:
            return envelope.fail("brief.show", "未找到简报文件", code="not_found")
        return envelope.ok("brief.show", data)
    return envelope.fail("brief", f"未知子命令 {args.part}")


# ------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fin", description="A 股数据工具：只输出 JSON，供 Hermes 技能使用")
    p.add_argument("--offline", action="store_true", help="只用本地缓存/快照，不访问网络")
    sub = p.add_subparsers(dest="group", required=True)

    # resolve
    r = sub.add_parser("resolve", help="名称/代码 → 股票代码")
    r.add_argument("query")
    r.set_defaults(func=cmd_resolve)

    s = sub.add_parser("symbols", help="刷新本地股票符号表")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_symbols)

    # market
    m = sub.add_parser("market", help="大盘行情")
    m.add_argument("part", choices=["quote", "breadth", "sector", "limitup", "snapshot"])
    m.add_argument("--limit", type=int, default=10)
    m.add_argument("--date", default=None, help="YYYY-MM-DD，仅 limitup 使用")
    m.set_defaults(func=cmd_market)

    # stock
    st = sub.add_parser("stock", help="个股数据")
    st.add_argument("target", help="代码或名称")
    st.add_argument("--parts", default="all",
                    help="quote,financials,peers,risk,news,announce,reports,calendar 或 all")
    st.add_argument("--periods", type=int, default=4)
    st.set_defaults(func=cmd_stock)

    # news
    n = sub.add_parser("news", help="资讯/公告/研报")
    n.add_argument("part", choices=["list", "search", "announce", "reports"])
    n.add_argument("keyword", nargs="?", default="", help="search 用关键词；announce/reports 用代码或名称")
    n.add_argument("--limit", type=int, default=10)
    n.set_defaults(func=cmd_news)

    # risk
    rk = sub.add_parser("risk", help="风险规则扫描")
    rk.add_argument("target")
    rk.set_defaults(func=cmd_risk)

    # calendar
    c = sub.add_parser("calendar", help="解禁与披露日程")
    c.add_argument("target", nargs="?", default=None)
    c.set_defaults(func=cmd_calendar)

    # brief
    b = sub.add_parser("brief", help="日报骨架")
    b.add_argument("part", choices=["assemble", "save", "show"])
    b.add_argument("--date", default=None)
    b.add_argument("--markdown", default=None, help="save 时直接传入正文；不传则读 stdin")
    b.set_defaults(func=cmd_brief)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store.init_db()
    return _emit(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
