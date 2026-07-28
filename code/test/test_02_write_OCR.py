"""test_02_write_OCR.py — 步骤 02-write-OCR 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + uv run 跑真实脚本
  * tmp_path 隔离,不污染 processed_data/
  * scope="session" 自检 .venv + filelock
  * happy path + 关键错误分支

覆盖:
  * 成功路径: status=1 / status=0 两种合法值
  * 错误路径: 非法 status / 找不到 filename / checklist 缺失 / 缺 OCR 列
  * 并发路径: 两个子进程真正并发写不同行,验证 FileLock 覆盖 read-modify-write
    全程,无丢失更新
"""

from __future__ import annotations

import concurrent.futures
import csv
import subprocess
from pathlib import Path

import pytest

# ---- 路径常量 ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "code" / "requirements.txt"
SCRIPT = PROJECT_ROOT / "code" / "02-write-OCR.py"


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

def _run(checklist: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--checklist", str(checklist), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
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

def test_status_1_writes_ocr_column(checklist: Path) -> None:
    """status=1 写入对应行的 OCR 列,其他行未变。"""
    cp = _run(checklist, "--filename", "img-1.png", "--status", "1")
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert cp.stdout.strip() == "[OK] OCR=1 for img-1.png"

    with checklist.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["img-1.png", "1", ""]
    for i, r in enumerate(rows[2:], start=2):
        assert r[1] == "", f"row {i} OCR 应仍为空, got {r!r}"


def test_status_0_writes_ocr_column(checklist: Path) -> None:
    """status=0 也合法,写入对应行。"""
    cp = _run(checklist, "--filename", "img-2.png", "--status", "0")
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    with checklist.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[2] == ["img-2.png", "0", ""]


# ---- 错误路径 ----

def test_invalid_status_exits_1(checklist: Path) -> None:
    """--status 不是 0/1 → exit 1。"""
    cp = _run(checklist, "--filename", "img-1.png", "--status", "2")
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


def test_missing_ocr_column_exits_1(tmp_path: Path) -> None:
    """checklist 表头没有 OCR 列 → exit 1。"""
    p = tmp_path / "no-ocr-col.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("Filename,Feature Extract\nimg-1.png,\n", encoding="utf-8")
    cp = _run(p, "--filename", "img-1.png", "--status", "1")
    assert cp.returncode == 1
    assert "OCR" in cp.stderr


# ---- 并发路径 ----

def test_concurrent_writes_both_succeed(tmp_path: Path) -> None:
    """两个子进程真正并发写不同行:验证 FileLock 覆盖 read-modify-write 全程。

    修复前,update_row 只在 read 阶段持锁、write 阶段在锁外,两个并发写
    不同行时后写者会覆盖前者的更新(loses-update)。修复后锁覆盖全程,
    应满足:
    (1) 两个进程都成功返回 0(锁能防 read 阶段竞争,无超时)
    (2) 文件结构(行数/表头)未损坏
    (3) 未触及行保持空
    (4) img-1.png 的 OCR=1、img-3.png 的 OCR=0 都正确写入(无丢失更新)
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
    # 真正并发等待:之前 p1.communicate() 串行等完才启动 p2,实际上未并发。
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(p1.communicate)
        f2 = ex.submit(p2.communicate)
        _, err1 = f1.result()
        _, err2 = f2.result()
    assert p1.returncode == 0, f"p1 stderr={err1}"
    assert p2.returncode == 0, f"p2 stderr={err2}"

    with p.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    # 文件结构未损坏
    assert len(rows) == 5
    assert rows[0] == ["Filename", "OCR", "Feature Extract"]
    # 未触及行保持空
    assert rows[2][1] == ""  # img-2.png
    assert rows[4][1] == ""  # img-4.png
    # 两个并发写入都正确落地 (修复后锁覆盖写阶段,loses-update 已修复)
    assert rows[1] == ["img-1.png", "1", ""], f"img-1.png 丢失更新: {rows[1]!r}"
    assert rows[3] == ["img-3.png", "0", ""], f"img-3.png 丢失更新: {rows[3]!r}"
