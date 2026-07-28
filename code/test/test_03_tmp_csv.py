"""test_03_tmp_csv.py — 步骤 03-tmp-csv 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + uv run 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 简单值;带逗号/引号的 CSV 格式值(验证 RFC 4180 解析)
  * 错误路径: --txt 缺失 / --field-table 缺失 / --values 列数不匹配 / 字段表无表头
  * uncertain 成功路径: 写入 markdown 段(中文分号分隔)/ 段间空行 / no-op / 空数组
  * uncertain 错误路径: JSON 解析失败 / 非 list / 元素非 dict / 缺必填 / options 类型错
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "code" / "requirements.txt"
SCRIPT = PROJECT_ROOT / "code" / "03-tmp-csv.py"


# ---- 环境自检 ----

def _venv_ready() -> bool:
    if not VENV_DIR.exists():
        return False
    return subprocess.run(
        ["uv", "run", "python", "-c", "import filelock"],
        cwd=PROJECT_ROOT, capture_output=True,
    ).returncode == 0


@pytest.fixture(scope="session", autouse=True)
def _ensure_env() -> None:
    if _venv_ready():
        return
    if not VENV_DIR.exists():
        subprocess.run(["uv", "venv"], cwd=PROJECT_ROOT, check=True)
    subprocess.run(
        ["uv", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=PROJECT_ROOT, check=True,
    )


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", str(SCRIPT), *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )


# ---- 共享夹具: txt + 3 字段的 field table ----

@pytest.fixture
def setup(tmp_path: Path):
    txt = tmp_path / "in.txt"
    txt.write_text("dummy ocr text", encoding="utf-8")
    ft = tmp_path / "fields.csv"
    ft.write_text("col1,col2,col3\n", encoding="utf-8")
    out = tmp_path / "csvs" / "out.csv"
    return txt, ft, out


# ---- uncertain 测试数据(模块级常量) ----

UNC_A = json.dumps(
    [
        {
            "field": "价格敏感度",
            "question": "期望是高/中/低 还是 高敏感?",
            "options": ["高/中/低", "高敏感"],
        },
        {
            "field": "电话",
            "question": "多个电话选哪个?",
            "value": "+1-555-0100; +1-555-0200",
        },
    ],
    ensure_ascii=False,
)

UNC_OPTS_ONLY = json.dumps(
    [{"field": "客户类型", "question": "是分销商还是代理商?", "options": ["分销商", "代理商"]}],
    ensure_ascii=False,
)

UNC_VAL_ONLY = json.dumps(
    [{"field": "公司网址", "question": "这是官网吗?", "value": "example.com"}],
    ensure_ascii=False,
)


# ---- 成功路径 ----

def test_happy_path_simple_values(setup: tuple[Path, Path, Path]) -> None:
    """简单值: 写入 2 行 CSV,header 取自 field table,data 取自 --values。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "3 fields" in cp.stdout

    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [["col1", "col2", "col3"], ["a", "b", "c"]]


def test_happy_path_values_with_comma_and_quote(setup: tuple[Path, Path, Path]) -> None:
    """--values 中含逗号和引号 → 按 RFC 4180 解析,不被逗号切碎。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", '"ACME, Corp",USA,"分销,商"',
        "--output", str(out),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["ACME, Corp", "USA", "分销,商"]


# ---- uncertain 成功路径 ----

def test_uncertain_appends_markdown_block(setup: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """--uncertain 非空 JSON 数组 -> 追加 markdown 段,中文分号分隔,stem 来自 --txt。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.md"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", UNC_A,
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "appended 2 uncertain" in cp.stdout

    content = unc.read_text(encoding="utf-8")
    # stem 是 "in"(setup 里 txt 名是 in.txt -> 去 .txt)
    assert "## in\n\n" in content
    # 中文分号分隔;反引号包裹;多个候选用 " / " 分隔
    assert "**价格敏感度**：期望是高/中/低 还是 高敏感?；候选：`高/中/低` / `高敏感`" in content
    assert "**电话**：多个电话选哪个?；值：`+1-555-0100; +1-555-0200`" in content
    # 不应出现双问号(早期 bug 修复)
    assert "??候选" not in content
    assert "??值" not in content
    # 段末保留 1 个换行
    assert content.endswith("\n")


