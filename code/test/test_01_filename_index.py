"""test_01_filename_index.py — 步骤 01 端到端测试。

对照 README §4 验证 `code/01-filename-index.py`:

  * §4.3 成功路径产物: ROW_COUNT / HEADER / EMPTY_COLS / ORDER 四项
  * §4.4 错误路径冒烟: 目录不存在 / 目录无 .png 两项

测试前会自动检查 `.venv` 和 `code/requirements.txt`,
缺失时用 `uv` 创建 venv 并安装依赖,无需手工准备环境。
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

# ---- 路径常量 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "code" / "requirements.txt"
SCRIPT = PROJECT_ROOT / "code" / "01-filename-index.py"
RAW_DIR = PROJECT_ROOT / "raw_data"
OUTPUT = PROJECT_ROOT / "processed_data" / "names-checklist.csv"


# ---- 环境自检 ----

def _venv_ready() -> bool:
    """.venv 存在且 `filelock` 可被 import。"""
    if not VENV_DIR.exists():
        return False
    return subprocess.run(
        ["uv", "run", "python", "-c", "import filelock"],
        cwd=PROJECT_ROOT,
        capture_output=True,
    ).returncode == 0


@pytest.fixture(scope="session", autouse=True)
def _ensure_env() -> None:
    """保证 .venv 存在且依赖装好;缺失则用 `uv` 创建/安装。"""
    if _venv_ready():
        return
    if not VENV_DIR.exists():
        subprocess.run(["uv", "venv"], cwd=PROJECT_ROOT, check=True)
    subprocess.run(
        ["uv", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=PROJECT_ROOT,
        check=True,
    )


# ---- 跑脚本的辅助 ----

def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def _expected_png_count() -> int:
    """动态数 raw_data/ 下 .png 文件数,作为 row count 的预期基准。

    raw_data/ 会被陆续添加新的名片图片,不能把 4 写死。
    """
    return sum(1 for p in RAW_DIR.glob("*.png") if p.is_file())


@pytest.fixture(scope="module")
def expected_rows() -> int:
    """module 级:本次测试启动时 raw_data/ 里的 .png 数,产物文件行数应等于此值。"""
    return _expected_png_count()


@pytest.fixture(scope="module")
def ran_success(expected_rows: int) -> subprocess.CompletedProcess:
    """module 级:跑一次成功路径,产物供 §4.3 测试复用。"""
    if OUTPUT.exists():
        OUTPUT.unlink()
    cp = _run("--raw-dir", str(RAW_DIR), "--output", str(OUTPUT))
    assert cp.returncode == 0, f"script failed: stderr={cp.stderr}"
    return cp


# ---- §4.3 成功路径 ----

def test_4_3_stdout_ok_message(ran_success: subprocess.CompletedProcess, expected_rows: int) -> None:
    """stdout 应为 `[OK] wrote N rows to <output>`,N 等于 raw_data/ 下 .png 文件数。"""
    assert ran_success.stdout.strip() == f"[OK] wrote {expected_rows} rows to {OUTPUT}"


def test_4_3_row_count(ran_success: subprocess.CompletedProcess, expected_rows: int) -> None:
    """ROW_COUNT_OK:1 表头 + N 数据 = N+1 行。"""
    n = sum(1 for _ in OUTPUT.open(encoding="utf-8"))
    assert n == expected_rows + 1, f"expected {expected_rows + 1} lines, got {n}"


def test_4_3_header(ran_success: subprocess.CompletedProcess) -> None:
    """HEADER_OK:表头严格匹配。"""
    with OUTPUT.open(encoding="utf-8", newline="") as f:
        first = next(csv.reader(f))
    assert first == ["Filename", "OCR", "Feature Extract"]


def test_4_3_empty_ocr_and_feature_columns(ran_success: subprocess.CompletedProcess) -> None:
    """EMPTY_COLS_OK:OCR / Feature Extract 列初始为空。"""
    with OUTPUT.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:
        assert row[1] == "", f"OCR column not empty: {row}"
        assert row[2] == "", f"Feature Extract column not empty: {row}"


def test_4_3_ascii_ascending_order(ran_success: subprocess.CompletedProcess, expected_rows: int) -> None:
    """ORDER_OK:首行是 '2011-08-12 1.png',整体按 ASCII 升序,共 N 条。"""
    with OUTPUT.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    names = [r[0] for r in rows[1:]]
    assert names[0] == "2011-08-12 1.png"
    assert names == sorted(names)
    assert len(names) == expected_rows


# ---- §4.4 错误路径 ----

def test_4_4_missing_raw_dir_exits_1() -> None:
    """`--raw-dir` 指向不存在的目录 → exit code 1。"""
    cp = _run("--raw-dir", "/no/such/dir", "--output", "/tmp/x.csv")
    assert cp.returncode == 1


def test_4_4_no_png_in_dir_exits_1(tmp_path: Path) -> None:
    """`--raw-dir` 里没 .png → exit code 1。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    cp = _run("--raw-dir", str(empty), "--output", str(tmp_path / "x.csv"))
    assert cp.returncode == 1
