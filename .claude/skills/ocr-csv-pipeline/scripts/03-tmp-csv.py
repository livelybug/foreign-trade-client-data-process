"""03-tmp-csv.py — 为单个 OCR 文本生成结构化临时 CSV,并收集"不确定"信息。

用法:
    # 基本用法(无不确定):
    .venv/bin/python "$SKILL/scripts/03-tmp-csv.py" \\
        --txt processed_data/txts/2011-08-12 1.txt \\
        --field-table raw_data/tg_features.csv \\
        --values "ACME Corp,USA,分销商,,..." \\
        --output processed_data/csvs/2011-08-12 1.csv

    # 携带不确定清单(子 Agent 把提取过程中遇到的不确定点以 JSON 数组传入):
    .venv/bin/python "$SKILL/scripts/03-tmp-csv.py" \\
        --txt processed_data/txts/2011-08-12 1.txt \\
        --field-table raw_data/tg_features.csv \\
        --values "ACME Corp,USA,分销商,,..." \\
        --output processed_data/csvs/2011-08-12 1.csv \\
        --uncertain '[{"field":"价格敏感度","question":"期望是高/中/低 还是 高敏感?","options":["高/中/低","高敏感"]}]'

行为:
    从 --field-table 读第 1 行作为表头,结合 --values 写 2 行 CSV
    (表头 + 数据)。写入后立刻做契约检验: 文件存在 / 共 2 行 /
    表头列数匹配 / 数据列数匹配。任一失败 exit 1。

    若 --uncertain 提供非空 JSON 数组,则契约通过后再以 filelock
    排他锁将不确定清单按文件分组追加写入 --uncertain-path(默认
    仓库根 uncertain.json,顶层结构 {basename: [items...]}),供后
    续人工 review。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from filelock import FileLock, Timeout

UNCERTAIN_PATH_DEFAULT = Path("uncertain.json")
LOCK_TIMEOUT = 10  # seconds: append_uncertain 持锁时间极短,排队快


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


def validate_uncertain(raw: str) -> list[dict]:
    """解析并校验 --uncertain JSON 数组。

    - 空串或 "[]" 返回空列表(调用方据此跳过写入)。
    - 其它输入必须能 json.loads,且解析结果为 list。
    - 每个元素必须为 dict,且包含 field(str) 与 question(str)。
    - 可选字段 options(list[str])、value(str) 存在时类型必须正确。
    任何校验失败 -> exit 1。
    """
    if raw == "" or raw.strip() == "[]":
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] --uncertain 不是合法 JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(parsed, list):
        print(
            f"[ERROR] --uncertain 必须是 JSON 数组, 实际类型: {type(parsed).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)

    for idx, item in enumerate(parsed):
        if not isinstance(item, dict):
            print(
                f"[ERROR] --uncertain[{idx}] 不是对象, 实际类型: {type(item).__name__}",
                file=sys.stderr,
            )
            sys.exit(1)
        field = item.get("field")
        question = item.get("question")
        if not isinstance(field, str) or field == "":
            print(
                f"[ERROR] --uncertain[{idx}].field 必填且为非空字符串",
                file=sys.stderr,
            )
            sys.exit(1)
        if not isinstance(question, str) or question == "":
            print(
                f"[ERROR] --uncertain[{idx}].question 必填且为非空字符串",
                file=sys.stderr,
            )
            sys.exit(1)
        if "options" in item:
            options = item["options"]
            if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
                print(
                    f"[ERROR] --uncertain[{idx}].options 必须是字符串数组",
                    file=sys.stderr,
                )
                sys.exit(1)
        if "value" in item:
            value = item["value"]
            if not isinstance(value, str):
                print(
                    f"[ERROR] --uncertain[{idx}].value 必须是字符串",
                    file=sys.stderr,
                )
                sys.exit(1)
    return parsed


def load_uncertain(path: Path) -> dict:
    """读取已有的 uncertain.json;文件不存在返回空 dict。

    顶层必须是 dict,否则 exit 1;JSON 解析失败也 exit 1。
    """
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] {path} 不是合法 JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"[ERROR] failed to read {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(
            f"[ERROR] {path} 顶层必须是 dict, 实际类型: {type(data).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)
    return data


def append_uncertain(path: Path, basename: str, items: list[dict]) -> None:
    """在 filelock 排他锁下将 items 追加到 uncertain.json 中 basename 键下。

    顶层结构: {<basename>: [<item>, <item>, ...]}。
    - 文件不存在:写 {basename: items}。
    - 文件存在:读出 dict,basename 键已存在则 extend,否则新增。
    - basename 键已存在但值不是 list → exit 1(防止数据被覆盖/破坏)。
    - 写回时使用 indent=2, ensure_ascii=False, 末尾补一个 '\\n'。
    lock 文件: <path>.lock(与 02-write-OCR / 03-write-feature 风格一致)。
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(lock_path), timeout=LOCK_TIMEOUT):
            data = load_uncertain(path)
            if basename in data:
                existing = data[basename]
                if not isinstance(existing, list):
                    print(
                        f"[ERROR] {path}[{basename!r}] 必须是 list, "
                        f"实际类型: {type(existing).__name__}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                existing.extend(items)
            else:
                data[basename] = items
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
    except Timeout:
        print(f"[ERROR] could not acquire lock: {lock_path}", file=sys.stderr)
        sys.exit(1)
    except OSError as exc:
        print(f"[ERROR] failed to write {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--txt", required=True, type=Path, help="OCR 文本文件路径(脚本内部读取以触发存在性检查)")
    parser.add_argument("--field-table", required=True, type=Path, help="字段表 CSV 路径(读其第 1 行作为表头)")
    parser.add_argument("--values", required=True, help="逗号分隔的提取字段值")
    parser.add_argument("--output", required=True, type=Path, help="输出临时 CSV 路径")
    parser.add_argument(
        "--uncertain",
        required=False,
        default="",
        help='JSON 数组字符串,每项描述一个"不确定"点;空串或 "[]" 表示无。',
    )
    parser.add_argument(
        "--uncertain-path",
        required=False,
        type=Path,
        default=UNCERTAIN_PATH_DEFAULT,
        help="不确定清单的追加目标文件路径(默认: 仓库根 uncertain.json,顶层结构 {basename: [items...]})",
    )
    args = parser.parse_args()

    if not args.txt.exists():
        print(f"[ERROR] --txt 不存在: {args.txt}", file=sys.stderr)
        sys.exit(1)

    header = read_header(args.field_table)
    values = parse_values(args.values, expected_cols=len(header))

    write_tmp_csv(args.output, header, values)
    verify_contract(args.output, header)

    # 契约通过后再处理 uncertain:契约失败时本段不执行,避免基于错误数据记录问题
    items = validate_uncertain(args.uncertain)
    if items:
        basename = args.txt.stem
        append_uncertain(args.uncertain_path, basename, items)
        print(f"[OK] appended {len(items)} uncertain item(s) to {args.uncertain_path}")

    print(f"[OK] wrote tmp csv {args.output} ({len(values)} fields)")


if __name__ == "__main__":
    main()
