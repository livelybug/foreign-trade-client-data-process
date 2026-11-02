# 外贸客户名片 OCR 流水线 — 4 步提示词

> 本文件包含将 `raw_data/*.png` 经 OCR + 信息抽取后汇总为标准 CSV 表格的 4 个步骤提示词。
> 每个提示词都是自包含的，可直接复制到独立的 Claude Code 会话中使用。
>
> 流水线总览：
> - **第 1 步** — 扫描 `raw_data/*.png` 生成 `processed_data/names-checklist.csv`
> - **第 2 步** — 对每批图（每调度轮 `max_concurrency` 个子 Agent × 每子批 `ocr_batch_size` 个 PNG）调度 OCR 子 Agent，写出对应 .txt，更新 checklist 的 OCR 列
> - **第 3 步** — 对每批 txt（每调度轮 `max_concurrency` 个子 Agent × 每子批 `nlp_batch_size` 个 TXT）调度 NLP 子 Agent，写出对应临时 csv，更新 checklist 的 Feature Extract 列
> - **第 4 步** — 按 checklist 顺序合并所有临时 csv 为 `processed_data/final.csv`

---

## 工具调用总则

> 所有步骤提示词都遵循以下三条原则；具体落地细节见各步的"通用约定"。

1. **尽量批量调用，尽量避免串行**：所有"独立、无依赖"的操作必须放进**同一条 tool 调用**里执行。
   - 多操作令用 `;` / `&&` 或 `for` 循环串成**单条 Bash** → 一次执行。一次性输出 `[OK]/[MISSING]`
   - 写 N 行 checklist → 把 N 个脚本调用串成单条 Bash
   - **典型反例（禁止）**：N 个文件用 N 次 Bash 各做一次；`max_concurrency` 个子 Agent 完成后用 `max_concurrency` 次 Bash 各写一次 checklist
2. **Python 调用必须走 `uv run`**：所有 `python code/*.py` 一律改为 `uv run python code/*.py`（详见 [README §2](../README.md)）。**禁止直接用 `python` 命令**。
3. **并发上限取自配置文件**：第二步（OCR）与第三步（NLP）派发子 Agent 的并发数 `max_concurrency` 从仓库根 `pipeline.config.json` 读取；若该文件不存在或 `max_concurrency` 字段缺失，默认 6。启动相关步骤前先用 Read 工具读该文件取该值；后续分批、并发派发都按这个数走。

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
2. 执行 `code/01-filename-index.py`（必须走 `uv run`）：
   ```bash
   uv run python code/01-filename-index.py \
     --raw-dir raw_data \
     --output processed_data/names-checklist.csv
   ```
3. **批量**验证（**单条 Bash** 一次性跑完 4 项检查；任一项 `[FAIL]` 立即 `exit 1`）：
   ```bash
   out=processed_data/names-checklist.csv
   echo "--- check 1: exists ---";       [ -f "$out" ] && echo "[OK]" || { echo "[FAIL] missing"; exit 1; }
   echo "--- check 2: header ---";       [ "$(head -n 1 "$out")" = "Filename,OCR,Feature Extract" ] && echo "[OK]" || { echo "[FAIL] header"; exit 1; }
   echo "--- check 3: row_count ---";    [ "$(($(wc -l < "$out") - 1))" = "$(ls -1 raw_data/*.png | wc -l)" ] && echo "[OK]" || { echo "[FAIL] row_count"; exit 1; }
   echo "--- check 4: order (ASCII) ---"; fp=$(ls -1 raw_data/*.png | head -n 1 | xargs basename); [ "$fp" = "$(sed -n '2p' "$out" | cut -d, -f1)" ] && echo "[OK]" || { echo "[FAIL] order"; exit 1; }
   echo "--- all 4 checks passed ---"
   ```

# 通用约定（务必遵守）
- 不要修改任何文件名（不去空格、不转小写、不做去重、不做编码转换）。
- CSV 编码 UTF-8（无 BOM），行尾 `\n`，分隔符 `,`。
- **批量调用，禁止串行**：4 项验证必须**单条 Bash** 一次跑完（见 §执行步骤 3），禁止拆成 4 次 Bash 串行。原则见文件顶部"工具调用总则"。
- **Python 必须走 `uv run`**：`uv run python code/01-filename-index.py ...`，**禁止直接用 `python`**。

