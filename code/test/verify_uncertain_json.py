"""verify_uncertain_json.py — 独立验证脚本,核对 03-tmp-csv.py 的 uncertain.json 语义契约。

不在 pytest 套件内(它需要看子进程真实并发时文件系统行为,放在 tmp 隔离目录跑,不污染仓库)。

跑法:
    uv run python code/test/verify_uncertain_json.py

覆盖 5 条契约:
    1. 顶层必须是 dict,不是 list / scalar
    2. 同一 basename 多次 append 是 extend,不是覆盖
    3. 不同 basename 各占一个 key,互不污染
    4. read-modify-write 整体在锁内,真并发 2 子进程对同一文件 → 两条都在,文件始终是合法 JSON
    5. 写盘格式 indent=2 + ensure_ascii=False + 末尾换行
"""
from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = PROJECT_ROOT / "code" / "03-tmp-csv.py"


def _run_03(tmp: Path, txt_name: str, items: list[dict]) -> None:
    """起一个子进程跑 03-tmp-csv.py,带一份 uncertain items,失败立即退出 1。"""
    txt = tmp / txt_name
    txt.write_text("dummy", encoding="utf-8")
    ft = tmp / "fields.csv"
    ft.write_text("c1,c2,c3\n", encoding="utf-8")
    unc = tmp / "unc.json"
    cp = subprocess.run(
        [
            "uv", "run", "python", str(SCRIPT),
            "--txt", str(txt),
            "--field-table", str(ft),
            "--values", "a,b,c",
            "--output", str(tmp / "out.csv"),
            "--uncertain", json.dumps(items, ensure_ascii=False),
            "--uncertain-path", str(unc),
        ],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    if cp.returncode != 0:
        print(f"[FAIL] subprocess exit={cp.returncode}\nstderr={cp.stderr}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="unc_verify_"))
    try:
        # ---- (1) 顶层是 dict ----
        _run_03(tmp, "a.txt", [{"field": "F", "question": "Q", "value": "v"}])
        unc = tmp / "unc.json"
        data = json.loads(unc.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"top-level must be dict, got {type(data).__name__}"
        assert list(data.keys()) == ["a"], f"keys={list(data.keys())}"
        print("[OK] 顶层是 dict,key=stem")

        # ---- (2) 同一 basename 二次 append 是 extend ----
        _run_03(tmp, "a.txt", [{"field": "F2", "question": "Q2", "value": "v2"}])
        data2 = json.loads(unc.read_text(encoding="utf-8"))
        assert len(data2["a"]) == 2, f"a 应该有 2 项,实际 {len(data2['a'])}"
        assert [x["field"] for x in data2["a"]] == ["F", "F2"]
        print("[OK] 同 basename 二次 append 是 extend")

        # ---- (3) 不同 basename 各占一 key ----
        _run_03(tmp, "b.txt", [{"field": "FB", "question": "QB", "value": "vb"}])
        data3 = json.loads(unc.read_text(encoding="utf-8"))
        assert set(data3.keys()) == {"a", "b"}
        assert data3["b"][0]["field"] == "FB"
        print("[OK] 不同 basename 各占一 key")

        # ---- (4) 写盘格式: indent=2 + ensure_ascii=False + 末尾 \n ----
        _run_03(tmp, "中文.txt", [{"field": "中文字段", "question": "中文问?", "value": "中文值"}])
        raw = unc.read_text(encoding="utf-8")
        assert "中文字段" in raw, "ensure_ascii=False 必须保留中文原字符"
        # indent=2 → 顶层 dict 后的键行有 2 空格缩进
        assert "\n  \"" in raw or raw.startswith("  \""), "应当有 2 空格缩进"
        # 末尾换行
        assert raw.endswith("\n")
        print("[OK] 写盘格式: 中文保留 / 2 空格缩进 / 末尾换行")

        # ---- (5) 真并发 2 子进程对同一 uncertain.json ----
        # 用独立目录,避免前面累积数据干扰
        tmp2 = Path(tempfile.mkdtemp(prefix="unc_conc_"))
        try:
            ft2 = tmp2 / "fields.csv"
            ft2.write_text("c1,c2,c3\n", encoding="utf-8")
            out2 = tmp2 / "out.csv"
            unc2 = tmp2 / "unc.json"

            def one(idx: int) -> int:
                txt = tmp2 / f"x{idx}.txt"
                txt.write_text("dummy", encoding="utf-8")
                return subprocess.run(
                    [
                        "uv", "run", "python", str(SCRIPT),
                        "--txt", str(txt),
                        "--field-table", str(ft2),
                        "--values", "a,b,c",
                        "--output", str(out2),
                        "--uncertain", json.dumps(
                            [{"field": f"F{idx}", "question": f"Q{idx}"}],
                            ensure_ascii=False,
                        ),
                        "--uncertain-path", str(unc2),
                    ],
                    cwd=PROJECT_ROOT, capture_output=True, text=True,
                ).returncode

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                results = list(ex.map(one, range(2)))
            assert all(rc == 0 for rc in results), f"并发子进程失败: {results}"
            data_c = json.loads(unc2.read_text(encoding="utf-8"))
            assert isinstance(data_c, dict)
            assert set(data_c.keys()) == {"x0", "x1"}, f"keys={list(data_c.keys())}"
            # 两个 stem 各有 1 条,且其 field 对应
            fields = {k: [it["field"] for it in v] for k, v in data_c.items()}
            assert fields == {"x0": ["F0"], "x1": ["F1"]}, f"fields={fields}"
            print("[OK] 真并发 2 子进程: 文件仍是合法 dict,无丢失更新")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

        print("\n=== 独立验证全部通过 ===")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
