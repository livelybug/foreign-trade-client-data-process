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

## 1-checklist-check.py

### 功能描述

对 `01-filename-index.py` 生成的 checklist 批量执行 4 项校验：文件存在；表头为 `Filename,OCR,Feature Extract`；数据行数等于 raw 目录下 `.png` 文件数；第 1 个数据行的 Filename 等于 ASCII 排序后的第 1 个 `.png` 文件名（用 csv 标准解析取字段，支持含逗号的文件名）。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--checklist` | checklist CSV 文件路径（默认 `processed_data/names-checklist.csv`） | `processed_data/names-checklist.csv` |
| `--raw-dir` | 存放 PNG 图片的目录路径（默认 `raw_data`） | `raw_data` |

### 输出

- 逐项打印 `--- check N: ---` 与 `[OK]` / `[FAIL] ...`（FAIL 附带具体值便于定位）
- 全部通过：末行 `--- all 4 checks passed ---`，exit code 0
- 任一项失败：立即 exit code 1

### 错误处理

- checklist 缺失 / 表头不符 / 行数不符 / 顺序不符 → 打印 `[FAIL]` 并 exit code 1

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

## 2-txt-check.py

### 功能描述

OCR 调度轮内批量检查本轮 PNG 对应的 txt 是否满足契约：文件存在、大小 > 0、去除全部空白后非空。仅输出逐文件状态行供主 Agent 解析，不修改任何文件。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--txts-dir` | OCR 输出的 txt 文件目录（默认 `processed_data/txts`） | `processed_data/txts/` |
| `pngs`（位置参数，≥1 个） | 本调度轮的 PNG 文件名列表 | `"2011-08-12 1.png"` |

### 输出

- 每个文件一行：`[OK] <f>` 或 `[MISSING/EMPTY] <f>`（`.png` 后缀替换为 `.txt`，文件名其余部分原样保留）
- 恒 exit code 0（成功/失败由主 Agent 解析输出得出）

### 错误处理

- 无失败退出码；txt 缺失 / 空 / 只含空白 → 该文件报 `[MISSING/EMPTY]`

---

## 3-read-header.py

### 功能描述

读取字段表 CSV 第 1 行作为表头原文并打印，是第 3 步的全局唯一权威来源（后续由主 Agent 嵌入子 Agent 提示词的 `FIELD_HEADER` 代码块）。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--field-table` | 字段表 CSV 路径（默认 `raw_data/tg_features.csv`） | `raw_data/tg_features.csv` |

### 输出

- 成功：`[OK] hdr=<表头原文>`，exit code 0
- 失败：`[FAIL] ... 读取失败: ...` 或 `[FAIL] ... 表头为空`，exit code 1

### 错误处理

- 文件缺失 / 不可读 → 报错退出（exit code 1）
- 第 1 行为空 → 报错退出（exit code 1）

---

## 3-list-option-jsons.py

### 功能描述

按 ASCII 顺序枚举 `prompts/option_category/` 下全部 `.json` 并逐行打印路径，供人工确认文件集及其与 `OPTIONS_BLOCK` / `HIERARCHY_BLOCK` 的对应关系。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--dir` | option_category 目录路径（默认 `prompts/option_category`） | `prompts/option_category` |

### 输出

- 成功：每个 `.json` 一行路径（ASCII 排序），exit code 0
- 失败：`[FAIL] <dir> 下没有任何 .json`，exit code 1

### 错误处理

- 目录不存在或目录下没有任何 `.json` → 报错退出（exit code 1）

---

## 3-load-option-jsons.py

### 功能描述

