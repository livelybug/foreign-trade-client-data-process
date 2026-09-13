"""test_3_read_header.py — 步骤 3-read-header 端到端测试。

参照 test_02_OCR_check.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 正常字段表 → "[OK] hdr=<原文>"
  * 错误路径: 文件缺失 / 文件为空 / 第 1 行为空行
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[5]
VENV_DIR = PROJECT_ROOT / ".venv"
VENV_PY = VENV_DIR / "bin" / "python"
SCRIPTS = PROJECT_ROOT / ".claude" / "skills" / "ocr-csv-pipeline" / "scripts"
REQUIREMENTS = SCRIPTS / "requirements.txt"
SCRIPT = SCRIPTS / "3-read-header.py"


# ---- 环境自检 ----

def _venv_ready() -> bool:
    if not VENV_PY.exists():
        return False
    return subprocess.run(
        [str(VENV_PY), "-c", "import filelock"],
        cwd=PROJECT_ROOT, capture_output=True,
    ).returncode == 0


@pytest.fixture(scope="session", autouse=True)
def _ensure_env() -> None:
    if _venv_ready():
        return
    if not VENV_PY.exists():
        subprocess.run(["python3", "-m", "venv", str(VENV_DIR)], cwd=PROJECT_ROOT, check=True)
    subprocess.run(
        [str(VENV_PY), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=PROJECT_ROOT, check=True,
    )


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(VENV_PY), str(SCRIPT), *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )


# ---- 成功路径 ----

def test_happy_path_exits_0(tmp_path: Path) -> None:
    ft = tmp_path / "tg_features.csv"
    ft.write_text("field1,field2,字段3\nv1,v2,v3\n", encoding="utf-8")
    cp = _run("--field-table", str(ft))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert cp.stdout == "[OK] hdr=field1,field2,字段3\n"


# ---- 错误路径 ----

def test_missing_file_exits_1(tmp_path: Path) -> None:
    cp = _run("--field-table", str(tmp_path / "no.csv"))
    assert cp.returncode == 1
    assert "[FAIL]" in cp.stdout


def test_empty_file_exits_1(tmp_path: Path) -> None:
    ft = tmp_path / "tg_features.csv"
    ft.write_text("", encoding="utf-8")
    cp = _run("--field-table", str(ft))
    assert cp.returncode == 1
    assert "表头为空" in cp.stdout


def test_blank_first_line_exits_1(tmp_path: Path) -> None:
    ft = tmp_path / "tg_features.csv"
    ft.write_text("\na,b\n", encoding="utf-8")
    cp = _run("--field-table", str(ft))
    assert cp.returncode == 1
    assert "表头为空" in cp.stdout
