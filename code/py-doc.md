# Python 脚本说明

---

## 01-filename-index.py

### 功能描述

扫描 `raw_data/` 目录下所有 `.png` 文件，按 ASCII 顺序排序，生成待处理文件清单 CSV。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--raw-dir` | 存放 PNG 图片的目录路径 | `raw_data/` |
| `--output` | 输出的 checklist CSV 文件路径 | `processed_data/names-checklist.csv` |

### 输出

- **文件**：`processed_data/names-checklist.csv`
- **格式**：UTF-8 编码，三列 `Filename,OCR,Feature Extract`，OCR 和 Feature Extract 列初始为空
- **行数**：1 行表头 + N 行数据（N = PNG 文件数量）

### 错误处理

- `--raw-dir` 不存在或无 `.png` 文件 → 报错退出（exit code 1）
- 无法创建输出目录或写入文件 → 报错退出（exit code 1）

---

## 02-write-OCR.py

### 功能描述

将单个文件的 OCR 处理结果（成功=1，失败=0）写入 `names-checklist.csv` 的 `OCR` 列。使用 `filelock` 加排他锁，避免并行写入冲突。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--checklist` | checklist CSV 文件路径 | `processed_data/names-checklist.csv` |
| `--filename` | 单个 PNG 文件名（精确匹配） | `2011-08-12 1.png` |
| `--status` | OCR 结果：`1`（成功）或 `0`（失败） | `1` |

### 输出

- 修改 `--checklist` 文件中对应行的 `OCR` 列值为 `--status`
- 无新文件产生

### 错误处理

- `--filename` 在 checklist 中找不到 → 报错退出（exit code 1）
- `--status` 不是 `0` 或 `1` → 报错退出（exit code 1）
- 文件被其他进程锁定时等待，超时后报错退出

---

## 02-OCR-check.py

### 功能描述

在所有 OCR 子 Agent 完成后，验证 checklist 的 OCR 列完整性和 txt 文件一致性。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--checklist` | checklist CSV 文件路径 | `processed_data/names-checklist.csv` |
| `--txts-dir` | OCR 输出的 txt 文件目录 | `processed_data/txts/` |

### 验证规则

1. checklist 中每一行的 `OCR` 列必须为 `0` 或 `1`（不得有空值）
2. OCR=1 的行对应的 txt 文件必须在 `--txts-dir` 中存在、大小 > 0、去除空白后含可见字符
3. OCR=1 的行数与符合条件的 txt 文件数必须一一对应

### 输出

- 验证通过：标准输出打印成功信息，exit code 0
- 验证失败：标准输出打印具体不匹配项，exit code 1

### 错误处理

- checklist 或 txts 目录不存在 → 报错退出（exit code 1）
- 任何验证不通过 → 退出码 1，输出详细差异

---

## 03-tmp-csv.py

### 功能描述

为单个 OCR 文本生成结构化临时 CSV。从字段表中读取表头行，结合 NLP 子 Agent 提取的字段值，输出 2 行（表头 + 数据）的临时 CSV 文件。并在写入后执行判定契约检验。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--txt` | OCR 文本文件的路径（脚本内部读取） | `processed_data/txts/2011-08-12 1.txt` |
| `--field-table` | 字段表 CSV 路径（脚本读取其第一行作为表头） | `raw_data/1.client_features.csv` |
| `--values` | 逗号分隔的提取字段值 | `"ACME Corp,USA,分销商,,..."` |
| `--output` | 输出的临时 CSV 文件路径 | `processed_data/csvs/2011-08-12 1.csv` |

### 输出

- **文件**：`--output` 指定的临时 CSV
- **格式**：第 1 行为 `--field-table` 的表头行，第 2 行为 `--values` 的数据
- **编码**：UTF-8（无 BOM），行尾 `\n`

### 判定契约检验（写入后自动执行）

1. 输出文件存在
2. 共 2 行（表头 + 数据）
3. 表头列数 == 字段表列数（逐列完全一致）
4. 数据行列数 == 表头列数

全部通过 → exit code 0；任一不通过 → exit code 1，输出具体失败原因。

### 错误处理

- `--txt` 或 `--field-table` 不存在 → 报错退出
- `--values` 的字段数与表头列数不匹配 → 报错退出
- 输出目录无法创建或文件无法写入 → 报错退出
- 判定契约检验失败 → 报错退出（exit code 1）

---

## 03-write-feature.py

### 功能描述

将单个文件的 NLP 特征提取结果（成功=1，失败=0）写入 `names-checklist.csv` 的 `Feature Extract` 列。使用 `filelock` 加排他锁，避免并行写入冲突。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--checklist` | checklist CSV 文件路径 | `processed_data/names-checklist.csv` |
| `--filename` | 单个 PNG 文件名（精确匹配） | `2011-08-12 1.png` |
| `--status` | 特征提取结果：`1`（成功）或 `0`（失败） | `1` |

### 输出

- 修改 `--checklist` 文件中对应行的 `Feature Extract` 列值为 `--status`
- 无新文件产生

### 错误处理

- `--filename` 在 checklist 中找不到 → 报错退出（exit code 1）
- `--status` 不是 `0` 或 `1` → 报错退出（exit code 1）
- 文件被其他进程锁定时等待，超时后报错退出

---

## 03-NLP-check.py

### 功能描述

在所有 NLP 子 Agent 完成后，验证 checklist 的 Feature Extract 列完整性和临时 CSV 文件一致性。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--checklist` | checklist CSV 文件路径 | `processed_data/names-checklist.csv` |
| `--csvs-dir` | 临时 CSV 文件目录 | `processed_data/csvs/` |

### 验证规则

1. checklist 中每一行的 `Feature Extract` 列必须为 `0` 或 `1`（不得有空值）
2. Feature Extract=1 的行对应的临时 CSV 文件必须在 `--csvs-dir` 中存在
3. Feature Extract=1 的行数与符合条件的 CSV 文件数必须一一对应

### 输出

- 验证通过：标准输出打印成功信息，exit code 0
- 验证失败：标准输出打印具体不匹配项，exit code 1

### 错误处理

- checklist 或 csvs 目录不存在 → 报错退出（exit code 1）
- 任何验证不通过 → 退出码 1，输出详细差异

---

## 04-merge.py

### 功能描述

将所有 Feature Extract=1 的临时 CSV 文件按 checklist 行序合并为最终汇总文件 `final.csv`。仅保留第一个文件的表头，去重后续文件的表头行。Feature Extract=0 的行不进入最终输出。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--checklist` | checklist CSV 文件路径 | `processed_data/names-checklist.csv` |
| `--csvs-dir` | 临时 CSV 文件目录 | `processed_data/csvs/` |
| `--output` | 最终汇总 CSV 文件路径 | `processed_data/final.csv` |

### 输出

- **文件**：`--output` 指定的最终 CSV
- **行数**：1 行表头 + M 行数据（M = Feature Extract=1 的行数）
- **顺序**：按 checklist 中的行序排列
- **编码**：UTF-8（无 BOM），行尾 `\n`

### 合并后验证

1. `final.csv` 数据行数 == checklist 中 Feature Extract=1 的行数
2. 每一数据行的列数 == 表头列数
3. 不存在重复的表头行

### 错误处理

- checklist 或 csvs 目录不存在 → 报错退出
- `--output` 已存在 → 删除后重建
- Feature Extract=1 的行对应的临时 CSV 文件缺失 → 报错退出
- 合并后验证不通过 → 报错退出（exit code 1）