# 完成后输出
简明告知：
- 生成的 checklist 行数（不含表头）
- 抽样前 3 行确认表头与数据格式
- 三个中间目录的最终路径
````

---

## 提示词 2️⃣ — 第二步：OCR 文字提取

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
当前执行 **第 2 步：OCR 文字提取**。
仓库根目录就是当前工作目录。

# 本步目标
对 `processed_data/names-checklist.csv` 中 OCR 列仍为空的每一行：
1. 主 Agent 把目标清单按 `ocr_batch_size` 个一组装成"子批"（每个子批 = 一个子 Agent 一次处理的文件集，最多 `ocr_batch_size` 个 PNG）；每**调度轮**内并发派发 `max_concurrency` 个 OCR 子 Agent（Claude 子实例），每轮同时在飞最多 `max_concurrency × ocr_batch_size` 个 PNG（默认 60）；每个子 Agent 内部对其子批内 PNG **严格串行**处理（一对 `Read` + `Write` 一次只处理一张图，写完 txt 才进下一张）。
2. 子 Agent 用视觉识别读图、输出按视觉阅读顺序的纯文本。
3. 子 Agent 用 Write 工具把每张图的文本写为 `processed_data/txts/<原文件名>.txt`。
4. 成功后用 `code/02-write-OCR.py` 把对应行 OCR 列填为 `1`；失败填 `0`。
5. 全部完成后用 `code/02-OCR-check.py` 验证。

# 前置检查
1. `processed_data/names-checklist.csv` 必须存在（来自第 1 步）。
2. 用 Read 工具读 `pipeline.config.json`，取两个字段：
   - `max_concurrency`（默认 6）：同一 message 中并发派发的子 Agent 数。
   - `ocr_batch_size`（默认 10）：每个子 Agent 一次最多处理的 PNG 数。
3. 读出 checklist 中所有 **OCR 列为空** 的 PNG 文件名，得到目标清单。
4. 如果目标清单为空，直接跳到"全量验证"。

# 子 Agent 提示词模板
每个**子批**（最多 `ocr_batch_size` 个 PNG）启动一个子 Agent 实例。把下面整段发给它（`{files_block}` 替换为本子批 PNG 文件名列表，每行一个）：

---
你是 OCR 子 Agent。本子批待处理的 PNG 文件清单（最多 ocr_batch_size 个，**严格按顺序串行处理**，每张读完图就立刻写对应的 txt，再处理下一张）：

```
{files_block}
```

其中每行是 `<basename>.png`（位于 `raw_data/` 下），最终 txt 写到 `processed_data/txts/<同名.txt>`（仅替换扩展名，其它部分原样保留含空格）。

请严格按下列步骤执行（**严格串行**，一次只处理一张图；子批内某张失败不要中断，继续处理剩余文件）：

对子批内每一张 PNG（按清单顺序）：
1. 用 Read 工具读取 `raw_data/<basename>.png`。Claude 的视觉能力会告诉你图中文字。
2. 按视觉阅读顺序逐行输出识别出的文字（保留原始换行；不要翻译、总结、推断、补全）。
3. 识别不出的字符用合理占位（如 `?`），不要编造。
4. 用 Write 工具，把识别出的纯文本写入 `processed_data/txts/<同名.txt>`。
   - 路径规则：把 `<basename>.png` 的扩展名 `.png` 替换为 `.txt`，其它部分原样保留（含空格）。
   - 例：`2011-08-14 1.png` → `processed_data/txts/2011-08-14 1.txt`
5. 这一张处理完，回到循环顶部处理下一张。

子批内任何一张处理失败（例如 Read 报错、Write 报错、视觉识别失败等）→ 跳过该文件，**继续处理本子批剩余文件**，不写任何文件，最终在回执里按文件粒度报告。

完成后用一段按文件粒度的回执（每张一行，**仅文件名 + 状态**，不要其他文字）：
- 成功 → `OK: <basename>.png`
- 失败 → `FAIL: <basename>.png: <原因>`

除上述外，不要输出任何其他内容；不要修改任何文件名。
---

