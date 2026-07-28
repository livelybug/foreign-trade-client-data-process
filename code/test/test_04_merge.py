"""test_04_merge.py — 步骤 04-merge 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + uv run 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 合并 2 个 csv,跳过 FE=0 行,保留 checklist 顺序;输出已存在时覆盖
  * 错误路径: FE=1 但 csv 缺失 / 临时 csv 表头不一致 / 全 FE=0 / checklist 缺失 / csvs 目录缺失
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "code" / "requirements.txt"
SCRIPT = PROJECT_ROOT / "code" / "04-merge.py"


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
    """checklist: img-1=1, img-2=0, img-3=1, img-4=0 → 合并 img-1 + img-3。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1", "img-2.png": "0", "img-3.png": "1", "img-4.png": "0"})
    csvs = tmp_path / "csvs"
    _seed_csvs(csvs, {
        "img-1.csv": "col1,col2,col3\nA,1,x\n",
        "img-3.csv": "col1,col2,col3\nC,3,z\n",
    })
    out = tmp_path / "final.csv"
    return cl, csvs, out


# ---- 成功路径 ----

def test_happy_path_merges_in_checklist_order(setup: tuple[Path, Path, Path]) -> None:
    """2 个 FE=1 行按 checklist 行序合并,跳过 FE=0 行。"""
    cl, csvs, out = setup
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs), "--output", str(out))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "merged 2 rows" in cp.stdout

    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["col1", "col2", "col3"]
    # checklist 行序: img-1, img-3
    assert rows[1] == ["A", "1", "x"]
    assert rows[2] == ["C", "3", "z"]
    assert len(rows) == 3  # 1 表头 + 2 数据


def test_output_overwritten_if_exists(setup: tuple[Path, Path, Path]) -> None:
    """output 已存在 → 删除后重建(不应崩溃,内容应为新合并结果)。"""
    cl, csvs, out = setup
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("OLD_HEADER\nOLD_DATA\n", encoding="utf-8")
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs), "--output", str(out))
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["col1", "col2", "col3"]  # 不是 OLD_HEADER
    assert len(rows) == 3


# ---- 错误路径 ----

def test_missing_tmp_csv_exits_1(tmp_path: Path) -> None:
    """checklist 标 FE=1 但 csvs-dir 里没有对应 csv → exit 1。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1"})
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs), "--output", str(tmp_path / "out.csv"))
    assert cp.returncode == 1
    assert "缺失" in cp.stderr
    assert "img-1" in cp.stderr


def test_header_mismatch_exits_1(tmp_path: Path) -> None:
    """两个临时 csv 表头不一致 → exit 1。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "1", "img-2.png": "1"})
    csvs = tmp_path / "csvs"
    _seed_csvs(csvs, {
        "img-1.csv": "a,b,c\n1,2,3\n",
        "img-2.csv": "a,b,d\n4,5,6\n",  # 表头第 3 列是 d,与首个不一致
    })
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs), "--output", str(tmp_path / "out.csv"))
    assert cp.returncode == 1
    assert "表头" in cp.stderr


def test_no_fe_1_rows_exits_1(tmp_path: Path) -> None:
    """所有行 FE=0 → 没有可合并的内容,exit 1。"""
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {"img-1.png": "0", "img-2.png": "0"})
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(cl), "--csvs-dir", str(csvs), "--output", str(tmp_path / "out.csv"))
    assert cp.returncode == 1
    assert "全为 0" in cp.stderr or "没有" in cp.stderr


def test_missing_checklist_exits_1(tmp_path: Path) -> None:
    csvs = tmp_path / "csvs"
    csvs.mkdir()
    cp = _run("--checklist", str(tmp_path / "no.csv"), "--csvs-dir", str(csvs), "--output", str(tmp_path / "out.csv"))
    assert cp.returncode == 1


def test_missing_csvs_dir_exits_1(tmp_path: Path) -> None:
    cl = tmp_path / "cl.csv"
    _seed_checklist(cl, {})
    cp = _run("--checklist", str(cl), "--csvs-dir", str(tmp_path / "no"), "--output", str(tmp_path / "out.csv"))
    assert cp.returncode == 1
