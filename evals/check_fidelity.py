"""数字保真度检查：把报告里的数字与 CLI 输出快照逐项比对。

用法：
    python evals/check_fidelity.py --fixture evals/fixtures/300750.json --report report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 匹配 1,234.56 / 1234.56 / -12.3；负号前不能是数字或连字符（排除 2026-10-22 这类日期片段）
NUM = re.compile(r"(?<![\d\-])-?\d+(?:,\d{3})*(?:\.\d+)?")


def flatten(obj, prefix="") -> dict[str, float]:
    """把嵌套 JSON 展平成 {路径: 数值}，只保留数值叶子。"""
    out: dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"as_of", "cmd", "sources", "cache"}:
                continue
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix] = float(obj)
    return out


def numbers_in(text: str) -> list[float]:
    vals = []
    for m in NUM.finditer(text):
        try:
            vals.append(float(m.group().replace(",", "")))
        except ValueError:
            continue
    return vals


def check(fixture: dict, report: str, tolerance: float = 0.02) -> dict:
    allowed = list(flatten(fixture).values())
    found = numbers_in(report)
    # 忽略明显的非数据数字：序号、年份、日期片段
    skip = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100, 2024, 2025, 2026, 2027,
            2024.0, 2025.0, 2026.0, 2027.0}
    # 股票代码本身不是"数字断言"
    fixture_codes = {float(c) for c in re.findall(r"\b\d{6}\b", json.dumps(fixture, ensure_ascii=False))}
    checks = [n for n in found if n not in skip and n not in fixture_codes]
    suspect = [
        n for n in checks
        if not any(abs(n - a) <= max(tolerance * max(abs(a), 1e-9), 1e-6) for a in allowed)
    ]
    return {
        "numbers_total": len(checks),
        "numbers_matched": len(checks) - len(suspect),
        "fidelity": round((len(checks) - len(suspect)) / len(checks), 4) if checks else 1.0,
        "suspects": suspect[:50],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, help="CLI 输出 JSON")
    ap.add_argument("--report", required=True, help="生成的 markdown 报告")
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    report = Path(args.report).read_text(encoding="utf-8")
    result = check(fixture, report, args.tolerance)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["fidelity"] >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
