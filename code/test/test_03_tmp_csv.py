"""test_03_tmp_csv.py — 步骤 03-tmp-csv 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + uv run 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 简单值;带逗号/引号的 CSV 格式值(验证 RFC 4180 解析)
  * 错误路径: --txt 缺失 / --field-table 缺失 / --values 列数不匹配 / 字段表无表头
"""

from __future__ import annotations

import csv
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
