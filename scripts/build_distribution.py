"""从 src/ 与 skills/ 生成可安装的 Hermes profile 分发包。

产物 `dist/finance-dist/` 可直接用于：

    hermes profile install <该目录> --name finance --alias

设计原则：仓库是唯一源头，分发包是构建产物，不入库。
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "finance-dist"

MANIFEST = """name: fin-research-assistant
version: {version}
description: "A 股每日盘后简报与个股研究助手。数据来自公开行情、财报、公告，不做涨跌预测。"
author: fin
license: MIT

env_requires:
  - name: FIN_DATA_DIR
    description: "CLI 缓存与简报存档目录，留空则用 ~/.fin-data"
    required: false
    default: "~/.fin-data"

distribution_owned:
  - SOUL.md
  - config.yaml
  - .no-bundled-skills
  - skills/
  - cron/
  - src/
  - README.md
  - pyproject.toml
  - docs/
  - CUSTOMER-SETUP.md
"""

SOUL = """# 金融研究助手

你是 A 股公开信息研究助手，服务于需要快速掌握市场与个股情况的研究人员。

## 定位

- **整理者，不是预言者**：组织公开数据、解释现象、指出风险；不预测涨跌、不推荐买卖。
- **数据优先于叙事**：任何数字都必须来自 `fin` CLI 的本次输出。宁可说"暂无数据"，也不用记忆或推断填补。
- **出处可追溯**：每条结论标注来源键，让用户能自己核对。

## 不做

- 不预测股价、不判断"能不能买"
- 不给目标价、不给仓位建议
- 不声称数据实时——行情有 1–2 分钟缓存，财报是最近一期
- 不对未上市、退市、非 A 股标的做分析

## 语气

专业、克制、直接。用数据说话，不用"可能""或将"这类模糊表述代替事实。
风险要说清楚，但不吓唬人——列出证据，让用户自己判断。

## 出错时

数据源不可用时，如实说明哪一块缺了、为什么、是否用了旧数据。
不要为了让报告完整而编造或估算。
"""

CONFIG = """# 金融研究助手 profile 配置
#
# 模型与 API Key 必须由使用者自行填写 —— 分发包不带任何密钥。
# 首次运行 `hermes -p finance setup` 可自动补全。
model:
  default: ""
  provider: ""

agent:
  max_turns: 60
  verbose: false
  reasoning_effort: medium

terminal:
  backend: local
  timeout: 180

skills:
  creation_nudge_interval: 15

compression:
  enabled: true
  threshold: 0.5

memory:
  memory_enabled: true
  user_profile_enabled: true
  nudge_interval: 10
  flush_min_turns: 6

display:
  streaming: true
  tool_progress: all
  show_reasoning: false

session_reset:
  mode: both
  idle_minutes: 1440
  at_hour: 4
"""

NO_BUNDLED = """# 存在此文件时，Hermes 不会向本 profile 灌入内置技能。
# 需要内置技能时删除本文件即可。
"""


def _copytree(src: Path, dst: Path) -> None:
    shutil.copytree(
        src, dst, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def build(version: str = "0.1.0", force: bool = False) -> Path:
    if OUT.exists():
        if not force:
            raise SystemExit(f"{OUT} 已存在。加 --force 覆盖。")
        shutil.rmtree(OUT)

    OUT.mkdir(parents=True)
    (OUT / "distribution.yaml").write_text(MANIFEST.format(version=version), encoding="utf-8")
    (OUT / "SOUL.md").write_text(SOUL, encoding="utf-8")
    (OUT / "config.yaml").write_text(CONFIG, encoding="utf-8")
    (OUT / ".no-bundled-skills").write_text(NO_BUNDLED, encoding="utf-8")

    _copytree(ROOT / "src" / "fin", OUT / "src" / "fin")
    _copytree(ROOT / "skills", OUT / "skills")
    shutil.copy2(ROOT / "pyproject.toml", OUT / "pyproject.toml")

    docs = OUT / "docs"
    docs.mkdir()
    for name in ("技术文档.md", "hermes-integration.md"):
        src = ROOT / "docs" / name
        if src.exists():
            shutil.copy2(src, docs / name)

    (OUT / "README.md").write_text(
        (ROOT / "README.md").read_text(encoding="utf-8")
        + "\n\n---\n\n本目录由 `scripts/build_distribution.py` 生成，请勿直接编辑。\n",
        encoding="utf-8",
    )
    setup = next(
        (p for p in (ROOT / "docs" / "CUSTOMER-SETUP.md", ROOT / "distribution" / "CUSTOMER-SETUP.md")
         if p.exists()),
        None,
    )
    if setup:
        shutil.copy2(setup, OUT / "CUSTOMER-SETUP.md")

    cron_src = ROOT / "distribution" / "cron" / "jobs.json"
    if cron_src.exists():
        (OUT / "cron").mkdir()
        shutil.copy2(cron_src, OUT / "cron" / "jobs.json")

    return OUT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out = build(args.version, args.force)
    files = sorted(p for p in out.rglob("*") if p.is_file())
    print(f"已生成 {out}")
    print(f"共 {len(files)} 个文件")
    print("\n安装：")
    print(f"  hermes profile install {out} --name finance --alias")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
