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
- **并发配置**（`pipeline.config.json`，启动相关步骤前用 Read 工具确认）：
    - `max_concurrency`（默认 6）：主 Agent 一次性派发的子 Agent 数。
    - `ocr_batch_size`（默认 10）：每个 OCR 子 Agent 一次最多串行处理的 PNG 数。
    - `nlp_batch_size`（默认 10）：每个 NLP 子 Agent 一次最多串行处理的 TXT 数。

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

## 第二步：OCR 文字提取（并行处理）

- **并发配置**：`pipeline.config.json` 读取两个字段，开始本步前用 Read 工具确认：
    - `max_concurrency`（默认 6）：主 Agent 一次性派发的子 Agent 数（即同一 message 中 `Agent` 工具调用数）。
    - `ocr_batch_size`（默认 10）：每个子 Agent 一次最多串行处理的 PNG 数。
- **主 Agent 调度 OCR 子 Agent**：把目标清单按 `ocr_batch_size` 个一组分批；每一批派发一个子 Agent，最多并发`max_concurrency`个子 Agent ；每个子 Agent 内部对其批内 PNG **严格串行**处理（一对 `Read` + `Write` 一次只处理一张图，写完 txt 才进下一张）。
- **输入**：子 Agent 接收一个 PNG 文件名列表（长度 1–`ocr_batch_size`，按 checklist 行序）。
- **子 Agent 动作**（批内每张 PNG 都执行一遍，**严格串行**）：
    1. 用 Read 工具读取 `raw_data/<filename>.png`。
    2. 仅做 OCR 文字识别，**按行输出、保留视觉阅读顺序**；不要翻译、总结、推断、补全；识别不出的字符用 `?` 占位。
    3. 用 Write 工具把纯文本写入 `processed_data/txts/<filename>.txt`（仅替换扩展名，文件名其他部分原样保留）。
    4. 写完再处理下一张；批内某张失败不中断本批，**跳过失败文件、继续处理剩余文件**。
    5. 除上述外不要输出任何其他内容；不要修改任何文件名。
- **子 Agent 输出**：批内每张 PNG **按文件粒度**回执一行：
    - 成功 → `OK: <filename>`（同时 `processed_data/txts/<filename>.txt` 已存在且非空）。
    - 失败 → `FAIL: <filename>: <原因>`（不写任何文件）。
- **判定契约**（对批内每张 PNG **独立**判定，**满足全部**条件视为成功，记为 `1`）：
    - `processed_data/txts/<原文件名>.txt` 存在；
    - 文件大小 > 0；
    - 去除首尾空白后仍含可见字符（非空字符串）。
- **重试**（**单文件粒度**）：主 Agent 收集到本批失败文件清单后，等 3 秒，对**仅这些失败文件**按 `ocr_batch_size` 个一组重新装填成新批、重新派发子 Agent；同一文件累计重试最多 3 次；3 次仍失败记 `0`。
- **主 Agent 写入 checklist**：`names-checklist.csv` → OCR 列填入 `1` 或 `0`（按文件粒度逐行写）。
- **所有文件处理结束后的验证**：
    - `names-checklist.csv` → OCR 列每一行都已填入 `0` 或 `1`。
    - 筛选 OCR=1 的行，核对 `processed_data/txts/` 下 txt 文件个数与文件名一一对应。

- **执行**：
    - 本步OCR相关部分由agent执行，其余调python执行，见以下。
    - 主 Agent 写入 checklist使用对应的python文件：`code/02-write-OCR.py`。写入时使用 `filelock` 库对 `names-checklist.csv` 加排他锁，避免并发写入冲突。
    - **所有文件处理结束后的验证** 使用对应的python文件：`code/02-OCR-check.py`

## 第三步：关键信息抽取与结构化（并行处理）

- **并发配置**：`pipeline.config.json` 读取两个字段，开始本步前用 Read 工具确认：
    - `max_concurrency`（默认 6）：主 Agent 一次性派发的子 Agent 数（即同一 message 中 `Agent` 工具调用数）。
    - `nlp_batch_size`（默认 10）：每个子 Agent 一次最多串行处理的 TXT 数。
