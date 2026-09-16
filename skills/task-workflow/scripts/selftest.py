#!/usr/bin/env python3
"""task-workflow の3スクリプトの自己テスト。

使い方: python3 selftest.py

標準ライブラリだけで動く（このリポジトリに依存パッケージを増やさないため）。
落ちたら非0で終わる。

**ここで守っているのは「モデルが誤読しない出力を返すこと」**。
判定そのものより、`INVALID` と traceback の区別・新しい順の保全・書き戻しの拒否といった、
間違えると*静かに*データを失う／原因を取り違える経路を重点的に見る。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import taskfiles  # noqa: E402

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


def task(tid: str, **kw) -> dict:
    t = {
        "id": tid,
        "difficulty": "haiku",
        "loopable": "Y",
        "dependencies": [],
        "summary": f"{tid} のやること",
        "task": "## 背景\n本文\n",
        "status": "todo",
        "passes": False,
        "evidence": "",
    }
    t.update(kw)
    return t


def write(path: str, body: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def write_tasks(path: str, tasks: list[dict]) -> str:
    return write(path, json.dumps(tasks, ensure_ascii=False))


# --- taskfiles ----------------------------------------------------------


def test_load_tasks() -> None:
    print("taskfiles.load_tasks")
    with tempfile.TemporaryDirectory() as d:
        ok, err = taskfiles.load_tasks(write_tasks(os.path.join(d, "a.json"), [task("T-001")]))
        check("正しいファイルは (中身, None)", err is None and len(ok) == 1, str(err))

        _, err = taskfiles.load_tasks(write(os.path.join(d, "b.json"), "[{"))
        check("壊れた JSON は理由を返す（例外を投げない）", err is not None and "JSON" in err, str(err))

        _, err = taskfiles.load_tasks(write(os.path.join(d, "c.json"), '{"a":1}'))
        check("配列でなければ理由を返す", err is not None and "配列ではない" in err, str(err))

        _, err = taskfiles.load_tasks(write(os.path.join(d, "d.json"), "[1,2]"))
        check("要素がオブジェクトでなければ理由を返す", err is not None and "オブジェクト" in err, str(err))

        _, err = taskfiles.load_tasks(os.path.join(d, "無い.json"))
        check("開けないファイルも理由を返す", err is not None, str(err))


def test_done_plan() -> None:
    print("taskfiles.done_plan")
    todos = [task(f"T-{i:03d}") for i in range(50)]
    _, _, hit = taskfiles.done_plan(todos, 10, 10)
    check("todo はサイズにも件数にも数えない", hit is False)

    dones = [task(f"T-{i:03d}", status="done") for i in range(10)]
    done, _, hit = taskfiles.done_plan(dones, 10, 10**9)
    check("done が件数に達したら鳴る", hit is True and len(done) == 10)

    _, size, hit = taskfiles.done_plan(dones[:1], 99, 10)
    check("done が文字数を超えたら鳴る", hit is True and size > 10)

    # サイズは**文字数**。日本語でバイト数と取り違えていないこと。
    ja = [task("T-001", status="done", summary="あ" * 100, task="", evidence="")]
    _, size, _ = taskfiles.done_plan(ja, 99, 10**9)
    check("サイズは文字数で測る（UTF-8 バイト数ではない）", size < 400, f"size={size}")


def test_progress_sections() -> None:
    print("taskfiles: progress.md の節")
    body = (
        "# 進捗\n\n## 完了したこと\n\n"
        "### 2026-03-03 c（T-003）\nccc\n\n"
        "### 2026-02-02 b（T-002）\nbbb\n\n"
        "### 2026-01-01 a（T-001）\naaa\n\n"
        "## 未解決\n\nなし\n"
    )
    head, sections, tail = taskfiles.split_done_section(body)
    check("小節を3つに割る", sections is not None and len(sections) == 3)
    check("「未解決」以降は後ろに残す", tail.startswith("## 未解決"))
    check("見出しは前に残す", head.rstrip().endswith("## 完了したこと"))
    check("新しい順なら True", taskfiles.is_newest_first(sections))

    rev = list(reversed(sections))
    check("古い順なら False（アーカイブを止める）", not taskfiles.is_newest_first(rev))

    _, none_sections, _ = taskfiles.split_done_section("# 進捗\n\n## 未解決\n")
    check("「完了したこと」節が無ければ None", none_sections is None)

    keep, move = taskfiles.progress_plan(sections, 2, 10**9)
    check("件数の予算で新しい2つを残す", [s.date for s in keep] == ["2026-03-03", "2026-02-02"])
    check("溢れた古いほうを移す", [s.date for s in move] == ["2026-01-01"])

    keep, move = taskfiles.progress_plan(sections, 99, 1)
    check("1小節で予算を超えても最低1小節は残す", len(keep) == 1 and len(move) == 2)


# --- status.py ----------------------------------------------------------


def test_status() -> None:
    print("status.py")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "tasks.json")

        r = run("status.py", os.path.join(d, "無い.json"))
        check("ファイルが無ければ MISSING", r.stdout.strip() == "MISSING" and r.returncode == 0)

        write_tasks(p, [])
        r = run("status.py", p)
        check("空なら EMPTY", r.stdout.startswith("EMPTY") and r.returncode == 0)

        write(p, "[{")
        r = run("status.py", p)
        check(
            "壊れた JSON は INVALID 行（traceback ではない）",
            r.returncode == 0 and r.stdout.startswith("INVALID\t") and not r.stderr,
            r.stdout + r.stderr,
        )

        broken = {"id": "T-001", "status": "todo", "summary": "x"}
        write_tasks(p, [broken])
        r = run("status.py", p)
        lines = r.stdout.splitlines()
        check(
            "フィールドが欠けても落ちない",
            r.returncode == 0 and not r.stderr,
            r.stderr,
        )
        check("欠けた列は ? で埋める", lines and lines[0].split("\t")[2] == "?", lines[0] if lines else "")
        mf = [l for l in lines if l.startswith("missing_field\t")]
        check(
            "missing_field 行が欠けた名前を挙げる",
            mf and "difficulty" in mf[0] and "dependencies" in mf[0] and "passes" in mf[0],
            mf[0] if mf else "行が無い",
        )

        write_tasks(p, [task("T-001", status="done", passes=True), task("T-002", dependencies=["T-001"])])
        r = run("status.py", p)
        rows = [l.split("\t") for l in r.stdout.splitlines() if l.startswith("T-")]
        check("依存が done なら READY", rows[1][5] == "READY", rows[1][5])

        write_tasks(p, [task("T-001"), task("T-002", dependencies=["T-001"])])
        r = run("status.py", p)
        rows = [l.split("\t") for l in r.stdout.splitlines() if l.startswith("T-")]
        check("依存が todo なら BLOCKED", rows[1][5] == "BLOCKED:T-001", rows[1][5])

        # アーカイブ済み（tasks.json に無い）依存は完了扱い。
        write_tasks(p, [task("T-009", dependencies=["T-001"])])
        r = run("status.py", p)
        rows = [l.split("\t") for l in r.stdout.splitlines() if l.startswith("T-")]
        check("存在しない依存はアーカイブ済み＝READY", rows[0][5] == "READY", rows[0][5])

        write_tasks(p, [task("T-001", summary="あ" * 60)])
        r = run("status.py", p)
        check(
            "全角60文字は表示幅120桁として long_summary に出る",
            any(l.startswith("long_summary\t1\t") for l in r.stdout.splitlines()),
        )

        write_tasks(p, [task("T-001", status="done", summary="あ" * 60, passes=True)])
        r = run("status.py", p)
        check(
            "done の長い summary は遡って責めない",
            any(l.startswith("long_summary\t0\t") for l in r.stdout.splitlines()),
        )


# --- archive.py ---------------------------------------------------------


def test_archive() -> None:
    print("archive.py")
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            os.makedirs("develop")
            p = "develop/tasks.json"

            write(p, "[{")
            r = run("archive.py", p)
            check(
                "読めないファイルには書き戻さない",
                "tasks\tINVALID" in r.stdout and "書き換えずに中止" in r.stdout,
                r.stdout,
            )
            check("壊れたファイルは元のまま", open(p, encoding="utf-8").read() == "[{")

            dones = [task(f"T-{i:03d}", status="done", passes=True, evidence="e") for i in range(1, 11)]
            keep = task("T-011")
            write_tasks(p, dones + [keep])

            r = run("archive.py", p, "--dry-run")
            check("--dry-run は書かない", "DRY-RUN" in r.stdout)
            check("--dry-run 後もファイルは元のまま", len(json.load(open(p, encoding="utf-8"))) == 11)

            r = run("archive.py", p)
            check("トリガー到達で MOVED", "tasks\tMOVED\t10件" in r.stdout, r.stdout)
            left = json.load(open(p, encoding="utf-8"))
            check("todo は残る", [t["id"] for t in left] == ["T-011"])
            arch = open("docs/history/tasks.md", encoding="utf-8").read()
            check("全 done がアーカイブに載る", all(f"## T-{i:03d}" in arch for i in range(1, 11)))
            check("evidence も移る", "**evidence**:" in arch)
            check("本文も移る", "## 背景" in arch)

            r = run("archive.py", p)
            check("2回目は NOOP（トリガー未達）", "NOOP" in r.stdout, r.stdout)
        finally:
            os.chdir(cwd)


def test_archive_progress_order() -> None:
    print("archive.py: progress.md の並び")
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            os.makedirs("develop")
            p = write_tasks("develop/tasks.json", [task("T-001")])
            body = "# 進捗\n\n## 完了したこと\n\n" + "".join(
                f"### 2026-01-{i:02d} 作業{i}（T-{i:03d}）\n本文{i}\n\n" for i in range(9, 0, -1)
            ) + "## 未解決\n\nなし\n"
            write("develop/progress.md", body)

            r = run("archive.py", p)
            check("予算超過で MOVED", "progress\tMOVED" in r.stdout, r.stdout)
            left = open("develop/progress.md", encoding="utf-8").read()
            check("新しい5小節が残る", "2026-01-09" in left and "2026-01-05" in left)
            check("古い小節は消える", "2026-01-04" not in left)
            check("「未解決」節は残る", "## 未解決" in left)
            arch = open("docs/history/progress.md", encoding="utf-8").read()
            check("移した先に古い小節がある", "2026-01-04" in arch and "2026-01-01" in arch)
            check(
                "移した先も新しいものが上",
                arch.index("2026-01-04") < arch.index("2026-01-01"),
            )

            # 逆順のファイルには触らない（触ると新しいほうを捨てる）。
            write(
                "develop/progress.md",
                "# 進捗\n\n## 完了したこと\n\n"
                + "".join(
                    f"### 2026-02-{i:02d} 作業{i}\n本文{i}\n\n" for i in range(1, 10)
                ),
            )
            before = open("develop/progress.md", encoding="utf-8").read()
            r = run("archive.py", p)
            check("古い順に並んでいたら ERROR", "progress\tERROR" in r.stdout, r.stdout)
            check("ERROR のときは書き換えない", open("develop/progress.md", encoding="utf-8").read() == before)
        finally:
            os.chdir(cwd)


# --- init.py ------------------------------------------------------------


def test_init() -> None:
    print("init.py")
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            r = run("init.py", "develop")
            check("3ファイルを作る", r.stdout.count("CREATED") == 3, r.stdout)
            check("CLAUDE.md が無ければ MISSING", "MISSING\tCLAUDE.md" in r.stdout, r.stdout)
            # init.py が作る骨組みを、archive.py が節として認識できること。
            _, sections, _ = taskfiles.split_done_section(
                open("develop/progress.md", encoding="utf-8").read()
            )
            check("作った progress.md の節をアーカイブ側が見つけられる", sections is not None)

            r = run("init.py", "develop")
            check("2回目は上書きしない", r.stdout.count("KEPT") == 3 and "CREATED" not in r.stdout)
            check("既存 tasks.json は OK 判定", "OK: 0件" in r.stdout, r.stdout)

            write("develop/direction.md", "# 未対応の指示メモ\n\nこれをやって\n")
            r = run("init.py", "develop")
            check("未タスク化の指示は PENDING", "PENDING:" in r.stdout, r.stdout)

            write("CLAUDE.md", "# x\n\n## タスク運用\n\n- 検証コマンド: `なし`\n")
            r = run("init.py", "develop")
            check("整形コマンド行が無ければ MISSING_LINE", "MISSING_LINE" in r.stdout, r.stdout)

            write("CLAUDE.md", "# x\n\n## タスク運用\n\n- 検証コマンド: `なし`\n- 整形コマンド: `なし`\n")
            r = run("init.py", "develop")
            check("2行そろえば OK", "OK\tCLAUDE.md" in r.stdout, r.stdout)

            r = run("init.py", "--help")
            check("打ち間違いをディレクトリにしない", r.returncode == 2 and not os.path.exists("--help"))
        finally:
            os.chdir(cwd)


def main() -> None:
    for t in (
        test_load_tasks,
        test_done_plan,
        test_progress_sections,
        test_status,
        test_archive,
        test_archive_progress_order,
        test_init,
    ):
        t()
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
