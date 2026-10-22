---
name: fin-market
description: 生成 A 股每日盘后简报。当用户问"今天大盘怎么样""生成简报""复盘"或定时任务触发时使用。输出结构化的行情解读、板块冷热、重点资讯、次日关注与昨日判断回顾。
version: 0.1.0
author: fin
license: MIT
metadata:
  hermes:
    tags: [finance, a-share, market, brief, daily]
    related_skills: [fin-research]
---

# A 股盘后简报

## Overview

用 `fin` CLI 取数、Hermes 写解读，产出一份 5 分钟读完的盘后简报，并落盘供次日回顾。
**所有数字来自 CLI 输出，你不计算、不补充、不回忆。**

## When to Use

- 定时任务触发（每天 15:35，工作日）
- 用户问"今天大盘怎么样""帮我复盘""生成今日简报"
- 用户问"最近市场热点"

Don't use for：个股分析 → `fin-research`；风险扫描 → `fin risk <code>`

## 执行步骤

### 1. 环境自检

首次使用或报 `fin: command not found` 时，先试：

```bash
python -m fin.cli --help
```

不通则执行一次（幂等，可重复跑）：

```bash
pip install -e "${HERMES_SKILL_DIR}/../.." --quiet
```

`${HERMES_SKILL_DIR}` 会替换成本技能的绝对路径，向上两级就是 profile 根目录
（含 `pyproject.toml`）。装好后 `fin` 与 `python -m fin.cli` 等价。

### 2. 交易日判断

```bash
fin market quote
```
- 若 `ok: false` 且提示上游失败，先确认是否周末（看 `data.summary.weekday`）
- 周末或节假日：输出"今日休市"，**不要编造行情**

完成标准：拿到 4 个指数的 `price` / `change_pct`。

### 3. 取全部数据块

```bash
fin market breadth
fin market sector --limit 10
fin market limitup
fin brief assemble
```

完成标准：四个命令都返回，或已记录哪些失败及原因。

### 4. 写简报

按 `brief assemble` 返回的 `narrative_slots` 逐一填写：

```markdown
# A 股盘后简报 · {date}

## 一句话
{最显著特征，不超过 40 字}

## 今日市场
{指数表现}
{涨跌家数：用 market_total.up / down}
{成交额：total_amount_yi，单位亿元}

## 板块冷热
{领涨 3 个、领跌 3 个，各附涨跌幅}
{主力资金净流入/流出最多的板块}

## 重点资讯
{从 news 挑 3-5 条，每条：标题 + 为什么值得关注 + 来源}

## 次日关注
{从 calendar.disclosure_next_7d 挑最重要的 3 条}

## 昨日回顾
{读 previous_brief，逐条标注：已验证 / 未验证 / 不成立}
{没有前一日简报就写"次日开始回顾"}

## 数据说明
{列出 warnings 中的每一条数据缺陷}
```

完成标准：每个数字都能在 `brief assemble` 的 JSON 里找到；每段末尾有 `[来源键]`。

### 5. 落盘

```bash
fin brief save --date {date} --markdown "{简报正文}"
```

完成标准：返回 `path`。

### 6. 记录预测（供明日回顾）

在简报末尾加 HTML 注释，只写**可证伪**的判断：

```markdown
<!-- predictions:
1. 若明日成交额继续低于 2 万亿，指数难有反弹
2. 关注 XX 板块能否延续
-->
```

禁止写"明日可能上涨"这类无法验证的判断。

## 硬规则

1. 每个数字必须出现在本次 CLI 输出的 JSON 中，不得跨日期拼接。
2. 每段结论末尾标注来源键，如 `[market.indexes]`、`[news]`。
3. 数据缺失写"暂无数据"，不得推断、不得用历史数据代替。
4. 不预测涨跌、不给买卖建议。
5. `warnings` 里的每一条都要在"数据说明"中出现。

## 常见错误

| 错误 | 正确做法 |
|---|---|
| 把创业板指跌 4% 说成"全市场下跌" | 创业板是子集，用 `market_total.up/down` 描述全市场 |
| 把 `by_index` 四个指数涨跌家数相加 | 只能加沪指 + 深成指，其余是子集 |
| 板块排名里出现"电机Ⅱ""电机Ⅲ" | 正常情况 CLI 已去重；若仍出现，在数据说明里标注 |
| 成交额单位写成"万亿"却没换算 | 用 `total_amount_yi`，单位亿元 |
| 涨跌家数缺失时写"0 家" | 看 `breadth.unavailable`，写"暂无数据"并用 `sentiment` 替代 |
