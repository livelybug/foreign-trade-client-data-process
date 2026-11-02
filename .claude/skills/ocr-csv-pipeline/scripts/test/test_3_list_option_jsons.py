"""test_3_list_option_jsons.py — 步骤 3-list-option-jsons 端到端测试。

参照 test_02_OCR_check.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 枚举全部 .json（忽略非 .json）, 按 ASCII 排序输出
  * 错误路径: 目录为空 / 目录不存在
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
SCRIPT = SCRIPTS / "3-list-option-jsons.py"


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


def _seed(d: Path, names: list[str]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text("{}", encoding="utf-8")


# ---- 成功路径 ----

def test_lists_sorted_jsons_ignores_others(tmp_path: Path) -> None:
    """.json 全部列出(ASCII 排序), 非 .json 忽略。"""
    d = tmp_path / "option_category"
    _seed(d, ["b.json", "a.json", "a10.json", "a2.json", "notes.txt", "c.txt"])
    cp = _run("--dir", str(d))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert cp.stdout.splitlines() == [
        str(d / "a.json"),
        str(d / "a10.json"),
        str(d / "a2.json"),
        str(d / "b.json"),
    ]


# ---- 错误路径 ----

def test_empty_dir_exits_1(tmp_path: Path) -> None:
    d = tmp_path / "option_category"
    d.mkdir()
    cp = _run("--dir", str(d))
    assert cp.returncode == 1
    assert "下没有任何 .json" in cp.stdout


def test_missing_dir_exits_1(tmp_path: Path) -> None:
    cp = _run("--dir", str(tmp_path / "no_such_dir"))
    assert cp.returncode == 1
    assert "[FAIL]" in cp.stdout
