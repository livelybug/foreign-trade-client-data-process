"""test_03_NLP_check.py — 步骤 03-NLP-check 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + uv run 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

与 test_02_OCR_check.py 的区别: 只检查 CSV 文件是否存在,不要求内容非空。

覆盖:
  * 成功路径: 有 FE=1 行 + 匹配的 csv;全 FE=0 + 空 csvs 目录
  * 错误路径: checklist 缺失 / csvs 目录缺失 / FE=1 但 csv 缺失
            / FE 列为空 / 孤儿 csv / 缺必需列
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "code" / "requirements.txt"
SCRIPT = PROJECT_ROOT / "code" / "03-NLP-check.py"


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


# ---- 共享夹具 ----

def _seed_checklist(path: Path, fe_values: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Filename", "OCR", "Feature Extract"])
        for i in range(1, 5):
            fn = f"img-{i}.png"
            w.writerow([fn, "", (fe_values or {}).get(fn, "")])


def _seed_csvs(csvs: Path, files: dict[str, str]) -> None:
    csvs.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (csvs / name).write_text(content, encoding="utf-8")


@pytest.fixture
def setup(tmp_path: Path):
    """4 行 checklist, img-1/img-3 = FE=1, 配 2 个 csv。"""
    cl = tmp_path / "names-checklist.csv"
    _seed_checklist(cl, {"img-1.png": "1", "img-3.png": "1"})
    csvs = tmp_path / "csvs"
    _seed_csvs(csvs, {"img-1.csv": "a,b\n1,2\n", "img-3.csv": "a,b\n3,4\n"})
    return cl, csvs


# ---- 成功路径 ----

def test_happy_path_exits_0(setup: tuple[Path, Path]) -> None:
    """2 行 FE=1, 2 个匹配的 csv → exit 0。"""
    cl, csvs = setup
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "2 Feature Extract=1" in cp.stdout


def test_empty_csv_allowed(tmp_path: Path) -> None:
    """FE=1 行的 csv 即使内容为空(只有 header)也算成功(与 OCR-check 不同)。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    csvs = tmp_path / "csvs"
    _seed_csvs(csvs, {"img-1.csv": "a,b,c\n"})  # 只有 header, 无数据行
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "1 Feature Extract=1" in cp.stdout


def test_zero_fe_1_rows_exits_0(tmp_path: Path) -> None:
    """所有行 FE=0 + 空 csvs 目录 → exit 0。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "0", "img-2.png": "0"})
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "0 Feature Extract=1" in cp.stdout


# ---- 错误路径 ----

def test_missing_checklist_exits_1(tmp_path: Path) -> None:
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(tmp_path / "no.csv"), "--csvs-dir", str(csvs))
    assert cp.returncode == 1


def test_missing_csvs_dir_exits_1(tmp_path: Path) -> None:
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {})
    cp = _run("--checklist", str(cl), "--csvs-dir", str(tmp_path / "no"))
    assert cp.returncode == 1


def test_missing_csv_for_fe_1_exits_1(tmp_path: Path) -> None:
    """checklist 标 FE=1 但 csvs-dir 里没有对应 csv。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 1
    assert "缺失" in cp.stderr


def test_empty_feature_value_exits_1(tmp_path: Path) -> None:
    """Feature Extract 列有行未填 → exit 1。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {})  # 所有行 FE=""
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 1
    assert "非法" in cp.stderr or "空" in cp.stderr


def test_extra_csv_no_matching_row_exits_1(tmp_path: Path) -> None:
    """csvs-dir 里存在 checklist 没有对应 FE=1 的 csv。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    csvs = tmp_path / "csvs"
    _seed_csvs(csvs, {"img-1.csv": "a\n1\n", "img-99.csv": "a\n2\n"})
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 1
    assert "img-99" in cp.stderr


def test_missing_required_column_exits_1(tmp_path: Path) -> None:
    """checklist 表头缺 Feature Extract 或 Filename → exit 1。"""
    cl = tmp_path / "cl.csv"
    cl.write_text("col1,col2\na,b\n", encoding="utf-8")
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs))
    assert cp.returncode == 1
    assert "missing required columns" in cp.stderr
