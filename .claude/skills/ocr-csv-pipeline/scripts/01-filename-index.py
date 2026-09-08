"""01-filename-index.py — 扫描 raw_data/*.png 生成 checklist CSV。

用法:
    .venv/bin/python "$SKILL/scripts/01-filename-index.py" \\
        --raw-dir raw_data \\
        --output processed_data/names-checklist.csv

行为:
    按 ASCII 顺序遍历 --raw-dir 下的所有 .png 文件,生成 3 列 CSV
    (Filename, OCR, Feature Extract),后两列初始为空。这是流水线第 1 步,
    生成的文件供 02 / 03 阶段的子 Agent 写入 OCR / Feature Extract 状态。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HEADER = ["Filename", "OCR", "Feature Extract"]


def collect_pngs(raw_dir: Path) -> list[str]:
    """Return a list of PNG filenames in `raw_dir`, sorted ASCII."""
    if not raw_dir.exists() or not raw_dir.is_dir():
        print(f"[ERROR] raw dir not found: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    names = sorted(p.name for p in raw_dir.glob("*.png"))
    if not names:
        print(f"[ERROR] no .png files under: {raw_dir}", file=sys.stderr)
        sys.exit(1)
    return names


def write_checklist(names: list[str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(HEADER)
            for name in names:
                writer.writerow([name, "", ""])
    except OSError as exc:
        print(f"[ERROR] failed to write {output}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path, help="存放 PNG 图片的目录路径")
    parser.add_argument("--output", required=True, type=Path, help="输出的 checklist CSV 文件路径")
    args = parser.parse_args()

    names = collect_pngs(args.raw_dir)
    write_checklist(names, args.output)
    print(f"[OK] wrote {len(names)} rows to {args.output}")


if __name__ == "__main__":
    main()