def test_uncertain_second_call_separates_by_blank_line(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """两次 --uncertain 写入 -> 段间用空行分隔(连续两次 ## 之间有 \\n\\n)。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.md"
    item = json.dumps(
        [{"field": "客户阶段", "question": "阶段定义?", "value": "初始"}],
        ensure_ascii=False,
    )
    for _ in range(2):
        cp = _run(
            "--txt", str(txt),
            "--field-table", str(ft),
            "--values", "a,b,c",
            "--output", str(out),
            "--uncertain", item,
            "--uncertain-path", str(unc),
        )
        assert cp.returncode == 0, f"stderr={cp.stderr}"

    content = unc.read_text(encoding="utf-8")
    # 两段都有
    assert content.count("## in\n") == 2
    # 段间空行
    assert "\n\n## in\n" in content


def test_uncertain_omitted_does_not_create_file(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """不传 --uncertain 时,即使显式指定 --uncertain-path,文件也不应被创建。"""
    txt, ft, out = setup
    unc = tmp_path / "should_not_exist.md"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert not unc.exists()


def test_uncertain_empty_array_equivalent_to_omitted(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain='[]' 等价于不传,不会写入文件。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.md"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", "[]",
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert not unc.exists()


def test_uncertain_options_only(setup: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """只有 options,无 value -> 渲染为 '候选:...'。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.md"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", UNC_OPTS_ONLY,
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    content = unc.read_text(encoding="utf-8")
    assert "候选：`分销商` / `代理商`" in content
    assert "值：" not in content


def test_uncertain_value_only(setup: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """只有 value,无 options -> 渲染为 '值:...'。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.md"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", UNC_VAL_ONLY,
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    content = unc.read_text(encoding="utf-8")
    assert "值：`example.com`" in content
    assert "候选：" not in content


# ---- 错误路径 ----

def test_missing_txt_exits_1(tmp_path: Path) -> None:
    ft = tmp_path / "fields.csv"
    ft.write_text("a,b\n", encoding="utf-8")
    cp = _run(
        "--txt", str(tmp_path / "no.txt"),
        "--field-table", str(ft),
        "--values", "1,2",
        "--output", str(tmp_path / "out.csv"),
    )
    assert cp.returncode == 1
    assert "不存在" in cp.stderr or "txt" in cp.stderr.lower()


def test_missing_field_table_exits_1(tmp_path: Path) -> None:
    txt = tmp_path / "in.txt"
    txt.write_text("x", encoding="utf-8")
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(tmp_path / "no.csv"),
        "--values", "1",
        "--output", str(tmp_path / "out.csv"),
    )
    assert cp.returncode == 1


def test_values_column_mismatch_exits_1(setup: tuple[Path, Path, Path]) -> None:
    """field table 有 3 列, --values 只有 2 个值 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b",
        "--output", str(out),
    )
    assert cp.returncode == 1
    assert "字段数" in cp.stderr


def test_empty_field_table_exits_1(tmp_path: Path) -> None:
    """field table 是空文件 → 报 'no header',exit 1。"""
    txt = tmp_path / "in.txt"
    txt.write_text("x", encoding="utf-8")
    ft = tmp_path / "empty.csv"
    ft.write_text("", encoding="utf-8")
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "1",
        "--output", str(tmp_path / "out.csv"),
    )
    assert cp.returncode == 1
    assert "no header" in cp.stderr


# ---- uncertain 错误路径 ----

def test_uncertain_json_parse_error_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 不是合法 JSON → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", "not-json",
        "--uncertain-path", str(tmp_path / "unc.md"),
    )
    assert cp.returncode == 1
    assert "JSON" in cp.stderr


def test_uncertain_not_list_exits_1(setup: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """--uncertain 是合法 JSON 但不是数组 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '{"field":"x","question":"y"}',  # JSON object, not array
        "--uncertain-path", str(tmp_path / "unc.md"),
    )
    assert cp.returncode == 1
    assert "数组" in cp.stderr


def test_uncertain_element_not_dict_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 数组元素不是对象 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '["just a string"]',
        "--uncertain-path", str(tmp_path / "unc.md"),
    )
    assert cp.returncode == 1
    assert "对象" in cp.stderr


def test_uncertain_missing_required_field_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 元素缺 field → exit 1(缺 question 同理)。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '[{"question":"x"}]',  # 缺 field
        "--uncertain-path", str(tmp_path / "unc.md"),
    )
    assert cp.returncode == 1
    assert "field" in cp.stderr


def test_uncertain_invalid_options_type_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 元素 options 不是字符串数组 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '[{"field":"x","question":"y","options":"not-a-list"}]',
        "--uncertain-path", str(tmp_path / "unc.md"),
    )
    assert cp.returncode == 1
    assert "options" in cp.stderr
