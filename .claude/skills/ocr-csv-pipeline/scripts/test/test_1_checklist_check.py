"""test_1_checklist_check.py — 步骤 1-checklist-check 端到端测试。

参照 test_02_OCR_check.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 3 个 png(含带空格/逗号文件名) + 匹配 checklist → 4 项全过
  * 错误路径: checklist 缺失 / 表头不符 / 行数不符 / 首行顺序不符
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[5]
VENV_DIR = PROJECT_ROOT / ".venv"
VENV_PY = VENV_DIR / "bin" / "python"
SCRIPTS = PROJECT_ROOT / ".claude" / "skills" / "ocr-csv-pipeline" / "scripts"
REQUIREMENTS = SCRIPTS / "requirements.txt"
SCRIPT = SCRIPTS / "1-checklist-check.py"

HEADER = ["Filename", "OCR", "Feature Extract"]


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


# ---- 共享夹具 ----

def _seed_raw(raw_dir: Path, names: list[str]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for n in names:
        (raw_dir / n).write_bytes(b"png")


def _write_checklist(path: Path, rows: list[str], header: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header if header is not None else HEADER)
        for n in rows:
            w.writerow([n, "", ""])


# ---- 成功路径 ----

def test_happy_path_exits_0(tmp_path: Path) -> None:
    """3 个 png(含空格/逗号文件名), checklist 与之匹配 → 4 项全过。"""
    names = ["2011-08-12 1.png", "2011-08-12 2.png", "pic,comma.png"]
    raw = tmp_path / "raw_data"
    _seed_raw(raw, names)
    cl = tmp_path / "names-checklist.csv"
    _write_checklist(cl, sorted(names))

    cp = _run("--checklist", str(cl), "--raw-dir", str(raw))
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    assert cp.stdout.count("[OK]") == 4
    assert "--- all 4 checks passed ---" in cp.stdout


# ---- 错误路径 ----

def test_missing_checklist_exits_1(tmp_path: Path) -> None:
    raw = tmp_path / "raw_data"
    _seed_raw(raw, ["a.png"])
    cp = _run("--checklist", str(tmp_path / "no.csv"), "--raw-dir", str(raw))
    assert cp.returncode == 1
    assert "[FAIL] missing" in cp.stdout


def test_bad_header_exits_1(tmp_path: Path) -> None:
    raw = tmp_path / "raw_data"
    _seed_raw(raw, ["a.png"])
    cl = tmp_path / "cl.csv"
    _write_checklist(cl, ["a.png"], header=["Filename", "OCR", "Feature"])  # 缺 Extract
    cp = _run("--checklist", str(cl), "--raw-dir", str(raw))
    assert cp.returncode == 1
    assert "[FAIL] header" in cp.stdout


def test_row_count_mismatch_exits_1(tmp_path: Path) -> None:
    raw = tmp_path / "raw_data"
    _seed_raw(raw, ["a.png", "b.png", "c.png"])
    cl = tmp_path / "cl.csv"
    _write_checklist(cl, ["a.png", "b.png"])  # 少一行
    cp = _run("--checklist", str(cl), "--raw-dir", str(raw))
    assert cp.returncode == 1
    assert "[FAIL] row_count" in cp.stdout


def test_order_mismatch_exits_1(tmp_path: Path) -> None:
    raw = tmp_path / "raw_data"
    _seed_raw(raw, ["a.png", "b.png"])
    cl = tmp_path / "cl.csv"
    _write_checklist(cl, ["b.png", "a.png"])  # 首行不是 ASCII 第 1 个
    cp = _run("--checklist", str(cl), "--raw-dir", str(raw))
    assert cp.returncode == 1
    assert "[FAIL] order" in cp.stdout
