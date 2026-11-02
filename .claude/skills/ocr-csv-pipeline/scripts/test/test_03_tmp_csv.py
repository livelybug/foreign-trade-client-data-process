"""test_03_tmp_csv.py — 步骤 03-tmp-csv 端到端测试。

参照 test_01_filename_index.py 风格:
  * subprocess + .venv/bin/python 跑真实脚本
  * tmp_path 隔离
  * happy path + 关键错误分支

覆盖:
  * 成功路径: 简单值;带逗号/引号的 CSV 格式值(验证 RFC 4180 解析)
  * 错误路径: --txt 缺失 / --field-table 缺失 / --values 列数不匹配 / 字段表无表头
  * uncertain 成功路径: 写入 JSON dict({basename: [items...]})/ 同一 basename 二次追加 / 跨 basename 合并 / no-op / 空数组
  * uncertain 并发追加: 两个子进程真正并发写同一 uncertain.json,验证锁覆盖 read-modify-write 全程
  * uncertain 错误路径: JSON 解析失败 / 非 list / 元素非 dict / 缺必填 / options 类型错
"""

from __future__ import annotations

import concurrent.futures
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
SCRIPT = SCRIPTS / "03-tmp-csv.py"


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


# ---- 共享夹具: txt + 3 字段的 field table ----

@pytest.fixture
def setup(tmp_path: Path):
    txt = tmp_path / "in.txt"
    txt.write_text("dummy ocr text", encoding="utf-8")
    ft = tmp_path / "fields.csv"
    ft.write_text("col1,col2,col3\n", encoding="utf-8")
    out = tmp_path / "csvs" / "out.csv"
    return txt, ft, out


# ---- uncertain 测试数据(模块级常量) ----

UNC_A = json.dumps(
    [
        {
            "field": "价格敏感度",
            "question": "期望是高/中/低 还是 高敏感?",
            "options": ["高/中/低", "高敏感"],
        },
        {
            "field": "电话",
            "question": "多个电话选哪个?",
            "value": "+1-555-0100; +1-555-0200",
        },
    ],
    ensure_ascii=False,
)

UNC_OPTS_ONLY = json.dumps(
    [{"field": "客户类型", "question": "是分销商还是代理商?", "options": ["分销商", "代理商"]}],
    ensure_ascii=False,
)

UNC_VAL_ONLY = json.dumps(
    [{"field": "公司网址", "question": "这是官网吗?", "value": "example.com"}],
    ensure_ascii=False,
)


# ---- 成功路径 ----

def test_happy_path_simple_values(setup: tuple[Path, Path, Path]) -> None:
    """简单值: 写入 2 行 CSV,header 取自 field table,data 取自 --values。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "3 fields" in cp.stdout

    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [["col1", "col2", "col3"], ["a", "b", "c"]]


def test_happy_path_values_with_comma_and_quote(setup: tuple[Path, Path, Path]) -> None:
    """--values 中含逗号和引号 → 按 RFC 4180 解析,不被逗号切碎。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", '"ACME, Corp",USA,"分销,商"',
        "--output", str(out),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["ACME, Corp", "USA", "分销,商"]


# ---- uncertain 成功路径 ----