# 主 Agent 调度流程
维护"待重试"队列，每项是 `(filename, retry_count)`，初始 = checklist 中所有 OCR 列为空的 PNG 文件名，每个 `retry_count = 0`。

循环直到"待重试"队列为空：
1. 从"待重试"队列中按 checklist 行序取出最多 `max_concurrency * ocr_batch_size` 个文件。
2. 按 `ocr_batch_size` 个一组装成子批（最后一个子批可能 < `ocr_batch_size`）；每组准备一份子 Agent 提示词（`{files_block}` = 该组全部 PNG 文件名，每行一个）。
3. 本调度轮内取最多 `max_concurrency` 个子批，**同一 message 并发派发**对应的 `max_concurrency` 个 OCR 子 Agent（同一 message 内最多 `max_concurrency` 个 `Agent` 工具调用同时启动）。若子批数 > `max_concurrency`，超出部分进入下一调度轮。
4. 等待本调度轮所有子 Agent 完成；汇总每个子 Agent 的回执（按文件粒度的 `OK` / `FAIL`）→ 得到本调度轮全部 PNG 的"成功"与"失败"两份名单。
5. **单条 Bash `for` 循环**一次性检查本调度轮全部 PNG 对应的 txt 是否存在 + 非空 + strip 后非空，输出 `[OK]/[MISSING]`：
   ```bash
   for f in "<f1>" "<f2>" ... "<fN>"; do
     p="processed_data/txts/${f%.png}.txt"
     if [ -s "$p" ] && [ -n "$(tr -d '[:space:]' < "$p")" ]; then echo "[OK] $f"; else echo "[MISSING/EMPTY] $f"; fi
   done
   ```
   这一步是最终权威；子 Agent 自报 `OK` 但 txt 不满足契约 → 视为本调度轮失败。
6. **单条 Bash** 把本调度轮全部成功的 `02-write-OCR.py --status 1` 用 `&&` 串起来一次跑完（必须走 `uv run`）：
   ```bash
   uv run python code/02-write-OCR.py --checklist processed_data/names-checklist.csv --filename "<f1>" --status 1 && \
   uv run python code/02-write-OCR.py --checklist processed_data/names-checklist.csv --filename "<f2>" --status 1 && \
   ...
   ```
7. 对本调度轮失败文件：`retry_count + 1`：
   - `retry_count < 3` → 重新加入"待重试"队列。
   - `retry_count >= 3` → 把它们串成**单条 Bash** `02-write-OCR.py --status 0` 一次跑完（必须走 `uv run`）：
     ```bash
     uv run python code/02-write-OCR.py --checklist processed_data/names-checklist.csv --filename "<f1>" --status 0 && \
     ...
     ```
8. 若"待重试"队列非空 → 等待 3 秒 → 回到步骤 1。

全部处理完后，调用 `code/02-OCR-check.py` 验证（**单条 Bash**，必须走 `uv run`）：
```bash
uv run python code/02-OCR-check.py \
  --checklist processed_data/names-checklist.csv \
  --txts-dir processed_data/txts/
```
验证 exit 0 即视为通过；否则打印所有错误信息并停下来报告。

# 通用约定（务必遵守）
- 不要修改任何文件名（含空格原样保留）。
- 不要用 Bash 跑 OCR 工具。OCR 只通过 Read 工具 + Claude 视觉。
- **每个子 Agent 一次最多处理 `ocr_batch_size`（默认 10）个 PNG，且必须严格串行**：一对 `Read` + `Write` 一次只处理一张图，写完 txt 才进下一张；子批内某张失败要跳过继续、**不要中断本子批**。
- **主 Agent 派发层并发 = `max_concurrency`（默认 6）**：每**调度轮**（= 同一条 message）内最多 `max_concurrency` 个 `Agent` 工具调用同时启动；每个 `Agent` 调用处理一个子批（≤`ocr_batch_size` 个 PNG），所以每轮同时在飞最多 `max_concurrency × ocr_batch_size` 个 PNG（默认 60）。
- 写 checklist 必须用 `code/02-write-OCR.py`（内部有 filelock，按单文件粒度写）；不要直接修改 CSV。
- 子 Agent 回执**仅按文件粒度**给出 `OK/FAIL`，不要输出 OCR 文本本身、不要输出其它总结性文字。

