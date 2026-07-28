"""02-write-OCR.py — 将单个文件的 OCR 结果写入 checklist 的 OCR 列。

用法:
    python code/02-write-OCR.py \\
        --checklist processed_data/names-checklist.csv \\
        --filename "2011-08-12 1.png" \\
        --status 1

行为:
    在 filelock 保护下读 checklist,定位 --filename 所在行,把 OCR 列
    写为 --status (0 / 1),再写回。这是流水线第 2 步,被并行的 OCR
    子 Agent 调用,互斥锁避免并发写入冲突。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from filelock import FileLock, Timeout

OCR_COL = "OCR"
VALID_STATUS = {"0", "1"}
LOCK_TIMEOUT = 10  # seconds: 锁覆盖读-改-写全程后,串行排队依然很快


def validate_status(status: str) -> None:
    if status not in VALID_STATUS:
        print(f"[ERROR] --status must be 0 or 1, got: {status!r}", file=sys.stderr)
        sys.exit(1)


def update_row(checklist: Path, filename: str, status: str, ocr_col_idx: int) -> None:
    """读-改-写全程在 FileLock 内,避免并发子 Agent 之间的丢失更新。

    之前版本只锁住读、写回在锁外:进程 A 读完释放锁后,进程 B 拿到锁
    读到的可能是 A 已截断/未写完的中间状态,造成数据丢失。修复后,读
    到的快照与写回的版本在同一个临界区内,串行化保证不丢更新。
    """
    lock_path = checklist.with_suffix(checklist.suffix + ".lock")
    try:
        with FileLock(str(lock_path), timeout=LOCK_TIMEOUT):
            with checklist.open("r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)

            if not rows:
                print(f"[ERROR] checklist is empty: {checklist}", file=sys.stderr)
                sys.exit(1)

            header, *data = rows
            target_row = None
            target_idx = None
            for idx, row in enumerate(data):
                if row and row[0] == filename:
                    target_row = row
                    target_idx = idx
                    break

            if target_row is None:
                print(f"[ERROR] filename not found in checklist: {filename!r}", file=sys.stderr)
                sys.exit(1)

            # pad row if needed
            while len(target_row) <= ocr_col_idx:
                target_row.append("")
            target_row[ocr_col_idx] = status
            data[target_idx] = target_row

            with checklist.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(header)
                writer.writerows(data)
    except Timeout:
        print(f"[ERROR] could not acquire lock: {lock_path}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"[ERROR] failed to access {checklist}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path, help="checklist CSV 路径")
    parser.add_argument("--filename", required=True, help="PNG 文件名(精确匹配)")
    parser.add_argument("--status", required=True, help="OCR 结果: 1 成功 / 0 失败")
    args = parser.parse_args()

    validate_status(args.status)

    if not args.checklist.exists():
        print(f"[ERROR] checklist not found: {args.checklist}", file=sys.stderr)
        sys.exit(1)

    # 读 header 找 OCR 列索引(允许列顺序变化)
    with args.checklist.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print(f"[ERROR] checklist is empty: {args.checklist}", file=sys.stderr)
            sys.exit(1)

    if OCR_COL not in header:
        print(f"[ERROR] column {OCR_COL!r} not in checklist header", file=sys.stderr)
        sys.exit(1)
    ocr_col_idx = header.index(OCR_COL)

    update_row(args.checklist, args.filename, args.status, ocr_col_idx)
    print(f"[OK] OCR={args.status} for {args.filename}")


if __name__ == "__main__":
    main()
