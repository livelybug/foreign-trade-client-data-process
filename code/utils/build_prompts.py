#!/usr/bin/env python3
"""为每个 batch 生成子 Agent 提示词，保存到 /tmp/prompts/."""
from __future__ import annotations
import os
from pathlib import Path

BATCHES_DIR = Path("/tmp/batches")
OUT_DIR = Path("/tmp/prompts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 读取主数据（主 Agent 一次性读取，后续不再 Read）
HDR = Path("raw_data/tg_features.csv").read_text(encoding="utf-8").splitlines()[0]
OPTS = Path("prompts/option_category/subdivision-options.json").read_text(encoding="utf-8")
HIER = Path("prompts/option_category/option-hierarchy.json").read_text(encoding="utf-8")

TEMPLATE = """你是 NLP 子 Agent，负责把一批 OCR 文本各自抽取为结构化字段。

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
- 不确定清单（如有）：`uncertain.json`（仓库根，顶层结构 `{{basename: [items...]}}`，由 `code/03-tmp-csv.py` 在契约通过后追加写入）

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
           - 命中 0 个 → 字段**留空**，并在 `uncertain` 数组追加一项：`{{"field":"<字段名>","question":"未匹配到任何 option 的 evidence","options":[],"value":""}}`
           - 命中 1 个 → 直接把该 option 的 `name` 填入该字段（**原样照抄 `OPTIONS_BLOCK` 中 `细分选项` 里的字符串，不要改大小写、不要省略括号内的英文别名**）。
           - 命中 ≥ 2 个 → 取文本中出现频率/突出度最高的一个 option 填值，并在 `uncertain` 数组追加一项：`{{"field":"<字段名>","question":"文本同时匹配多个 option","options":["命中 1","命中 2",...],"value":"<当前填的>"}}`
   - 对 `FIELD_HEADER` 中**不在 `FIXED_FIELDS` 内的**字段：按"通用规则"处理即可（**不要硬编码"非固定选项字段"列表**——以本项目 `OPTIONS_BLOCK` 的实际 key 集合为准）。
   - 字段值含 `,` / `"` / 换行时，整个字段值用双引号包裹，内部 `"` 写成 `""`。
3. 整理出两个字符串：
   - **values**：所有字段值按 `FIELD_HEADER` 块顺序拼成 **单行 CSV 字符串**（用 csv 标准转义，可含逗号）。
   - **uncertain**（可选）：若有任何不确定点（无字段示例、无映射规则、多值歧义、固定选项字段命中 0 个/多个等），整理为 JSON 数组字符串。每项形如 `{{"field":"<字段名>","question":"<你的疑问>","options":["候选1","候选2"],"value":"<你当前填的值>"}}`；无不确定则传空串。
4. 调 `code/03-tmp-csv.py` 写入（脚本会自动做契约检验：文件存在 / 共 2 行 / 表头匹配 / 数据列数匹配；契约通过后自动追加 `uncertain.json`（顶层结构 `{{basename: [items...]}}`）；**必须走 `uv run`**）：
   ```bash
   uv run python code/03-tmp-csv.py \\
     --txt "processed_data/txts/<basename>.txt" \\
     --field-table raw_data/tg_features.csv \\
     --values "<第 3 步的 values 字符串>" \\
     --output "processed_data/csvs/<basename>.csv" \\
     --uncertain "<第 3 步的 JSON 数组字符串 或 空>"
   ```
5. 脚本 exit 0 即视为本 txt 成功；非 0 视为本 txt 失败。
6. 处理完一个 txt，回到循环顶部处理下一个。

子批内任何一个 txt 处理失败（Read 报错、契约未过等）→ 跳过该 txt，**继续处理本子批剩余 txt**，最终在回执里按文件粒度报告。

完成后用一段按文件粒度的回执（每个 txt 一行，**仅文件名 + 状态**，不要其他文字）：
- 成功 → `OK: <basename>.txt`
- 失败 → `FAIL: <basename>.txt: <原因>`
除上述外不要输出其他内容；不要修改任何文件名。
"""

batch_files = sorted(BATCHES_DIR.glob("batch_*"))
for bf in batch_files:
    basenames = [line.strip() for line in bf.read_text(encoding="utf-8").splitlines() if line.strip()]
    # 转成 "<basename>.txt" 列表（每行一个）
    files_block = "\n".join(f"{Path(p).stem}.txt" for p in basenames)
    prompt = TEMPLATE.format(
        files_block=files_block,
        header=HDR,
        options=OPTS,
        hierarchy=HIER,
    )
    out = OUT_DIR / f"{bf.stem}.txt"
    out.write_text(prompt, encoding="utf-8")
    print(f"{bf.stem}: {len(basenames)} files, prompt {len(prompt)} bytes -> {out}")