按 `3-list-option-jsons.py` 枚举 + 人工确认后的文件清单，逐个校验 JSON 文件可读且非空（等价于原 shell 的 `cat` 到变量 + 非空校验）。文件内容本身仍由主 Agent 用 Read 工具读取后嵌入子 Agent 提示词。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--json`（可重复传，≥1 个） | 待校验的 JSON 文件路径 | `prompts/option_category/subdivision-options.json` |

### 输出

- 成功：`[OK] N json loaded`，exit code 0
- 失败：`[FAIL] <basename> 缺失或为空`，exit code 1

### 错误处理

- 任一文件缺失 / 为空 / 只含换行 / 解码失败 → 指名该文件报错退出（exit code 1）
- 未传 `--json` → argparse 报错退出（exit code 2）

---

## 03-tmp-csv.py

### 功能描述

为单个 OCR 文本生成结构化临时 CSV。从字段表中读取表头行，结合 NLP 子 Agent 提取的字段值，输出 2 行（表头 + 数据）的临时 CSV 文件。并在写入后执行判定契约检验。契约通过后，若 `--uncertain` 提供了非空 JSON 数组，则以 filelock 排他锁将"不确定"清单按 `--txt` 文件名分组追加写入 `--uncertain-path`（默认 `uncertain.json`），顶层结构为 `{<basename>: [<item>, ...]}`，供后续人工 review。

### 输入参数

| 参数 | 含义 | 示例值 |
|------|------|--------|
| `--txt` | OCR 文本文件的路径（脚本内部读取） | `processed_data/txts/2011-08-12 1.txt` |
| `--field-table` | 字段表 CSV 路径（脚本读取其第一行作为表头） | `raw_data/tg_features.csv` |
| `--values` | 逗号分隔的提取字段值 | `"ACME Corp,USA,分销商,,..."` |
| `--output` | 输出的临时 CSV 文件路径 | `processed_data/csvs/2011-08-12 1.csv` |
| `--uncertain` | JSON 数组字符串，每项描述一个"不确定"点；空串或 `[]` 表示无 | `'[{"field":"价格敏感度","question":"期望是高/中/低 还是 高敏感?","options":["高/中/低","高敏感"]}]'` |
| `--uncertain-path` | 不确定清单的追加目标文件路径 | `uncertain.json`（默认，结构 `{basename: [items...]}`） |

### 输出

- **文件**：`--output` 指定的临时 CSV
- **格式**：第 1 行为 `--field-table` 的表头行，第 2 行为 `--values` 的数据
- **编码**：UTF-8（无 BOM），行尾 `\n`
- **附加输出**（仅当 `--uncertain` 非空 JSON 数组时）：`--uncertain-path`（默认 `uncertain.json`）以"读-改-写"方式更新顶层 dict；新增的 items 追加到 `--txt` 的 stem（去 `.txt`）对应键的 list 末尾；不存在该键则新建。

### 判定契约检验（写入后自动执行）

1. 输出文件存在
2. 共 2 行（表头 + 数据）
3. 表头列数 == 字段表列数（逐列完全一致）
4. 数据行列数 == 表头列数

全部通过 → exit code 0；任一不通过 → exit code 1，输出具体失败原因。

### 不确定清单追加（契约通过后自动执行）

- **触发条件**：`--uncertain` 经 `validate_uncertain` 校验后得到非空 `list[dict]`。空串、`"[]"` 或校验失败均不进入追加流程。
- **时机**：在 `verify_contract` 之后执行；契约失败（exit 1）时本段不执行，避免基于错误数据记录问题。
- **并发安全**：使用 `filelock.FileLock` 排他锁，锁文件位于 `<uncertain-path>.lock`（例如 `uncertain.json.lock`），与 `02-write-OCR.py` / `03-write-feature.py` 风格一致；`timeout=10s`，超时 → exit 1。
- **数据结构**：顶层是 `dict`，key 是 `--txt` 的 stem（去 `.txt`），value 是 `list[dict]`。每个 item 形如：

  - 必填字段：`field`（非空 str）、`question`（非空 str）
  - 可选字段：`options`（`list[str]`）、`value`（str）

  写回时使用 `indent=2`、`ensure_ascii=False`，便于人工 review；末尾保留 1 个 `\n`。

  示例（`--txt` = `2011-08-12 1.txt`，`--uncertain` 含两条，且与 `2011-08-12 2` 共享同一 `uncertain.json`）：

  ```json
  {
    "2011-08-12 1": [
      {
        "field": "价格敏感度",
        "question": "期望是高/中/低 还是 高敏感?",
        "options": ["高/中/低", "高敏感"]
      },
      {
        "field": "电话",
        "question": "多个电话选哪个?",
        "value": "+1-555-0100; +1-555-0200"
      }
    ],
    "2011-08-12 2": [
      {
        "field": "客户阶段",
        "question": "阶段定义?",
        "value": "初始"
      }
    ]
  }
  ```

- **更新规则**：
  - 文件不存在 → 写入 `{basename: items}`；
  - 文件存在但目标键不存在 → 新增该键，值取本次 items；
  - 文件存在且目标键已是 `list` → 追加（`list.extend`）；
  - 文件存在但目标键不是 `list` → 报错退出（防止覆盖/破坏既有数据）；
  - 顶层非 `dict`（例如人为写入 JSON 数组）→ 报错退出；
  - 父目录不存在则自动创建（`parents=True, exist_ok=True`）。

### 错误处理

- `--txt` 或 `--field-table` 不存在 → 报错退出
- `--values` 的字段数与表头列数不匹配 → 报错退出
- 输出目录无法创建或文件无法写入 → 报错退出
- 判定契约检验失败 → 报错退出（exit code 1）
- `--uncertain` JSON 解析失败或非 list 类型 → 报错退出（exit code 1）
- `--uncertain` 元素缺 `field` / `question` 必填字段，或 `options` / `value` 类型不正确 → 报错退出（exit code 1）
- filelock 获取超时（`Timeout`）或追加时 `OSError` → 报错退出（exit code 1）

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
