"""test_2_txt_check.py — 步骤 2-txt-check 端到端测试。

参照 test_02_OCR_check.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 有效 txt / 内容仅含首尾空白的 txt → [OK]
  * 失败路径: txt 缺失 / 空文件 / 只含空白字符 → [MISSING/EMPTY]
  * 恒 exit 0; .png 后缀正确替换为 .txt; 文件名含空格原样保留
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
SCRIPT = SCRIPTS / "2-txt-check.py"


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


def _seed_txts(txts: Path, files: dict[str, str]) -> None:
    txts.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (txts / name).write_text(content, encoding="utf-8")


# ---- 成功路径 ----

def test_mixed_statuses_all_reported(tmp_path: Path) -> None:
    """有效/缺失/空文件/纯空白 混合 → 每个文件一行状态, 顺序保持输入序。"""
    txts = tmp_path / "txts"
    _seed_txts(txts, {
        "2011-08-14 1.txt": "hello world",   # 有效
        "b.txt": "  \n  x \n",               # 内容仅首尾空白 → 有效
        "d.txt": "",                          # 空文件
        "e.txt": " \n\t ",                    # 只含空白字符
    })
    cp = _run("--txts-dir", str(txts), "2011-08-14 1.png", "b.png", "c.png", "d.png", "e.png")
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert cp.stdout.splitlines() == [
        "[OK] 2011-08-14 1.png",
        "[OK] b.png",
        "[MISSING/EMPTY] c.png",
        "[MISSING/EMPTY] d.png",
        "[MISSING/EMPTY] e.png",
    ]


def test_exit_0_even_when_missing(tmp_path: Path) -> None:
    """脚本只输出状态供主 Agent 解析, 有 MISSING 也恒 exit 0。"""
    cp = _run("--txts-dir", str(tmp_path / "txts"), "a.png")
    assert cp.returncode == 0
    assert cp.stdout == "[MISSING/EMPTY] a.png\n"


def test_png_suffix_stripped_once(tmp_path: Path) -> None:
    """${f%.png} 语义: 仅去掉一个 .png 后缀再补 .txt。"""
    txts = tmp_path / "txts"
    _seed_txts(txts, {"a.txt": "ok"})
    cp = _run("--txts-dir", str(txts), "a.png")
    assert cp.returncode == 0
    assert cp.stdout == "[OK] a.png\n"