# 完成后输出
简明告知：
- 处理的 PNG 总数
- OCR=1 成功数 / OCR=0 失败数
- `02-OCR-check.py` 的验证结果
- 若有失败，列出对应的 PNG 文件名
````

---

## 提示词 3️⃣ — 第三步：关键信息抽取与结构化

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
当前执行 **第 3 步：关键信息抽取与结构化**。
仓库根目录就是当前工作目录。

# 本步目标
对 checklist 中 `OCR=1` 且 `Feature Extract` 仍为空的每一行：
1. 主 Agent 把目标清单按 `nlp_batch_size` 个一组装成"子批"（每个子批 = 一个子 Agent 一次处理的文件集，最多 `nlp_batch_size` 个 TXT）；每**调度轮**内并发派发 `max_concurrency` 个 NLP 子 Agent（Claude 子实例），每轮同时在飞最多 `max_concurrency × nlp_batch_size` 个 TXT（默认 60）；每个子 Agent 内部对其子批内 TXT **严格串行**处理（一个 txt 一次 `Read` + 一次 `03-tmp-csv.py` 调用，写完 csv 才进下一个）。
2. 子 Agent 基于注入的字段表头对每个 txt 抽取关键字段。
3. 子 Agent 通过调 `code/03-tmp-csv.py` 把抽取结果写入 `processed_data/csvs/<basename>.csv`（脚本内已含契约验证 + 自动追加 `uncertain.json`，顶层结构 `{basename: [items...]}`）。
4. 成功后用 `code/03-write-feature.py` 把对应行 Feature Extract 列填为 `1`；失败填 `0`。
5. 全部完成后用 `code/03-NLP-check.py` 验证。

# 前置检查
1. 用 Read 工具读 `pipeline.config.json`，取两个字段：
   - `max_concurrency`（默认 6）：同一 message 中并发派发的子 Agent 数。
   - `nlp_batch_size`（默认 10）：每个子 Agent 一次最多处理的 TXT 数。
2. **一次性**读取字段表头到 shell 变量 `hdr`，作为本步全局唯一权威来源：
   ```bash
   hdr=$(head -n 1 raw_data/tg_features.csv)
   [ -n "$hdr" ] || { echo "[FAIL] raw_data/tg_features.csv 表头为空"; exit 1; }
   echo "[OK] hdr=$hdr"
   ```
   - **人工确认（human-in-the-loop）**：把读到的 `hdr` 原文完整展示给用户，请用户确认 `raw_data/tg_features.csv` 的字段名与列序是否正确；确认前不得继续。用户要求修改时**停下**，等其改完文件后重新读取并再次确认。
   - 表头列数不固定；**禁止硬编码字段列表，禁止增删改列**。
   - 后续每调度轮派发 `max_concurrency` 个子 Agent 时，每份子 Agent 提示词都必须把 `$hdr` 字符串原文嵌入到 `FIELD_HEADER` 代码块；**子 Agent 不要再 Read `raw_data/tg_features.csv`**。
3. **一次性**加载项目级动态配置到 shell 变量（**文件清单动态发现，禁止硬编码文件名**）：
   - 先**动态枚举** `prompts/option_category/` 下全部 `.json`：
     ```bash
     shopt -s nullglob
     files=(prompts/option_category/*.json)
     [ "${#files[@]}" -gt 0 ] || { echo "[FAIL] prompts/option_category/ 下没有任何 .json"; exit 1; }
     printf '%s\n' "${files[@]}"
     ```
   - **人工确认（human-in-the-loop）**：把枚举到的文件清单展示给用户，请用户确认：
     - 文件集是否正确（有无缺失 / 多余 / 需要先修改的内容）；
     - 各文件与代码块的对应关系（哪个注入 `OPTIONS_BLOCK`、哪个注入 `HIERARCHY_BLOCK`）；
     - 文件集与下方示例不一致时，是否需要同步更新下方示例块。
     - 确认通过才继续；否则**停下**，等用户处理完 `prompts/option_category/` 后重新枚举并再次确认。
   - 按枚举结果**动态生成**加载命令（每个文件一行 `cat` 到对应 shell 变量 + 非空校验），拼成**单条 Bash** 一次执行。当前项目文件集的生成结果示例：
     ```bash
     opts=$(cat prompts/option_category/subdivision-options.json)
     [ -n "$opts" ] || { echo "[FAIL] subdivision-options.json 缺失或为空"; exit 1; }
     hier=$(cat prompts/option_category/option-hierarchy.json)
     [ -n "$hier" ] || { echo "[FAIL] option-hierarchy.json 缺失或为空"; exit 1; }
     echo "[OK] opts+hier loaded"
     ```
   - 这些 JSON 内容**逐项目不同**：文件名、键名集合、各 key 下的 `细分选项` 数组、evidence 结构都可能变；示例只示意格式，**文件集变化时按同样规则重新生成，不要照抄示例**。
   - 后续每调度轮派发 `max_concurrency` 个子 Agent 时，每份子 Agent 提示词都必须把 `$opts` 字符串原文嵌入到 `OPTIONS_BLOCK` 代码块、`$hier` 字符串原文嵌入到 `HIERARCHY_BLOCK` 代码块；**子 Agent 不要再 Read 这些 JSON**。
