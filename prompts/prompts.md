# 外贸客户名片 OCR 流水线 — 4 步提示词

> 本文件包含将 `raw_data/*.png` 经 OCR + 信息抽取后汇总为标准 CSV 表格的 4 个步骤提示词。
> 每个提示词都是自包含的，可直接复制到独立的 Claude Code 会话中使用。
>
> 流水线总览：
> - **第 1 步** — 扫描 `raw_data/*.png` 生成 `processed_data/names-checklist.csv`
> - **第 2 步** — 对每张图调度 OCR 子 Agent，写出对应 .txt，更新 checklist 的 OCR 列
> - **第 3 步** — 对每个 txt 调度 NLP 子 Agent，写出对应临时 csv，更新 checklist 的 Feature Extract 列
> - **第 4 步** — 按 checklist 顺序合并所有临时 csv 为 `processed_data/final.csv`

---

## 提示词 1️⃣ — 第一步：文件索引构建

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
仓库根目录就是当前工作目录，所有相对路径都基于此根目录。

整个流水线的目标：把 `raw_data/` 下的所有 PNG 图片，最终汇总成一份标准 CSV 表格。

**流水线总览**：
- 第 1 步（本步）：扫描 `raw_data/*.png` 生成 `processed_data/names-checklist.csv`
- 第 2 步：对每张图调度 OCR 子 Agent，写出对应 .txt，更新 checklist 的 OCR 列
- 第 3 步：对每个 txt 调度 NLP 子 Agent，写出对应临时 csv，更新 checklist 的 Feature Extract 列
- 第 4 步：按 checklist 顺序合并所有临时 csv 为 `processed_data/final.csv`

# 本步目标
生成 `processed_data/names-checklist.csv`，作为后续 3 步的"调度总表"。

# 前置检查（幂等性）
先检查 `processed_data/names-checklist.csv`：
- 若已存在且非空 → **直接结束本步**，报告"checklist 已存在，跳过本步"，不要重新生成。
- 若不存在或为空 → 继续。

# 执行步骤
1. 创建中间目录（若不存在）：
   - `processed_data/`
   - `processed_data/txts/`
   - `processed_data/csvs/`
2. 执行 `code/01-filename-index.py`：
   ```bash
   python code/01-filename-index.py \
     --raw-dir raw_data \
     --output processed_data/names-checklist.csv
   ```
3. 验证：
   - `processed_data/names-checklist.csv` 已生成
   - 第 1 行表头为 `Filename,OCR,Feature Extract`（3 列，UTF-8 无 BOM）
   - 每一行第 1 列是 `raw_data/*.png` 的某个文件名（含 `.png`），按 ASCII 顺序排列
   - 行数 == `raw_data/*.png` 的文件数

# 通用约定（务必遵守）
- 不要修改任何文件名（不去空格、不转小写、不做去重、不做编码转换）。
- CSV 编码 UTF-8（无 BOM），行尾 `\n`，分隔符 `,`。

# 完成后输出
简明告知：
- 生成的 checklist 行数（不含表头）
- 抽样前 3 行确认表头与数据格式
- 三个中间目录的最终路径
````

---

## 提示词 2️⃣ — 第二步：OCR 文字提取（并行 6）

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
当前执行 **第 2 步：OCR 文字提取**。
仓库根目录就是当前工作目录。

# 本步目标
对 `processed_data/names-checklist.csv` 中 OCR 列仍为空的每一行：
1. 调度一个 OCR 子 Agent（Claude 子实例）处理对应的 PNG。
2. 子 Agent 用视觉识别读图、输出按视觉阅读顺序的纯文本。
3. 子 Agent 用 Write 工具把文本写为 `processed_data/txts/<原文件名>.txt`。
4. 成功后用 `code/02-write-OCR.py` 把该行 OCR 列填为 `1`；失败填 `0`。
5. 全部完成后用 `code/02-OCR-check.py` 验证。

# 前置检查
1. `processed_data/names-checklist.csv` 必须存在（来自第 1 步）。
2. 读出 checklist 中所有 **OCR 列为空** 的 PNG 文件名，得到目标清单。
3. 如果目标清单为空，直接跳到"全量验证"。

# 子 Agent 提示词模板
每个待处理的 PNG 都启动一个子 Agent 实例。把下面整段发给它（`{filename}` 替换成实际文件名）：

---
你是 OCR 子 Agent。当前待处理的 PNG 文件是 `raw_data/{filename}`。

请严格按下列步骤执行：
1. 用 Read 工具读取该 PNG。Claude 的视觉能力会告诉你图中文字。
2. 按视觉阅读顺序逐行输出识别出的文字（保留原始换行；不要翻译、总结、推断、补全）。
3. 识别不出的字符用合理占位（如 `?`），不要编造。
4. 用 Write 工具，把识别出的纯文本写入 `processed_data/txts/<同名.txt>`。
   - 路径规则：把 `{filename}` 的扩展名 `.png` 替换为 `.txt`，其它部分原样保留（含空格）。
   - 例：`2011-08-14 1.png` → `processed_data/txts/2011-08-14 1.txt`
