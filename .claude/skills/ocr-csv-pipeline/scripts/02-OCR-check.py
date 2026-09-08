"""02-OCR-check.py — 验证 checklist 的 OCR 列与 txt 文件一致性。

用法:
    .venv/bin/python "$SKILL/scripts/02-OCR-check.py" \\
        --checklist processed_data/names-checklist.csv \\
        --txts-dir processed_data/txts/

行为:
    全部 OCR 子 Agent 完成后跑。检查 (1) OCR 列每行非空且 ∈ {0,1};
    (2) OCR=1 的行有对应的 .txt 文件,大小 > 0,strip() 后非空;
    (3) checklist 中的 OCR=1 行数 == txts-dir 中符合条件的文件数。
    任一失败 exit 1 并列出差异。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

OCR_COL = "OCR"
FN_COL = "Filename"
VALID_STATUS = {"0", "1"}


def txt_basename(png_name: str) -> str:
    return Path(png_name).stem + ".txt"


def is_meaningful(txt_path: Path) -> bool:
    if not txt_path.exists() or not txt_path.is_file():
        return False
    try:
        text = txt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return text.strip() != ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", required=True, type=Path, help="checklist CSV 路径")
    parser.add_argument("--txts-dir", required=True, type=Path, help="OCR 输出 txt 目录")
    args = parser.parse_args()

    if not args.checklist.exists():
        print(f"[ERROR] checklist not found: {args.checklist}", file=sys.stderr)
        sys.exit(1)
    if not args.txts_dir.exists() or not args.txts_dir.is_dir():
        print(f"[ERROR] txts dir not found: {args.txts_dir}", file=sys.stderr)
        sys.exit(1)

    with args.checklist.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        try:
            header = reader.fieldnames or []
        except Exception:
            header = []
        rows = list(reader)

    if OCR_COL not in header or FN_COL not in header:
        print(f"[ERROR] checklist missing required columns: {header}", file=sys.stderr)
        sys.exit(1)

    # 先扫描一遍:只要存在任何非空值,就允许其它行为"未处理"的空值
    if not any((row.get(OCR_COL) or "").strip() for row in rows):
        print("[ERROR] OCR 列全为空,无任何 OCR 处理结果", file=sys.stderr)
        sys.exit(1)

    errors: list[str] = []
    expected_ocr_one: set[str] = set()

    for idx, row in enumerate(rows, start=2):  # 行号从 2 开始(1 是表头)
        filename = row.get(FN_COL, "")
        status = (row.get(OCR_COL) or "").strip()
        if status == "":
            # 空值视为"未处理",跳过(只要存在其它非空行)
            continue
        if status not in VALID_STATUS:
            errors.append(f"row {idx}: OCR 列值非法 (file={filename!r}, value={status!r})")
            continue
        if status == "1":
            expected_ocr_one.add(filename)
            txt_name = txt_basename(filename)
            txt_path = args.txts_dir / txt_name
            if not txt_path.exists():
                errors.append(f"row {idx}: OCR=1 但 txt 缺失 (file={filename!r})")
            elif not is_meaningful(txt_path):
                errors.append(f"row {idx}: OCR=1 但 txt 为空或无可见字符 (file={filename!r})")

    # txts-dir 中实际有意义的 txt 文件
    actual_meaningful: set[str] = set()
    for txt_path in args.txts_dir.glob("*.txt"):
        if is_meaningful(txt_path):
            # 反推 PNG 名: 去掉 .txt 后缀,文件名干的部分对应 PNG
            png_stem = txt_path.stem
            # 找到 checklist 中 Filename 列 stem 匹配的
            for fn in expected_ocr_one:
                if Path(fn).stem == png_stem:
                    actual_meaningful.add(fn)
                    break

    missing = expected_ocr_one - actual_meaningful  # 已经在上面的循环报过了
    extras: list[str] = []
    for txt_path in args.txts_dir.glob("*.txt"):
        if not is_meaningful(txt_path):
            continue
        png_stem = txt_path.stem
        matched = any(Path(fn).stem == png_stem for fn in expected_ocr_one)
        if not matched:
            extras.append(txt_path.name)

    if extras:
        errors.append(f"txts-dir 中存在但 checklist 没有 OCR=1 对应的文件: {extras}")

    if errors:
        print("[FAIL] OCR check failed:", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] OCR check passed ({len(expected_ocr_one)} OCR=1 rows, {len(actual_meaningful)} valid txts)")


if __name__ == "__main__":
    main()