4. **核对子 Agent 提示词模板**（LLM 直接阅读对比，不要走脚本）：
   - 本步的子 Agent 提示词由 `code/utils/build_prompts.py` 根据模板生成；**本提示词文件下方"子 Agent 提示词模板"一节是该模板的权威源**，`build_prompts.py` 内部的 `TEMPLATE` 常量是实现副本，**容易与权威源漂移**。
   - 启动第 3 步前必须用 Read 工具读 `code/utils/build_prompts.py`，把 `TEMPLATE = """..."""` 三引号字符串（按 Python 转义还原后）与下方"子 Agent 提示词模板"一节比对：
     - **意思一致** → 继续， 不必要求逐字一致。
     - **意思不一致** → 立即停下，**报告差异（哪一行/哪一句）**， 根据下方"子 Agent 提示词模板" 更新 `code/utils/build_prompts.py`->`TEMPLATE`. 
5. 读 checklist 中所有 `OCR=1` 且 `Feature Extract` 为空的行，得到目标清单。
6. 如果目标清单为空，跳到"全量验证"。

# 子 Agent 提示词模板
每个**子批**（最多 `nlp_batch_size` 个 TXT）启动一个子 Agent 实例。把下面整段发给它（`{files_block}` 替换为本子批 TXT 文件名列表——每行一个 `<basename>.txt`，不含路径；`{header}` 替换为前置检查读到的 `hdr` 原文；`{options}` 替换为 `$opts` 原文；`{hierarchy}` 替换为 `$hier` 原文）：

---
你是 NLP 子 Agent，负责把一批 OCR 文本各自抽取为结构化字段。

**输入**（全部由主 Agent 注入；以代码块内容为准，**不要再 Read 任何 JSON / CSV 源文件**）：
- TXT 文件清单：本子批共 N 个（最多 `nlp_batch_size` 个），由主 Agent 注入到下方 `FILES_BLOCK` 代码块（每行一个 `<basename>.txt`）。
- 字段表头：由主 Agent 注入到下方 `FIELD_HEADER` 代码块（**列数不固定，以代码块内容为准**）。
- 固定选项字典：由主 Agent 注入到下方 `OPTIONS_BLOCK` 代码块（**本项目动态内容，禁止硬编码字段名；以代码块内容为准**）。
- 选项依据语料：由主 Agent 注入到下方 `HIERARCHY_BLOCK` 代码块（**本项目动态内容，evidence 结构因项目而异；以代码块内容为准**）。

   ```
   <FILES_BLOCK>
   {files_block}
   </FILES_BLOCK>
   ```

   ```
   <FIELD_HEADER>
   {header}
   </FIELD_HEADER>
   ```

   ```
   <OPTIONS_BLOCK>
   {options}
   </OPTIONS_BLOCK>
   ```

   ```
   <HIERARCHY_BLOCK>
   {hierarchy}
   </HIERARCHY_BLOCK>
   ```

**输出**（每张 txt 一个独立产物）：
- CSV：`processed_data/csvs/<basename>.csv`（仅替换扩展名，文件名其它部分原样保留）
- 不确定清单（如有）：`uncertain.json`（仓库根，顶层结构 `{basename: [items...]}`，由 `code/03-tmp-csv.py` 在契约通过后追加写入）

