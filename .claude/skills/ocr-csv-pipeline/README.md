# ocr-csv-pipeline — 安装与使用

外贸名片 OCR 流水线 skill（PNG → final.csv）。本目录自带 `scripts/`（全部脚本、测试、`requirements.txt`），整个目录即完整可复制单元；流程与用法见 [SKILL.md](SKILL.md)。

## 前置

- Python 3.10+（自带 `venv` / `pip`，无需安装任何额外工具）。

## 安装（两步）

1. 复制本目录到目标项目 `.claude/skills/ocr-csv-pipeline/`（或用户级 `~/.claude/skills/ocr-csv-pipeline/`）。
2. 备齐项目侧输入（相对目标项目根）：
   - `raw_data/*.png` — 名片图片
   - `raw_data/tg_features.csv` — 字段表（第 1 行为表头，列数不固定）
   - `prompts/option_category/*.json` — 固定选项字典 + 选项依据语料（文件名与结构逐项目不同）
   - 可选 `pipeline.config.json`（缺省 `max_concurrency=6`、`ocr_batch_size=10`、`nlp_batch_size=10`）

`.venv` 无需手建（第 1 步前置检查自动创建并装依赖）；`processed_data/` 无需手建。

## 首次验证

在目标项目根执行 `/ocr-csv-pipeline 1`：应自动建 `.venv` 并生成 `processed_data/names-checklist.csv`；再执行一次应报「checklist 已存在，跳过本步」（幂等冒烟）。

## 使用

- `/ocr-csv-pipeline all` — 全流程，任一步验证失败即停。
- `/ocr-csv-pipeline 1|2|3|4` — 单步执行；按 checklist 状态幂等续跑。
