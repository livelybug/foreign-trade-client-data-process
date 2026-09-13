"""test_3_load_option_jsons.py — 步骤 3-load-option-jsons 端到端测试。

参照 test_02_OCR_check.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 多个非空 JSON → "[OK] N json loaded"
  * 错误路径: 文件缺失 / 空文件 / 只含换行 → FAIL 指名文件; 不传 --json → argparse 报错
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
SCRIPT = SCRIPTS / "3-load-option-jsons.py"


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


def _seed(d: Path, files: dict[str, str]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return d


# ---- 成功路径 ----

def test_happy_path_exits_0(tmp_path: Path) -> None:
    d = _seed(tmp_path, {
        "subdivision-options.json": '{"客户类型": {"细分选项": ["经销商"]}}',
        "option-hierarchy.json": '{"客户类型": []}',
    })
    cp = _run(
        "--json", str(d / "subdivision-options.json"),
        "--json", str(d / "option-hierarchy.json"),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert cp.stdout == "[OK] 2 json loaded\n"


# ---- 错误路径 ----

def test_missing_file_exits_1(tmp_path: Path) -> None:
    d = _seed(tmp_path, {"a.json": "{}"})
    cp = _run("--json", str(d / "a.json"), "--json", str(d / "gone.json"))
    assert cp.returncode == 1
    assert "[FAIL] gone.json 缺失或为空" in cp.stdout


def test_empty_file_exits_1(tmp_path: Path) -> None:
    d = _seed(tmp_path, {"a.json": ""})
    cp = _run("--json", str(d / "a.json"))
    assert cp.returncode == 1
    assert "[FAIL] a.json 缺失或为空" in cp.stdout


def test_newlines_only_file_exits_1(tmp_path: Path) -> None:
    """只含换行的文件与空文件同等对待。"""
    d = _seed(tmp_path, {"a.json": "\n\n"})
    cp = _run("--json", str(d / "a.json"))
    assert cp.returncode == 1
    assert "[FAIL] a.json 缺失或为空" in cp.stdout


def test_no_json_arg_exits_2(tmp_path: Path) -> None:
    """--json 必传: argparse 报错退出。"""
    cp = _run()
    assert cp.returncode == 2