请严格按下列步骤执行（**严格串行**，一次只处理一个 txt；子批内某 txt 失败不要中断，继续处理剩余 txt）：

对子批内每一个 txt `<basename>.txt`（按清单顺序）：
1. 用 Read 工具读取 `processed_data/txts/<basename>.txt`。
2. 基于 `FIELD_HEADER` 代码块中的字段列表（**顺序与名称以代码块为准，不要改**），抽取每个字段：
   - 先从 `OPTIONS_BLOCK` 中取出**顶层 key 集合**，作为本项目"固定选项字段"名单（记为 `FIXED_FIELDS`）。**不要硬编码字段名**——`OPTIONS_BLOCK` 内容因项目而异；本项目当前示例（仅作参考，**以代码块注入内容为准**）：`客户类型` / `客户阶段` / `客户来源` / `价格敏感度` / `采购意向` / `阿里买家身份`。
   - **通用规则**：文本中能直接对应到的字段就填原文（去除多余空白）；找不到的字段**留空**（不要写 `null` / `N/A` / `-` / `<empty>`，更不要编造）。
   - 对 `FIELD_HEADER` 中**与 `FIXED_FIELDS` 任一 key 严格同名**的字段，按"固定选项字段值抽取流程"处理：
       - 该字段值**只能**从 `OPTIONS_BLOCK` 中该 key 对应 `细分选项` 数组里挑一个原样填入，**禁止自由文本，禁止编造**。
       - **挑选依据**取自 `HIERARCHY_BLOCK`：在该 key 节点下逐个 option 的 `evidence` 节点，把所有叶子字符串**扁平化**为一个搜索词集合；用 OCR 文本与该集合做语义匹配，命中的 option 即为该字段候选值。
       - **匹配结果处理**：
           - 命中 0 个 → 字段**留空**，并在 `uncertain` 数组追加一项：`{"field":"<字段名>","question":"未匹配到任何 option 的 evidence","options":[],"value":""}`
           - 命中 1 个 → 直接把该 option 的 `name` 填入该字段（**原样照抄 `OPTIONS_BLOCK` 中 `细分选项` 里的字符串，不要改大小写、不要省略括号内的英文别名**）。
           - 命中 ≥ 2 个 → 取文本中出现频率/突出度最高的一个 option 填值，并在 `uncertain` 数组追加一项：`{"field":"<字段名>","question":"文本同时匹配多个 option","options":["命中 1","命中 2",...],"value":"<当前填的>"}`
   - 对 `FIELD_HEADER` 中**不在 `FIXED_FIELDS` 内的**字段：按"通用规则"处理即可（**不要硬编码"非固定选项字段"列表**——以本项目 `OPTIONS_BLOCK` 的实际 key 集合为准）。
   - 字段值含 `,` / `"` / 换行时，整个字段值用双引号包裹，内部 `"` 写成 `""`。
3. 整理出两个字符串：
   - **values**：所有字段值按 `FIELD_HEADER` 块顺序拼成 **单行 CSV 字符串**（用 csv 标准转义，可含逗号）。
   - **uncertain**（可选）：若有任何不确定点（无字段示例、无映射规则、多值歧义、固定选项字段命中 0 个/多个等），整理为 JSON 数组字符串。每项形如 `{"field":"<字段名>","question":"<你的疑问>","options":["候选1","候选2"],"value":"<你当前填的值>"}`；无不确定则传空串。
4. 调 `code/03-tmp-csv.py` 写入（脚本会自动做契约检验：文件存在 / 共 2 行 / 表头匹配 / 数据列数匹配；契约通过后自动追加 `uncertain.json`（顶层结构 `{basename: [items...]}`）；**必须走 `uv run`**）：
   ```bash
   uv run python code/03-tmp-csv.py \
     --txt "processed_data/txts/<basename>.txt" \
     --field-table raw_data/tg_features.csv \
     --values "<第 3 步的 values 字符串>" \
     --output "processed_data/csvs/<basename>.csv" \
     --uncertain "<第 3 步的 JSON 数组字符串 或 空>"
   ```
