#!/usr/bin/env python3
"""`task.py`（1件1ファイル＋台帳の形）の自己テスト。

使い方: python3 selftest_task.py

一時ディレクトリに git リポジトリと作業ツリー2本を作り、`task.py` を実際に
子プロセスで（並行するテストは同時に）起こして検証する。正典は
`docs/task-workflow-redesign.md`。落ちたら非0で終わる（`selftest.py` と同じ形）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ledger  # noqa: E402
import legacy  # noqa: E402
import taskfile  # noqa: E402

TASK_PY = os.path.join(HERE, "task.py")
BODY = "## 目的\nx\n\n## 完了条件\nx\n\n## 背景\nx\n"

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def write(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗: {r.stderr}")
    return r


def run_task(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, TASK_PY, *args], cwd=cwd, capture_output=True, text=True)


def start_task(cwd: str, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, TASK_PY, *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


def make_repo(
    tmp: str,
    branch: str = "既定",
    verify: str | None = None,
    base: str = "main",
    config_filename: str = "CLAUDE.md",
) -> tuple[str, str, str]:
    """`(本体, 作業ツリー1, 作業ツリー2)`。本体だけが主ブランチを出す。

    `branch`/`verify` は設定ファイル「## タスク運用」の `- ブランチ:`／`- 検証コマンド:` の値
    （6.1・6.3）。`verify` を省略すると行自体を書かない（`ship.read_verify_command` は
    `None` を返す＝打たない）。`base` は主ブランチの名前——リモートを持たない足場なので
    `ledger.base_branch` の順3（`main`・`master`・`trunk` のうち実在するもの）で決まる。
    `config_filename` は設定ファイルの置き場（既定 `CLAUDE.md`。T-020: `AGENTS.md` も同じ形で読める）。
    """
    main_path = os.path.join(tmp, "base")
    os.makedirs(main_path)
    git(main_path, "init", "-q", "-b", base)
    git(main_path, "config", "user.email", "test@example.com")
    git(main_path, "config", "user.name", "test")
    write(
        os.path.join(main_path, "develop", "direction.md"),
        "# 未対応の指示メモ\n\n## ユーザーから\n\n## エージェントのドラフト\n",
    )
    write(os.path.join(main_path, "docs", "history", "tasks.md"), "# 完了タスクのアーカイブ\n")
    config_md = "# x\n\n## タスク運用\n\n"
    if verify is not None:
        config_md += f"- 検証コマンド: {verify}\n"
    config_md += f"- ブランチ: {branch}\n"
    write(os.path.join(main_path, config_filename), config_md)
    write(os.path.join(main_path, "shared.txt"), "line1\n")
    git(main_path, "add", "-A")
    git(main_path, "commit", "-q", "-m", "init")

    wt1 = os.path.join(tmp, "wt1")
    wt2 = os.path.join(tmp, "wt2")
    git(main_path, "worktree", "add", "-q", "-b", "wt1-branch", wt1, base)
    git(main_path, "worktree", "add", "-q", "-b", "wt2-branch", wt2, base)
    return main_path, wt1, wt2


def body_file(dirpath: str, name: str = "body.md") -> str:
    return write(os.path.join(dirpath, name), BODY)


def commit_task(main_path: str, task: taskfile.Task) -> None:
    write(os.path.join(main_path, "develop", "task", f"{task.id}.md"), taskfile.render(task))
    git(main_path, "add", "-A")
    git(main_path, "commit", "-q", "-m", f"{task.id}を足す")


# --- taskfile.py ----------------------------------------------------------


def test_taskfile_parse() -> None:
    print("taskfile.parse / render / validate_new_body")
    ok_text = (
        "---\nid: T-001\nsummary: 例\nstatus: todo\ndifficulty: sonnet\nloopable: Y\n"
        "dependencies: []\n---\n本文\n"
    )
    task, err = taskfile.parse(ok_text)
    check("正しい6行は読める", err is None and task is not None and task.id == "T-001", str(err))
    check("本文がそのまま残る", task is not None and task.body == "本文\n")

    task, err = taskfile.parse(ok_text.replace("dependencies: []", "dependencies: [T-001, T-002]"))
    check(
        "dependenciesは', '区切りで読める",
        err is None and task is not None and task.dependencies == ("T-001", "T-002"),
        str(err),
    )

    _, err = taskfile.parse(ok_text.replace("dependencies: []", "dependencies: [T-001,T-002]"))
    check("区切りが','だけだとINVALID", err is not None, str(err))

    _, err = taskfile.parse(ok_text.replace("loopable: Y", "loopable: y"))
    check("loopableの小文字はINVALID", err is not None, str(err))

    _, err = taskfile.parse(ok_text.replace("status: todo", "status: doing"))
    check("着手中(doing)はファイルに書けないのでINVALID", err is not None, str(err))

    _, err = taskfile.parse(ok_text.replace("\n", "\r\n"))
    check("CRLFはINVALID", err is not None, str(err))

    task, err = taskfile.parse(ok_text.replace("summary: 例", "summary: `a: b` # c [d]"))
    check(
        "summaryは記号を含んでもそのまま",
        err is None and task is not None and task.summary == "`a: b` # c [d]",
        str(err),
    )

    task, err = taskfile.parse(ok_text.replace("summary: 例", "summary:   前後に空白   "))
    check(
        "summaryの前後の空白は落ちる", err is None and task is not None and task.summary == "前後に空白", str(err)
    )
    assert task is not None
    task2, err2 = taskfile.parse(taskfile.render(task))
    check("render→parseで往復する", err2 is None and task2 == task)

    check("目的・完了条件・背景が無い本文は拒む", taskfile.validate_new_body("## 目的\nx\n") is not None)
    check(
        "登録時にやること/結果を含む本文は拒む", taskfile.validate_new_body(BODY + "\n## やること\nx\n") is not None
    )
    check("正しい登録時の本文はOK", taskfile.validate_new_body(BODY) is None)


# --- task.py: 単独の作業ツリー ---------------------------------------------


def test_new_and_status_single_worktree() -> None:
    print("task.py new/status（単独の作業ツリー）")
    with tempfile.TemporaryDirectory() as tmp:
        _main_path, wt1, _wt2 = make_repo(tmp)

        r = run_task(
            wt1, "new", "--summary", "1件目", "--difficulty", "sonnet", "--loopable", "Y", "--body-file", body_file(wt1)
        )
        check("CREATEDで返る", r.returncode == 0 and r.stdout.startswith("CREATED\t"), r.stdout + r.stderr)
        task_id = r.stdout.split("\t")[1]
        check(
            "develop/task/T-xxx.md ができる",
            os.path.exists(os.path.join(wt1, "develop", "task", f"{task_id}.md")),
        )
        with open(os.path.join(wt1, "develop", "task", f"{task_id}.md"), encoding="utf-8") as f:
            written = f.read()
        check(
            "閉じる --- の次は空行1行で、末尾は改行1つ（整形ツールの検査に合う）",
            "\n---\n\n## " in written and "\n---\n\n\n" not in written and written.endswith("\n") and not written.endswith("\n\n"),
            written,
        )

        r = run_task(wt1, "status")
        check(
            "statusにlocalの印が出る",
            any(l.startswith(f"{task_id}\t") and "\tlocal\t" in l for l in r.stdout.splitlines()),
            r.stdout,
        )
        check("long_summary 行は0件", "\nlong_summary\t0\t-" in r.stdout, r.stdout)

        run_task(
            wt1, "new", "--summary", "あ" * 41, "--difficulty", "haiku", "--loopable", "Y", "--body-file", body_file(wt1)
        )
        r = run_task(wt1, "status")
        check("80桁を超える summary を long_summary に出す", "\nlong_summary\t1\t" in r.stdout, r.stdout)

        bad_body = write(os.path.join(wt1, "bad.md"), "## 目的\nx\n")
        r = run_task(
            wt1, "new", "--summary", "本文が足りない", "--difficulty", "haiku", "--loopable", "N", "--body-file", bad_body
        )
        check("必須節が無い本文は終了コード2", r.returncode == 2 and r.stdout == "", r.stdout + r.stderr)


def test_claim_and_release_single_worktree() -> None:
    print("task.py claim/release（単独の作業ツリー）")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp)
        commit_task(main_path, taskfile.Task("T-100", "既存タスク", "todo", "sonnet", "Y", (), BODY))

        r = run_task(wt1, "claim", "T-100")
        check(
            "CLAIMEDで返り、feature枝を切る",
            r.returncode == 0 and r.stdout.startswith("CLAIMED\tT-100"),
            r.stdout + r.stderr,
        )
        check("feature/T-100に移っている", ledger.current_branch(cwd=wt1) == "feature/T-100")

        r = run_task(wt1, "claim", "T-100")
        check("同じ作業ツリーからの2回目はTAKEN", r.returncode == 4 and r.stdout.startswith("TAKEN\t"), r.stdout)

        r = run_task(wt1, "release", "T-100")
        check("releaseでRELEASED", r.returncode == 0 and r.stdout.strip() == "RELEASED\tT-100", r.stdout)

        r = run_task(wt1, "release", "T-100")
        check(
            "2回目のreleaseもNOT_CLAIMEDで0終了",
            r.returncode == 0 and r.stdout.strip() == "NOT_CLAIMED\tT-100",
            r.stdout,
        )

        r = run_task(wt1, "claim", "T-999")
        check("存在しないIDはNOT_READY", r.returncode == 4 and r.stdout.startswith("NOT_READY\t"), r.stdout)


def test_new_missing_and_legacy() -> None:
    print("task.py: MISSING/LEGACY の判定")
    with tempfile.TemporaryDirectory() as tmp:
        empty_repo = os.path.join(tmp, "empty")
        os.makedirs(empty_repo)
        git(empty_repo, "init", "-q", "-b", "main")
        git(empty_repo, "config", "user.email", "test@example.com")
        git(empty_repo, "config", "user.name", "test")
        write(os.path.join(empty_repo, ".gitkeep"), "")
        git(empty_repo, "add", "-A")
        git(empty_repo, "commit", "-q", "-m", "init")
        r = run_task(empty_repo, "status")
        check("develop/direction.mdも無ければMISSING", r.returncode == 6 and r.stdout.strip() == "MISSING", r.stdout)

        write(os.path.join(empty_repo, "develop", "tasks.json"), "[]\n")
        git(empty_repo, "add", "-A")
        git(empty_repo, "commit", "-q", "-m", "legacy")
        r = run_task(empty_repo, "status")
        check("tasks.jsonがあればLEGACY", r.returncode == 5 and r.stdout.startswith("LEGACY\t"), r.stdout)


# --- legacy.py / task.py migrate（5.9・10章） -------------------------------
#
# **架空のタスクだけを使う**（実際のプロジェクトの tasks.json をフィクスチャにしない）。


def _make_legacy_repo(tmp: str, tasks: list[dict] | None = None, progress: str | None = None) -> str:
    """旧形式（`develop/tasks.json` あり）の一時リポジトリを1つ作る。`develop/direction.md` は
    実在のプロジェクトと同じく最初から置く（無いと移行後に `NEW` ではなく `MISSING` になる）。
    """
    repo = os.path.join(tmp, "legacy")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write(
        os.path.join(repo, "develop", "direction.md"),
        "# 未対応の指示メモ\n\n## ユーザーから\n\n## エージェントのドラフト\n",
    )
    write(os.path.join(repo, "docs", "history", "tasks.md"), "# 完了タスクのアーカイブ\n")
    if tasks is not None:
        write(os.path.join(repo, "develop", "tasks.json"), json.dumps(tasks, ensure_ascii=False, indent=2) + "\n")
    if progress is not None:
        write(os.path.join(repo, "develop", "progress.md"), progress)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


LEGACY_TASKS = [
    {
        "id": "T-001",
        "summary": "架空1件目",
        "task": "## やること\n\n架空のタスク本文1行目\n2行目\n",
        "status": "todo",
        "difficulty": "sonnet",
        "loopable": "Y",
        "dependencies": [],
        "passes": False,
        "evidence": "",
    },
    {
        "id": "T-002",
        "summary": "架空2件目（依存あり・完了）",
        "task": "架空のタスク本文2\n",
        "status": "done",
        "difficulty": "haiku",
        "loopable": "N",
        "dependencies": ["T-001"],
        "passes": True,
        "evidence": "bun test: 3 pass",
    },
    {
        "id": "T-003",
        "summary": "架空3件目（着手しない判断で閉じた）",
        "task": "架空のタスク本文3\n",
        "status": "done",
        "difficulty": "opus",
        "loopable": "Y",
        "dependencies": [],
        "passes": False,
        "evidence": "",
    },
]

LEGACY_PROGRESS = (
    "# 現在の状態\n\n(架空の前置きの説明文)\n\n"
    "## 完了したこと（このセッション）\n\n"
    "### 2026-01-02 架空のこと2\n\n本文2\n\n"
    "### 2026-01-01 架空のこと1\n\n本文1\n\n"
    "## 未解決\n\n- 架空の未解決事項\n\n"
    "## 注意\n\n- 架空の注意1\n- 架空の注意2\n"
)

LEGACY_PROGRESS_PREAMBLE_ONLY = (
    "# 現在の状態\n\n(架空の前置き文だけが残るケース)\n\n"
    "## 完了したこと（このセッション）\n\n"
    "### 2026-01-01 架空のこと\n\n本文\n\n"
    "## 未解決\n\n## 注意\n"
)


def test_legacy_convert_task() -> None:
    print("legacy.convert_task: 架空タスクの変換（10.1の表）")
    task, err = legacy.convert_task(
        {
            "id": "T-010",
            "summary": "todo",
            "task": "本文\n",
            "status": "todo",
            "difficulty": "sonnet",
            "dependencies": [],
            "passes": False,
            "evidence": "",
        }
    )
    check("loopableが無ければYで補う", err is None and task is not None and task.loopable == "Y", str(err))

    task, err = legacy.convert_task(
        {
            "id": "T-011",
            "summary": "done true",
            "task": "本文\n",
            "status": "done",
            "difficulty": "haiku",
            "loopable": "N",
            "dependencies": ["T-010"],
            "passes": True,
            "evidence": "証拠",
        }
    )
    check(
        "done+passes:trueはdoneで結果節が付く",
        err is None
        and task is not None
        and task.status == "done"
        and task.dependencies == ("T-010",)
        and task.body.endswith("## 結果\n\n証拠\n"),
        str(err),
    )

    task, err = legacy.convert_task(
        {
            "id": "T-012",
            "summary": "done false",
            "task": "本文\n",
            "status": "done",
            "difficulty": "opus",
            "loopable": "Y",
            "dependencies": [],
            "passes": False,
            "evidence": "",
        }
    )
    check(
        "done+passes:falseはdroppedで結果節は付かない（evidenceが空）",
        err is None and task is not None and task.status == "dropped" and "## 結果" not in task.body,
        str(err),
    )

    task, err = legacy.convert_task(
        {
            "id": "T-013",
            "summary": None,
            "task": "先頭行がsummaryになる\n2行目\n",
            "status": "todo",
            "difficulty": "sonnet",
            "dependencies": [],
            "passes": False,
            "evidence": "",
        }
    )
    check(
        "summaryが無ければtaskの先頭行を使う",
        err is None and task is not None and task.summary == "先頭行がsummaryになる",
        str(err),
    )

    _, err = legacy.convert_task(
        {
            "id": "T-014",
            "summary": "壊れる",
            "task": "本文\n## 結果\n既にある\n",
            "status": "done",
            "difficulty": "sonnet",
            "dependencies": [],
            "passes": True,
            "evidence": "証拠",
        }
    )
    check("本文に既に'## 結果'があればINVALID", err is not None, str(err))

    _, err = legacy.convert_task(
        {
            "id": "T-015",
            "summary": "不明",
            "task": "x\n",
            "status": "doing",
            "difficulty": "sonnet",
            "dependencies": [],
            "passes": False,
        }
    )
    check("statusがdoingならINVALID（migrateは呼び出し側で先に止める）", err is not None, str(err))

    task, conv_err = legacy.convert_task(LEGACY_TASKS[1])
    check("架空タスクのconvert_taskが通る", conv_err is None and task is not None, str(conv_err))
    assert task is not None
    round_tripped, render_err = taskfile.parse(taskfile.render(task))
    check("convert_task→render→parseで往復する", render_err is None and round_tripped == task, str(render_err))


def test_migrate_dry_run_then_real() -> None:
    print("task.py migrate: 架空のtasks.json/progress.mdの変換の往復")
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_legacy_repo(tmp, tasks=LEGACY_TASKS, progress=LEGACY_PROGRESS)

        r = run_task(repo, "migrate", "--dry-run")
        check("dry-runは終了コード0", r.returncode == 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        check("WRITEが3件出る", sum(1 for l in lines if l.startswith("WRITE\t")) == 3, r.stdout)
        check("MOVEに2小節と出る", any(l.startswith("MOVE\t") and "2小節" in l for l in lines), r.stdout)
        check(
            "LEFTOVERに未解決1・注意2と出る",
            any(l.startswith("LEFTOVER\t") and "未解決 1 / 注意 2" in l for l in lines),
            r.stdout,
        )
        check(
            "前置き文を残したLEFTOVER行も出る",
            "LEFTOVER\tdevelop/progress.md\t前置き文を残した" in lines,
            r.stdout,
        )
        check("REMOVEにtasks.jsonが出る", "REMOVE\tdevelop/tasks.json" in lines, r.stdout)
        check("末尾はPLAN\\t3", lines[-1] == "PLAN\t3", r.stdout)
        check("dry-runはファイルを作らない", not os.path.isdir(os.path.join(repo, "develop", "task")))
        check("dry-runはtasks.jsonを消さない", os.path.exists(os.path.join(repo, "develop", "tasks.json")))

        r = run_task(repo, "migrate")
        check("実行は終了コード0", r.returncode == 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        check("末尾はMIGRATED\\t3", lines[-1] == "MIGRATED\t3", r.stdout)
        check("tasks.jsonがファイルから消える", not os.path.exists(os.path.join(repo, "develop", "tasks.json")))

        task_dir = os.path.join(repo, "develop", "task")
        t1, err1 = taskfile.read_task_file(os.path.join(task_dir, "T-001.md"))
        check("todoはtodoのまま", err1 is None and t1 is not None and t1.status == "todo", str(err1))

        t2, err2 = taskfile.read_task_file(os.path.join(task_dir, "T-002.md"))
        check(
            "done+passes:trueはdoneでevidenceが結果節に入る",
            err2 is None and t2 is not None and t2.status == "done" and "bun test: 3 pass" in t2.body,
            str(err2),
        )
        check("dependenciesもそのまま写る", t2 is not None and t2.dependencies == ("T-001",))
        check("loopableもそのまま写る", t2 is not None and t2.loopable == "N")

        t3, err3 = taskfile.read_task_file(os.path.join(task_dir, "T-003.md"))
        check(
            "done+passes:falseはdroppedになる",
            err3 is None and t3 is not None and t3.status == "dropped" and "## 結果" not in t3.body,
            str(err3),
        )

        progress_path = os.path.join(repo, "develop", "progress.md")
        with open(progress_path, encoding="utf-8") as f:
            leftover = f.read()
        check("未解決が残る", "架空の未解決事項" in leftover, leftover)
        check("注意が残る", "架空の注意1" in leftover and "架空の注意2" in leftover, leftover)
        check("完了したこと節の本文は残らない（履歴へ移した）", "架空のこと1" not in leftover and "架空のこと2" not in leftover, leftover)
        check("前置き文は消さずに残る（データを失わない）", "架空の前置きの説明文" in leftover, leftover)
        check("移行の残りの注記が先頭に付く", leftover.startswith("移行の残り。"), leftover)

        history_progress_path = os.path.join(repo, "docs", "history", "progress.md")
        with open(history_progress_path, encoding="utf-8") as f:
            history_text = f.read()
        check(
            "完了したことの小節が履歴へ移る",
            "架空のこと1" in history_text and "架空のこと2" in history_text,
            history_text,
        )

        staged = git(repo, "diff", "--cached", "--name-only").stdout
        check("tasks.jsonの削除がstageされる", "develop/tasks.json" in staged, staged)
        check("develop/task/以下がstageされる", "develop/task/T-001.md" in staged, staged)
        check("progress.mdの更新がstageされる", "develop/progress.md" in staged, staged)
        check("history/progress.mdの追記もstageされる", "docs/history/progress.md" in staged, staged)
        check(
            "migrateはコミットしない（initの1件のまま）",
            git(repo, "log", "--oneline").stdout.strip().count("\n") == 0,
        )

        r = run_task(repo, "status", "--all")
        check("migrate後はstatusが読める（NEW形式になる）", r.returncode == 0, r.stdout + r.stderr)
        ids_out = {l.split("\t")[0] for l in r.stdout.splitlines() if l.startswith("T-0")}
        check("3件とも一覧に出る", ids_out == {"T-001", "T-002", "T-003"}, r.stdout)


def test_migrate_keeps_preamble_when_sections_empty() -> None:
    print("task.py migrate: 未解決・注意が空でも前置き文があればprogress.mdを消さない")
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_legacy_repo(tmp, tasks=LEGACY_TASKS, progress=LEGACY_PROGRESS_PREAMBLE_ONLY)

        r = run_task(repo, "migrate")
        check("実行は終了コード0", r.returncode == 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        check(
            "LEFTOVERに未解決0・注意0と出る",
            any(l.startswith("LEFTOVER\t") and "未解決 0 / 注意 0" in l for l in lines),
            r.stdout,
        )
        check(
            "前置き文を残したLEFTOVER行が出る",
            "LEFTOVER\tdevelop/progress.md\t前置き文を残した" in lines,
            r.stdout,
        )
        check("REMOVEにprogress.mdは出ない（消さない）", "REMOVE\tdevelop/progress.md" not in lines, r.stdout)

        progress_path = os.path.join(repo, "develop", "progress.md")
        check("progress.mdは消えない", os.path.exists(progress_path))
        with open(progress_path, encoding="utf-8") as f:
            leftover = f.read()
        check("前置き文がそのまま残る", "架空の前置き文だけが残るケース" in leftover, leftover)
        check("完了したことの本文は残らない（履歴へ移した）", "架空のこと" not in leftover, leftover)
        check("移行の残りの注記が先頭に付く", leftover.startswith("移行の残り。"), leftover)


def test_migrate_stops_on_doing() -> None:
    print("task.py migrate: doingが残っていればNOT_READYで止まる")
    with tempfile.TemporaryDirectory() as tmp:
        tasks = [dict(LEGACY_TASKS[0], status="doing")]
        repo = _make_legacy_repo(tmp, tasks=tasks)
        r = run_task(repo, "migrate", "--dry-run")
        check(
            "NOT_READYで終了コード4",
            r.returncode == 4 and r.stdout.strip() == "NOT_READY\tT-001\tdoing",
            r.stdout + r.stderr,
        )
        check("develop/task/は作られない", not os.path.isdir(os.path.join(repo, "develop", "task")))


def test_migrate_dirty_worktree_stops() -> None:
    print("task.py migrate: 作業ツリーが汚れていればDIRTYで止まる")
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_legacy_repo(tmp, tasks=LEGACY_TASKS)
        write(os.path.join(repo, "dirty.txt"), "x")
        r = run_task(repo, "migrate")
        check("DIRTYで終了コード4", r.returncode == 4 and r.stdout.strip() == "DIRTY", r.stdout + r.stderr)


def test_migrate_nothing_when_no_tasks_json() -> None:
    print("task.py migrate: develop/tasks.jsonが無ければNOTHING")
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_legacy_repo(tmp, tasks=None)
        r = run_task(repo, "migrate", "--dry-run")
        check(
            "NOTHINGで終了コード0",
            r.returncode == 0 and r.stdout.startswith("NOTHING\t"),
            r.stdout + r.stderr,
        )


# --- 3.4 節が要求する読み取りの見本を、実際の CLI 経由でも確かめる -----------


def test_new_parallel_no_collision() -> None:
    print("task.py new: 2本の作業ツリーから同時に打っても番号が重ならない")
    with tempfile.TemporaryDirectory() as tmp:
        _main_path, wt1, wt2 = make_repo(tmp)
        b1 = body_file(wt1)
        b2 = body_file(wt2)
        p1 = start_task(wt1, "new", "--summary", "並行1", "--difficulty", "sonnet", "--loopable", "Y", "--body-file", b1)
        p2 = start_task(wt2, "new", "--summary", "並行2", "--difficulty", "sonnet", "--loopable", "Y", "--body-file", b2)
        out1, err1 = p1.communicate(timeout=30)
        out2, err2 = p2.communicate(timeout=30)
        check("wt1側はCREATED", p1.returncode == 0 and out1.startswith("CREATED\t"), out1 + err1)
        check("wt2側はCREATED", p2.returncode == 0 and out2.startswith("CREATED\t"), out2 + err2)
        id1 = out1.split("\t")[1] if out1.startswith("CREATED\t") else "?1"
        id2 = out2.split("\t")[1] if out2.startswith("CREATED\t") else "?2"
        check("番号が重ならない", id1 != id2, f"{id1} {id2}")
        check(
            "2本ともそれぞれの作業ツリーにファイルができる",
            os.path.exists(os.path.join(wt1, "develop", "task", f"{id1}.md"))
            and os.path.exists(os.path.join(wt2, "develop", "task", f"{id2}.md")),
        )


def test_claim_race() -> None:
    print("task.py claim: 2本から取り合うと片方だけ通る")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        commit_task(main_path, taskfile.Task("T-100", "取り合うタスク", "todo", "sonnet", "Y", (), BODY))

        p1 = start_task(wt1, "claim", "T-100")
        p2 = start_task(wt2, "claim", "T-100")
        out1, err1 = p1.communicate(timeout=30)
        out2, err2 = p2.communicate(timeout=30)
        results = sorted([out1.split("\t")[0], out2.split("\t")[0]])
        check(
            "片方だけCLAIMEDでもう片方はTAKEN",
            results == ["CLAIMED", "TAKEN"],
            f"out1={out1!r} err1={err1!r} out2={out2!r} err2={err2!r}",
        )


def test_new_avoids_history_ids() -> None:
    print("task.py new: docs/history/tasks.md の番号を採番が避ける")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp)
        write(
            os.path.join(main_path, "docs", "history", "tasks.md"),
            "# 完了タスクのアーカイブ\n\n## T-050\n\nむかしのタスク\n",
        )
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "T-050を履歴に積む")

        r = run_task(
            wt1, "new", "--summary", "履歴の後", "--difficulty", "haiku", "--loopable", "Y", "--body-file", body_file(wt1)
        )
        check("CREATEDで返る", r.returncode == 0 and r.stdout.startswith("CREATED\t"), r.stdout + r.stderr)
        task_id = r.stdout.split("\t")[1]
        check("履歴のT-050より大きい番号になる（重複を避ける）", taskfile.id_number(task_id) > 50, task_id)


# --- taskfile.py: `## 結果` 節（5.7） ---------------------------------------


def test_taskfile_set_result_section() -> None:
    print("taskfile.set_result_section")
    body = "## 目的\nx\n\n## 完了条件\nx\n\n## 背景\nx\n"
    out = taskfile.set_result_section(body, "結果その1")
    check("結果が無ければ末尾に足す", out.endswith("## 結果\n\n結果その1\n"), out)
    check("元の節は残る", "## 目的" in out and "## 背景" in out, out)

    out2 = taskfile.set_result_section(out, "結果その2（差し替え）")
    check(
        "既存の結果は置き換わる",
        "結果その1" not in out2 and "結果その2（差し替え）" in out2,
        out2,
    )
    check("置き換え後も節は1つだけ", out2.count("## 結果") == 1, out2)


# --- task.py: done（5.7） ----------------------------------------------------


def test_done_single_worktree() -> None:
    print("task.py done（単独の作業ツリー）")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp)
        commit_task(main_path, taskfile.Task("T-100", "完了させる", "todo", "sonnet", "Y", (), BODY))

        # premature.md は wt1 の外に置く（中に置くと未claimの判定の前にDIRTYでclaimが拒まれる）。
        premature = write(os.path.join(tmp, "premature.md"), "早すぎる結果\n")
        r = run_task(wt1, "done", "T-100", "--result-file", premature)
        check("未claimはNOT_OWNER", r.returncode == 4 and r.stdout.strip() == "NOT_OWNER\tT-100", r.stdout)

        r = run_task(wt1, "claim", "T-100")
        check("claimできる", r.returncode == 0, r.stdout + r.stderr)

        empty_result = write(os.path.join(wt1, "empty.md"), "   \n")
        r = run_task(wt1, "done", "T-100", "--result-file", empty_result)
        check("結果が空なら終了コード2", r.returncode == 2 and r.stdout == "", r.stdout + r.stderr)

        result_path = write(os.path.join(wt1, "result.md"), "bun run check: 5 pass\n")
        r = run_task(wt1, "done", "T-100", "--result-file", result_path)
        check(
            "DONEで返りstaged",
            r.returncode == 0 and r.stdout.strip() == "DONE\tT-100\tdevelop/task/T-100.md\tstaged",
            r.stdout,
        )

        staged = git(wt1, "diff", "--cached", "--name-only").stdout
        check("develop/task/T-100.mdがstageされる", "develop/task/T-100.md" in staged, staged)

        task_path = os.path.join(wt1, "develop", "task", "T-100.md")
        task, err = taskfile.read_task_file(task_path)
        check("statusがdoneになる", err is None and task is not None and task.status == "done", str(err))
        check(
            "結果節が入る",
            task is not None and "bun run check: 5 pass" in task.body,
            task.body if task else "",
        )

        r = run_task(wt1, "done", "T-100", "--dropped", "--result-file", result_path)
        check("--droppedもDONEで返る", r.returncode == 0, r.stdout + r.stderr)
        task2, _err2 = taskfile.read_task_file(task_path)
        check("--droppedでdroppedになる", task2 is not None and task2.status == "dropped")


# --- task.py: ship（5.8・6章） -----------------------------------------------


def _claim_work_and_done(wt: str, task_id: str, note: str = "") -> None:
    """`claim` 済みのタスクに1件コミットぶんの作業をして `done` にする（コミットはしない）。"""
    write(os.path.join(wt, f"work{note}.txt"), "x")
    git(wt, "add", "-A")
    result_path = write(os.path.join(wt, f"result{note}.md"), "検証OK\n")
    r = run_task(wt, "done", task_id, "--result-file", result_path)
    if r.returncode != 0:
        raise RuntimeError(f"task done が失敗: {r.stdout}{r.stderr}")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", f"{task_id}: 完了")


def _no_merge_commits(repo: str, base: str = "main") -> str:
    return git(repo, "log", "--oneline", "--merges", base).stdout


def test_ship_fast_forward() -> None:
    print("task.py ship: main が進んでいなければ追い付くだけで送る")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, branch="切らない")
        commit_task(main_path, taskfile.Task("T-100", "追い付くだけ", "todo", "sonnet", "Y", (), BODY))

        run_task(wt1, "claim", "T-100")
        _claim_work_and_done(wt1, "T-100")

        r = run_task(wt1, "ship")
        check("SHIPPEDで返る", r.returncode == 0 and r.stdout.startswith("SHIPPED\t"), r.stdout + r.stderr)
        check("rebasedはno", "rebased=no" in r.stdout, r.stdout)
        check("releasedにT-100を含む", "released=T-100" in r.stdout, r.stdout)
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")

        head_task = git(main_path, "show", "main:develop/task/T-100.md").stdout
        check("mainのタスクファイルがdoneになる", "status: done" in head_task, head_task)
        check(
            "着手の印は消える",
            not os.path.isdir(ledger.claim_dir(ledger.ledger_root(cwd=wt1), "T-100")),
        )


def test_ship_rebases_when_main_advances() -> None:
    print("task.py ship: main が先に進んでいれば付け替えてから送る")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, branch="切らない", verify="`echo verified`")
        commit_task(main_path, taskfile.Task("T-100", "付け替え", "todo", "sonnet", "Y", (), BODY))

        run_task(wt1, "claim", "T-100")

        write(os.path.join(main_path, "unrelated.txt"), "x")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "mainだけの変更")

        _claim_work_and_done(wt1, "T-100")

        r = run_task(wt1, "ship")
        check("SHIPPEDで返る", r.returncode == 0 and r.stdout.startswith("SHIPPED\t"), r.stdout + r.stderr)
        check("rebasedはyes", "rebased=yes" in r.stdout, r.stdout)
        check("verifyはran", "verify=ran" in r.stdout, r.stdout)
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")

        log = git(main_path, "log", "--oneline", "main").stdout
        check("mainだけの変更がmainに残る", "mainだけの変更" in log, log)
        check("T-100の完了もmainに乗る", "T-100: 完了" in log, log)


def test_ship_conflict_aborts_rebase() -> None:
    print("task.py ship: 衝突すればrebase --abortして止まる")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, branch="切らない")
        commit_task(main_path, taskfile.Task("T-100", "衝突", "todo", "sonnet", "Y", (), BODY))

        run_task(wt1, "claim", "T-100")

        write(os.path.join(main_path, "shared.txt"), "main側の変更\n")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "main側でshared.txtを変える")

        write(os.path.join(wt1, "shared.txt"), "wt1側の変更\n")
        git(wt1, "add", "-A")
        result_path = write(os.path.join(wt1, "result.md"), "検証OK\n")
        run_task(wt1, "done", "T-100", "--result-file", result_path)
        git(wt1, "add", "-A")
        git(wt1, "commit", "-q", "-m", "T-100: 完了")

        r = run_task(wt1, "ship")
        check("CONFLICTで終了コード7", r.returncode == 7 and r.stdout.startswith("CONFLICT\t"), r.stdout + r.stderr)
        check("衝突ファイルにshared.txtが出る", "shared.txt" in r.stdout, r.stdout)
        check(
            "rebase --abort済みで作業ツリーがきれい",
            git(wt1, "status", "--porcelain").stdout.strip() == "",
        )
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")


def test_ship_main_dirty_stops() -> None:
    print("task.py ship: 本体が汚れていれば送らずに止まる")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, branch="切らない")
        commit_task(main_path, taskfile.Task("T-100", "本体汚れ", "todo", "sonnet", "Y", (), BODY))

        run_task(wt1, "claim", "T-100")
        _claim_work_and_done(wt1, "T-100")

        write(os.path.join(main_path, "dirty.txt"), "汚れ")

        r = run_task(wt1, "ship")
        check("MAIN_DIRTYで終了コード4", r.returncode == 4 and r.stdout.startswith("MAIN_DIRTY\t"), r.stdout + r.stderr)
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")


def test_ship_skips_send_on_main_worktree() -> None:
    print("task.py ship: main の作業ツリーで起こしたときは送る段を飛ばす")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, _wt1, _wt2 = make_repo(tmp, branch="切らない")
        commit_task(main_path, taskfile.Task("T-100", "本体で完結", "todo", "sonnet", "Y", (), BODY))

        r = run_task(main_path, "claim", "T-100")
        check("main上でもclaimできる", r.returncode == 0, r.stdout + r.stderr)
        check("branchはmainのまま", ledger.current_branch(cwd=main_path) == "main")

        _claim_work_and_done(main_path, "T-100")

        r = run_task(main_path, "ship")
        check(
            "SHIPPED main（送る段なし）で返る",
            r.returncode == 0 and r.stdout.startswith("SHIPPED\tmain\t(送る段なし)"),
            r.stdout + r.stderr,
        )
        check("releasedにT-100を含む", "released=T-100" in r.stdout, r.stdout)
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")
        check(
            "着手の印は消える",
            not os.path.isdir(ledger.claim_dir(ledger.ledger_root(cwd=main_path), "T-100")),
        )


def test_ship_race_gives_up_after_three_tries() -> None:
    print("task.py ship: 相手に先を越され続けるとRACEで終わる")
    with tempfile.TemporaryDirectory() as tmp:
        # 相手役は**検証コマンドそのもの**にする。rebase の直後・送る直前に必ず本体が1コミット
        # 進むので `--ff-only` は毎回落ちる。（別スレッドから一定間隔で commit する形は、
        # 機械の混み具合で窓を外すと送れてしまい、落ち方が日によって変わった。）
        racer = os.path.join(tmp, "racer.sh")
        main_path, wt1, _wt2 = make_repo(tmp, branch="切らない", verify=f"`sh {racer}`")
        write(
            racer,
            "set -e\n"
            f'count="{os.path.join(tmp, "race-count")}"\n'
            'i=$(cat "$count" 2>/dev/null || echo 0)\n'
            "i=$((i + 1))\n"
            'echo "$i" > "$count"\n'
            f'cd "{main_path}"\n'
            'printf x > "race-$i.txt"\n'
            'git add "race-$i.txt"\n'
            'git commit -q -m "race $i"\n',
        )
        commit_task(main_path, taskfile.Task("T-100", "競争", "todo", "sonnet", "Y", (), BODY))

        run_task(wt1, "claim", "T-100")
        _claim_work_and_done(wt1, "T-100")
        # 1回めから rebase が起きるように、送る前に本体を1つ進めておく（検証は付け替えた回だけ走る）。
        write(os.path.join(main_path, "head-start.txt"), "x")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "本体が先に1つ進む")

        r = run_task(wt1, "ship")

        check("RACEで終了コード9", r.returncode == 9 and r.stdout.strip() == "RACE\t3", r.stdout + r.stderr)
        with open(os.path.join(tmp, "race-count"), encoding="utf-8") as f:
            tries = f.read().strip()
        check("3回とも rebase → 検証 → 送るを試した", tries == "3", tries)
        check(
            "3回試したあとも作業ツリーはきれい（rebaseは完了、送るのだけ失敗）",
            git(wt1, "status", "--porcelain").stdout.strip() == "",
        )
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")


def test_ship_default_branch_leaves_feature_branch() -> None:
    print("task.py ship: 既定の枝設定で本体が main を出していても feature 枝を残さない")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp, branch="既定")
        commit_task(main_path, taskfile.Task("T-100", "戻り先あり", "todo", "sonnet", "Y", (), BODY))
        commit_task(main_path, taskfile.Task("T-101", "戻り先なし", "todo", "sonnet", "Y", (), BODY))

        r = run_task(wt1, "claim", "T-100")
        check("claim が feature/T-100 を切る", "branch=feature/T-100" in r.stdout, r.stdout + r.stderr)
        _claim_work_and_done(wt1, "T-100")
        r = run_task(wt1, "ship")
        check("SHIPPEDで返る", r.returncode == 0 and r.stdout.startswith("SHIPPED\t"), r.stdout + r.stderr)
        check("claim した時点の枝へ戻る", r.stdout.rstrip().endswith("branch=wt1-branch"), r.stdout)
        check("戻った枝は main に追い付いている", git(wt1, "rev-parse", "HEAD").stdout == git(main_path, "rev-parse", "main").stdout)
        check(
            "feature/T-100 は消える",
            git(main_path, "branch", "--list", "feature/T-100").stdout.strip() == "",
        )

        # 戻り先が無い（detached で claim した）ときは main の位置で detached にして枝を消す。
        git(wt2, "checkout", "-q", "--detach", "main")
        r = run_task(wt2, "claim", "T-101")
        check("detached からでも claim できる", r.returncode == 0 and "branch=feature/T-101" in r.stdout, r.stdout + r.stderr)
        _claim_work_and_done(wt2, "T-101", note="2")
        r = run_task(wt2, "ship")
        check("SHIPPEDで返る（detached）", r.returncode == 0 and r.stdout.startswith("SHIPPED\t"), r.stdout + r.stderr)
        check("戻れなければ detached と出す", r.stdout.rstrip().endswith("branch=detached"), r.stdout)
        check(
            "feature/T-101 も消える",
            git(main_path, "branch", "--list", "feature/T-101").stdout.strip() == "",
        )
        check("main にmerge commitが無い", _no_merge_commits(main_path).strip() == "")


def test_branch_setting_reads_leading_word() -> None:
    print("task.py claim: - ブランチ: は先頭語だけを読む（後ろの説明は自由）")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, branch="切らない。作業ツリーの枝のまま ship で送る")
        commit_task(main_path, taskfile.Task("T-100", "先頭語", "todo", "sonnet", "Y", (), BODY))
        r = run_task(wt1, "claim", "T-100")
        check("句読点で続いても切らない として読む", r.returncode == 0 and "branch=wt1-branch" in r.stdout, r.stdout + r.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, branch="自分で切らない")
        commit_task(main_path, taskfile.Task("T-100", "語彙外", "todo", "sonnet", "Y", (), BODY))
        r = run_task(wt1, "claim", "T-100")
        check("語彙に無い先頭語は INVALID（終了コード3）", r.returncode == 3 and r.stdout.startswith("INVALID\t"), r.stdout + r.stderr)


def test_prune() -> None:
    print("task.py prune: 振り返り済みの done/dropped だけを git rm して stage する")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, _wt1, _wt2 = make_repo(tmp, branch="切らない")
        reviewed_body = BODY + "\n## 結果\n\n- 検証: x\n- 振り返り: 兆候なし\n"
        plain_body = BODY + "\n## 結果\n\n- 検証: x\n"
        commit_task(main_path, taskfile.Task("T-102", "基準点より前に done", "dropped", "sonnet", "Y", (), plain_body))
        base = git(main_path, "rev-parse", "--short", "HEAD").stdout.strip()
        commit_task(main_path, taskfile.Task("T-101", "1件ごとに振り返り済み", "done", "sonnet", "Y", (), reviewed_body))
        commit_task(main_path, taskfile.Task("T-103", "基準点より後に done", "done", "sonnet", "Y", (), plain_body))
        commit_task(main_path, taskfile.Task("T-104", "T-101 を待つ", "todo", "sonnet", "Y", ("T-101",), BODY))
        commit_task(main_path, taskfile.Task("T-105", "印が立っている", "done", "sonnet", "Y", (), reviewed_body))
        record = os.path.join(main_path, "develop", "retrospective.md")
        write(record, f"# 振り返りの記録\n\n最後に振り返ったコミット: `{base}`\n")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "記録")
        ledger.try_claim(ledger.ledger_root(cwd=main_path), "T-105", main_path, "main")

        r = run_task(main_path, "prune")
        check("既定のしきい値（10件）に届かなければ NOTHING", r.returncode == 0 and r.stdout.startswith("NOTHING\t"), r.stdout + r.stderr)
        check("しきい値未満では消さない", os.path.exists(os.path.join(main_path, "develop", "task", "T-101.md")))
        r = run_task(main_path, "prune", "--min", "3", "--dry-run")
        check("--min 3 でも2件なら --dry-run も NOTHING", r.returncode == 0 and r.stdout.startswith("NOTHING\t"), r.stdout + r.stderr)

        r = run_task(main_path, "prune", "--min", "2", "--dry-run")
        check("--dry-run は PLAN で2件", r.returncode == 0 and r.stdout.splitlines()[-1] == "PLAN\t2", r.stdout + r.stderr)
        check(
            "対象と理由",
            r.stdout.splitlines()[:2] == ["PRUNE\tT-101\treviewed", "PRUNE\tT-102\tretrospect"],
            r.stdout,
        )
        check("--dry-run は消さない", os.path.exists(os.path.join(main_path, "develop", "task", "T-101.md")))

        write(os.path.join(main_path, "scratch.txt"), "x\n")
        r = run_task(main_path, "prune", "--min", "2")
        check("汚れていれば DIRTY(4)", r.returncode == 4 and r.stdout.strip() == "DIRTY", r.stdout + r.stderr)
        r = run_task(main_path, "prune", "--min", "2", "--dry-run")
        check("--dry-run は汚れていても打てる", r.returncode == 0, r.stdout + r.stderr)
        os.remove(os.path.join(main_path, "scratch.txt"))

        r = run_task(main_path, "prune", "--min", "2")
        check("PRUNED で2件", r.returncode == 0 and r.stdout.splitlines()[-1] == "PRUNED\t2", r.stdout + r.stderr)
        staged = git(main_path, "diff", "--cached", "--name-status").stdout.split()
        check(
            "2件の削除だけが stage される",
            staged == ["D", "develop/task/T-101.md", "D", "develop/task/T-102.md"],
            str(staged),
        )
        git(main_path, "commit", "-q", "-m", "振り返り済みのタスクファイルを消す（2件）")
        status = run_task(main_path, "status").stdout
        check("消した依存は解決済みのまま", any(l.startswith("T-104\ttodo") and "\tREADY\t" in l for l in status.splitlines()), status)
        check("status --check が通る", run_task(main_path, "status", "--check").returncode == 0)
        r = run_task(main_path, "prune", "--min", "1")
        check("2回目は NOTHING", r.returncode == 0 and r.stdout.startswith("NOTHING"), r.stdout + r.stderr)

        write(record, "最後に振り返ったコミット: `0000000`\n")
        git(main_path, "commit", "-q", "-am", "壊れた記録")
        r = run_task(main_path, "prune", "--dry-run")
        check("基準点が無いコミットなら INVALID(3)", r.returncode == 3 and r.stdout.startswith("INVALID\t"), r.stdout + r.stderr)


# --- 主ブランチ（`main` 固定をやめた分） -------------------------------------


def test_base_branch_resolution() -> None:
    print("ledger.base_branch: CLAUDE.md の行 → origin/HEAD → main/master/trunk → NoBaseBranch")
    with tempfile.TemporaryDirectory() as tmp:
        ledger.clear_base_branch_cache()
        master_repo, _wt1, _wt2 = make_repo(tmp, base="master")
        check("順3: master しか無ければ master", ledger.base_branch(cwd=master_repo) == "master")

        # 順1（CLAUDE.md の任意行）が順2・順3より先。
        git(master_repo, "branch", "main")
        ledger.clear_base_branch_cache()
        check("main も出来たら順3では main が先", ledger.base_branch(cwd=master_repo) == "main")
        claude_md = os.path.join(master_repo, "CLAUDE.md")
        with open(claude_md, encoding="utf-8") as f:
            body = f.read()
        write(claude_md, body.replace("- ブランチ:", "- 主ブランチ: `master`（保護ブランチ）\n- ブランチ:"))
        ledger.clear_base_branch_cache()
        check("順1: `- 主ブランチ:` 行が最優先（バッククォートも落ちる）", ledger.base_branch(cwd=master_repo) == "master")

    with tempfile.TemporaryDirectory() as tmp:
        # 順2: origin/HEAD の枝名。候補の順（main が先）より優先する。
        ledger.clear_base_branch_cache()
        repo, _wt1, _wt2 = make_repo(tmp, base="main")
        git(repo, "branch", "trunk")
        git(repo, "remote", "add", "origin", repo)
        git(repo, "update-ref", "refs/remotes/origin/trunk", "trunk")
        git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        ledger.clear_base_branch_cache()
        check("順2: origin/HEAD が指す枝を採る", ledger.base_branch(cwd=repo) == "trunk")

    with tempfile.TemporaryDirectory() as tmp:
        # 順4: 候補の枝が無ければ黙って main を作らず INVALID（終了コード3）。
        ledger.clear_base_branch_cache()
        repo, _wt1, _wt2 = make_repo(tmp, base="dev")
        raised = False
        try:
            ledger.base_branch(cwd=repo)
        except ledger.NoBaseBranch:
            raised = True
        check("順4: 決まらなければ NoBaseBranch", raised)
        r = run_task(repo, "status")
        check(
            "task.py は INVALID（終了コード3）で止まる",
            r.returncode == 3 and r.stdout.startswith("INVALID\t"),
            r.stdout + r.stderr,
        )
    ledger.clear_base_branch_cache()


def test_config_file_agents_md_and_conflict() -> None:
    print("設定ファイルの探索（T-020: AGENTS.md → CLAUDE.md の順、両方あれば INVALID）")
    with tempfile.TemporaryDirectory() as tmp:
        # AGENTS.md だけのリポジトリ: claim・ship まで CLAUDE.md と同じ形で通る。
        main_path, wt1, _wt2 = make_repo(tmp, config_filename="AGENTS.md", verify="`echo verified`")
        commit_task(main_path, taskfile.Task("T-100", "AGENTS.md だけ", "todo", "sonnet", "Y", (), BODY))
        r = run_task(wt1, "claim", "T-100")
        check("AGENTS.md だけでも claim できる", r.returncode == 0 and r.stdout.startswith("CLAIMED"), r.stdout + r.stderr)
        result_path = write(os.path.join(tmp, "result.md"), "- 検証: x\n")
        r = run_task(wt1, "done", "T-100", "--result-file", result_path)
        check("done できる", r.returncode == 0, r.stdout + r.stderr)
        git(wt1, "add", "-A")
        git(wt1, "commit", "-q", "-m", "T-100: AGENTS.md だけ")
        r = run_task(wt1, "ship")
        check(
            "ship も AGENTS.md の検証コマンドを読む（verify=none にならない）",
            r.returncode == 0 and r.stdout.startswith("SHIPPED") and "verify=none" not in r.stdout,
            r.stdout + r.stderr,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # 両方に「## タスク運用」節があるリポジトリ: どちらが正か機械が決められないので INVALID。
        # `- 主ブランチ:` は無くても main が実在するので順3で決まる（順1・順2が動く前に検査が要る）。
        main_path, _wt1, _wt2 = make_repo(tmp, config_filename="AGENTS.md")
        write(os.path.join(main_path, "CLAUDE.md"), "# y\n\n## タスク運用\n\n- ブランチ: 既定\n")
        r = run_task(main_path, "status")
        check(
            "AGENTS.md と CLAUDE.md の両方に節があれば INVALID（終了コード3）",
            r.returncode == 3 and r.stdout.startswith("INVALID\t") and "AGENTS.md" in r.stdout and "CLAUDE.md" in r.stdout,
            r.stdout + r.stderr,
        )


def _make_config_doctor_repo(tmp: str, name: str) -> str:
    """`task config-doctor`（T-021）のフィクスチャ用の最小リポジトリ。

    `make_repo` は「## タスク運用」の3行のうち `- 整形コマンド:` を書かない（他のテストが
    `read_verify_command`／`read_branch_setting` しか見ないため）ので、`claude_md_lines`
    検査が必ず `MISSING_LINE` になってしまう。ここでは3行そろった CLAUDE.md を直接書く。
    """
    repo = os.path.join(tmp, name)
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write(
        os.path.join(repo, "develop", "direction.md"),
        "# 未対応の指示メモ\n\n## ユーザーから\n\n## エージェントのドラフト\n",
    )
    write(os.path.join(repo, "docs", "history", "tasks.md"), "# 完了タスクのアーカイブ\n")
    write(
        os.path.join(repo, "CLAUDE.md"),
        "# x\n\n## タスク運用\n\n- 検証コマンド: なし\n- 整形コマンド: なし\n- ブランチ: 既定\n",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def test_config_doctor() -> None:
    print("task.py config-doctor（T-021: 設定と形式のズレの点検。読むだけ）")

    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_config_doctor_repo(tmp, "ok")
        r = run_task(repo, "config-doctor")
        lines = r.stdout.splitlines()
        check(
            "OKのリポジトリは終了コード0で4検査ともOK",
            r.returncode == 0
            and any(l.startswith("base_branch\tOK\tmain\t順3") for l in lines)
            and any(l.startswith("config_file\tOK\tCLAUDE.md") for l in lines)
            and any(l.startswith("claude_md_lines\tOK") for l in lines)
            and "legacy\tOK" in lines,
            r.stdout + r.stderr,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # 旧形式の残り（develop/tasks.json・develop/progress.md）だけがあるケース。
        # 他の3検査はOKでも、残りがあれば全体は「直すものがある」＝終了コード1。
        repo = _make_config_doctor_repo(tmp, "leftover")
        write(os.path.join(repo, "develop", "tasks.json"), "[]\n")
        write(os.path.join(repo, "develop", "progress.md"), "## 未解決\n\n- x\n")
        r = run_task(repo, "config-doctor")
        lines = r.stdout.splitlines()
        check(
            "旧形式の残りがあれば終了コード1で案内する",
            r.returncode == 1
            and any(
                l.startswith("legacy\tFOUND\t") and "develop/tasks.json" in l and "develop/progress.md" in l
                and l.endswith("task migrate --dry-run")
                for l in lines
            )
            and any(l.startswith("base_branch\tOK") for l in lines)
            and any(l.startswith("claude_md_lines\tOK") for l in lines),
            r.stdout + r.stderr,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # AGENTS.md と CLAUDE.md の両方に「## タスク運用」節があるケース。
        repo = _make_config_doctor_repo(tmp, "conflict")
        write(os.path.join(repo, "AGENTS.md"), "# a\n\n## タスク運用\n\n- ブランチ: 既定\n")
        r = run_task(repo, "config-doctor")
        lines = r.stdout.splitlines()
        check(
            "両方に節があれば終了コード3で全検査がINVALIDと言う",
            r.returncode == 3
            and any(l.startswith("base_branch\tINVALID\t") for l in lines)
            and any(l.startswith("config_file\tINVALID\t") for l in lines)
            and any(l.startswith("claude_md_lines\tINVALID\t") for l in lines)
            and "legacy\tOK" in lines,
            r.stdout + r.stderr,
        )


def test_full_cycle_on_master_repo() -> None:
    print("task.py: 主ブランチが master のリポジトリで一式（status→new→claim→done→ship→prune）")
    with tempfile.TemporaryDirectory() as tmp:
        base_path, wt1, wt2 = make_repo(tmp, branch="既定", verify="`echo verified`", base="master")
        commit_task(base_path, taskfile.Task("T-100", "master で一式", "todo", "sonnet", "Y", (), BODY))

        status = run_task(wt1, "status")
        check(
            "status が master の版のタスクを READY で見せる",
            status.returncode == 0 and any(l.startswith("T-100\ttodo") and "\tREADY\t" in l for l in status.stdout.splitlines()),
            status.stdout + status.stderr,
        )

        r = run_task(wt1, "new", "--summary", "master で採番", "--difficulty", "haiku", "--loopable", "Y", "--body-file", body_file(wt1))
        check("new が採番できる（master の履歴を読む）", r.returncode == 0 and r.stdout.startswith("CREATED\tT-101\t"), r.stdout + r.stderr)
        os.remove(os.path.join(wt1, "develop", "task", "T-101.md"))
        os.remove(os.path.join(wt1, "body.md"))

        r = run_task(wt1, "claim", "T-100")
        check("claim が master から feature 枝を切る", r.returncode == 0 and "branch=feature/T-100" in r.stdout, r.stdout + r.stderr)
        check("いまの枝は feature/T-100", ledger.current_branch(cwd=wt1) == "feature/T-100")

        _claim_work_and_done(wt1, "T-100")
        r = run_task(wt1, "ship")
        check("ship が master へ送る", r.returncode == 0 and r.stdout.startswith("SHIPPED\t"), r.stdout + r.stderr)
        check("戻り先は claim 時点の枝", "branch=wt1-branch" in r.stdout, r.stdout)
        check("feature 枝は消える", git(base_path, "branch", "--list", "feature/T-100").stdout.strip() == "", r.stdout)
        shipped = git(base_path, "show", "master:develop/task/T-100.md").stdout
        check("master のタスクファイルが done になる", "status: done" in shipped, shipped)
        check("master に merge commit が無い", _no_merge_commits(base_path, "master").strip() == "")

        # master が先に進んでいる側から送ると、付け替えて検証してから送る。
        commit_task(base_path, taskfile.Task("T-102", "付け替え", "todo", "sonnet", "Y", (), BODY))
        run_task(wt2, "claim", "T-102")
        _claim_work_and_done(wt2, "T-102", note="2")
        write(os.path.join(base_path, "unrelated.txt"), "x")
        git(base_path, "add", "-A")
        git(base_path, "commit", "-q", "-m", "master だけの変更")
        r = run_task(wt2, "ship")
        check(
            "rebase してから送り、付け替えた回だけ検証が走る",
            r.returncode == 0 and "rebased=yes" in r.stdout and "verify=ran" in r.stdout,
            r.stdout + r.stderr,
        )
        log = git(base_path, "log", "--oneline", "master").stdout
        check("両方の変更が master に乗る", "master だけの変更" in log and "T-102: 完了" in log, log)

        # prune も master の版で見る。
        reviewed = BODY + "\n## 結果\n\n- 検証: x\n- 振り返り: 兆候なし\n"
        commit_task(base_path, taskfile.Task("T-104", "振り返り済み", "done", "sonnet", "Y", (), reviewed))
        r = run_task(base_path, "prune", "--min", "1")
        check("prune が1件消して stage する", r.returncode == 0 and r.stdout.splitlines()[-1] == "PRUNED\t1", r.stdout + r.stderr)
        git(base_path, "commit", "-q", "-m", "振り返り済みのタスクファイルを消す（1件）")
        check("status --check が通る", run_task(base_path, "status", "--check").returncode == 0)
        check("master に merge commit が無い", _no_merge_commits(base_path, "master").strip() == "")

    # 本体（master を出している作業ツリー）で枝を切らずに起こしたときは送る段が無い。
    with tempfile.TemporaryDirectory() as tmp:
        base_path, _wt1, _wt2 = make_repo(tmp, branch="切らない", base="master")
        commit_task(base_path, taskfile.Task("T-100", "本体で完結", "todo", "sonnet", "Y", (), BODY))
        run_task(base_path, "claim", "T-100")
        _claim_work_and_done(base_path, "T-100")
        r = run_task(base_path, "ship")
        check(
            "SHIPPED master（送る段なし）で返る",
            r.returncode == 0 and r.stdout.startswith("SHIPPED\tmaster\t(送る段なし)") and "released=T-100" in r.stdout,
            r.stdout + r.stderr,
        )
        r = run_task(_wt1, "ship")
        check(
            "送るものが無い側は NOTHING（枝名を埋め込む）",
            r.returncode == 0 and r.stdout.strip() == "NOTHING\t(master に無いコミットが無い)",
            r.stdout + r.stderr,
        )


def main() -> None:
    for t in (
        test_taskfile_parse,
        test_new_and_status_single_worktree,
        test_claim_and_release_single_worktree,
        test_new_missing_and_legacy,
        test_legacy_convert_task,
        test_migrate_dry_run_then_real,
        test_migrate_keeps_preamble_when_sections_empty,
        test_migrate_stops_on_doing,
        test_migrate_dirty_worktree_stops,
        test_migrate_nothing_when_no_tasks_json,
        test_new_parallel_no_collision,
        test_claim_race,
        test_new_avoids_history_ids,
        test_taskfile_set_result_section,
        test_done_single_worktree,
        test_ship_fast_forward,
        test_ship_rebases_when_main_advances,
        test_ship_conflict_aborts_rebase,
        test_ship_main_dirty_stops,
        test_ship_skips_send_on_main_worktree,
        test_ship_race_gives_up_after_three_tries,
        test_ship_default_branch_leaves_feature_branch,
        test_branch_setting_reads_leading_word,
        test_prune,
        test_base_branch_resolution,
        test_config_file_agents_md_and_conflict,
        test_config_doctor,
        test_full_cycle_on_master_repo,
    ):
        t()
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
