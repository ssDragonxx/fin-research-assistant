---
name: fin-research
description: 对指定 A 股公司做基础投研分析。当用户提到公司名称/股票代码并希望了解其经营、估值、财务、同业对比、近期动态或风险时使用。输出带数据来源的研究摘要，不预测股价、不给买卖建议。
version: 0.1.0
author: fin
license: MIT
metadata:
  hermes:
    tags: [finance, a-share, stock, research, valuation]
    related_skills: [fin-market]
---

# 个股研究

## Overview

用户给一个公司名或代码 → `fin` CLI 取数与规则扫描 → 你写一份带出处的研报摘要。

## When to Use

- "帮我看看宁德时代""分析一下比亚迪"
- "XX 和 YY 哪个估值便宜"（做两次，再横向对比）
- "这家公司最近有什么消息""财务怎么样"

Don't use for：大盘行情 → `fin-market`；单纯的股价查询用 `fin market quote` 更轻。

## 执行步骤

### 0. 环境自检

报 `fin: command not found` 时先试 `python -m fin.cli --help`；若不通，执行一次：

```bash
pip install -e "${HERMES_SKILL_DIR}/../.." --quiet
```

`${HERMES_SKILL_DIR}` 会替换成本技能的绝对路径，向上两级即 profile 根目录。

### 1. 解析标的

```bash
fin resolve {用户输入}
```

- `exact` 有值 → 继续
- `exact` 为 null 且 `candidates` 非空 → **先反问用户是哪一个**，不要自己选
- 报错 → 告诉用户没找到，请给代码

完成标准：拿到 6 位 `code`。

### 2. 取数

```bash
fin stock {code} --parts quote,financials,peers,announce,news
fin risk {code}
fin calendar {code}
```

一次 `fin stock` 已包含大部分数据；风险与日程单独取，便于分别引用。
如果 `fin stock` 某部分失败，`warnings` 里会说明，照实转述。

完成标准：五个部分至少拿到四个，缺失项记入"数据说明"。

### 3. 写研报

```markdown
# {name}（{code}）研究摘要
数据截至 {as_of}

## 公司概况
{主营 + 所属行业，信息仅来自 quote.industry，不要展开你没有的行业知识}

## 行情与估值
| 指标 | 数值 |
|---|---|
| 最新价 | {quote.price} |
| 总市值 | {quote.market_cap_yi} 亿元 |
| PE-TTM | {quote.pe_ttm} |
| PB | {quote.pb} |
[quote]

## 财务表现
{最近 4 期：营收、归母净利、同比、ROE、毛利率、负债率}
{指出趋势：改善/恶化/平稳，只用数据说话}
[financials]

## 同业对比
{peers.peers 里 3-5 家，对比 PE/PB/市值}
{个股 PE 相对行业中位数高/低多少}
[peers]

## 近期公告与新闻
{公告 3 条 + 新闻 3 条，每条附日期与链接}
[announce] [news]

## 风险提示
{risk.hits 逐条列出，保留 evidence 原文}
{按 risk.max_level 给出一句总体判断}
[risk]

## 数据说明
{列出 warnings 与所有"暂无数据"的项}
```

完成标准：表格里每个数字都在 JSON 中存在；风险段落的条数等于 `risk.hit_count`。

### 4. 对比场景（两家公司）

分别执行步骤 1-2，然后只比较**同名指标**：

```markdown
| 指标 | A | B |
|---|---|---|
| PE-TTM | ... | ... |
| PB | ... | ... |
| 营收同比 | ... | ... |
| 毛利率 | ... | ... |
| 资产负债率 | ... | ... |
```

禁止说"A 更值得买"，可以说"A 的 PE 高于 B，但营收增速也更高"。

## 硬规则

1. 每个数字必须来自本次 CLI 输出；不得用记忆里的股价、市值、财务数据。
2. 财务数据要标明报告期（如"2026 三季报"），不同报告期不可混用。
3. PE 统一使用 `pe_ttm`；若只有动态 PE，需注明口径。
4. 风险条目不得增删，只能解释；`evidence` 里的数字原样保留。
5. 无数据：写"暂无数据"，不得用行业均值或历史值替代。
6. 不做涨跌预测，不出现"建议买入/卖出/持有"，不用"必将""肯定会"。
7. 报告末尾固定注明：本内容为公开信息整理，不构成投资建议。

## 常见错误

| 错误 | 正确做法 |
|---|---|
| 说"行业龙头"却没数据支撑 | 只能说 `peers.member_count` 里的市值排名 |
| 把 H 股公告当 A 股公告分析 | 公告标题含"H股"的单独标注 |
| 用历史 PE 分位数说"低估" | CLI 不提供分位数，禁止此类结论 |
| 融资/股东变化凭印象写 | 只写 `announce` 和 `news` 里出现的内容 |
