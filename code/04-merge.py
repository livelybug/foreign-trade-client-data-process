"""04-merge.py — 合并所有 Feature Extract=1 的临时 CSV 为 final.csv。

用法:
    python code/04-merge.py \\
        --checklist processed_data/names-checklist.csv \\
        --csvs-dir processed_data/csvs/ \\
        --output processed_data/final.csv

行为:
    按 checklist 行序遍历,只取 Feature Extract=1 的行,把对应的临时
    CSV 拼起来。第一个文件的表头保留,后续的表头行去重(直接跳过第 1
    行)。合并后做 3 项验证: 数据行数 == Feature Extract=1 的行数;
    每行列数 == 表头列数; 不存在重复的表头行。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

FEATURE_COL = "Feature Extract"
FN_COL = "Filename"


def csv_basename(png_name: str) -> str:
    return Path(png_name).stem + ".csv"


def collect_targets(checklist: Path, csvs_dir: Path) -> list[tuple[str, Path]]:
    """Return [(png_filename, csv_path), ...] in checklist order, FE=1 only."""
    with checklist.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if FEATURE_COL not in header or FN_COL not in header:
            print(
                f"[ERROR] checklist missing required columns: {header}",
                file=sys.stderr,
            )
            sys.exit(1)
        rows = list(reader)

    targets: list[tuple[str, Path]] = []
    for row in rows:
        if (row.get(FEATURE_COL) or "").strip() != "1":
            continue
        filename = row.get(FN_COL, "")
        csv_path = csvs_dir / csv_basename(filename)
        if not csv_path.exists():
            print(f"[ERROR] 缺失临时 CSV: {csv_path} (file={filename!r})", file=sys.stderr)
            sys.exit(1)
        targets.append((filename, csv_path))
    return targets


def merge(targets: list[tuple[str, Path]], output: Path) -> tuple[list[str], int]:
    """Merge targets into output. Returns (header, data_row_count)."""
    if output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    header: list[str] | None = None
    data_rows = 0
    seen_headers: list[list[str]] = []

    try:
        with output.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            for _, csv_path in targets:
                with csv_path.open("r", encoding="utf-8", newline="") as src:
                    reader = csv.reader(src)
                    rows = list(reader)
                if not rows:
                    print(f"[ERROR] 临时 CSV 为空: {csv_path}", file=sys.stderr)
                    sys.exit(1)
                file_header, *file_data = rows
                if header is None:
                    header = file_header
                    writer.writerow(header)
                    seen_headers.append(file_header)
                else:
                    # 检查后续临时 CSV 的表头是否一致(以第一个为准)
                    if file_header != header:
                        print(
                            f"[ERROR] 临时 CSV 表头与首个不一致: {csv_path}\n"
                            f"  first: {header}\n  this:  {file_header}",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    seen_headers.append(file_header)
                for row in file_data:
                    writer.writerow(row)
                    data_rows += 1
    except OSError as exc:
        print(f"[ERROR] failed to write {output}: {exc}", file=sys.stderr)
        sys.exit(1)

    if header is None:
        print("[ERROR] 没有可合并的 CSV(Feature Extract 全为 0)", file=sys.stderr)
        sys.exit(1)
    return header, data_rows


def verify_final(output: Path, header: list[str], expected_rows: int) -> None:
    with output.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        all_rows = list(reader)
    if not all_rows:
        print("[ERROR] 验证失败: final.csv 为空", file=sys.stderr)
        sys.exit(1)
    file_header, *file_data = all_rows
    if file_header != header:
        print("[ERROR] 验证失败: final.csv 表头异常", file=sys.stderr)
        sys.exit(1)
    if len(file_data) != expected_rows:
        print(
            f"[ERROR] 验证失败: 数据行数 {len(file_data)} != 期望 {expected_rows}",
            file=sys.stderr,
        )
        sys.exit(1)
    ncols = len(header)
    for idx, row in enumerate(file_data, start=2):
        if len(row) != ncols:
            print(
                f"[ERROR] 验证失败: row {idx} 列数 {len(row)} != 表头列数 {ncols}",
                file=sys.stderr,
            )
            sys.exit(1)
    # 重复表头行检查: data 里不应再出现 file_header 这样的行
    for idx, row in enumerate(file_data, start=2):
        if row == file_header:
            print(f"[ERROR] 验证失败: 数据中发现重复表头行 at row {idx}", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path, help="checklist CSV 路径")
    parser.add_argument("--csvs-dir", required=True, type=Path, help="临时 CSV 目录")
    parser.add_argument("--output", required=True, type=Path, help="最终汇总 CSV 路径")
    args = parser.parse_args()

    if not args.checklist.exists():
        print(f"[ERROR] checklist not found: {args.checklist}", file=sys.stderr)
        sys.exit(1)
    if not args.csvs_dir.exists() or not args.csvs_dir.is_dir():
        print(f"[ERROR] csvs dir not found: {args.csvs_dir}", file=sys.stderr)
        sys.exit(1)

    targets = collect_targets(args.checklist, args.csvs_dir)
    header, data_rows = merge(targets, args.output)
    verify_final(args.output, header, expected_rows=len(targets))
    print(f"[OK] merged {data_rows} rows into {args.output} ({len(header)} columns)")


if __name__ == "__main__":
    main()
