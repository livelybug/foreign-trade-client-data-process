"""1-checklist-check.py — 批量校验 names-checklist.csv（steps/1.md 的 4 项检查）。

用法:
    .venv/bin/python "$SKILL/scripts/1-checklist-check.py" \\
        --checklist processed_data/names-checklist.csv \\
        --raw-dir raw_data

行为:
    依次执行 4 项检查, 任一项 [FAIL] 立即 exit 1:
      1. checklist 文件存在
      2. 表头为 "Filename,OCR,Feature Extract"
      3. 数据行数 == raw-dir 下 .png 文件数
      4. 第 1 个数据行的 Filename == ASCII 排序后的第 1 个 .png 文件名
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HEADER = "Filename,OCR,Feature Extract"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", type=Path, default=Path("processed_data/names-checklist.csv"), help="checklist CSV 文件路径")
    parser.add_argument("--raw-dir", type=Path, default=Path("raw_data"), help="存放 PNG 图片的目录路径")
    args = parser.parse_args()

    pngs = sorted(p.name for p in args.raw_dir.glob("*.png"))

    print("--- check 1: exists ---")
    if not args.checklist.is_file():
        print("[FAIL] missing")
        sys.exit(1)
    print("[OK]")

    lines = args.checklist.read_text(encoding="utf-8").splitlines()
    rows = list(csv.reader(lines))

    print("--- check 2: header ---")
    if not lines or lines[0] != HEADER:
        print(f"[FAIL] header: {lines[0] if lines else '<empty>'!r}")
        sys.exit(1)
    print("[OK]")

    print("--- check 3: row_count ---")
    if len(lines) - 1 != len(pngs):
        print(f"[FAIL] row_count: csv={len(lines) - 1} png={len(pngs)}")
        sys.exit(1)
    print("[OK]")

    print("--- check 4: order (ASCII) ---")
    first_png = pngs[0] if pngs else ""
    first_field = rows[1][0] if len(rows) > 1 and rows[1] else ""
    if first_png != first_field:
        print(f"[FAIL] order: csv={first_field!r} png={first_png!r}")
        sys.exit(1)
    print("[OK]")

    print("--- all 4 checks passed ---")


if __name__ == "__main__":
    main()
