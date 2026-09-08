# Plan: prompts/prompts.md → `/ocr-csv-pipeline` skill

## Context

`prompts/prompts.md`（30KB）是外贸名片 OCR 流水线的 4 个自包含提示词（索引→OCR→NLP 抽取→合并），现状是人工复制粘贴到独立 Claude Code 会话执行。目标：封装成项目级 skill，用 `/ocr-csv-pipeline <1|2|3|4|all>` 调用，替代手工复制。skill 成为唯一权威源，`prompts/prompts.md` 直接删除（探索确认全仓库零引用，删除不断链）。

**用户已确认的决定**：
- 名字：`ocr-csv-pipeline`
- user-invoked（`disable-model-invocation: true`，零常驻上下文；description 作人类可读一行说明）
- 粒度：单步 `1..4` + `all` 一口气 1→4
- prompts.md 直接删除

## 结构

```
.claude/skills/ocr-csv-pipeline/     # 真目录，与 37 个 symlink 共存无冲突（名字不撞）
├── SKILL.md                         # 路由 + 总则（每次调用必载）
└── steps/
    ├── 1.md                         # 第 1 步：文件索引构建
    ├── 2.md                         # 第 2 步：OCR 文字提取
    ├── 3.md                         # 第 3 步：关键信息抽取与结构化
    └── 4.md                         # 第 4 步：数据合并
```

依据 writing-for-agents 的分层原则：SKILL.md = 路由 + 全分支共需的材料（总览、总则）；每步一个文件 = disclosed reference，只在该步运行时载入（progressive disclosure / 按序列切分）。

## SKILL.md

```markdown
---
name: ocr-csv-pipeline
description: 外贸名片 OCR 流水线（PNG → final.csv）。用法：/ocr-csv-pipeline <1|2|3|4|all>。
disable-model-invocation: true
---
```

正文（中文）包含：

1. **一段背景**：目标（raw_data/*.png → processed_data/final.csv）、仓库根 = 当前工作目录、4 步各一行 + 指向 `steps/N.md`。
2. **调用**：
   - `1`–`4` → Read 对应 `steps/N.md`，按其执行到该步"完成后输出"为止。
   - `all` → 依次执行 1→4；**每步全量验证 exit 0 才进下一步，任何一步失败即停并报告**（防抢跑的完成判据）。
   - 一行幂等说明：各步按 checklist 状态续跑，重复执行只处理未完成部分。
3. **工具调用总则**（从 prompts.md 顶部原文迁入，3 条）：批量单条 Bash 禁串行；Python 一律 `uv run`；并发参数读 `pipeline.config.json`（`max_concurrency` 缺省 6）。

## steps/N.md 改编规则（对 prompts.md 各提示词，**逐字迁移为主**）

各步文件 = 原"提示词 N"内容，做且仅做以下改动：

- **删**「任务背景」整节（4 步重复 4 次；共享信息已在 SKILL.md）。标题升为 H1：`# 第 N 步：<名称>`。
- **删**「通用约定」里纯复述总则的行（"Python 必须走 uv run / 禁止直接用 python"、"批量调用原则见总则"类）；保留步骤特有约定（不改文件名、子 Agent 串行/并发上限、必须经 0X-xxx.py 写 checklist 等）。命令示例里的 `uv run` 原样保留（那是落地细节不是复述）。
- **改** steps/3.md 前置检查 #4 的权威源指向：原文"本提示词文件下方'子 Agent 提示词模板'一节"→"本文件（steps/3.md）下方'子 Agent 提示词模板'一节"（build_prompts.py 的 TEMPLATE 仍是需比对的漂移副本，比对逻辑不变）。
- 保留各步内部的**子 Agent 提示词模板**代码块逐字不动（子 Agent 看不到 SKILL.md，必须自包含）。
- 前置检查 / 调度流程 / 完成后输出等其余内容逐字保留。

## 执行分解（subAgent 并行）

1. **本人直接写** SKILL.md（路由是关键件，含 frontmatter）。
2. **3 个并行 subagent**（逐字迁移 + 上述规则，禁止自行改写措辞）：
   - A：steps/1.md + steps/4.md（小）
   - B：steps/2.md（大，OCR 调度）
   - C：steps/3.md（大，NLP 调度 + 权威源指向修正）
3. **删** `prompts/prompts.md`（`rm`，git 会记录删除；不自动 commit，报告后由用户提交）。

## 验证

1. 结构：5 个文件就位，SKILL.md frontmatter 三键齐全，steps/N.md 无残留「任务背景」节。
2. 内容完整性：逐节比对原 prompts.md → 各步文件（任务背景/总则复述行除外），确认无内容丢失；子 Agent 模板块逐字一致。
3. 冒烟：运行 `/ocr-csv-pipeline 1` — 本仓库 `processed_data/names-checklist.csv` 已存在，应走幂等分支报告"checklist 已存在，跳过本步"，零副作用。
4. 残留引用：`grep -r "prompts.md"` 全仓库无命中。

## 范围外（提及、不动）

- `main_flow.md`（根目录）是同一流水线的旧叙述版，本就无人引用；本次不动，留用户处置。
- `prompts/option_category/` 两个 JSON 保留（步骤 3 运行时读取）。
- `raw_data/tg_features.csv` 当前存在（仅表头一行，作为字段表模板），步骤 3 运行依赖它。