def test_uncertain_appends_to_json_dict(setup: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """--uncertain 非空 JSON 数组 -> 写入顶层 dict 的 basename 键,值为 items 列表。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.json"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", UNC_A,
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert "appended 2 uncertain" in cp.stdout

    # 顶层是 dict,key = stem = "in",value = [item, item]
    data = json.loads(unc.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert list(data.keys()) == ["in"]
    items = data["in"]
    assert isinstance(items, list) and len(items) == 2

    # 第 1 条:options,无 value
    assert items[0]["field"] == "价格敏感度"
    assert items[0]["question"] == "期望是高/中/低 还是 高敏感?"
    assert items[0]["options"] == ["高/中/低", "高敏感"]
    assert "value" not in items[0]

    # 第 2 条:value,无 options
    assert items[1]["field"] == "电话"
    assert items[1]["question"] == "多个电话选哪个?"
    assert items[1]["value"] == "+1-555-0100; +1-555-0200"
    assert "options" not in items[1]


def test_uncertain_second_call_extends_same_key(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """两次 --uncertain 写入(同 basename) -> 同一键的 list 长度翻倍,不是覆盖。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.json"
    item = json.dumps(
        [{"field": "客户阶段", "question": "阶段定义?", "value": "初始"}],
        ensure_ascii=False,
    )
    for _ in range(2):
        cp = _run(
            "--txt", str(txt),
            "--field-table", str(ft),
            "--values", "a,b,c",
            "--output", str(out),
            "--uncertain", item,
            "--uncertain-path", str(unc),
        )
        assert cp.returncode == 0, f"stderr={cp.stderr}"

    data = json.loads(unc.read_text(encoding="utf-8"))
    # 同 basename 仍只有 1 个键,list 长度 = 2
    assert list(data.keys()) == ["in"]
    assert data["in"] == [
        {"field": "客户阶段", "question": "阶段定义?", "value": "初始"},
        {"field": "客户阶段", "question": "阶段定义?", "value": "初始"},
    ]


def test_uncertain_different_basenames_make_separate_keys(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """两个不同 stem 的 txt 写入同一 uncertain.json -> 顶层 dict 有 2 个键。"""
    _, ft, out = setup
    unc = tmp_path / "unc.json"
    item_x = json.dumps(
        [{"field": "客户类型", "question": "X 类?", "value": "分销商"}],
        ensure_ascii=False,
    )
    item_y = json.dumps(
        [{"field": "客户类型", "question": "Y 类?", "value": "终端用户"}],
        ensure_ascii=False,
    )

    # 自己造两个 stem 不同的 txt(setup 里只有 in.txt)
    txt_x = tmp_path / "doc-x.txt"
    txt_x.write_text("dummy", encoding="utf-8")
    txt_y = tmp_path / "doc-y.txt"
    txt_y.write_text("dummy", encoding="utf-8")

    for t, item in [(txt_x, item_x), (txt_y, item_y)]:
        cp = _run(
            "--txt", str(t),
            "--field-table", str(ft),
            "--values", "a,b,c",
            "--output", str(out),
            "--uncertain", item,
            "--uncertain-path", str(unc),
        )
        assert cp.returncode == 0, f"stderr={cp.stderr}"

    data = json.loads(unc.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"doc-x", "doc-y"}
    assert data["doc-x"][0]["value"] == "分销商"
    assert data["doc-y"][0]["value"] == "终端用户"


def test_uncertain_omitted_does_not_create_file(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """不传 --uncertain 时,即使显式指定 --uncertain-path,文件也不应被创建。"""
    txt, ft, out = setup
    unc = tmp_path / "should_not_exist.json"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert not unc.exists()


def test_uncertain_empty_array_equivalent_to_omitted(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain='[]' 等价于不传,不会写入文件。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.json"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", "[]",
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    assert not unc.exists()


def test_uncertain_options_preserved_in_json(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """只有 options,无 value -> JSON 中只保留 options,不引入 value 键。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.json"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", UNC_OPTS_ONLY,
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    data = json.loads(unc.read_text(encoding="utf-8"))
    assert data["in"][0]["options"] == ["分销商", "代理商"]
    assert "value" not in data["in"][0]


def test_uncertain_value_preserved_in_json(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """只有 value,无 options -> JSON 中只保留 value,不引入 options 键。"""
    txt, ft, out = setup
    unc = tmp_path / "unc.json"
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", UNC_VAL_ONLY,
        "--uncertain-path", str(unc),
    )
    assert cp.returncode == 0, f"stderr={cp.stderr}"
    data = json.loads(unc.read_text(encoding="utf-8"))
    assert data["in"][0]["value"] == "example.com"
    assert "options" not in data["in"][0]


def test_concurrent_uncertain_appends(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """两个子进程真正并发追加到同一 uncertain.json: 验证锁覆盖 read-modify-write 全程。

    append_uncertain 在 FileLock 内完成 load/extend/write,串行化保证:
    (1) 两个进程都成功返回 0
    (2) 两条 item 都在文件 dict 中(无丢失更新)
    (3) 文件始终是合法 JSON dict(无拼接污染)
    """
    txt, ft, out = setup
    unc = tmp_path / "unc.json"

    item_a = json.dumps(
        [{"field": "field-A", "question": "Q-A?"}], ensure_ascii=False,
    )
    item_b = json.dumps(
        [{"field": "field-B", "question": "Q-B?"}], ensure_ascii=False,
    )

    p1 = subprocess.Popen(
        [str(VENV_PY), str(SCRIPT),
         "--txt", str(txt), "--field-table", str(ft),
         "--values", "a,b,c", "--output", str(out),
         "--uncertain", item_a, "--uncertain-path", str(unc)],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    p2 = subprocess.Popen(
        [str(VENV_PY), str(SCRIPT),
         "--txt", str(txt), "--field-table", str(ft),
         "--values", "a,b,c", "--output", str(out),
         "--uncertain", item_b, "--uncertain-path", str(unc)],
        cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    # 真正并发等待:同时跑两个 communicate()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(p1.communicate)
        f2 = ex.submit(p2.communicate)
        _, err1 = f1.result()
        _, err2 = f2.result()
    assert p1.returncode == 0, f"p1 stderr={err1}"
    assert p2.returncode == 0, f"p2 stderr={err2}"

    # 锁覆盖全程,文件必须仍是合法 JSON dict
    data = json.loads(unc.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert set(data.keys()) == {"in"}
    fields = [it["field"] for it in data["in"]]
    # 两条都落地(顺序不固定,只要都在)
    assert "field-A" in fields and "field-B" in fields
    assert len(data["in"]) == 2


# ---- 错误路径 ----

def test_missing_txt_exits_1(tmp_path: Path) -> None:
    ft = tmp_path / "fields.csv"
    ft.write_text("a,b\n", encoding="utf-8")
    cp = _run(
        "--txt", str(tmp_path / "no.txt"),
        "--field-table", str(ft),
        "--values", "1,2",
        "--output", str(tmp_path / "out.csv"),
    )
    assert cp.returncode == 1
    assert "不存在" in cp.stderr or "txt" in cp.stderr.lower()


def test_missing_field_table_exits_1(tmp_path: Path) -> None:
    txt = tmp_path / "in.txt"
    txt.write_text("x", encoding="utf-8")
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(tmp_path / "no.csv"),
        "--values", "1",
        "--output", str(tmp_path / "out.csv"),
    )
    assert cp.returncode == 1


def test_values_column_mismatch_exits_1(setup: tuple[Path, Path, Path]) -> None:
    """field table 有 3 列, --values 只有 2 个值 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b",
        "--output", str(out),
    )
    assert cp.returncode == 1
    assert "字段数" in cp.stderr


def test_empty_field_table_exits_1(tmp_path: Path) -> None:
    """field table 是空文件 → 报 'no header',exit 1。"""
    txt = tmp_path / "in.txt"
    txt.write_text("x", encoding="utf-8")
    ft = tmp_path / "empty.csv"
    ft.write_text("", encoding="utf-8")
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "1",
        "--output", str(tmp_path / "out.csv"),
    )
    assert cp.returncode == 1
    assert "no header" in cp.stderr


# ---- uncertain 错误路径 ----

def test_uncertain_json_parse_error_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 不是合法 JSON → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", "not-json",
        "--uncertain-path", str(tmp_path / "unc.json"),
    )
    assert cp.returncode == 1
    assert "JSON" in cp.stderr


def test_uncertain_not_list_exits_1(setup: tuple[Path, Path, Path], tmp_path: Path) -> None:
    """--uncertain 是合法 JSON 但不是数组 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '{"field":"x","question":"y"}',  # JSON object, not array
        "--uncertain-path", str(tmp_path / "unc.json"),
    )
    assert cp.returncode == 1
    assert "数组" in cp.stderr


def test_uncertain_element_not_dict_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 数组元素不是对象 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '["just a string"]',
        "--uncertain-path", str(tmp_path / "unc.json"),
    )
    assert cp.returncode == 1
    assert "对象" in cp.stderr


def test_uncertain_missing_required_field_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 元素缺 field → exit 1(缺 question 同理)。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '[{"question":"x"}]',  # 缺 field
        "--uncertain-path", str(tmp_path / "unc.json"),
    )
    assert cp.returncode == 1
    assert "field" in cp.stderr


def test_uncertain_invalid_options_type_exits_1(
    setup: tuple[Path, Path, Path], tmp_path: Path,
) -> None:
    """--uncertain 元素 options 不是字符串数组 → exit 1。"""
    txt, ft, out = setup
    cp = _run(
        "--txt", str(txt),
        "--field-table", str(ft),
        "--values", "a,b,c",
        "--output", str(out),
        "--uncertain", '[{"field":"x","question":"y","options":"not-a-list"}]',
        "--uncertain-path", str(tmp_path / "unc.json"),
    )
    assert cp.returncode == 1
    assert "options" in cp.stderr
