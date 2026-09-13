"""test_e2e_pipeline.py — skill 端到端测试（scripts 全链路）。

按 steps/1-4.md 的主 Agent 流程, 在 tmp_path 沙箱里串起全部确定性脚本,
OCR / NLP 子 Agent 环节用桩模拟(直接写 txt / 调 03-tmp-csv.py)。
所有脚本以沙箱为 cwd 运行(03-main-task.py 内部是硬编码相对路径)。

覆盖:
  * 第 1 步: 01-filename-index.py → 1-checklist-check.py
  * 第 2 步: (桩: 写 txt) → 2-txt-check.py → 02-write-OCR.py → 02-OCR-check.py
             (1 个 png 模拟 OCR 失败 → status 0, 不产生 txt)
  * 第 3 步: 3-read-header.py → 3-list-option-jsons.py → 3-load-option-jsons.py
             → (桩: 03-tmp-csv.py, 其中 1 个带 uncertain) → 03-main-task.py
             → 03-write-feature.py → 03-NLP-check.py
  * 第 4 步: 04-merge.py → 校验 final.csv 行数/列序/逗号转义 与 uncertain.json
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[5]
VENV_DIR = PROJECT_ROOT / ".venv"
VENV_PY = VENV_DIR / "bin" / "python"
SCRIPTS = PROJECT_ROOT / ".claude" / "skills" / "ocr-csv-pipeline" / "scripts"
REQUIREMENTS = SCRIPTS / "requirements.txt"

PNGS = ["2011-08-12 1.png", "2011-08-12 2.png", "2011-08-14 1.png"]
OCR_OK = ["2011-08-12 1.png", "2011-08-14 1.png"]  # 2011-08-12 2.png 模拟失败
OCR_FAIL = ["2011-08-12 2.png"]
HEADER_LINE = "公司名称,国家,客户类型,价格敏感度,备注"


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


def _run(cwd: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(VENV_PY), str(SCRIPTS / script), *args],
        cwd=cwd, capture_output=True, text=True,
    )


def _seed_sandbox(sandbox: Path) -> None:
    raw = sandbox / "raw_data"
    raw.mkdir(parents=True)
    for n in PNGS:
        (raw / n).write_bytes(b"\x89PNG-fake")
    (raw / "tg_features.csv").write_text(
        HEADER_LINE + "\n示例公司,美国,经销商,高,\n", encoding="utf-8")

    oc = sandbox / "prompts" / "option_category"
    oc.mkdir(parents=True)
    (oc / "subdivision-options.json").write_text(
        '{"客户类型": {"细分选项": ["经销商", "分销商"]}}', encoding="utf-8")
    (oc / "option-hierarchy.json").write_text(
        '{"客户类型": []}', encoding="utf-8")


def test_full_pipeline(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    _seed_sandbox(sandbox)
    cl = "processed_data/names-checklist.csv"

    # ---- 第 1 步: 索引 + 批量校验 ----
    cp = _run(sandbox, "01-filename-index.py", "--raw-dir", "raw_data", "--output", cl)
    assert cp.returncode == 0, cp.stderr
    cp = _run(sandbox, "1-checklist-check.py", "--checklist", cl, "--raw-dir", "raw_data")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "--- all 4 checks passed ---" in cp.stdout

    # ---- 第 2 步: OCR 桩 + 逐轮检查 + 回写 + 全量验证 ----
    txts = sandbox / "processed_data" / "txts"
    txts.mkdir(parents=True)
    (txts / "2011-08-12 1.txt").write_text("ACME, Inc.\nUSA 经销商\n", encoding="utf-8")
    (txts / "2011-08-14 1.txt").write_text("Beta Ltd\nDE 分销商\n", encoding="utf-8")

    cp = _run(sandbox, "2-txt-check.py", "--txts-dir", "processed_data/txts", *OCR_OK)
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.splitlines() == [f"[OK] {f}" for f in OCR_OK]

    for f in OCR_OK:
        cp = _run(sandbox, "02-write-OCR.py", "--checklist", cl, "--filename", f, "--status", "1")
        assert cp.returncode == 0, cp.stderr
    for f in OCR_FAIL:
        cp = _run(sandbox, "02-write-OCR.py", "--checklist", cl, "--filename", f, "--status", "0")
        assert cp.returncode == 0, cp.stderr

    cp = _run(sandbox, "02-OCR-check.py", "--checklist", cl, "--txts-dir", "processed_data/txts/")
    assert cp.returncode == 0, cp.stdout + cp.stderr

    # ---- 第 3 步: 前置检查脚本 + NLP 桩 + 契约验证 + 回写 + 全量验证 ----
    cp = _run(sandbox, "3-read-header.py", "--field-table", "raw_data/tg_features.csv")
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout == f"[OK] hdr={HEADER_LINE}\n"

    cp = _run(sandbox, "3-list-option-jsons.py", "--dir", "prompts/option_category")
    assert cp.returncode == 0, cp.stdout
    assert cp.stdout.splitlines() == [
        "prompts/option_category/option-hierarchy.json",
        "prompts/option_category/subdivision-options.json",
    ]

    cp = _run(sandbox, "3-load-option-jsons.py",
              "--json", "prompts/option_category/subdivision-options.json",
              "--json", "prompts/option_category/option-hierarchy.json")
    assert cp.returncode == 0, cp.stderr
    assert "[OK] 2 json loaded" in cp.stdout

    cp = _run(sandbox, "03-tmp-csv.py",
              "--txt", "processed_data/txts/2011-08-12 1.txt",
              "--field-table", "raw_data/tg_features.csv",
              "--values", '"ACME, Inc.",USA,经销商,高,无',
              "--output", "processed_data/csvs/2011-08-12 1.csv",
              "--uncertain", "[]")
    assert cp.returncode == 0, cp.stderr

    uncertain = json.dumps(
        [{"field": "价格敏感度", "question": "文本同时匹配多个 option",
          "options": ["高", "高敏感"], "value": "高"}],
        ensure_ascii=False)
    cp = _run(sandbox, "03-tmp-csv.py",
              "--txt", "processed_data/txts/2011-08-14 1.txt",
              "--field-table", "raw_data/tg_features.csv",
              "--values", "Beta Ltd,DE,分销商,低,",
              "--output", "processed_data/csvs/2011-08-14 1.csv",
              "--uncertain", uncertain)
    assert cp.returncode == 0, cp.stderr

    cp = _run(sandbox, "03-main-task.py",
              "--basename", "2011-08-12 1", "--basename", "2011-08-14 1")
    assert cp.returncode == 0, cp.stdout
    assert "OK=2 BAD=0" in cp.stdout

    for f in OCR_OK:
        cp = _run(sandbox, "03-write-feature.py", "--checklist", cl, "--filename", f, "--status", "1")
        assert cp.returncode == 0, cp.stderr

    cp = _run(sandbox, "03-NLP-check.py", "--checklist", cl, "--csvs-dir", "processed_data/csvs/")
    assert cp.returncode == 0, cp.stdout + cp.stderr

    # ---- 第 4 步: 合并 + 终检 ----
    cp = _run(sandbox, "04-merge.py", "--checklist", cl,
              "--csvs-dir", "processed_data/csvs/", "--output", "processed_data/final.csv")
    assert cp.returncode == 0, cp.stderr

    rows = list(csv.reader((sandbox / "processed_data" / "final.csv").open(encoding="utf-8")))
    assert rows[0] == HEADER_LINE.split(",")
    assert len(rows) == 3  # 表头 + 2 数据行; OCR=0 的 2011-08-12 2.png 不进入
    assert rows[1][0] == "ACME, Inc."  # 含逗号的值经 csv 转义后还原
    assert rows[2][0] == "Beta Ltd"
    assert [r[0] for r in rows[1:]] == ["ACME, Inc.", "Beta Ltd"]  # checklist 行序

    unc = json.loads((sandbox / "uncertain.json").read_text(encoding="utf-8"))
    assert unc["2011-08-14 1"][0]["field"] == "价格敏感度"
    assert "2011-08-12 1" not in unc  # 无 uncertain 的文件不产生键
