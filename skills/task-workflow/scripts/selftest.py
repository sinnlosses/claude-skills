#!/usr/bin/env python3
"""`legacy.py`（旧形式の読み取り）と `init.py` の自己テスト。

使い方: python3 selftest.py

標準ライブラリだけで動く（このリポジトリに依存パッケージを増やさないため）。
落ちたら非0で終わる。`task.py` 一式は `selftest_task.py` が見る。

**ここで守っているのは「モデルが誤読しない出力を返すこと」**。
`INVALID` と traceback の区別、旧形式で骨組みを混ぜないこと、既存ファイルを上書きしないこと
といった、間違えると*静かに*データを失う／原因を取り違える経路を重点的に見る。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import legacy  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, os.path.join(HERE, script), *args],
        capture_output=True,
        text=True,
    )


def write(path: str, body: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


# --- legacy: tasks.json の読み取り ------------------------------------------


def test_load_tasks() -> None:
    print("legacy.load_tasks")
    with tempfile.TemporaryDirectory() as d:
        ok, err = legacy.load_tasks(write(os.path.join(d, "a.json"), json.dumps([{"id": "T-001"}])))
        check("正しいファイルは (中身, None)", err is None and len(ok) == 1, str(err))

        _, err = legacy.load_tasks(write(os.path.join(d, "b.json"), "[{"))
        check("壊れた JSON は理由を返す（例外を投げない）", err is not None and "JSON" in err, str(err))

        _, err = legacy.load_tasks(write(os.path.join(d, "c.json"), '{"a":1}'))
        check("配列でなければ理由を返す", err is not None and "配列ではない" in err, str(err))

        _, err = legacy.load_tasks(write(os.path.join(d, "d.json"), "[1,2]"))
        check("要素がオブジェクトでなければ理由を返す", err is not None and "オブジェクト" in err, str(err))

        _, err = legacy.load_tasks(os.path.join(d, "無い.json"))
        check("開けないファイルも理由を返す", err is not None, str(err))


# --- legacy: progress.md の節分け -------------------------------------------


def test_progress_sections() -> None:
    print("legacy: progress.md の節")
    body = (
        "# 進捗\n\n## 完了したこと\n\n"
        "### 2026-03-03 c（T-003）\nccc\n\n"
        "### 2026-02-02 b（T-002）\nbbb\n\n"
        "### 2026-01-01 a（T-001）\naaa\n\n"
        "## 未解決\n\n- なし\n"
    )
    head, sections, tail = legacy.split_done_section(body)
    check("小節を3つに割る", sections is not None and len(sections) == 3)
    check("小節の日付を読む", [s.date for s in sections or []] == ["2026-03-03", "2026-02-02", "2026-01-01"])
    check("「未解決」以降は後ろに残す", tail.startswith("## 未解決"))
    check("見出しは前に残す", head.rstrip().endswith("## 完了したこと"))

    _, none_sections, _ = legacy.split_done_section("# 進捗\n\n## 未解決\n")
    check("「完了したこと」節が無ければ None", none_sections is None)

    _, mid, _ = legacy.split_named_section(body, "## 未解決")
    check("名前つきの節を切り出す", mid.startswith("## 未解決") and "- なし" in mid, mid)
    _, mid, _ = legacy.split_named_section(body, "## 注意")
    check("無い節は空文字", mid == "")

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "docs", "history", "progress.md")
        legacy.prepend_to_history(p, legacy.PROGRESS_ARCHIVE_HEADER, "### 2026-01-01 古い\n")
        legacy.prepend_to_history(p, legacy.PROGRESS_ARCHIVE_HEADER, "### 2026-02-02 新しい\n")
        text = open(p, encoding="utf-8").read()
        check(
            "履歴には新しいものを見出しの直後に差し込む",
            text.startswith(legacy.PROGRESS_ARCHIVE_HEADER) and text.index("新しい") < text.index("古い"),
            text,
        )


# --- init.py ----------------------------------------------------------------


def test_init() -> None:
    print("init.py")
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            r = run("init.py", "develop")
            check("direction.md だけを作る", r.stdout.count("CREATED") == 1 and "direction.md" in r.stdout, r.stdout)
            check("tasks.json・progress.md は作らない", not os.path.exists("develop/tasks.json") and not os.path.exists("develop/progress.md"))
            check("CLAUDE.md が無ければ MISSING", "MISSING\tCLAUDE.md" in r.stdout, r.stdout)

            created = open("develop/direction.md", encoding="utf-8").read()
            check(
                "作った direction.md に2節がある",
                all(h in created for h in ("## ユーザーから", "## エージェントのドラフト")),
                created,
            )

            r = run("init.py", "develop")
            check("2回目は上書きしない", "KEPT" in r.stdout and "CREATED" not in r.stdout, r.stdout)
            check("まっさらなら OK", "OK: 未対応の指示は無い" in r.stdout, r.stdout)

            write("develop/direction.md", "# 未対応の指示メモ\n\nこれをやって\n")
            r = run("init.py", "develop")
            check(
                "節が無いファイルは全体を「ユーザーから」とみなして PENDING",
                "PENDING:" in r.stdout and "ユーザーから1行" in r.stdout,
                r.stdout,
            )

            write(
                "develop/direction.md",
                "# 未対応の指示メモ\n\n## ユーザーから\nこれをやって\n\n"
                "## エージェントのドラフト\nこれも直したい\n",
            )
            r = run("init.py", "develop")
            check(
                "節ごとの行数を分けて数える",
                "ユーザーから1行" in r.stdout and "エージェントのドラフト1行" in r.stdout,
                r.stdout,
            )

            write("CLAUDE.md", "# x\n\n## タスク運用\n\n- 検証コマンド: `なし`\n- 整形コマンド: `なし`\n")
            r = run("init.py", "develop")
            check("ブランチ行が無ければ MISSING_LINE", "MISSING_LINE" in r.stdout and "- ブランチ:" in r.stdout, r.stdout)

            write("CLAUDE.md", "# x\n\n## タスク運用\n\n- 検証コマンド: `なし`\n- 整形コマンド: `なし`\n- ブランチ: 自分で切らない\n")
            r = run("init.py", "develop")
            check("ブランチの先頭語が語彙に無ければ BAD_BRANCH", "BAD_BRANCH" in r.stdout, r.stdout)

            write("CLAUDE.md", "# x\n\n## タスク運用\n\n- 検証コマンド: `なし`\n- 整形コマンド: `なし`\n- ブランチ: 切らない。main に直接積む\n")
            r = run("init.py", "develop")
            check("3行そろい語彙に当たれば OK", "OK\tCLAUDE.md" in r.stdout, r.stdout)

            r = run("init.py", "--help")
            check("打ち間違いをディレクトリにしない", r.returncode == 2 and not os.path.exists("--help"))
        finally:
            os.chdir(cwd)

    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            write("develop/tasks.json", "[]\n")
            r = run("init.py", "develop")
            check("旧形式なら LEGACY（終了コード5）", r.returncode == 5 and r.stdout.startswith("LEGACY\t"), r.stdout)
            check("旧形式には骨組みを混ぜない", not os.path.exists("develop/direction.md"))
        finally:
            os.chdir(cwd)


def main() -> None:
    for t in (test_load_tasks, test_progress_sections, test_init):
        t()
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
