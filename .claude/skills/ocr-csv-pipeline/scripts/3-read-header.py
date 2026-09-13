"""3-read-header.py — 读取字段表表头（steps/3.md 前置检查）。

用法:
    .venv/bin/python "$SKILL/scripts/3-read-header.py" \\
        --field-table raw_data/tg_features.csv

行为:
    打印 "[OK] hdr=<表头原文>"（第 1 行, 去行尾换行）; 该原文是本步全局唯一
    权威来源, 后续派发时嵌入子 Agent 提示词的 FIELD_HEADER 代码块。
    文件读取失败或表头为空 → "[FAIL] ..." 并 exit 1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field-table", type=Path, default=Path("raw_data/tg_features.csv"), help="字段表 CSV 路径")
    args = parser.parse_args()

    try:
        with args.field_table.open("r", encoding="utf-8") as f:
            hdr = f.readline().rstrip("\n")
    except OSError as exc:
        print(f"[FAIL] {args.field_table} 读取失败: {exc}")
        sys.exit(1)

    if not hdr:
        print(f"[FAIL] {args.field_table} 表头为空")
        sys.exit(1)
    print(f"[OK] hdr={hdr}")


if __name__ == "__main__":
    main()