5. 脚本 exit 0 即视为本 txt 成功；非 0 视为本 txt 失败。
6. 处理完一个 txt，回到循环顶部处理下一个。

子批内任何一个 txt 处理失败（Read 报错、契约未过等）→ 跳过该 txt，**继续处理本子批剩余 txt**，最终在回执里按文件粒度报告。

完成后用一段按文件粒度的回执（每个 txt 一行，**仅文件名 + 状态**，不要其他文字）：
- 成功 → `OK: <basename>.txt`
- 失败 → `FAIL: <basename>.txt: <原因>`
除上述外不要输出其他内容；不要修改任何文件名。

---

# 主 Agent 调度流程
维护"待重试"队列，每项是 `(basename, retry_count)`，初始 = checklist 中所有 `OCR=1` 且 `Feature Extract` 为空的行对应的 txt basename（去掉 `.txt` 后缀），每个 `retry_count = 0`。

循环直到"待重试"队列为空：
1. 从"待重试"队列中按 checklist 行序取出最多 `max_concurrency * nlp_batch_size` 个 basename。
2. 按 `nlp_batch_size` 个一组装成子批（最后一个子批可能 < `nlp_batch_size`）；每组准备一份子 Agent 提示词（`{files_block}` = 该组全部 `<basename>.txt`，每行一个；`{header}` = `$hdr` 原文）。
3. 本调度轮内取最多 `max_concurrency` 个子批，**同一 message 并发派发**对应的 `max_concurrency` 个 NLP 子 Agent（同一 message 内最多 `max_concurrency` 个 `Agent` 工具调用同时启动）。若子批数 > `max_concurrency`，超出部分进入下一调度轮。
4. 等待本调度轮所有子 Agent 完成；汇总每个子 Agent 的回执（按文件粒度的 `OK` / `FAIL`）→ 得到本调度轮全部 txt 的"成功"与"失败"两份名单。
5. **单条 Bash** 一次性调 `code/03-main-task.py` 验证本调度轮全部 txt 对应的 csv（脚本内已含契约检查：存在 / 共 2 行 / 表头等于 `raw_data/tg_features.csv` 第 1 行 / 数据列数等于表头列数），输出 `[OK]/[BAD]`：
   ```bash
   uv run python code/03-main-task.py \
     --basename "<b1>" --basename "<b2>" ... --basename "<bN>"
   ```
   - **输入**：每个 `--basename` 一个 basename（无扩展名，如 `"2011-08-12 1"`），本调度轮有几个 txt 就传几个。脚本自动从 `raw_data/tg_features.csv` 第 1 行取字段表头做契约比对，**调用方无需再读表头**。
   - **输出**：每个 basename 一行 `[OK] b` 或 `[BAD] b: <原因>`（`<原因>` 可能是 `file not found` / `row count N != 2` / `header mismatch` / `data col count N != header col count N` / `read error: ...` 之一）；末行汇总 `OK=X BAD=Y`。
   - **退出码**：全 OK → `0`；有 BAD → `1`（便于在单条 Bash 里用 `&&` 串接后续 `03-write-feature.py` 调用，contract 失败立即短路）。
   - 这一步是最终权威；子 Agent 自报 `OK` 但 csv 不满足契约 → 视为本调度轮失败。
6. **单条 Bash** 把本调度轮全部成功的 `03-write-feature.py --status 1` 用 `&&` 串起来一次跑完（必须走 `uv run`，写入目标 filename 是 `<basename>.png`——checklist 存的 png 全名，**不是 txt**）：
   ```bash
   uv run python code/03-write-feature.py --checklist processed_data/names-checklist.csv --filename "<png1>" --status 1 && \
   uv run python code/03-write-feature.py --checklist processed_data/names-checklist.csv --filename "<png2>" --status 1 && \
   ...
   ```
   - 注意：`03-write-feature.py --filename` 收的是 **PNG 全名**（如 `"2011-08-12 1.png"`），不是 txt 的 basename；要在派发前把每个 txt basename 映射回对应 png 行（同一 basename，仅扩展名不同）。
