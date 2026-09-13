"""2-txt-check.py — 检查本调度轮 PNG 对应的 txt 是否存在且非空（steps/2.md 调度流程步骤 5）。

用法:
    .venv/bin/python "$SKILL/scripts/2-txt-check.py" \\
        --txts-dir processed_data/txts/ "f1.png" "f2.png" ... "fN.png"

行为:
    对每个 PNG 文件名 f, 检查 <txts-dir>/${f%.png}.txt:
      存在 + 大小 > 0 + 去除全部空白后非空 → "[OK] f"
      否则 → "[MISSING/EMPTY] f"
    仅输出状态行(由主 Agent 解析), 恒 exit 0。
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txts-dir", type=Path, default=Path("processed_data/txts"), help="OCR 输出的 txt 文件目录")
    parser.add_argument("pngs", nargs="+", help="本调度轮的 PNG 文件名列表")
    args = parser.parse_args()

    for png in args.pngs:
        stem = png[: -len(".png")] if png.endswith(".png") else png
        p = args.txts_dir / f"{stem}.txt"
        ok = p.is_file() and p.stat().st_size > 0 and bool("".join(p.read_text(encoding="utf-8").split()))
        print(f"[OK] {png}" if ok else f"[MISSING/EMPTY] {png}")


if __name__ == "__main__":
    main()