- **主 Agent 调度 NLP 子 Agent**：把目标清单按 `nlp_batch_size` 个一组分批；同一批内 `max_concurrency` 个子 Agent 并发派发；每个子 Agent 内部对其子批内 TXT **严格串行**处理（一个 txt 一对 `Read` + 调 `03-tmp-csv.py`，写完 csv 才进下一个）。
- **输入**：子 Agent 接收一个 TXT 文件名列表（长度 1–`nlp_batch_size`，按 checklist 行序）；**字段表 `raw_data/tg_features.csv` 的表头行（第一行）由主 Agent 注入**（列数不固定，以主 Agent 注入的内容为准；子 Agent **不要**再 Read `raw_data/tg_features.csv`）。
- **子 Agent 动作**（子批内每个 TXT 都执行一遍，**严格串行**）：
    1. 用 Read 工具读取 `processed_data/txts/<basename>.txt`。
    2. 基于注入的字段表头，**按列顺序与列名**抽取每个字段。
    3. **提取规则**：
        - **通用规则**：文本中能直接对应到的字段就填原文（去除多余空白）；找不到的字段**留空**（连续逗号），**不写 `null` / `N/A` / `-` / `<empty>` 等任何字面值，也不编造**。
        - **固定选项字段判定**（**禁止硬编码字段名**——`prompts/option_category/subdivision-options.json` 与 `prompts/option_category/option-hierarchy.json` 是项目级动态配置，因项目而异）：
            - **主 Agent** 在前置检查阶段用 Read 工具把 `subdivision-options.json`（记为 `OPTIONS_BLOCK`）与 `option-hierarchy.json`（记为 `HIERARCHY_BLOCK`）**整体读出**，在派发子批时分别注入到子 Agent 提示词对应的 `OPTIONS_BLOCK` / `HIERARCHY_BLOCK` 代码块（**子 Agent 不要再 Read 这两个 JSON**）。
            - **子 Agent** 从 `OPTIONS_BLOCK` 中取出**顶层 key 集合**作为本项目"固定选项字段"名单（记为 `FIXED_FIELDS`）。当前本项目示例（仅作参考，**以 `OPTIONS_BLOCK` 注入内容为准**）：`客户类型` / `客户阶段` / `客户来源` / `价格敏感度` / `采购意向` / `阿里买家身份`。
        - 对 `FIELD_HEADER` 中**与 `FIXED_FIELDS` 任一 key 严格同名**的字段，按"固定选项字段值抽取流程"处理：
            - 该字段值**只能**从 `OPTIONS_BLOCK` 中该 key 对应 `细分选项` 数组里挑一个原样填入，**禁止自由文本，禁止编造**。
            - 在 `HIERARCHY_BLOCK` 中找到该 key 节点，逐个 option 的 `evidence` 节点，把所有叶子字符串**扁平化**为一个搜索词集合；用 OCR 文本与该集合做语义匹配，命中的 option 即为该字段候选值。
            - **匹配结果处理**：
                - 命中 0 个 → 字段**留空**，并在 `uncertain` 数组追加一项：`{"field":"<字段名>","question":"未匹配到任何 option 的 evidence","options":[],"value":""}`
                - 命中 1 个 → 直接把该 option 的 `name` 填入该字段（**原样照抄 `OPTIONS_BLOCK` 中 `细分选项` 里的字符串，不要改大小写、不要省略括号内的英文别名**）。
                - 命中 ≥ 2 个 → 取文本中出现频率/突出度最高的一个 option 填值，并在 `uncertain` 数组追加一项：`{"field":"<字段名>","question":"文本同时匹配多个 option","options":["命中 1","命中 2",...],"value":"<当前填的>"}`
        - 对 `FIELD_HEADER` 中**不在 `FIXED_FIELDS` 内的**字段：按"通用规则"处理即可（**不要硬编码"非固定选项字段"列表**——以本项目 `OPTIONS_BLOCK` 的实际 key 集合为准）。
        - 字段值含 `,` / `"` / 换行时，整个字段值用双引号包裹，内部 `"` 写成 `""`。
    4. 整理出两个字符串：
        - **values**：所有字段值按表头列顺序拼成**单行 CSV 字符串**（用 csv 标准转义，可含逗号）。
        - **uncertain**（可选）：若有不确定点（无字段示例、无映射规则、多值歧义等），整理为 JSON 数组字符串，每项形如 `{"field":"<字段名>","question":"<你的疑问>","options":["候选1","候选2"],"value":"<你当前填的值>"}`；无不确定则传空串。
    5. 调 `code/03-tmp-csv.py`（**必须走 `uv run`**，脚本内已含契约检验 + 自动追加 `uncertain.md`）：
        ```
        uv run python code/03-tmp-csv.py \
          --txt "processed_data/txts/<basename>.txt" \
          --field-table raw_data/tg_features.csv \
          --values "<values 字符串>" \
          --output "processed_data/csvs/<basename>.csv" \
          --uncertain "<JSON 数组字符串 或 空>"
        ```
        脚本 exit 0 → 本 txt 成功；非 0 → 本 txt 失败。
    6. 处理完一个 txt 再处理下一个；子批内某 txt 失败不中断本子批，**跳过失败文件、继续处理剩余文件**。
    7. 除上述外不要输出任何其他内容；不要修改任何文件名。
- **子 Agent 输出**：子批内每个 TXT **按文件粒度**回执一行：
    - 成功 → `OK: <basename>.txt`（同时 `processed_data/csvs/<basename>.csv` 已存在且通过 4 条契约）。
    - 失败 → `FAIL: <basename>.txt: <原因>`（不写 csv、不追加 uncertain）。
- **判定契约**（对子批内每个 TXT **独立**判定，**满足全部**条件视为成功，记为 `1`）：
    - `processed_data/csvs/<原文件名>.csv` 存在；
    - 共 2 行（第 1 行表头 + 第 1 行数据）；
    - 表头列数 == 字段表列数（逐列完全一致，包括列名、列顺序、列分隔符样式）；
    - 数据行列数 == 表头列数。
- **重试**（**单文件粒度**）：主 Agent 收集到本调度轮失败 TXT 清单后，等 3 秒，对**仅这些失败 TXT** 按 `nlp_batch_size` 个一组重新装填成新子批、重新派发子 Agent；同一文件累计重试最多 3 次；3 次仍失败记 `0`。
- **主 Agent 写入 checklist**：`names-checklist.csv` → Feature Extract 列填入 `1` 或 `0`（按文件粒度逐行写）。
- **所有文件处理结束后的验证**：
    - `names-checklist.csv` → Feature Extract 列每一行都已填入 `0` 或 `1`。
    - 筛选 Feature Extract=1 的行，核对 `processed_data/csvs/` 下 csv 文件个数与文件名一一对应。

- **执行**：
    - 本步NLP相关部分由agent执行，其余调python执行，见以下。
    - 子 Agent提取关键字段成功，调用python生成独立的临时 CSV 文件，并在同一脚本中完成判定契约检验；若有任何不确定都写入`uncertain.md`：`code/03-tmp-csv.py`（脚本已用 filelock 保护 `uncertain.md` 的追加写，子 Agent 串行调多次安全追加）。
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