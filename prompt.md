**任务目标**：将目录下所有 PNG 图片中的外贸客户名片/文档信息，经过 OCR 识别和语义理解，最终整理为一份标准的 CSV 表格。

**执行步骤**：

**第一步：文件索引构建**

- **动作**：
    1. 扫描当前工作目录，筛选出所有后缀为 `.png` 的文件。
    2. 将文件名按照**ASCII顺序**进行排序，生成一个待处理文件列表checklist table，存储为processed_data/names-checklist.csv。
        
        names-checklist.csv 样例：
        
        | Filename | OCR | Feature Extract |
        | --- | --- | --- |
        | NAME1 |  |  |
        | NAME2 |  |  |

**第二步：OCR 文字提取（并行处理， 最大并行=6）**

- 主Agent调度OCR 子 Agent（针对列表中的每个文件启动一个独立实例）
- **输入**：单个 PNG 图片文件
- **动作**：
    1. 使用（OCR）仅提取图片中的文字内容。
    2. 保留原始排版。
    3. 除原始文字外，不输出任何其他内容！
    4. 结果：
        - 成功后：将提取的纯文本保存为 `.txt` 文件。与原图片文件名一致，后缀改为 `.txt`。存放在`processed_data/txts`
        - 结果记录 names-checklist.csv → OCR 那一列,：1成功，0失败
- **所有文件处理结束后的验证**：
    - 确保names-checklist.csv → OCR 那一列的每一行都有填入0或1；
    - 根据names-checklist.csv → OCR 那一列数值为1的那几行,核对txt文件个数与文件名，确保匹配

**第三步：关键信息抽取与结构化（并行处理，最大并行=6）**

- 主Agent调度 NLP 子 Agent（针对列表中的每个 TXT 文件启动一个独立实例）
- **输入**：单个 TXT 文件（原文件名.txt）； `raw_data/1.client_features.csv`
- **动作**：
    1. 阅读文本内容，基于语义理解提取关键字段。关键字段为 `1.client_features.csv` 的第一行。请严格对应提取。
    2. **提取规则**：
        - 若某字段在文本中未找到，请填入 `null；` ，不要编造。
    3. **输出**：
        - 为了避免并发写入冲突，请每个 Agent 生成一个独立的临时 CSV 文件（`原文件名.csv`），存储于`processed_data/csvs`。
        - 文件格式：第一行为上述字段的表头，第二行为提取的数据。
        - 结果记录 names-checklist.csv → `Feature Extract` 那一列,：1成功，0失败
- **所有文件处理结束后的验证**：
    - 确保names-checklist.csv → `Feature Extract` 那一列的每一行都有填入0或1
    - 根据names-checklist.csv → `Feature Extract` 那一列数值为1的那几行,核对csv文件个数与文件名，确保匹配


**第四步：数据合并（最终汇总）**

- **动作**：
    1. 等待所有子 Agent 完成任务。
    2. 根据文件名按照**ASCII顺序依次**读取所有生成的临时 CSV 文件。
    3. 将它们合并为一个最终的 `processed_data/final.csv`。
    4. **注意**：确保最终文件中只保留第一行的表头，删除中间合并产生的重复表头。