---
name: ocr-csv-pipeline
description: 外贸名片 OCR 流水线（PNG → final.csv）。用法：/ocr-csv-pipeline <1|2|3|4|all>。
disable-model-invocation: true
---

# 外贸客户名片 OCR 流水线

把 `raw_data/` 下所有 PNG 经 OCR + 信息抽取，汇总为一份标准 CSV 表格（`processed_data/final.csv`）。仓库根目录就是当前工作目录，所有相对路径都基于此根目录。

本 skill 自带 `scripts/`（全部流水线脚本、测试与 `requirements.txt`），目录整体即完整可复制单元；`$SKILL` = 本 SKILL.md 所在目录，执行命令时以绝对路径代入。安装到新项目 → 见 [README.md](README.md)。

流水线共 4 步，每步一个文件：

1. [第 1 步：文件索引构建](steps/1.md) — 扫描 `raw_data/*.png` 生成 `processed_data/names-checklist.csv`（后续 3 步的调度总表）
2. [第 2 步：OCR 文字提取](steps/2.md) — 按批调度 OCR 子 Agent，写出对应 .txt，更新 checklist 的 OCR 列
3. [第 3 步：关键信息抽取与结构化](steps/3.md) — 按批调度 NLP 子 Agent，写出对应临时 csv，更新 checklist 的 Feature Extract 列
4. [第 4 步：数据合并](steps/4.md) — 按 checklist 顺序合并所有临时 csv 为 `processed_data/final.csv`

## 调用

- `1`–`4`：Read 对应的 `steps/N.md`，按其执行到该步「完成后输出」为止。
- `all`：依次执行第 1 → 4 步。**每步全量验证 exit 0 才进下一步；任何一步失败立即停下并报告**，不得跳过或继续。
- 各步幂等：按 checklist 状态续跑，重复执行只处理未完成部分。

## 工具调用总则

所有步骤都遵循以下三条原则；具体落地细节见各步的「通用约定」。

1. **尽量批量调用，尽量避免串行**：所有"独立、无依赖"的操作必须放进**同一条 tool 调用**里执行。
   - 多操作令用 `;` / `&&` 或 `for` 循环串成**单条 Bash** → 一次执行。一次性输出 `[OK]/[MISSING]`
   - 写 N 行 checklist → 把 N 个脚本调用串成单条 Bash
   - **典型反例（禁止）**：N 个文件用 N 次 Bash 各做一次；`max_concurrency` 个子 Agent 完成后用 `max_concurrency` 次 Bash 各写一次 checklist
2. **Python 一律用项目根 `.venv` 解释器**：所有脚本调用形如 `.venv/bin/python "$SKILL/scripts/NN-x.py" ...`（无需 activate；**禁止直接用系统 `python` 命令**）。一次性环境准备（幂等，第 1 步前置检查会自动做）：
   ```bash
   [ -x .venv/bin/python ] || python3 -m venv .venv
   .venv/bin/pip install -q -r "$SKILL/scripts/requirements.txt"
   ```
3. **并发上限取自配置文件**：第二步（OCR）与第三步（NLP）派发子 Agent 的并发数 `max_concurrency` 从仓库根 `pipeline.config.json` 读取；若该文件不存在或 `max_concurrency` 字段缺失，默认 6。启动相关步骤前先用 Read 工具读该文件取该值；后续分批、并发派发都按这个数走。
