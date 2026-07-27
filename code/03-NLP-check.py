"""03-NLP-check.py — 验证 checklist 的 Feature Extract 列与临时 CSV 一致性。

用法:
    python code/03-NLP-check.py \\
        --checklist processed_data/names-checklist.csv \\
        --csvs-dir processed_data/csvs/

行为:
    全部 NLP 子 Agent 完成后跑。检查 (1) Feature Extract 列每行非空且
    ∈ {0,1}; (2) Feature Extract=1 的行有对应 .csv 文件存在;
    (3) Feature Extract=1 的行数 == csvs-dir 中匹配的文件数(一 一对应)。
    任一失败 exit 1 并列出差异。注意: 与 02-OCR-check.py 不同,这里
    不要求 CSV 文件内容非空/有意义。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

FEATURE_COL = "Feature Extract"
FN_COL = "Filename"
VALID_STATUS = {"0", "1"}


def csv_basename(png_name: str) -> str:
    return Path(png_name).stem + ".csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path, help="checklist CSV 路径")
    parser.add_argument("--csvs-dir", required=True, type=Path, help="临时 CSV 目录")
    args = parser.parse_args()

    if not args.checklist.exists():
        print(f"[ERROR] checklist not found: {args.checklist}", file=sys.stderr)
        sys.exit(1)
    if not args.csvs_dir.exists() or not args.csvs_dir.is_dir():
        print(f"[ERROR] csvs dir not found: {args.csvs_dir}", file=sys.stderr)
        sys.exit(1)

    with args.checklist.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    if FEATURE_COL not in header or FN_COL not in header:
        print(f"[ERROR] checklist missing required columns: {header}", file=sys.stderr)
        sys.exit(1)

    errors: list[str] = []
    expected: set[str] = set()
    for idx, row in enumerate(rows, start=2):
        filename = row.get(FN_COL, "")
        status = (row.get(FEATURE_COL) or "").strip()
        if status not in VALID_STATUS:
            errors.append(
                f"row {idx}: Feature Extract 列值非法或为空 (file={filename!r}, value={status!r})"
            )
            continue
        if status == "1":
            expected.add(filename)
            csv_name = csv_basename(filename)
            csv_path = args.csvs_dir / csv_name
            if not csv_path.exists() or not csv_path.is_file():
                errors.append(f"row {idx}: Feature Extract=1 但 CSV 缺失 (file={filename!r})")

    # csvs-dir 里多余的 CSV(无对应 checklist 行)
    extras: list[str] = []
    expected_stems = {Path(fn).stem for fn in expected}
    for csv_path in args.csvs_dir.glob("*.csv"):
        if csv_path.stem not in expected_stems:
            extras.append(csv_path.name)

    if extras:
        errors.append(f"csvs-dir 中存在但 checklist 没有 Feature Extract=1 对应的文件: {extras}")

    if errors:
        print("[FAIL] NLP check failed:", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] NLP check passed ({len(expected)} Feature Extract=1 rows)")


if __name__ == "__main__":
    main()
