"""3-load-option-jsons.py — 校验 option_category JSON 可加载且非空（steps/3.md 前置检查）。

用法:
    .venv/bin/python "$SKILL/scripts/3-load-option-jsons.py" \\
        --json prompts/option_category/subdivision-options.json \\
        --json prompts/option_category/option-hierarchy.json

行为:
    逐个读取 --json 指定的文件（可重复传, 文件清单由 3-list-option-jsons.py
    枚举 + 人工确认后给出）。任一缺失或去除换行后为空 →
    "[FAIL] <basename> 缺失或为空" 并 exit 1; 全部通过 → "[OK] N json loaded"。
    内容本身仍由主 Agent 用 Read 工具读取后嵌入子 Agent 提示词。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="jsons", action="append", required=True, type=Path,
                        help="待加载的 JSON 文件路径, 可重复传多个")
    args = parser.parse_args()

    for path in args.jsons:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        if not content.rstrip("\n"):
            print(f"[FAIL] {path.name} 缺失或为空")
            sys.exit(1)
    print(f"[OK] {len(args.jsons)} json loaded")


if __name__ == "__main__":
    main()
