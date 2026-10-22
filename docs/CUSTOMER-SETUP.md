# 金融研究助手 · 安装说明（给客户）

这个 profile 有三种装法：CLI 安装、桌面端导入、CLI 快照导入。**推荐方式 A**。

---

## 桌面端（Hermes Studio）能不能用？

**能用，但有一个硬前提：客户机器上必须另外装好 `hermes-agent`（Python 后端）。**

原因（已核实桌面端 0.20.6 源码）：Hermes Studio 的 Electron 外壳不包含 Python 运行时，
它启动时按 `HERMES_AGENT_ROOT` / `HERMES_BIN` / `PATH` 的顺序去找外部的 `hermes-agent`
目录（必须含 `run_agent.py`），找到后用 `uv` 拉起来跑。找不到会直接报错。

所以给桌面端客户的完整前置条件是：

1. 安装 Hermes Studio（桌面端）
2. **另装 hermes-agent 后端**（否则桌面上什么都跑不起来）
3. 再按下面的方式 A 装本 profile

装好后桌面端的行为：

| 能力 | 是否可用 | 说明 |
|---|---|---|
| profile 出现在切换列表 | ✅ | 桌面端读 `~/.hermes/profiles/`，与 CLI 同一份 |
| 技能加载 | ✅ | `skills/fin-market`、`fin-research` 会自动出现 |
| 对话式分析 | ✅ | 与 CLI 表现一致 |
| 定时任务自动触发 | ⚠️ | 依赖 gateway 常驻，桌面端不会替你启 |
| `fin` CLI | ⚠️ | 必须装在系统 `PATH` 上，详细见下 |

桌面端也支持图形化导入/导出 profile（`/api/hermes/profiles/import` 接受
`.tar.gz` / `.zip`），所以如果客户不熟悉命令行，可以走界面导入导出的归档包。

### 桌面端最容易踩的坑：`fin` 找不到

agent 执行技能里的 `fin market quote` 时，走的是**系统 PATH**，
不是 Hermes 自己的 Python 环境。客户必须保证：

```bash
python -m pip install -e ~/.hermes/profiles/finance
```

用的是**与系统 `python` 同一个解释器**。装完自检：

```bash
fin market quote
```

返回 JSON 即成功。若失败，技能里还有保底写法 `python -m fin.cli market quote`。

---

## 方式 A：一条命令安装（推荐）

前提：已安装 Hermes 后端，且 `hermes` 命令可用。

```bash
hermes profile install <发行包地址> --name finance --alias
```

`<发行包地址>` 可以是：

- **本地目录**：把 `distribution/` 整个文件夹发给客户，客户解压到任意位置后填那个路径
- **git 仓库**：`github.com/<你的账号>/fin-research-assistant`（需要先把 distribution 推上去）

装完得到：

- 一个新的 Hermes profile，名为 `finance`
- 命令别名 `finance`（可直接 `finance` 启动，与默认 profile 完全隔离）
- `skills/fin-market`、`skills/fin-research` 两个技能
- 预置的每日简报定时任务

### 然后执行三步

```bash
# 1. 安装数据 CLI（幂等，可重复执行）
python -m pip install -e ~/.hermes/profiles/finance

# 2. 配置模型（API Key 必须客户自己填）
finance setup

# 3. 启动 gateway —— 不启动则定时任务不会触发
hermes -p finance gateway install    # Windows 计划任务，登录自启
# 或者前台运行调试：hermes -p finance gateway run
```

验证：

```bash
fin market quote
finance cron list          # 应显示 Next run
```

然后在对话框里问"今天大盘怎么样"。

> Windows 上 profile 目录是 `C:\Users\<用户名>\.hermes\profiles\finance\`。
> `~` 在 Git Bash 里可用；若用 PowerShell，请写完整路径。
>
> **注意**：如果客户和你在同一台机器上演示，`pip install -e` 会把 `fin` 命令指向
> 最后安装的那个 profile。多个 profile 共存时，用 `python -m fin.cli` 并在
> profile 目录下执行，或为每个 profile 单独装一个 venv。

---

## 方式 B：快照导入（不要求客户装 git）

如果你只想给一个"已经调好、能直接演示"的包：

```bash
hermes profile export finance -o finance-demo.tar.gz
```

客户侧：

```bash
hermes profile import finance-demo.tar.gz --name finance
```

区别与注意事项：

| | 方式 A（install） | 方式 B（export/import） |
|---|---|---|
| 能否后续更新 | 能，`hermes profile update finance` | 不能，只能重导 |
| 是否含你的会话记录 | 否 | **否**（导出会自动排除 sessions/memories/auth） |
| 是否含模型 API Key | 否 | **否**（`auth.json`、`.env` 被排除） |
| 客户要做什么 | 装 CLI + 配模型 | 装 CLI + 配模型 |
| 适合场景 | 正式交付 | 临时演示 |

**两种方式都需要客户自己配模型**——这是刻意的：不能把你的 API Key 发给客户。

---

## 装完后客户要改的 3 处

| 位置 | 默认值 | 改成 |
|---|---|---|
| `config.yaml` 的 `model` | 空（必填） | 客户自己的模型 |
| `cron/jobs.json` 的 `deliver` | `local` | 要推送就改成 `feishu` 等，需先配好该渠道 |
| 环境变量 `FIN_DATA_DIR` | `~/.fin-data` | 一般不用改 |

`cron/jobs.json` 里预置的任务：简报任务默认 `enabled: true`；风险扫描默认 `enabled: false`，
客户配好自选股（`~/.fin-data/watchlist.txt`，每行一个代码）后改成 `true` 即可。

改了 `jobs.json` 后重启 gateway 生效：`hermes -p finance gateway run`。

---

## 升级

改了 `src/` 或技能后重新打一个发行包，客户执行：

```bash
hermes profile update finance
```

只会覆盖 `SOUL.md`、`skills/`、`cron/`、`src/`、文档。
客户的记忆、会话、API Key、`config.yaml` 里的个性化设置**不会被动**。
