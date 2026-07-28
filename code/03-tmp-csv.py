"""03-tmp-csv.py — 为单个 OCR 文本生成结构化临时 CSV。

用法:
    python code/03-tmp-csv.py \\
        --txt processed_data/txts/2011-08-12 1.txt \\
        --field-table raw_data/tg_features.csv \\
        --values "ACME Corp,USA,分销商,,..." \\
        --output processed_data/csvs/2011-08-12 1.csv

行为:
    从 --field-table 读第 1 行作为表头,结合 --values 写 2 行 CSV
    (表头 + 数据)。写入后立刻做契约检验: 文件存在 / 共 2 行 /
    表头列数匹配 / 数据列数匹配。任一失败 exit 1。
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path


def read_header(field_table: Path) -> list[str]:
    if not field_table.exists():
        print(f"[ERROR] field table not found: {field_table}", file=sys.stderr)
        sys.exit(1)
    with field_table.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print(f"[ERROR] field table has no header: {field_table}", file=sys.stderr)
            sys.exit(1)
    return header


def parse_values(values_str: str, expected_cols: int) -> list[str]:
    """Parse a CSV-formatted single line into expected_cols fields.

    Uses csv.reader so values containing commas/quotes/newlines are
    handled per RFC 4180.
    """
    # 单一 CSV 行的解析:包成一个 iterable 给 csv.reader
    parsed = next(csv.reader(io.StringIO(values_str)))
    if len(parsed) != expected_cols:
        print(
            f"[ERROR] --values 字段数 {len(parsed)} != 表头列数 {expected_cols}",
            file=sys.stderr,
        )
        sys.exit(1)
    return parsed


def write_tmp_csv(output: Path, header: list[str], data: list[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(header)
            writer.writerow(data)
    except OSError as exc:
        print(f"[ERROR] failed to write {output}: {exc}", file=sys.stderr)
        sys.exit(1)


def verify_contract(output: Path, expected_header: list[str]) -> None:
    # 1. 文件存在
    if not output.exists():
        print(f"[ERROR] 契约: 输出文件不存在 {output}", file=sys.stderr)
        sys.exit(1)
    # 2-4. 读出来逐项验证
    with output.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if len(rows) != 2:
        print(f"[ERROR] 契约: 行数应为 2 (表头+数据), 实际 {len(rows)}", file=sys.stderr)
        sys.exit(1)
    header, data = rows
    if header != expected_header:
        print(
            f"[ERROR] 契约: 表头不匹配\n  expected: {expected_header}\n  actual:   {header}",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(data) != len(expected_header):
        print(
            f"[ERROR] 契约: 数据列数 {len(data)} != 表头列数 {len(expected_header)}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txt", required=True, type=Path, help="OCR 文本文件路径(脚本内部读取以触发存在性检查)")
    parser.add_argument("--field-table", required=True, type=Path, help="字段表 CSV 路径(读其第 1 行作为表头)")
    parser.add_argument("--values", required=True, help="逗号分隔的提取字段值")
    parser.add_argument("--output", required=True, type=Path, help="输出临时 CSV 路径")
    args = parser.parse_args()

    if not args.txt.exists():
        print(f"[ERROR] --txt 不存在: {args.txt}", file=sys.stderr)
        sys.exit(1)

    header = read_header(args.field_table)
    values = parse_values(args.values, expected_cols=len(header))

    write_tmp_csv(args.output, header, values)
    verify_contract(args.output, header)

    print(f"[OK] wrote tmp csv {args.output} ({len(values)} fields)")


if __name__ == "__main__":
    main()
