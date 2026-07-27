**任务目标**：将 `raw_data/` 目录下所有 PNG 图片中的外贸客户名片/文档信息，经过 OCR 识别和语义理解，最终整理为一份标准的 CSV 表格。

### 脚本文档清单

| 脚本文件 | 说明文档 |
| --- | --- |
| `code/01-filename-index.py` | [文件索引构建](code/py-doc.md#01-filename-indexpy) |
| `code/02-write-OCR.py` | [OCR 结果写入](code/py-doc.md#02-write-ocrpy) |
| `code/02-OCR-check.py` | [OCR 验证](code/py-doc.md#02-ocr-checkpy) |
| `code/03-tmp-csv.py` | [临时 CSV 生成](code/py-doc.md#03-tmp-csvpy) |
| `code/03-write-feature.py` | [特征提取结果写入](code/py-doc.md#03-write-featurepy) |
| `code/03-NLP-check.py` | [NLP 验证](code/py-doc.md#03-nlp-checkpy) |
| `code/04-merge.py` | [数据合并](code/py-doc.md#04-mergepy) |

## 通用约定（所有步骤均适用）

- **路径基准**：所有相对路径均相对于本仓库根目录。
- **目录约定**：
    - 输入图片固定位于 `raw_data/`，只扫描此目录下的 `*.png`。
    - 中间产物位于 `processed_data/`。
- **文件名约定**：
    - 禁止子 Agent 修改任何文件名（不去空格、不转小写、不做去重、不做编码转换），仅在写入新产物时替换扩展名。
    - 例：`2011-08-14 1.png` 对应的 txt 必须是 `2011-08-14 1.txt`（空格原样保留）。
- **CSV 格式约定**（适用于 `names-checklist.csv`、所有 `csvs/*.csv`、`final.csv`）：
    - 编码：UTF-8（无 BOM）。
    - 行尾：`\n`。
    - 字段分隔符：英文逗号 `,`。
    - 引号规则：值含逗号 / 双引号 / 换行时，整字段用双引号包裹，内部双引号转义为 `""`。
    - 缺值字段：留空（连续两个逗号，或行首/行末的逗号），**不写 `null`、`N/A`、`-`、`<empty>` 等任何字面值**。

## 第一步：文件索引构建

- **动作**：
    0. 幂等检查：若 `processed_data/names-checklist.csv` 已存在且非空，跳过本步直接进入第二步。
    1. 创建中间目录（如不存在）：`processed_data/`、`processed_data/txts/`、`processed_data/csvs/`。
    2. 扫描 `raw_data/`，筛选出所有后缀为 `.png` 的文件。
    3. 将文件名按 **ASCII 顺序**排序，生成待处理文件列表 checklist，存储为 `processed_data/names-checklist.csv`。
- **`names-checklist.csv` 样例**（`Filename` 列必须含完整文件名，含 `.png` 扩展名；列名严格如下表）：

    | Filename | OCR | Feature Extract |
    | --- | --- | --- |
    | 2011-08-12 1.png |  |  |
    | 2011-08-12 2.png |  |  |
    | 2011-08-14 1.png |  |  |
    | 2011-08-14 2.png |  |  |

- **本步验证**：
    - `names-checklist.csv` 真实反映 `raw_data/*.png` 的文件集合（无遗漏、无多出）。

- **执行**：
    - 本步需求相应的python存放于`code/01-filename-index.py`
    - 主agent执行python文件

## 第二步：OCR 文字提取（并行处理，最大并行=6）

- **主 Agent 调度 OCR 子 Agent**，针对 checklist 中每个文件启动一个独立实例。
- **输入**：单个 PNG 图片文件。
- **子 Agent 动作**：
    1. 仅做 OCR 文字识别，**按行输出、保留视觉阅读顺序**。
    2. 除识别出的文字外，不输出任何其他内容。
- **子 Agent 输出**：
    - 成功后：将提取的纯文本保存为 `processed_data/txts/<原文件名>.txt`（仅替换扩展名，文件名其他部分原样保留）。
    - 失败后：不写任何文件。
- **判定契约**（OCR 子 Agent 任务**满足全部**条件视为成功，记为 `1`）：
    - `processed_data/txts/<原文件名>.txt` 存在；
    - 文件大小 > 0；
    - 去除首尾空白后仍含可见字符（非空字符串）。
- **重试**：失败时主 Agent 等待 3 秒后启动新的子 Agent 实例重试，共重试三次；仍失败则记 `0`。
- **主 Agent 写入 checklist**：`names-checklist.csv` → OCR 列填入 `1` 或 `0`。
- **所有文件处理结束后的验证**：
    - `names-checklist.csv` → OCR 列每一行都已填入 `0` 或 `1`。
    - 筛选 OCR=1 的行，核对 `processed_data/txts/` 下 txt 文件个数与文件名一一对应。

- **执行**：
    - 本步OCR相关部分由agent执行，其余调python执行，见以下。
    - 主 Agent 写入 checklist使用对应的python文件：`code/02-write-OCR.py`。写入时使用 `filelock` 库对 `names-checklist.csv` 加排他锁，避免并发写入冲突。
    - **所有文件处理结束后的验证** 使用对应的python文件：`code/02-OCR-check.py`

## 第三步：关键信息抽取与结构化（并行处理，最大并行=6）

- **主 Agent 调度 NLP 子 Agent**，针对 OCR 成功的每个 TXT 文件启动一个独立实例。
- **输入**：单个 TXT 文件（`processed_data/txts/<原文件名>.txt`）；字段表 `raw_data/1.client_features.csv` 的**表头行**（即第一行，作为输出列名）。
- **子 Agent 动作**：
    1. 阅读文本内容，基于语义理解提取关键字段。
    2. 严格按字段表的列顺序与列名输出，**不要对列做任何改动**。
    3. **提取规则**：
        - 若某字段在文本中未找到，**留空**（连续逗号），**不写 `null`、`N/A`、`-`、`<empty>` 等任何字面值，也不编造**。
        - 若有任何不确定，比如：
          - 没给字段示例（如 "价格敏感度" 期望 "高/中/低" 还是 "高敏感"？）
          - 没给映射规则（电话是手机还是座机？多个电话怎么办？）
          都写入`uncertain.md`

- **子 Agent 输出**：
    - 为避免并发写入冲突，每个子 Agent 生成一个独立的临时 CSV 文件（`processed_data/csvs/<原文件名>.csv`，仅替换扩展名，文件名其他部分原样保留）。
    - 文件格式：第 1 行为字段表表头，第 2 行为提取的数据。
- **判定契约**（NLP 子 Agent 任务**满足全部**条件视为成功，记为 `1`）：
    - `processed_data/csvs/<原文件名>.csv` 存在；
    - 共 2 行（第 1 行表头 + 第 1 行数据）；
    - 表头列数 == 字段表列数（逐列完全一致，包括列名、列顺序、列分隔符样式）；
    - 数据行列数 == 表头列数。
- **重试**：判定失败时主 Agent 等待 3 秒后启动新的子 Agent 实例重试，共重试三次；仍失败则记 `0`。
- **主 Agent 写入 checklist**：`names-checklist.csv` → Feature Extract 列填入 `1` 或 `0`。
- **所有文件处理结束后的验证**：
    - `names-checklist.csv` → Feature Extract 列每一行都已填入 `0` 或 `1`。
    - 筛选 Feature Extract=1 的行，核对 `processed_data/csvs/` 下 csv 文件个数与文件名一一对应。

- **执行**：
    - 本步相关部分由agent执行，其余调python执行，见以下。
    - 子 Agent 调用python生成独立的临时 CSV 文件，并在同一脚本中完成判定契约检验：`code/03-tmp-csv.py`
    - 主 Agent 写入 checklist使用对应的python文件：`code/03-write-feature.py`。写入时使用 `filelock` 库对 `names-checklist.csv` 加排他锁，避免并发写入冲突。
    - **所有文件处理结束后的验证** 使用对应的python文件：`code/03-NLP-check.py`

## 第四步：数据合并（最终汇总）

- **动作**：
    0. 等待所有 NLP 子 Agent 完成任务。
    1. 若 `processed_data/final.csv` 已存在， 删除。
    2. **按 `names-checklist.csv` 中的行序**依次读取 `Feature Extract=1` 的行所对应的临时 CSV 文件。
    3. 将它们合并为 `processed_data/final.csv`。
    4. **去重表头**：仅保留第一个临时 CSV 文件的表头作为 `final.csv` 的表头；其余临时 CSV 的表头行需丢弃。
    5. Feature Extract=0 的行不进入 final.csv。
- **本步结束时的验证**：
    - `final.csv` 总行数 = checklist 中 `Feature Extract=1` 的行数。
    - 每一行（不含表头）的列数 == 表头列数。
    - 不存在重复的表头行。

- **执行**：
    - 等待所有 NLP 子 Agent 完成任务后，调python执行其余部分：`code/04-merge.py`