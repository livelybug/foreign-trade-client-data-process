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
| `raw_data/` | 输入：`.png` 名片图片 + 字段表 `tg_features.csv` |
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
├── tg_features.csv          # 字段表（14 列）
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

### 4.5 自动测试

`code/test/` 下有 7 个端到端 pytest 测试文件 + 1 个独立验证脚本：

- **pytest 测试**（7 个）：`test_<脚本同名>.py`，每个对应一个被测脚本，覆盖成功路径、错误路径，写脚本的还含并发路径。
- **独立验证脚本**（1 个）：`verify_uncertain_json.py`，不在 pytest 套件内（因为要看真实子进程并发的文件系统行为），用 `uv run python` 直接跑。详见 [§4.6](#46-独立验证脚本)。

测试机制：

- `uv run --with pytest pytest` — uv 在临时 venv 里装 pytest 并运行，不依赖项目 `.venv` 是否就绪
- 测试内部的 `_ensure_env` fixture 跑 `uv venv` + `uv pip install -r code/requirements.txt`，自动建项目 venv 和装 `filelock`
- 测试用 `uv run python code/<script>.py ...` 跑被测脚本（自动走项目 venv）
- 第一次跑会触发 venv 创建 + 装 filelock + 装 pytest；之后环境已就绪，直接进入测试

按步骤分别跑：

```bash
# 步骤 01：文件索引构建（code/01-filename-index.py）
uv run --with pytest pytest code/test/test_01_filename_index.py -v

# 步骤 02：OCR 验证（code/02-OCR-check.py）
uv run --with pytest pytest code/test/test_02_OCR_check.py -v

# 步骤 02：OCR 结果写入（code/02-write-OCR.py）
uv run --with pytest pytest code/test/test_02_write_OCR.py -v

# 步骤 03：临时 CSV 生成（code/03-tmp-csv.py）
uv run --with pytest pytest code/test/test_03_tmp_csv.py -v

# 步骤 03：特征提取结果写入（code/03-write-feature.py）
uv run --with pytest pytest code/test/test_03_write_feature.py -v

# 步骤 03：NLP 验证（code/03-NLP-check.py）
uv run --with pytest pytest code/test/test_03_NLP_check.py -v

# 步骤 04：数据合并（code/04-merge.py）
uv run --with pytest pytest code/test/test_04_merge.py -v
```

一键全跑：

```bash
uv run --with pytest pytest code/test/ -v
```

### 4.6 独立验证脚本

`code/test/verify_uncertain_json.py` 不在 pytest 套件内——它需要起真实子进程并发跑 `03-tmp-csv.py` 看文件系统的 read-modify-write 行为，pytest 的 `tmp_path` 隔离与单进程 fixture 不适合这个场景。脚本用 `tempfile.mkdtemp` 在 `/tmp` 起隔离目录，对仓库无副作用。

跑法：

```bash
uv run python code/test/verify_uncertain_json.py
```

输出形如：

```
[OK] 顶层是 dict,key=stem
[OK] 同 basename 二次 append 是 extend
[OK] 不同 basename 各占一 key
[OK] 写盘格式: 中文保留 / 2 空格缩进 / 末尾换行
[OK] 真并发 2 子进程: 文件仍是合法 dict,无丢失更新

=== 独立验证全部通过 ===
```

任一契约失败立即 `exit 1` 并把 `[FAIL] ...` 打印到 stderr。

适用场景：

- 修改 `03-tmp-csv.py` 的 `load_uncertain` / `append_uncertain` 后做一次端到端 sanity check
- 排查"为什么 `uncertain.json` 没出现 / 内容不对 / 并发写入丢数据"类问题
- 流水线整体跑完后做一次最终验证（不依赖 pytest fixture）

---


## 5. 故障排查

| 现象 | 可能原因 | 解决 |
|------|----------|------|
| `ModuleNotFoundError: No module named 'filelock'` | 没装依赖 / 用了非 venv 的 python | `uv pip install -r code/requirements.txt`，并确认命令走 `uv run python` |
| 行尾变 `\r\n` | 用普通 `open()` 替代了 `csv` 模块 | 检查脚本里是否有 `open(..., newline="")` 和 `lineterminator="\n"` |
| checklist 写入后中文乱码 | 文件被外部编辑器另存为 GBK | 始终用 UTF-8 打开/写入；不要用 Excel 直接保存 |
| 02 阶段 lock 超时 | 两个进程同时抢锁 / 死锁 | 检查 `.lock` 文件是否残留，必要时 `rm -f processed_data/names-checklist.csv.lock` |
