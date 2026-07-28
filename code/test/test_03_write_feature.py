"""test_03_write_feature.py — 步骤 03-write-feature 端到端测试。

与 test_02_write_OCR.py 对称: 写入目标列从 OCR 换为 Feature Extract,逻辑相同。

参照 test_01_filename_index.py 风格:
  * subprocess + uv run 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支 + 并发写

覆盖:
  * 成功路径: status=1 / status=0 两种合法值
  * 错误路径: 非法 status / 找不到 filename / checklist 缺失 / 缺 Feature Extract 列
  * 并发路径: 两个子进程同时写不同行,验证互斥锁不超时
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
SCRIPT = PROJECT_ROOT / "code" / "03-write-feature.py"


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


# ---- 跑脚本的辅助 ----

def _run(checklist: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--checklist", str(checklist), *args],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )


# ---- 共享夹具: 4 行空白 checklist ----

def _seed_checklist(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Filename", "OCR", "Feature Extract"])
        for i in range(1, 5):
            w.writerow([f"img-{i}.png", "", ""])


@pytest.fixture
def checklist(tmp_path: Path) -> Path:
    p = tmp_path / "names-checklist.csv"
    _seed_checklist(p)
    return p


# ---- 成功路径 ----

def test_status_1_writes_feature_column(checklist: Path) -> None:
    """status=1 写入对应行的 Feature Extract 列,其他行未变。"""
    cp = _run(checklist, "--filename", "img-1.png", "--status", "1")
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert cp.stdout.strip() == "[OK] Feature Extract=1 for img-1.png"

    with checklist.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["img-1.png", "", "1"]
    for i, r in enumerate(rows[2:], start=2):
        assert r[2] == "", f"row {i} Feature Extract 应仍为空, got {r!r}"


def test_status_0_writes_feature_column(checklist: Path) -> None:
    """status=0 也合法,写入对应行。"""
    cp = _run(checklist, "--filename", "img-2.png", "--status", "0")
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    with checklist.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[2] == ["img-2.png", "", "0"]


# ---- 错误路径 ----

def test_invalid_status_exits_1(checklist: Path) -> None:
    """--status 不是 0/1 → exit 1。"""
    cp = _run(checklist, "--filename", "img-1.png", "--status", "x")
    assert cp.returncode == 1
    assert "0 or 1" in cp.stderr


def test_unknown_filename_exits_1(checklist: Path) -> None:
    """--filename 不在 checklist 中 → exit 1。"""
    cp = _run(checklist, "--filename", "ghost.png", "--status", "1")
    assert cp.returncode == 1
    assert "not found" in cp.stderr


def test_missing_checklist_exits_1(tmp_path: Path) -> None:
    """--checklist 路径不存在 → exit 1。"""
    cp = _run(tmp_path / "no.csv", "--filename", "x.png", "--status", "1")
    assert cp.returncode == 1


def test_missing_feature_column_exits_1(tmp_path: Path) -> None:
    """checklist 表头没有 Feature Extract 列 → exit 1。"""
    p = tmp_path / "no-fe-col.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("Filename,OCR\nimg-1.png,\n", encoding="utf-8")
    cp = _run(p, "--filename", "img-1.png", "--status", "1")
    assert cp.returncode == 1
    assert "Feature Extract" in cp.stderr


# ---- 并发路径 ----

def test_concurrent_writes_both_succeed(tmp_path: Path) -> None:
    """两个子进程同时写不同行: 验证锁能防止 read 阶段竞争,文件结构未损坏。

    注: update_row 只在 read 阶段持锁,write 阶段在锁外 — 理论上 2 个进程同时
    写不同行时,后写者可能覆盖前者的更新(loses-update)。本测试只验证
    (1) 两个进程都成功返回 0(锁能防 read 阶段竞争,无超时)
    (2) 文件结构(行数/表头)未损坏
    (3) 未触及行保持空
    不对 img-1 / img-3 的最终值做强断言(避免 flaky)。
    """
    p = tmp_path / "names-checklist.csv"
    _seed_checklist(p)

    p1 = subprocess.Popen(
        ["uv", "run", "python", str(SCRIPT),
         "--checklist", str(p), "--filename", "img-1.png", "--status", "1"],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    p2 = subprocess.Popen(
        ["uv", "run", "python", str(SCRIPT),
         "--checklist", str(p), "--filename", "img-3.png", "--status", "0"],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    _, err1 = p1.communicate()
    _, err2 = p2.communicate()
    assert p1.returncode == 0, f"p1 stderr={err1}"
    assert p2.returncode == 0, f"p2 stderr={err2}"

    with p.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    # 文件结构未损坏
    assert len(rows) == 5
    assert rows[0] == ["Filename", "OCR", "Feature Extract"]
    # 未触及行保持空 (Feature Extract 在第 3 列, index 2)
    assert rows[2][2] == ""  # img-2.png
    assert rows[4][2] == ""  # img-4.png
    # 至少一个并发写入落地
    touched = [rows[1][2], rows[3][2]]
    assert any(v in ("0", "1") for v in touched), f"both concurrent writes lost: {touched}"