7. 对本调度轮失败 txt：`retry_count + 1`：
   - `retry_count < 3` → 重新加入"待重试"队列。
   - `retry_count >= 3` → 把它们对应的 png 串成**单条 Bash** `03-write-feature.py --status 0` 一次跑完（必须走 `uv run`）：
     ```bash
     uv run python code/03-write-feature.py --checklist processed_data/names-checklist.csv --filename "<png1>" --status 0 && \
     ...
     ```
8. 若"待重试"队列非空 → 等待 3 秒 → 回到步骤 1。

全部处理完后，调用 `code/03-NLP-check.py` 验证（**单条 Bash**，必须走 `uv run`）：
```bash
uv run python code/03-NLP-check.py \
  --checklist processed_data/names-checklist.csv \
  --csvs-dir processed_data/csvs/
```
验证 exit 0 即视为通过；否则打印所有错误信息并停下来报告。

# 通用约定（务必遵守）
- 不要修改任何文件名（含空格原样保留）。
- 列名与列顺序严格按注入的 `FIELD_HEADER`，**不要改**。
- **每个子 Agent 一次最多处理 `nlp_batch_size`（默认 10）个 TXT，且必须严格串行**：一次只处理一个 txt（一个 `Read` + 一次 `03-tmp-csv.py` 调用），写完 csv 才进下一个；子批内某 txt 失败要跳过继续、**不要中断本子批**。
- **主 Agent 派发层并发 = `max_concurrency`（默认 6）**：每调度轮（= 同一条 message）内最多 `max_concurrency` 个 `Agent` 工具调用同时启动；每个 `Agent` 调用处理一个子批（≤`nlp_batch_size` 个 TXT），所以每轮同时在飞最多 `max_concurrency × nlp_batch_size` 个 TXT（默认 60）。
- 子 Agent 写 csv **必须经 `code/03-tmp-csv.py`**（脚本内已含契约验证 + filelock 保护的 `uncertain.json` read-modify-write），不要直接 Write csv；同一子 Agent 内连续调多次 `03-tmp-csv.py` 是安全的（每次独立 append 自己的段）。
- 写 checklist **必须经 `code/03-write-feature.py`**（按单文件粒度写，传入的是 PNG 全名）。
- 子 Agent 回执**仅按文件粒度**给出 `OK/FAIL`，不要输出抽取的字段值、不要输出其它总结性文字。
- **批量调用，禁止串行**：主 Agent：把 N 个 `03-write-feature.py` 串成单条 Bash；验证 N 个 csv 用单条 Bash `for` 循环。**禁止 N 个文件 N 次 Bash 串行**。原则见文件顶部"工具调用总则"。
- **Python 必须走 `uv run`**：`uv run python code/03-tmp-csv.py ...` / `uv run python code/03-write-feature.py ...` / `uv run python code/03-NLP-check.py ...`，**禁止直接用 `python`**。

# 完成后输出
简明告知：
- 处理目标数
- Feature Extract=1 成功数 / =0 失败数
- `03-NLP-check.py` 的验证结果
- 若 `uncertain.json` 有追加内容，告知条目数
````

---

## 提示词 4️⃣ — 第四步：数据合并

````markdown
# 任务背景
你正在执行一个外贸客户名片/文档 OCR + 信息抽取流水线（共 4 步）。
当前执行 **第 4 步：数据合并**（最终汇总）。
仓库根目录就是当前工作目录。

# 本步目标
按 `processed_data/names-checklist.csv` 的行序，把所有 `Feature Extract=1` 行对应的临时 CSV 合并为 `processed_data/final.csv`，**去重表头**（仅保留第 1 个临时 CSV 的表头）。

# 前置检查
1. `processed_data/names-checklist.csv` 存在，且第 3 步已完成（Feature Extract 列每行已填 `0` 或 `1`）。
2. `processed_data/csvs/` 下应有与 Feature Extract=1 行数一致的 .csv 文件。
3. 若 `processed_data/final.csv` 已存在，**不要手动删**，脚本会自己删。

# 执行步骤
直接调用：
```bash
uv run python code/04-merge.py \
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
- **Python 必须走 `uv run`**：`uv run python code/04-merge.py ...`，**禁止直接用 `python`**。

# 完成后输出
简明告知：
- final.csv 的总行数（含表头）
- 列数
- 与 checklist 中 Feature Extract=1 行数是否一致
- `04-merge.py` 的退出码与验证通过/失败信息
````
