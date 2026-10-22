"""把仓库里的 src/ 与 skills/ 同步到 profile 和分发包。

三份副本的来源只能有一个：
    src/fin, skills/            ← 唯一可编辑源头
        ├── ~/.hermes/profiles/finance/     （本机演示用）
        └── distribution/                   （交付给客户）

用法：
    python scripts/sync_payloads.py            # 同步两处
    python scripts/sync_payloads.py --dry-run  # 只看会改什么
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "fin"
SKILLS = ROOT / "skills"

TARGETS = [
    Path.home() / ".hermes" / "profiles" / "finance",
    ROOT / "distribution",
]


def _sync_tree(src: Path, dst: Path, dry_run: bool) -> list[str]:
    """把 src 目录整体覆盖到 dst，跳过 __pycache__。返回变更清单。"""
    changed: list[str] = []
    if not dst.exists():
        if not dry_run:
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return [f"新建 {dst}"]

    for item in src.rglob("*"):
        if item.is_dir() or item.suffix == ".pyc" or "__pycache__" in item.parts:
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if not target.exists() or not filecmp.cmp(item, target, shallow=False):
            changed.append(str(rel))
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                data = item.read_bytes()
                # 统一 LF，避免 Windows 下 CRLF 造成每次都"有变更"
                if item.suffix in {".py", ".md", ".yaml", ".json", ".toml"}:
                    data = data.replace(b"\r\n", b"\n")
                target.write_bytes(data)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total = 0
    for target in TARGETS:
        if not target.exists():
            print(f"跳过（不存在）: {target}")
            continue
        print(f"\n→ {target}")
        for rel_src, rel_dst in ((SRC, "src/fin"), (SKILLS, "skills")):
            changes = _sync_tree(rel_src, target / rel_dst, args.dry_run)
            total += len(changes)
            for c in changes:
                print(f"   {'[dry]' if args.dry_run else '更新'} {rel_dst}/{c}")
            if not changes:
                print(f"   {rel_dst}/ 已是最新")

    if args.dry_run:
        print(f"\n共 {total} 个文件待更新（dry-run，未写入）")
    else:
        print(f"\n共 {total} 个文件已同步")
        print("提示：若 fin 命令指向某个副本，改完需重装或确保指向最新那份。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
