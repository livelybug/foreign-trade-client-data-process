"""3-list-option-jsons.py — 枚举 prompts/option_category/ 下全部 .json（steps/3.md 前置检查）。

用法:
    .venv/bin/python "$SKILL/scripts/3-list-option-jsons.py" \\
        --dir prompts/option_category

行为:
    按 ASCII 顺序打印目录下全部 .json 的路径, 每行一个（供人工确认文件集
    及其与 OPTIONS_BLOCK / HIERARCHY_BLOCK 的对应关系）。
    一个都没有（含目录不存在）→ "[FAIL] <dir> 下没有任何 .json" 并 exit 1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("prompts/option_category"), help="option_category 目录路径")
    args = parser.parse_args()

    files = sorted(args.dir.glob("*.json"))
    if not files:
        print(f"[FAIL] {args.dir} 下没有任何 .json")
        sys.exit(1)
    for p in files:
        print(p)


if __name__ == "__main__":
    main()
