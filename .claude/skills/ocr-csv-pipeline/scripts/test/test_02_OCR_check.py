"""test_02_OCR_check.py — 步骤 02-OCR-check 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 有 OCR=1 行 + 匹配的有效 txt;全 OCR=0 + 空 txts 目录
  * 错误路径: checklist 缺失 / txts 目录缺失 / OCR=1 但 txt 缺失
            / OCR=1 但 txt 为空 / OCR 列为空 / 孤儿 txt / 缺必需列
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
SCRIPT = SCRIPTS / "02-OCR-check.py"


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

def _seed_checklist(path: Path, ocr_values: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Filename", "OCR", "Feature Extract"])
        for i in range(1, 5):
            fn = f"img-{i}.png"
            w.writerow([fn, (ocr_values or {}).get(fn, ""), ""])


def _seed_txts(txts: Path, files: dict[str, str]) -> None:
    txts.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (txts / name).write_text(content, encoding="utf-8")


@pytest.fixture
def setup(tmp_path: Path):
    """4 行 checklist, img-1/img-3 = OCR=1, 配 2 个有效 txt。"""
    cl = tmp_path / "names-checklist.csv"
    _seed_checklist(cl, {"img-1.png": "1", "img-3.png": "1"})
    txts = tmp_path / "txts"
    _seed_txts(txts, {"img-1.txt": "hello", "img-3.txt": "world"})
    return cl, txts


# ---- 成功路径 ----

def test_happy_path_exits_0(setup: tuple[Path, Path]) -> None:
    """2 行 OCR=1, 2 个匹配的 valid txt → exit 0。"""
    cl, txts = setup
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "2 OCR=1" in cp.stdout
    assert "2 valid txts" in cp.stdout


def test_zero_ocr_1_rows_exits_0(tmp_path: Path) -> None:
    """所有行 OCR=0 + 空 txts 目录 → exit 0。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "0", "img-2.png": "0"})
    txts = tmp_path / "txts"
    txts.mkdir()
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "0 OCR=1" in cp.stdout
    assert "0 valid txts" in cp.stdout


# ---- 错误路径 ----

def test_missing_checklist_exits_1(tmp_path: Path) -> None:
    cp = _run("--checklist", str(tmp_path / "no.csv"), "--txts-dir", str(tmp_path))
    assert cp.returncode == 1


def test_missing_txts_dir_exits_1(tmp_path: Path) -> None:
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {})
    cp = _run("--checklist", str(cl), "--txts-dir", str(tmp_path / "no"))
    assert cp.returncode == 1


def test_missing_txt_for_ocr_1_exits_1(tmp_path: Path) -> None:
    """checklist 标 OCR=1 但 txts-dir 里没有对应 txt。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    txts = tmp_path / "txts"
    txts.mkdir()
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 1
    assert "缺失" in cp.stderr


def test_empty_txt_for_ocr_1_exits_1(tmp_path: Path) -> None:
    """OCR=1 的 txt 只含空白字符 → 视作无意义,exit 1。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    txts = tmp_path / "txts"
    _seed_txts(txts, {"img-1.txt": "   \n\t  "})
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 1
    assert "空" in cp.stderr


def test_empty_ocr_value_exits_1(tmp_path: Path) -> None:
    """OCR 列有行未填 → exit 1。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {})  # 所有行 OCR=""
    txts = tmp_path / "txts"
    txts.mkdir()
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 1
    assert "非法" in cp.stderr or "空" in cp.stderr


def test_extra_txt_no_matching_row_exits_1(tmp_path: Path) -> None:
    """txts-dir 里存在 checklist 没有对应 OCR=1 的有效 txt。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    txts = tmp_path / "txts"
    _seed_txts(txts, {"img-1.txt": "ok", "img-99.txt": "extra"})
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 1
    assert "img-99" in cp.stderr


def test_missing_required_column_exits_1(tmp_path: Path) -> None:
    """checklist 表头缺 OCR 或 Filename → exit 1。"""
    cl = tmp_path / "cl.csv"
    cl.write_text("col1,col2\na,b\n", encoding="utf-8")
    txts = tmp_path / "txts"
    txts.mkdir()
    cp = _run("--checklist", str(cl), "--txts-dir", str(txts))
    assert cp.returncode == 1
    assert "missing required columns" in cp.stderr