5. 除上述外，不要输出任何其他内容；不要修改任何文件名。

完成后用一句话回执：
- 成功 → `OK: processed_data/txts/<同名.txt>`
- 失败 → `FAIL: <原因>`
---

# 主 Agent 调度流程
1. 把目标清单按 **6 个一组** 分批。
2. 每批并发派发 6 个 OCR 子 Agent（同一批 6 个子 Agent 同时启动）。
3. 收集每个子 Agent 的回执：
   - **成功**（txt 文件存在且非空且 strip 后非空）→ 调用：
     ```bash
     python code/02-write-OCR.py \
       --checklist processed_data/names-checklist.csv \
       --filename "<PNG文件名>" \
       --status 1
     ```
   - **失败** → 等 3 秒后重新派发新的子 Agent 实例（用同一份提示词）；最多重试 3 次；3 次仍失败记 0：
     ```bash
     python code/02-write-OCR.py \
       --checklist processed_data/names-checklist.csv \
       --filename "<PNG文件名>" \
       --status 0
     ```
4. 全部处理完后，调用 `code/02-OCR-check.py` 验证：
   ```bash
   python code/02-OCR-check.py \
     --checklist processed_data/names-checklist.csv \
     --txts-dir processed_data/txts/
   ```
   验证 exit 0 即视为通过；否则打印所有错误信息并停下来报告。

# 通用约定（务必遵守）
- 不要修改任何文件名（含空格原样保留）。
- 不要用 Bash 跑 OCR 工具。OCR 只通过 Read 工具 + Claude 视觉。
- 子 Agent 并发上限 = 6；超过请分批。
- 写 checklist 必须用 `code/02-write-OCR.py`（内部有 filelock）；不要直接修改 CSV。

# 完成后输出
简明告知：
- 处理的 PNG 总数
- OCR=1 成功数 / OCR=0 失败数
- `02-OCR-check.py` 的验证结果
- 若有失败，列出对应的 PNG 文件名
````

---

## 提示词 3️⃣ — 第三步：关键信息抽取与结构化（并行 6）

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
当前执行 **第 3 步：关键信息抽取与结构化**。
仓库根目录就是当前工作目录。

# 本步目标
对 checklist 中 `OCR=1` 且 `Feature Extract` 仍为空的每一行：
1. 调度一个 NLP 子 Agent，读取对应的 `processed_data/txts/<原文件名>.txt`。
2. 子 Agent 基于语义抽取关键字段。
3. 子 Agent 调用 `code/03-tmp-csv.py` 把抽取结果写入 `processed_data/csvs/<原文件名>.csv`（脚本内已含契约验证）。
4. 成功后用 `code/03-write-feature.py` 把 Feature Extract 列填为 `1`；失败填 `0`。
5. 全部完成后用 `code/03-NLP-check.py` 验证。

# 前置检查
1. 读 `raw_data/tg_features.csv` 第 1 行（表头），作为输出列名。**禁止增删改列**。
   当前字段表头（14 列，固定不变）：
   `公司名称,国家,客户类型,客户阶段,客户来源,公司网址,联系人姓名,电话,邮箱,感兴趣产品,价格敏感度,采购意向,阿里买家身份,跟进记录`
2. 读 checklist 中所有 `OCR=1` 且 `Feature Extract` 为空的行，得到目标清单。
3. 如果目标清单为空，跳到"全量验证"。
4. 并发池上限 = 6。

# 子 Agent 提示词模板
每个目标 txt 启动一个子 Agent 实例。把下面整段发给它（`{basename}` 替换成对应 txt 的 basename，不含扩展名）：

---
你是 NLP 子 Agent，负责把一份 OCR 文本抽取为结构化字段。

**输入**：
- 文本：`processed_data/txts/{basename}.txt`
- 字段表：`raw_data/tg_features.csv`（取第 1 行作表头，14 列固定不变）

**输出**：
- CSV：`processed_data/csvs/{basename}.csv`（仅替换扩展名，文件名其它部分原样保留）
- 不确定清单（如有）：`uncertain.md`（仓库根，由 `code/03-tmp-csv.py` 在契约通过后追加写入）

请严格按下列步骤执行：
1. 用 Read 工具读 `processed_data/txts/{basename}.txt`。
2. 用 Read 工具读 `raw_data/tg_features.csv` 的第 1 行（表头），得到 14 个字段名（顺序与名称固定，不要改）。
3. 基于文本内容抽取每个字段：
   - 文本中能直接对应到的字段就填原文（去除多余空白）。
   - **找不到的字段留空**（不要写 `null` / `N/A` / `-` / `<empty>`，更不要编造）。
   - 字段值含 `,` / `"` / 换行时，整个字段值用双引号包裹，内部 `"` 写成 `""`。
