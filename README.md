# Foreign Trade Client Data Process

把外贸客户名片图片（PNG）走 OCR + NLP 抽取成结构化 CSV 的流水线。整条流水线由 `code/` 下的 7 个 Python 脚本驱动，每个脚本职责单一，详情见 [`code/py-doc.md`](code/py-doc.md)。

```
raw_data/*.png  ──▶  01-filename-index  ──▶  names-checklist.csv
                                              │
                                              ▼
                                         02-write-OCR  (×N 并行)
                                              │
                                              ▼
                                  processed_data/txts/*.txt
                                              │
                                              ▼
                                       02-OCR-check
                                              │
                                              ▼
                                     03-tmp-csv  (×N 并行)
                                              │
                                              ▼
                                  processed_data/csvs/*.csv
                                              │
                                              ▼
                                    03-write-feature  (×N 并行)
                                              │
                                              ▼
                                       03-NLP-check
                                              │
                                              ▼
                                          04-merge
                                              │
                                              ▼
                                       processed_data/final.csv
```

---

## 1. 环境要求

- **Python**：3.10+
- **uv**：>= 0.4。`uv` 

---

## 2. 创建并激活虚拟环境

在 **项目根目录**（即 `README.md` 所在目录）执行：

### 推荐：用 `uv run` 一把搞定（无需手动激活）

```bash
# 一次性建虚拟环境 + 装依赖
uv venv
uv pip install -r code/requirements.txt
```

之后所有命令都加 `uv run` 前缀即可，例如：

```bash
uv run python code/01-filename-index.py --raw-dir raw_data --output processed_data/names-checklist.csv
```

### 备选：传统方式（手动激活 venv）

```bash
uv venv
source .venv/bin/activate              # Linux / macOS
# .venv\Scripts\activate               # Windows PowerShell

uv pip install -r code/requirements.txt
python code/01-filename-index.py --raw-dir raw_data --output processed_data/names-checklist.csv
```

---

## 3. 目录约定

执行流水线前确认以下目录存在：

| 路径 | 用途 |
|------|------|
| `raw_data/` | 输入：`.png` 名片图片 + 字段表 `1.client_features.csv` |
| `processed_data/` | 生成的 checklist / txts / csvs / final.csv 都放这里 |
| `processed_data/txts/` | 步骤 02 的 OCR 文本输出 |
| `processed_data/csvs/` | 步骤 03 的结构化临时 CSV |

如果 `processed_data/` 子目录不存在，脚本会自行 `mkdir(parents=True)`。

---

## 4. 端到端测试：步骤 01

**目标**：验证 01-filename-index.py 能正确扫描 `raw_data/` 下所有 PNG，生成 3 列 checklist CSV。

### 4.1 准备

仓库当前已经放了 4 个测试用的 PNG：

```
raw_data/
├── 1.client_features.csv          # 字段表（14 列）
├── 2011-08-12 1.png
├── 2011-08-12 2.png
├── 2011-08-14 1.png
└── 2011-08-14 2.png
```

如果 `processed_data/names-checklist.csv` 已经存在，先清掉，避免和上次产物混淆：

```bash
rm -f processed_data/names-checklist.csv
```

### 4.2 执行

```bash
# 用 uv run
uv run python code/01-filename-index.py \
    --raw-dir raw_data \
    --output processed_data/names-checklist.csv

# 或在已激活 venv 中
python code/01-filename-index.py \
    --raw-dir raw_data \
    --output processed_data/names-checklist.csv
```

### 4.3 验证

**期望输出**（stdout）：

```
[OK] wrote 4 rows to processed_data/names-checklist.csv
```

**期望文件**（`processed_data/names-checklist.csv`）：

```csv
Filename,OCR,Feature Extract
2011-08-12 1.png,,
2011-08-12 2.png,,
2011-08-14 1.png,,
2011-08-14 2.png,,
```

**自动验证**：

```bash
# 行数：1 表头 + 4 数据 = 5
test "$(wc -l < processed_data/names-checklist.csv)" = "5" && echo "ROW_COUNT_OK"

# 表头严格匹配
head -n 1 processed_data/names-checklist.csv | grep -qx "Filename,OCR,Feature Extract" && echo "HEADER_OK"

# OCR / Feature Extract 列初始为空
awk -F, 'NR>1 && ($2!="" || $3!="") {print "DIRTY"; exit 1} END {if (NR==5) print "EMPTY_COLS_OK"}' \
    processed_data/names-checklist.csv

# 顺序为 ASCII 升序
cut -d, -f1 processed_data/names-checklist.csv | tail -n +2 | grep -q "2011-08-12 1.png" && echo "ORDER_OK"
```

四项全 `*_OK` 即为通过。

### 4.4 错误路径冒烟

脚本应当能优雅地报错退出（exit code 1）：

```bash
# 目录不存在
uv run python code/01-filename-index.py --raw-dir /no/such/dir --output /tmp/x.csv
echo "exit=$?"   # 期望 exit=1

# 目录里没 .png
uv run python code/01-filename-index.py --raw-dir processed_data --output /tmp/x.csv
echo "exit=$?"   # 期望 exit=1
```

---

## 5. 后续步骤（预览）

01 步骤通过后，可继续跑 02 / 03 / 04。完整规范见 `code/py-doc.md`：

| 步骤 | 脚本 | 触发方式 |
|------|------|----------|
| 02 | `code/02-write-OCR.py` | 每个 OCR 子 Agent 完成后调用一次，标记单行 OCR 状态 |
| 02 校验 | `code/02-OCR-check.py` | 所有 02 写完后做一致性检查 |
| 03 | `code/03-tmp-csv.py` + `code/03-write-feature.py` | NLP 阶段并行 |
| 03 校验 | `code/03-NLP-check.py` | NLP 全部完成后做一致性检查 |
| 04 | `code/04-merge.py` | 最后合并为 `final.csv` |

> 02 / 03 阶段会有 N 个并行的子 Agent 写入 checklist，因此 `02-write-OCR.py` 和 `03-write-feature.py` 用 `filelock` 加排他锁（`code/requirements.txt` 中的 `filelock` 依赖为它们服务）。

---

## 6. 故障排查

| 现象 | 可能原因 | 解决 |
|------|----------|------|
| `ModuleNotFoundError: No module named 'filelock'` | 没装依赖 / 用了非 venv 的 python | `uv pip install -r code/requirements.txt`，并确认命令走 `uv run python` |
| `ModuleNotFoundError: No module named 'csv'` | 极少见的 Python < 2.7 环境 | 升级到 Python 3.10+ |
| 行尾变 `\r\n` | 用普通 `open()` 替代了 `csv` 模块 | 检查脚本里是否有 `open(..., newline="")` 和 `lineterminator="\n"` |
| checklist 写入后中文乱码 | 文件被外部编辑器另存为 GBK | 始终用 UTF-8 打开/写入；不要用 Excel 直接保存 |
| 02 阶段 lock 超时 | 两个进程同时抢锁 / 死锁 | 检查 `.lock` 文件是否残留，必要时 `rm -f processed_data/names-checklist.csv.lock` |
