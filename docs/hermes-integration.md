# 接入 Hermes

## 1. 安装 CLI

```bash
cd D:/2026/智能体开发/金融智能体
pip install -e .
```

验证：

```bash
fin market quote
```

## 2. 挂载技能目录

编辑 `~/.hermes/config.yaml`，加入 `external_dirs`（与其他 skills 配置同级）：

```yaml
skills:
  creation_nudge_interval: 15
  external_dirs:
    - D:/2026/智能体开发/金融智能体/skills
```

技能加载器有缓存，**改完要新开一个 Hermes 会话**才能看到 `fin-market` / `fin-research`。

验证：在 Hermes 里问"今天大盘怎么样"，应触发 `fin-market`。

## 3. 定时简报

```bash
hermes cron create "35 15 * * 1-5" \
  "使用 fin-market 技能生成今日 A 股盘后简报，落盘并输出全文" \
  --name "A股盘后简报" \
  --deliver feishu \
  --skill fin-market
```

说明：
- 15:35 在收盘（15:00）后，数据已稳定
- `--deliver` 可选 `feishu` / `wecom` / `email` / `telegram`，按需选择
- 周末不会触发（`1-5`），但法定节假日会触发 —— 简报技能第 1 步会判断休市

查看与调试：

```bash
hermes cron list
hermes cron run <job_id>      # 立即跑一次
```

## 4. 本地数据

| 路径 | 内容 |
|---|---|
| `~/.fin-data/fin.db` | SQLite 缓存 + 股票符号表 |
| `~/.fin-data/briefs/YYYY-MM-DD.md` | 每日简报存档 |

改位置：设置环境变量 `FIN_DATA_DIR`。

## 5. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 技能不出现 | 加载器缓存 | 新开会话 |
| `fin: command not found` | 未安装或 PATH 未刷新 | 重跑 `pip install -e .`，或直接用 `python -m fin.cli` |
| 中文乱码 | Windows 终端 GBK | CLI 已强制 UTF-8；若出现在文件里，检查 `PYTHONUTF8=1` |
| 行情接口报错 | 东财临时限流 | 等几分钟；CLI 会自动读过期缓存并标 `stale` |
| 想离线演示 | 无网络或限流 | 加 `--offline`，使用缓存快照 |