4. 整理出两个东西：
   - **values**：14 个字段值按表头顺序拼成 **单行 CSV 字符串**（用 csv 标准转义，可含逗号）。
   - **uncertain**（可选）：若有任何不确定点（无字段示例、无映射规则、多值歧义等），整理为 JSON 数组字符串。每项形如 `{"field":"<字段名>","question":"<你的疑问>","options":["候选1","候选2"],"value":"<你当前填的值>"}`；无不确定则传空串。
5. 调 `code/03-tmp-csv.py` 写入（脚本会自动做契约检验：文件存在 / 共 2 行 / 表头匹配 / 数据列数匹配）：
   ```bash
   python code/03-tmp-csv.py \
     --txt "processed_data/txts/{basename}.txt" \
     --field-table raw_data/tg_features.csv \
     --values "<第 4 步的 values 字符串>" \
     --output "processed_data/csvs/{basename}.csv" \
     --uncertain "<第 4 步的 JSON 数组字符串 或 空>"
   ```
6. 脚本 exit 0 即视为成功；否则视为失败。
7. 除上述外不要输出其他内容；不要修改任何文件名。

完成后用一句话回执：
- 成功 → `OK: processed_data/csvs/{basename}.csv`
- 失败 → `FAIL: <原因>`
---

# 主 Agent 调度流程
1. 把目标清单按 6 个一组分批。
2. 每批并发派发 6 个 NLP 子 Agent。
3. 收集每个子 Agent 的回执：
   - **成功**（csv 存在 / 共 2 行 / 表头完全一致 / 数据列数一致）→ 调用：
     ```bash
     python code/03-write-feature.py \
       --checklist processed_data/names-checklist.csv \
       --filename "<PNG文件名>" \
       --status 1
     ```
   - **失败** → 等 3 秒后重新派发；最多 3 次；3 次仍失败记 0：
     ```bash
     python code/03-write-feature.py \
       --checklist processed_data/names-checklist.csv \
       --filename "<PNG文件名>" \
       --status 0
     ```
4. 全部处理完后调用 `code/03-NLP-check.py` 验证：
   ```bash
   python code/03-NLP-check.py \
     --checklist processed_data/names-checklist.csv \
     --csvs-dir processed_data/csvs/
   ```

# 通用约定（务必遵守）
- 不要修改任何文件名。
- 列名与列顺序严格按字段表，**不要改**。
- 子 Agent 写 csv **必须经 `code/03-tmp-csv.py`**，不要直接 Write csv。
- 写 checklist **必须经 `code/03-write-feature.py`**。
- 子 Agent 并发上限 = 6。

# 完成后输出
简明告知：
- 处理目标数
- Feature Extract=1 成功数 / =0 失败数
- `03-NLP-check.py` 的验证结果
- 若 `uncertain.md` 有追加内容，告知条目数
````

---

## 提示词 4️⃣ — 第四步：数据合并

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
当前执行 **第 4 步：数据合并**（最终汇总）。
仓库根目录就是当前工作目录。

# 本步目标
按 `names-checklist.csv` 的行序，把所有 `Feature Extract=1` 行对应的临时 CSV 合并为 `processed_data/final.csv`，**去重表头**（仅保留第 1 个临时 CSV 的表头）。

# 前置检查
1. `processed_data/names-checklist.csv` 存在，且第 3 步已完成（Feature Extract 列每行已填 `0` 或 `1`）。
2. `processed_data/csvs/` 下应有与 Feature Extract=1 行数一致的 .csv 文件。
3. 若 `processed_data/final.csv` 已存在，**不要手动删**，脚本会自己删。

# 执行步骤
直接调用：
```bash
python code/04-merge.py \
  --checklist processed_data/names-checklist.csv \
  --csvs-dir processed_data/csvs/ \
  --output processed_data/final.csv
```

脚本会做：
- 按 checklist 行序取 `Feature Extract=1` 的行
- 合并到 `final.csv`（首个临时 CSV 的表头保留；其余表头行丢弃）
- 验证：
  - 数据行数 == Feature Extract=1 的行数
  - 每行列数 == 表头列数
  - 不存在重复表头行
- 任何一项失败 → exit 1 并打印差异

# 通用约定（务必遵守）
- 不要直接编辑 `final.csv`，**只能通过 `code/04-merge.py`**。
- 不要修改任何文件名。
- Feature Extract=0 的行不会进 final.csv。

# 完成后输出
简明告知：
- final.csv 的总行数（含表头）
- 列数
- 与 checklist 中 Feature Extract=1 行数是否一致
- `04-merge.py` 的退出码与验证通过/失败信息
````
