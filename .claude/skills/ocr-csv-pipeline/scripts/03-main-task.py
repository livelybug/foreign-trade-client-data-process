#!/usr/bin/env python3
"""Verify per-basename CSVs against the dynamic field header.

This script replaces the inline bash `for` loop that previously lived in the
step-3 dispatch prompt (which used `awk` / `wc` / `head` to spot-check each
round's intermediate CSV). It performs the same four contract checks:

    1. ``processed_data/csvs/<basename>.csv`` exists.
    2. The file has exactly 2 lines (header + 1 data row).
    3. The header row matches the dynamic field table
       ``raw_data/tg_features.csv`` (line 1, parsed via the standard CSV
       reader so any quoted commas are handled).
    4. The data row's column count equals the header's column count.

The original bash comments ①-⑥ are preserved below as Python comments, mapping
each step of the legacy inline check to its Python equivalent.

Usage (run with the project-root ``.venv`` interpreter):

    .venv/bin/python "$SKILL/scripts/03-main-task.py" \\
        --basename "2011-08-12 1" \\
        --basename "2011-08-12 2" \\
        --basename "2011-08-14 1"

Output (one line per basename, then a summary line)::

    [OK] 2011-08-12 1
    [BAD] 2011-08-14 1: header mismatch
    OK=2 BAD=1

Exit code: ``0`` when every basename passes; ``1`` when any basename fails
(so the caller can chain subsequent steps with ``&&`` and short-circuit on
contract violations).
"""

import argparse
import csv
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify per-basename CSVs against the dynamic field header.",
    )
    parser.add_argument(
        "--basename",
        action="append",
        default=[],
        metavar="NAME",
        help="basename without extension; pass one --basename per file. "
             "Example: --basename '2011-08-12 1'",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # ① 取动态表头: read the field-table header from raw_data/tg_features.csv
    #   (line 1), parsed via the standard CSV reader so any quoted commas are
    #   handled correctly (the legacy bash used `head -n 1` which would not
    #   have unquoted commas in the header).
    hdr_line = Path("raw_data/tg_features.csv").read_text(encoding="utf-8").splitlines()[0]
    expected_hdr = next(csv.reader([hdr_line]))
    expected_nf = len(expected_hdr)

    if not args.basename:
        # Mirror the original bash semantics: an empty `for` loop does nothing.
        return 0

    ok = bad = 0
    for b in args.basename:  # ② 遍历 N 个 basename(无扩展名)
        c = Path(f"processed_data/csvs/{b}.csv")  # ③ 拼出对应 csv 路径

        if not c.exists():
            print(f"[BAD] {b}: file not found: {c}")
            bad += 1
            continue
        try:
            rows = list(csv.reader(c.open(encoding="utf-8")))
        except Exception as exc:  # malformed CSV / decode error
            print(f"[BAD] {b}: read error: {exc}")
            bad += 1
            continue

        # ④ 行数必须等于 2 (header + 1 data row)
        if len(rows) != 2:
            print(f"[BAD] {b}: row count {len(rows)} != 2")
            bad += 1
            continue
        # ⑤ 表头必须等于字段表
        if rows[0] != expected_hdr:
            print(f"[BAD] {b}: header mismatch")
            bad += 1
            continue
        # ⑥ 数据列数必须等于表头列数
        if len(rows[1]) != expected_nf:
            print(f"[BAD] {b}: data col count {len(rows[1])} != header col count {expected_nf}")
            bad += 1
            continue

        print(f"[OK] {b}")  # → 打印 OK
        ok += 1

    print(f"OK={ok} BAD={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
