#!/usr/bin/env python3
"""1件1ファイル＋台帳の形のタスク運用を操作する入口コマンド。

使い方: task.py <status|new|claim|release|done|ship|prune|migrate|config-doctor> ...

正典は `docs/task-workflow-redesign.md`（5章が `task` コマンド、4章が状態と台帳、
3章がタスクファイル、6章が送り出し、5.9・10章が `migrate`）。スキルからは
`python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py <サブコマンド> …` で呼ぶ
（5.1。PATH には入れない）。スキル側の呼び方の正典は task-workflow の WORKFLOW.md
「`task` コマンドの参照」。

出力は常に stdout（先頭語で種類を判定する TSV）、stderr は使い方の誤りだけ、
終了コードは5.2の表のとおり。データの不備で traceback を出さない
（traceback は「環境の故障」の合図として取っておく）。`migrate` の実体は `legacy.py`（旧形式の
読み取りと実際の書き換え）にあり、ここは結果を印字するだけ（`ship.py`/`cmd_ship` と同じ形）。
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import beads
import init
import layout
import ledger
import legacy
import ship
import taskfile
import tracker


# --- 形式の判定（5.2） -----------------------------------------------------


def detect_format(toplevel: str) -> tuple[str, str | None]:
    tasks_json = os.path.join(toplevel, "develop", "tasks.json")
    task_dir = os.path.join(toplevel, layout.TASK_DIR)
    direction = os.path.join(toplevel, layout.DIRECTION_PATH)
    has_tasks_json = os.path.exists(tasks_json)
    has_task_files = os.path.isdir(task_dir) and any(
        n.endswith(".md") for n in os.listdir(task_dir)
    )
    if has_tasks_json:
        if has_task_files:
            return "INVALID", "develop/tasks.json と develop/task/ の両方がある（移行が途中）"
        return "LEGACY", None
    if os.path.exists(direction):
        return "NEW", None
    return "MISSING", None


# --- git の薄いラッパ（非0を「失敗」として使う呼び出しは例外を投げない） -------


def _run_git(toplevel: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=toplevel, capture_output=True, text=True)


def _list_base_task_filenames(toplevel: str, base: str) -> list[str]:
    r = _run_git(toplevel, ["ls-tree", "--name-only", "-r", base, "--", layout.TASK_DIR])
    if r.returncode != 0:
        return []
    return [os.path.basename(p) for p in r.stdout.splitlines() if p.endswith(".md")]


def _read_base_task_text(toplevel: str, base: str, filename: str) -> str | None:
    r = _run_git(toplevel, ["show", f"{base}:{layout.TASK_DIR}/{filename}"])
    return r.stdout if r.returncode == 0 else None


def _history_ids_at_base(toplevel: str) -> set[str]:
    base = ledger.base_branch(toplevel)
    r = _run_git(toplevel, ["show", f"{base}:{layout.HISTORY_TASKS_PATH}"])
    if r.returncode != 0:
        return set()
    return {m.group(1) for m in layout.HISTORY_HEADING_PATTERN.finditer(r.stdout)}


# --- タスクの読み取り（主ブランチを正とし、作業ツリーだけの分は local として足す） ---


def load_tasks(
    toplevel: str,
) -> tuple[dict[str, taskfile.Task], dict[str, str], list[str]]:
    """`(id→Task, id→INVALID理由, ローカルにしか無いID)` を返す（5.3: 主ブランチを正とする）。"""
    tasks: dict[str, taskfile.Task] = {}
    invalid: dict[str, str] = {}

    base = ledger.base_branch(toplevel)
    for filename in _list_base_task_filenames(toplevel, base):
        stem = os.path.splitext(filename)[0]
        text = _read_base_task_text(toplevel, base, filename)
        if text is None:
            continue
        parsed, err = taskfile.parse(text)
        if err is not None or parsed is None or parsed.id != stem:
            invalid[stem] = err or f"ファイル名（{stem}）と id（{parsed.id if parsed else '?'}）が不一致"
            continue
        tasks[parsed.id] = parsed

    task_dir = os.path.join(toplevel, layout.TASK_DIR)
    local_only: list[str] = []
    for stem in taskfile.local_task_ids(task_dir):
        if stem in tasks or stem in invalid:
            continue  # 主ブランチにもある ID は主ブランチを正とする
        parsed, err = taskfile.read_task_file(taskfile.task_path(task_dir, stem))
        if err is not None or parsed is None:
            invalid[stem] = err or "読めない"
            continue
        tasks[parsed.id] = parsed
        local_only.append(parsed.id)

    return tasks, invalid, local_only


def is_resolved(dep_id: str, tasks: dict[str, taskfile.Task]) -> bool:
    """4.1: done/dropped は解決済み。タスクファイルに無い ID（アーカイブ済み）も解決済み。"""
    t = tasks.get(dep_id)
    return t is None or t.status in ("done", "dropped")


def readiness(task: taskfile.Task, tasks: dict[str, taskfile.Task], claims: set[str]) -> str:
    if task.status == "hold":
        return "HOLD"
    if task.status != "todo":
        return "-"
    if task.id in claims:
        return "CLAIMED"
    blocked = [d for d in task.dependencies if not is_resolved(d, tasks)]
    if blocked:
        return "BLOCKED:" + ",".join(blocked)
    return "READY"


# WORKFLOW.md「summary」の「1行に収める」に反すると見なす幅。80桁はその一行だけで端末が
# 折り返す長さ（旧 status.py の実測: 52件中14件が該当。狭めると大半に火が点いて合図にならない）。
LONG_SUMMARY_WIDTH = 80


def display_width(s: str) -> int:
    """端末に出したときの桁数。日本語（East Asian Wide/Fullwidth）は2桁。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes}m" if minutes else f"{hours}h"


def classify_claim(
    root: str,
    task_id: str,
    base_task: taskfile.Task | None,
    worktrees: list[ledger.Worktree],
) -> tuple[str, str]:
    """4.3の判定。`(表示語, 詳細)` を返す。表示語は `CLAIMED` か `STALE:*`。"""
    d = ledger.claim_dir(root, task_id)
    owner = ledger.read_owner(d)
    if owner is None:
        age = time.time() - os.stat(d).st_mtime
        return ("STALE:no-owner", "") if age > 60 else ("CLAIMED", "書き込み中")
    worktree = owner.get("worktree", "?")
    if base_task is not None and base_task.status in ("done", "dropped"):
        return "STALE:shipped", worktree
    if not any(w.path == worktree for w in worktrees):
        return "STALE:gone", worktree
    age = ledger.owner_age_seconds(d)
    elapsed = format_elapsed(age) if age is not None else "?"
    return "CLAIMED", f"{os.path.basename(worktree)} {elapsed}"


BRANCH_WORDS = ("既定", "作業ブランチを切る", "切らない")


def read_branch_setting(toplevel: str) -> str:
    """設定ファイル（`layout.find_config_file`。`AGENTS.md` → `CLAUDE.md` の順）の
    `- ブランチ:` 行の先頭語だけを読む（6.1）。無ければ `既定`。

    後ろは人向けの説明で自由なので、`切らない。主ブランチに積む` のように句読点で続いても
    先頭語で決める。語彙のどれでも始まらなければ、その値の最初の語をそのまま返す
    （呼ぶ側が `INVALID` にする）。両方のファイルに節があれば `layout.ConfigConflict`
    （呼ぶ側の `main` が `INVALID`・終了コード3にする）。
    """
    found = layout.find_config_file(toplevel)
    if found is None:
        return "既定"
    _path, text = found
    m = re.search(r"^- ブランチ:[ \t]*(.*)$", text, flags=re.MULTILINE)
    if m is None:
        return "既定"
    value = m.group(1).strip()
    word = next((w for w in BRANCH_WORDS if value.startswith(w)), None)
    return word if word is not None else (value.split() or [""])[0]


def _section_bullets(text: str, heading_prefix: str) -> int:
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(heading_prefix)), None)
    if start is None:
        return 0
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return sum(1 for l in lines[start + 1 : end] if l.strip().startswith("- "))


def read_body(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


# --- status（5.3） ---------------------------------------------------------


def cmd_status(toplevel: str, show_all: bool, check: bool) -> None:
    root = ledger.ledger_root(cwd=toplevel)
    tasks, invalid, local_only = load_tasks(toplevel)
    claims = set(ledger.list_claims(root))
    worktrees = ledger.list_worktrees(cwd=toplevel)
    history_path = os.path.join(toplevel, layout.HISTORY_TASKS_PATH)
    history = taskfile.history_ids(history_path)

    if check:
        problems = [f"{stem}:{reason}" for stem, reason in invalid.items()]
        problems += [
            f"{tid}:タスクファイルと {layout.HISTORY_TASKS_PATH} の両方にある" for tid in tasks if tid in history
        ]
        if problems:
            print("INVALID\t" + "; ".join(problems))
            raise SystemExit(3)
        print("OK")
        return

    def marker_of(tid: str) -> str:
        if tid in claims:
            label, detail = classify_claim(root, tid, tasks[tid], worktrees)
            return detail if label == "CLAIMED" else f"{label}({detail})"
        return "local" if tid in local_only else "-"

    stale_entries = []
    for tid in claims:
        label, detail = classify_claim(root, tid, tasks.get(tid), worktrees)
        if label != "CLAIMED":
            stale_entries.append(f"{tid}:{label}({detail})" if detail else f"{tid}:{label}")

    _print_status_table(tasks, invalid, claims, show_all, marker_of, stale_entries)
    _print_legacy_progress(toplevel)


def _print_status_table(
    tasks: dict[str, taskfile.Task],
    invalid: dict[str, str],
    claims: set[str],
    show_all: bool,
    marker_of: Callable[[str], str],
    stale_entries: list[str],
    extra_rows: "list[list[str]] | None" = None,
    sort_key: Callable[[str], object] = taskfile.id_number,
) -> None:
    """`status` の行と `---` 以降の集計（`invalid` の行まで）。ファイル方式と Beads 方式で同じ形。

    `extra_rows` は番号順の行のあとに足す行（Beads 方式の振り分け前の課題）。集計には数えない。
    """
    for tid in sorted(tasks, key=sort_key):
        t = tasks[tid]
        if not show_all and t.status in ("done", "dropped"):
            continue
        ready = readiness(t, tasks, claims)
        print(
            "\t".join(
                [
                    tid,
                    t.status,
                    t.difficulty,
                    t.loopable,
                    ",".join(t.dependencies) or "-",
                    ready,
                    marker_of(tid),
                    t.summary,
                ]
            )
        )

    for row in extra_rows or []:
        print("\t".join(row))

    print("---")
    counts = {s: sum(1 for t in tasks.values() if t.status == s) for s in taskfile.STATUS_VALUES}
    counts["claimed"] = len(claims)
    print("counts\t" + "\t".join(f"{k}={v}" for k, v in counts.items()))

    ready_count = sum(
        1 for tid, t in tasks.items() if t.status == "todo" and readiness(t, tasks, claims) == "READY"
    )
    print(f"ready\t{ready_count}")

    todo_loopable_n = sum(1 for t in tasks.values() if t.status == "todo" and t.loopable == "N")
    print(f"todo_loopable\tN={todo_loopable_n}")

    long_ids = [
        tid
        for tid in sorted(tasks, key=sort_key)
        if tasks[tid].status in ("todo", "hold") and display_width(tasks[tid].summary) > LONG_SUMMARY_WIDTH
    ]
    print(f"long_summary\t{len(long_ids)}\t" + (",".join(long_ids) or "-"))

    print(f"stale\t{len(stale_entries)}\t" + (",".join(stale_entries) if stale_entries else "-"))

    print(f"invalid\t{len(invalid)}\t" + (",".join(sorted(invalid)) if invalid else "-"))


def _print_legacy_progress(toplevel: str) -> None:
    progress_path = os.path.join(toplevel, "develop", "progress.md")
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as f:
            text = f.read()
        unresolved = _section_bullets(text, "## 未解決")
        notes = _section_bullets(text, "## 注意")
        print(
            f"legacy_progress\tdevelop/progress.md\t未解決 {unresolved} / 注意 {notes}"
            "\t（移行の残り。振り分けたら消す）"
        )


# --- new（5.4） -------------------------------------------------------------


def cmd_new(toplevel: str, args: argparse.Namespace) -> None:
    summary = args.summary.strip()
    if summary == "" or "\n" in args.summary:
        print("usage: --summary は改行を含まない1行にする", file=sys.stderr)
        raise SystemExit(2)

    deps = tuple(d for d in (x.strip() for x in args.deps.split(",")) if d) if args.deps else ()
    for d in deps:
        if not taskfile.ID_PATTERN.match(d):
            print(f"usage: --deps の {d!r} が T-999 の形式でない", file=sys.stderr)
            raise SystemExit(2)

    body = read_body(args.body_file)
    error = taskfile.validate_new_body(body)
    if error is not None:
        print(f"usage: {error}", file=sys.stderr)
        raise SystemExit(2)

    root = ledger.ledger_root(cwd=toplevel)
    if not ledger.acquire_lock(root):
        age = ledger.lock_owner_age_seconds(root)
        hint = f"\trmdir {shlex.quote(os.path.join(root, ledger.LOCK_DIR_NAME))}" if age and age > 60 else ""
        print(f"LOCKED\t採番の錠が取れない{hint}")
        raise SystemExit(4)
    try:
        tasks, invalid, _ = load_tasks(toplevel)

        status = "hold" if args.hold else "todo"
        history_path = os.path.join(toplevel, layout.HISTORY_TASKS_PATH)
        candidate_ids = (
            list(tasks) + [i for i in invalid if taskfile.ID_PATTERN.match(i)]
            + list(taskfile.history_ids(history_path))
            + list(_history_ids_at_base(toplevel))
        )
        candidates = [0] + [taskfile.id_number(i) for i in candidate_ids]
        last_id = ledger.read_last_id(root)
        if last_id is not None:
            candidates.append(last_id)
        number = max(candidates) + 1
        task_id = taskfile.format_id(number)

        task_dir = os.path.join(toplevel, layout.TASK_DIR)
        os.makedirs(task_dir, exist_ok=True)
        path = taskfile.task_path(task_dir, task_id)
        rendered = taskfile.render(
            taskfile.Task(task_id, summary, status, args.difficulty, args.loopable, deps, body)
        )
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(rendered)

        ledger.write_last_id(root, number)
        print(f"CREATED\t{task_id}\t{layout.TASK_DIR}/{task_id}.md")
    finally:
        ledger.release_lock(root)


# --- claim（5.5） -----------------------------------------------------------


def cmd_claim(toplevel: str, task_id: str) -> None:
    if not taskfile.ID_PATTERN.match(task_id):
        print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
        raise SystemExit(2)

    branch_setting, base = _claim_preflight(toplevel)

    tasks, invalid, _ = load_tasks(toplevel)
    if task_id in invalid:
        print(f"INVALID\t{invalid[task_id]}")
        raise SystemExit(3)
    task = tasks.get(task_id)
    if task is None:
        print(f"NOT_READY\t{task_id}\t存在しない")
        raise SystemExit(4)
    if task.status != "todo":
        print(f"NOT_READY\t{task_id}\t{task.status}")
        raise SystemExit(4)
    blocked = [d for d in task.dependencies if not is_resolved(d, tasks)]
    if blocked:
        print(f"NOT_READY\t{task_id}\tBLOCKED:{','.join(blocked)}")
        raise SystemExit(4)

    root = ledger.ledger_root(cwd=toplevel)
    branch_after_sync = ledger.current_branch(cwd=toplevel)
    head = ledger.head_sha_or_none(cwd=toplevel)
    if not ledger.try_claim(root, task_id, toplevel, branch_after_sync, head):
        d = ledger.claim_dir(root, task_id)
        owner = ledger.read_owner(d) or {}
        age = ledger.owner_age_seconds(d)
        elapsed = format_elapsed(age) if age is not None else "?"
        print(f"TAKEN\t{task_id}\t{owner.get('worktree', '?')}\t{elapsed}")
        raise SystemExit(4)

    _claim_branch_out(toplevel, task_id, branch_setting, base, branch_after_sync, f"{layout.TASK_DIR}/{task_id}.md")


def _claim_preflight(toplevel: str) -> tuple[str, str]:
    """`claim` の git の前提（`- ブランチ:` が読める・clean・未送りなし・主ブランチへ追い付く）。

    `(ブランチの設定の先頭語, 主ブランチ)` を返す。前提を欠けば出力して `SystemExit`。
    ファイル方式と Beads 方式の `claim` が同じものを通る。
    """
    branch_setting = read_branch_setting(toplevel)
    if branch_setting not in BRANCH_WORDS:
        print(f"INVALID\t- ブランチ: の値 {branch_setting!r} を機械が読めない")
        raise SystemExit(3)

    if not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    base = ledger.base_branch(toplevel)
    branch = ledger.current_branch(cwd=toplevel)
    if branch != base:
        ahead = _run_git(toplevel, ["rev-list", "--count", f"{base}..HEAD"])
        if ahead.returncode == 0 and ahead.stdout.strip() not in ("0", ""):
            print(f"UNSHIPPED\t{ahead.stdout.strip()}")
            raise SystemExit(4)
        r = _run_git(toplevel, ["merge", "--ff-only", base])
        if r.returncode != 0:
            print(f"INVALID\t{base} へ追い付けない（{r.stderr.strip()}）")
            raise SystemExit(3)
    return branch_setting, base


def _claim_branch_out(
    toplevel: str, task_id: str, branch_setting: str, base: str, branch_after_sync: str, where: str
) -> None:
    """印を立てたあと、設定なら作業ブランチを切って `CLAIMED` を出す（`where` は3列目）。"""
    if branch_setting in ("既定", "作業ブランチを切る"):
        feature_branch = f"{layout.FEATURE_BRANCH_PREFIX}{task_id}"
        r = _run_git(toplevel, ["checkout", "-b", feature_branch, base])
        if r.returncode != 0:
            print(f"CLAIMED\t{task_id}\t{where}\tbranch=(切れない: {r.stderr.strip()})")
            return
        print(f"CLAIMED\t{task_id}\t{where}\tbranch={feature_branch}")
    else:
        print(f"CLAIMED\t{task_id}\t{where}\tbranch={branch_after_sync}")


# --- release（5.6） ---------------------------------------------------------


def cmd_release(toplevel: str, task_id: str, force: bool) -> None:
    if not taskfile.ID_PATTERN.match(task_id):
        print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
        raise SystemExit(2)
    root = ledger.ledger_root(cwd=toplevel)
    result = ledger.release_claim(root, task_id, toplevel, force=force)
    if result in ("RELEASED", "NOT_CLAIMED"):
        print(f"{result}\t{task_id}")
        return
    print(f"{result}\t{task_id}")
    raise SystemExit(4)


# --- done（5.7） ------------------------------------------------------------


def cmd_done(toplevel: str, task_id: str, dropped: bool, result_path: str) -> None:
    if not taskfile.ID_PATTERN.match(task_id):
        print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
        raise SystemExit(2)

    root = ledger.ledger_root(cwd=toplevel)
    owner = ledger.read_owner(ledger.claim_dir(root, task_id))
    if owner is None or owner.get("worktree") != toplevel:
        print(f"NOT_OWNER\t{task_id}")
        raise SystemExit(4)

    task_dir = os.path.join(toplevel, layout.TASK_DIR)
    path = taskfile.task_path(task_dir, task_id)
    task, err = taskfile.read_task_file(path)
    if err is not None or task is None:
        print(f"INVALID\t{err or '読めない'}")
        raise SystemExit(3)

    result = read_body(result_path).strip()
    if result == "":
        print("usage: --result-file の中身が空", file=sys.stderr)
        raise SystemExit(2)

    new_status = "dropped" if dropped else "done"
    new_body = taskfile.set_result_section(task.body, result)
    rendered = taskfile.render(
        taskfile.Task(task.id, task.summary, new_status, task.difficulty, task.loopable, task.dependencies, new_body)
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(rendered)

    relpath = os.path.join(layout.TASK_DIR, f"{task_id}.md")
    _run_git(toplevel, ["add", relpath])
    print(f"DONE\t{task_id}\t{relpath}\tstaged")
    _print_commits_since_claim(toplevel, task_id, owner.get("head"))


def _commits_since_claim(toplevel: str, head: str | None) -> list[str]:
    """`head`（claim 時の HEAD）から今の HEAD までにできたコミット（古い順、短縮ハッシュ）。

    `head` が無い（控えの無い古い印。ファイル方式は owner の `head=`、Beads 方式は metadata の
    `task_claim_head`）か `git log` が引けなければ空のまま返す（`task done` はそれを「委譲先の
    コミットは無い」と同じに扱い、落とさない）。
    """
    if not head:
        return []
    r = _run_git(toplevel, ["log", "--format=%h", "--reverse", f"{head}..HEAD"])
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line]


def _print_commits_since_claim(toplevel: str, shown_id: str, head: str | None) -> None:
    """claim から今までに委譲先が作ったコミットがあれば `COMMITS_SINCE_CLAIM` の行で知らせる。

    `next-task` の手順6（受け入れる）向けの合図で、`DONE` の判定・終了コードは変えない。
    """
    commits = _commits_since_claim(toplevel, head)
    if commits:
        print(f"COMMITS_SINCE_CLAIM\t{shown_id}\t{','.join(commits)}")


# --- edit・plan-check（`## やること` を作業より先に書いたか） ----------------

PLAN_FIRST = "first"
PLAN_AFTER_WORK = "after-work"


def cmd_edit(toplevel: str, args: argparse.Namespace) -> None:
    """ファイル方式の `edit`。本文だけを書き換え、`## やること` を初めて書いた時点の判定を印に残す。"""
    if any([args.summary, args.difficulty, args.loopable, args.status]) or not args.body_file:
        print("usage: ファイル方式の edit は --body-file だけ（ほかはタスクファイルを直に直す）", file=sys.stderr)
        raise SystemExit(2)
    task_id = args.task_id
    if not taskfile.ID_PATTERN.match(task_id):
        print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
        raise SystemExit(2)
    path = taskfile.task_path(os.path.join(toplevel, layout.TASK_DIR), task_id)
    if not os.path.exists(path):
        print(f"NOT_READY\t{task_id}\t存在しない")
        raise SystemExit(4)
    task, err = taskfile.read_task_file(path)
    if err is not None or task is None:
        print(f"INVALID\t{err or '読めない'}")
        raise SystemExit(3)
    if task.status not in ("todo", "hold"):
        print(f"NOT_READY\t{task_id}\t{task.status}")
        raise SystemExit(4)
    body = read_body(args.body_file)
    error = taskfile.validate_body(body)
    if error is not None:
        print(f"usage: {error}", file=sys.stderr)
        raise SystemExit(2)

    root = ledger.ledger_root(cwd=toplevel)
    owner = ledger.read_owner(ledger.claim_dir(root, task_id))
    state = None
    if (
        owner is not None
        and owner.get("worktree") == toplevel
        and taskfile.has_plan(body)
        and ledger.read_plan_mark(root, task_id) is None
    ):
        own = f"{layout.TASK_DIR}/{task_id}.md"
        state = _plan_state(toplevel, owner.get("head"), args.body_file, own)

    rendered = taskfile.render(
        taskfile.Task(task.id, task.summary, task.status, task.difficulty, task.loopable, task.dependencies, body)
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(rendered)
    if state is not None:
        ledger.write_plan_mark(root, task_id, state)
    print(f"EDITED\t{task_id}")


def cmd_plan_check(toplevel: str, task_id: str) -> None:
    if not taskfile.ID_PATTERN.match(task_id):
        print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
        raise SystemExit(2)
    root = ledger.ledger_root(cwd=toplevel)
    owner = ledger.read_owner(ledger.claim_dir(root, task_id))
    if owner is None or owner.get("worktree") != toplevel:
        print(f"NOT_OWNER\t{task_id}")
        raise SystemExit(4)
    task, err = taskfile.read_task_file(taskfile.task_path(os.path.join(toplevel, layout.TASK_DIR), task_id))
    if err is not None or task is None:
        print(f"INVALID\t{err or '読めない'}")
        raise SystemExit(3)
    _print_plan_check(task_id, taskfile.has_plan(task.body), ledger.read_plan_mark(root, task_id))


def _plan_state(toplevel: str, head: str | None, body_file: str, own_path: str | None) -> str:
    """いま `## やること` を書くと、作業より先（`first`）か作業が始まってから（`after-work`）か。

    作業が始まっているとは、claim した時点の `head` より後のコミットがあるか、タスク自身のファイル
    （`own_path`）と `body_file` 以外に `git status` の変更があること。
    """
    if _commits_since_claim(toplevel, head):
        return PLAN_AFTER_WORK
    ignored = {own_path} if own_path else set()
    if body_file != "-":
        ignored.add(os.path.relpath(os.path.realpath(body_file), os.path.realpath(toplevel)))
    r = _run_git(toplevel, ["status", "--porcelain", "-z", "--untracked-files=all"])
    changed = _porcelain_paths(r.stdout) if r.returncode == 0 else []
    return PLAN_AFTER_WORK if any(p not in ignored for p in changed) else PLAN_FIRST


def _porcelain_paths(out: str) -> list[str]:
    """`git status --porcelain -z` の出力から変更のあるパスを取り出す（名前の変更は元の名前を読み飛ばす）。"""
    paths: list[str] = []
    entries = iter(out.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            next(entries, None)
    return paths


def _print_plan_check(shown: str, has_plan: bool, mark: str | None) -> None:
    if has_plan and mark == PLAN_FIRST:
        print(f"PLAN_FIRST\t{shown}")
        return
    reason = "missing" if not has_plan else (mark or "unrecorded")
    print(f"PLAN_NOT_FIRST\t{shown}\t{reason}")


# --- ship（5.8・6章） --------------------------------------------------------


def _release_own_claims_when_shipped(root: str, toplevel: str) -> list[str]:
    """4.4・5.8手順7: 自分の作業ツリーの印のうち、主ブランチ（HEAD）で done/dropped に
    なったものを消す。主ブランチを正として読む（`load_tasks` は git show 経由なので、
    直前に送った変更もここで反映済みのものとして見える）。"""
    tasks, _invalid, _local_only = load_tasks(toplevel)
    released: list[str] = []
    for tid in ledger.list_claims(root):
        owner = ledger.read_owner(ledger.claim_dir(root, tid))
        if owner is None or owner.get("worktree") != toplevel:
            continue
        t = tasks.get(tid)
        if t is not None and t.status in ("done", "dropped"):
            ledger.release_claim(root, tid, toplevel)
            released.append(tid)
    return released


@dataclass(frozen=True)
class ShipHooks:
    """`ship` のうち、タスクの置き場（ファイル方式・Beads 方式）で変わる3点。

    `release_shipped`: 送り終えたあと自分の印を消し、消した ID を返す。
    `claimed_branch`: `claim` した時点の枝（作業ブランチから降りる先）。
    `after_send`: `SHIPPED`・`NOTHING` の行のあとに足す行（トラッカー・バックアップ）。
    """

    release_shipped: Callable[[], list[str]]
    claimed_branch: Callable[[str], "str | None"]
    after_send: Callable[[], list[str]]


def _file_ship_hooks(toplevel: str) -> ShipHooks:
    root = ledger.ledger_root(cwd=toplevel)
    return ShipHooks(
        release_shipped=lambda: _release_own_claims_when_shipped(root, toplevel),
        claimed_branch=lambda tid: (ledger.read_owner(ledger.claim_dir(root, tid)) or {}).get("branch"),
        after_send=lambda: [],
    )


def cmd_ship(toplevel: str, hooks: "ShipHooks | None" = None) -> None:
    if not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    if hooks is None:
        hooks = _file_ship_hooks(toplevel)
    base = ledger.base_branch(toplevel)
    branch = ledger.current_branch(cwd=toplevel)

    if branch == base:
        # 4.4: 主ブランチを出している作業ツリーで起こしたときは送る段が無い。
        ledger.clear_verify_owed(cwd=toplevel)
        released = hooks.release_shipped()
        print(f"SHIPPED\t{base}\t(送る段なし)\treleased={','.join(released) or '-'}")
        _print_lines(hooks.after_send())
        return

    ahead = _run_git(toplevel, ["rev-list", "--count", f"{base}..HEAD"])
    ahead_count = int(ahead.stdout.strip()) if ahead.returncode == 0 and ahead.stdout.strip().isdigit() else 0
    if ahead_count == 0:
        ledger.clear_verify_owed(cwd=toplevel)
        hooks.release_shipped()
        print(f"NOTHING\t({base} に無いコミットが無い)")
        _print_lines(hooks.after_send())
        return

    worktrees = ledger.list_worktrees(cwd=toplevel)
    base_worktree = ship.find_base_worktree(worktrees, toplevel, base)
    if base_worktree is not None and not ledger.is_clean(cwd=base_worktree.path):
        print(f"MAIN_DIRTY\t{base_worktree.path}")
        raise SystemExit(4)

    old_base = _run_git(toplevel, ["rev-parse", base]).stdout.strip()
    verify_command = ship.read_verify_command(toplevel)
    verify_owed = ledger.is_verify_owed(cwd=toplevel)
    outcome = ship.attempt(toplevel, base_worktree, verify_command, base, verify_owed=verify_owed)

    if outcome.kind == "CONFLICT":
        print("CONFLICT\t" + (",".join(outcome.conflict_files) or "?"))
        raise SystemExit(7)
    if outcome.kind == "VERIFY_FAILED":
        # 付け替え済みのまま送っていない。次の `ship` は打ち直しでも検証を飛ばさない（T-777）。
        ledger.mark_verify_owed(outcome.verify_command or "", cwd=toplevel)
        print(f"VERIFY_FAILED\t{outcome.verify_command}")
        if outcome.verify_tail:
            print(outcome.verify_tail)
        raise SystemExit(8)
    if outcome.kind == "RACE":
        print("RACE\t3")
        raise SystemExit(9)

    # ここに来るのは `SENT` だけ（`attempt` は借りがあれば検証を通してからでないと
    # `SENT` を返さない）。送れたので借りは無い。
    ledger.clear_verify_owed(cwd=toplevel)

    branch_note = f"branch={branch}"
    if read_branch_setting(toplevel) in ("既定", "作業ブランチを切る") and FEATURE_BRANCH.fullmatch(branch):
        # 印を消す前に読む（戻り先は印にある）。
        branch_note = _leave_feature_branch(toplevel, branch, hooks.claimed_branch)

    released = hooks.release_shipped()
    new_base = _run_git(toplevel, ["rev-parse", base]).stdout.strip()
    print(
        f"SHIPPED\t{old_base}..{new_base}\trebased={'yes' if outcome.rebased else 'no'}"
        f"\tverify={outcome.verify_state}\ttries={outcome.tries}\treleased={','.join(released) or '-'}"
        f"\t{branch_note}"
    )
    _print_lines(hooks.after_send())


def _print_lines(lines: list[str]) -> None:
    for line in lines:
        print(line)


FEATURE_BRANCH = layout.FEATURE_BRANCH_PATTERN


def _leave_feature_branch(toplevel: str, branch: str, claimed_branch: Callable[[str], "str | None"]) -> str:
    """送り終えた `feature/T-xxx` から降りて枝を消す（6.2手順7）。出力の `branch=…` 欄を返す。

    戻り先は `claim` した時点の枝（`claimed_branch`。ファイル方式は印の owner の `branch=`）→ 主ブランチの順に試す。主ブランチを
    別の作業ツリー（本体）が出していると `checkout` は通らないので、作業ツリー固有の枝が
    あればそこへ戻して主ブランチまで追い付かせる。どちらにも移れなければ主ブランチの位置で
    detached HEAD にする（枝を黙って残さない。detached のままでも次の `claim` は主ブランチから切る）。
    消せなかったときは `kept=<枝>` を添えて知らせる。
    """
    base = ledger.base_branch(toplevel)
    m = FEATURE_BRANCH.fullmatch(branch)
    back = claimed_branch(m.group(1)) if m else None
    targets = [b for b in dict.fromkeys([back, base]) if b and b not in (branch, "HEAD")]

    landed = None
    for target in targets:
        if _run_git(toplevel, ["checkout", "-q", target]).returncode == 0:
            if target != base:
                _run_git(toplevel, ["merge", "--ff-only", "-q", base])
            landed = target
            break
    if landed is None:
        if _run_git(toplevel, ["checkout", "-q", "--detach", base]).returncode != 0:
            return f"branch={branch}\tkept={branch}"
        landed = "detached"

    if _run_git(toplevel, ["branch", "-d", branch]).returncode != 0:
        return f"branch={landed}\tkept={branch}"
    return f"branch={landed}"


# --- prune（5.10） ----------------------------------------------------------

# 1件ごとの振り返りが済んだ印。`## 結果` の中のこの形の行（WORKFLOW.md「結果の書き方と知見の置き場」）。
REVIEWED_LINE = re.compile(r"^- 振り返り:")
# 消せるものがこの件数に届くまでは消さない。毎サイクル1件ずつ消すと削除だけのコミットが
# タスクと同じ数だけ積もるため、まとめて1コミットにする。
PRUNE_MIN_DEFAULT = 10


def cmd_prune(toplevel: str, dry_run: bool, minimum: int) -> None:
    """振り返りが済んだ done/dropped のタスクファイルを `git rm` して stage する（コミットしない）。

    判定は `HEAD` の版で done/dropped・台帳に印が無い・`## 結果` に `- 振り返り:` の行がある
    （`reviewed` ＝1件ごとの振り返り済み）。印のあるタスクを除くのは、`ship` が主ブランチの版で
    done を見て印を消すため。対象が `minimum` 件に届かなければ何もしない（`NOTHING`）。
    """
    if not dry_run and not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    claims = set(ledger.list_claims(ledger.ledger_root(cwd=toplevel)))
    targets: list[tuple[str, str]] = []
    for tid, task in sorted(_tasks_at(toplevel, "HEAD").items(), key=lambda kv: taskfile.id_number(kv[0])):
        if task.status not in ("done", "dropped") or tid in claims:
            continue
        if _has_review_line(task.body):
            targets.append((tid, "reviewed"))

    if not targets:
        print("NOTHING\t(消せるタスクファイルが無い)")
        return
    if len(targets) < minimum:
        print(f"NOTHING\t(消せるのは{len(targets)}件で、{minimum}件に届くまで溜める)")
        return
    for tid, reason in targets:
        print(f"PRUNE\t{tid}\t{reason}")
    if dry_run:
        print(f"PLAN\t{len(targets)}")
        return
    paths = [f"{layout.TASK_DIR}/{tid}.md" for tid, _ in targets]
    r = _run_git(toplevel, ["rm", "-q", "--", *paths])
    if r.returncode != 0:
        raise ledger.GitCommandError(f"git rm が失敗した: {r.stderr.strip()}")
    print(f"PRUNED\t{len(targets)}")


def _tasks_at(toplevel: str, rev: str) -> dict[str, taskfile.Task]:
    r = _run_git(toplevel, ["ls-tree", "--name-only", rev, f"{layout.TASK_DIR}/"])
    tasks: dict[str, taskfile.Task] = {}
    for path in r.stdout.splitlines() if r.returncode == 0 else []:
        stem = os.path.splitext(os.path.basename(path))[0]
        if not path.endswith(".md") or not taskfile.ID_PATTERN.match(stem):
            continue
        shown = _run_git(toplevel, ["show", f"{rev}:{path}"])
        parsed, err = taskfile.parse(shown.stdout) if shown.returncode == 0 else (None, "読めない")
        if err is None and parsed is not None and parsed.id == stem:
            tasks[stem] = parsed
    return tasks


def _has_review_line(body: str) -> bool:
    in_result = False
    for line in body.splitlines():
        if line.startswith("## "):
            in_result = line.strip() == taskfile.RESULT_HEADING
        elif in_result and REVIEWED_LINE.match(line):
            return True
    return False


# --- migrate（5.9・10章） ----------------------------------------------------


def cmd_migrate(toplevel: str, dry_run: bool) -> None:
    result = legacy.migrate(toplevel, dry_run)
    if result.kind == "DIRTY":
        print("DIRTY")
        raise SystemExit(4)
    if result.kind == "NOTHING":
        print(f"NOTHING\t{result.detail}")
        return
    if result.kind == "INVALID":
        print(f"INVALID\t{result.detail}")
        raise SystemExit(3)
    if result.kind == "NOT_READY":
        print(f"NOT_READY\t{result.detail}")
        raise SystemExit(4)

    for path in result.written:
        print(f"WRITE\t{path}")
    if result.moved_sections > 0:
        print(f"MOVE\tprogress 完了したこと {result.moved_sections}小節 → docs/history/progress.md")
    if result.leftover_counts is not None:
        unresolved, note = result.leftover_counts
        print(f"LEFTOVER\tdevelop/progress.md\t未解決 {unresolved} / 注意 {note}")
        if result.preamble_kept:
            print("LEFTOVER\tdevelop/progress.md\t前置き文を残した")
    elif result.progress_removed:
        print("REMOVE\tdevelop/progress.md")
    print("REMOVE\tdevelop/tasks.json")
    print(f"{'PLAN' if dry_run else 'MIGRATED'}\t{result.task_count}")


# --- config-doctor（T-021） --------------------------------------------------


def cmd_config_doctor(toplevel: str) -> None:
    """設定と形式のズレの点検（読むだけ・`--fix` は無い）。検査1つに1行、タブ区切りで出す
    （`task status` と同じ形。人向けの段落は出さない）。判定は書き起こさず、既存の部品
    （`ledger.base_branch`・`layout.find_config_file`・`init.check_claude_md`・旧形式の残りの
    直接の検出）を呼ぶだけ（正典 WORKFLOW.md「ファイル配置と設定ファイル（AGENTS.md →
    CLAUDE.md の順）」・T-013・T-020）。

    4行を必ず出す（途中の検査が INVALID でも残りの検査は続ける。呼び出し側が全体像を
    1回の実行で見られるようにする）。終了コードは 0（全部OK）／1（直すものがある）／
    3（INVALID）——最悪のものを返す。`main` の `ledger.NoBaseBranch`・`layout.ConfigConflict`
    の受け皿（呼び出し側で即 `INVALID` にする仕組み）は使わない。ここで捕まえて次の検査に進む。
    """
    exit_code = 0

    # 検査1: 主ブランチが何で決まったか（T-013 の順1〜3。順4＝決まらない＝INVALID）。
    try:
        base = ledger.base_branch(toplevel)
        order = ledger.base_branch_order(toplevel)
        print(f"base_branch\tOK\t{base}\t順{order}")
    except (ledger.NoBaseBranch, layout.ConfigConflict) as e:
        print(f"base_branch\tINVALID\t{e}")
        exit_code = 3

    # 検査2: 設定ファイルが AGENTS.md か CLAUDE.md か、両方に節があって INVALID か（T-020）。
    try:
        found = layout.find_config_file(toplevel)
    except layout.ConfigConflict as e:
        print(f"config_file\tINVALID\t{e}")
        exit_code = 3
    else:
        if found is None:
            existing = next(
                (n for n in layout.CONFIG_FILENAMES if os.path.exists(os.path.join(toplevel, n))), None
            )
            print(f"config_file\tMISSING\t{existing or layout.CONFIG_FILENAMES[-1]}")
            exit_code = max(exit_code, 1)
        else:
            path, _text = found
            print(f"config_file\tOK\t{os.path.relpath(path, toplevel)}")

    # 検査3: 「## タスク運用」の3行の在否と `- ブランチ:` の先頭語が語彙に当たるか
    # （`init.check_claude_md` そのもの。新しく判定を書き起こさない）。
    kind, _, rest = init.check_claude_md(toplevel).partition("\t")
    rest = rest.replace(toplevel + os.sep, "")  # 絶対パスの根を削り、check_file と表記を揃える
    print(f"claude_md_lines\t{kind}" + (f"\t{rest}" if rest else ""))
    if kind == "INVALID":
        exit_code = 3
    elif kind != "OK":
        exit_code = max(exit_code, 1)

    # 検査4: 旧形式の残り（develop/tasks.json・develop/progress.md）があるか。
    tasks_json = os.path.exists(os.path.join(toplevel, "develop", "tasks.json"))
    progress_md = os.path.exists(os.path.join(toplevel, "develop", "progress.md"))
    if tasks_json or progress_md:
        leftover = ", ".join(
            p
            for p, present in (("develop/tasks.json", tasks_json), ("develop/progress.md", progress_md))
            if present
        )
        print(f"legacy\tFOUND\t{leftover}\ttask migrate --dry-run")
        exit_code = max(exit_code, 1)
    else:
        print("legacy\tOK")

    # 検査5（`- タスクの置き場:` 行があるときだけ。無ければファイル方式で、4行のまま）。
    try:
        store_value = layout.read_setting_value(toplevel, layout.STORE_KEY)
    except layout.ConfigConflict:
        store_value = None
    if store_value is not None:
        store_code = _doctor_store(toplevel)
        exit_code = 3 if 3 in (exit_code, store_code) else max(exit_code, store_code)

    if exit_code:
        raise SystemExit(exit_code)


# --- Beads 方式（正典 WORKFLOW.md「Beads 方式」） ---------------------------------
#
# 錠・本文・履歴は Beads（`bd`）が持ち、ここは Beads とトラッカーと git をつなぐ。出力の先頭語・
# 列・終了コードはファイル方式と同じにし、スキルが方式で分かれずに済むようにする。違うのは、
# 3列目の置き場が `beads:<Beads の ID>` になること、`done` が stage しないこと、行のあとに
# `TRACKER`・`BACKUP` の行が付くことだけ。


def _actor(toplevel: str) -> str:
    """Beads の actor（着手の印の持ち主）は作業ツリーの名前。"""
    return os.path.basename(toplevel)


def _bd_task_id(task_id: str) -> str:
    """`T-123`・`GH-5`・Beads の ID（仮の `gh-new-…`・取り込んだままの `gh-1790…-1-4dfc`）を受ける。"""
    if not re.fullmatch(r"(?i:t|gh)-[0-9a-z.-]+", task_id):
        print(f"usage: {task_id!r} が T-999・GH-5 の形式でない", file=sys.stderr)
        raise SystemExit(2)
    return beads.to_bd_id(task_id)


@dataclass(frozen=True)
class BeadsSnapshot:
    tasks: dict  # T-xxx → taskfile.Task
    invalid: dict  # 見せる ID → 理由
    triage: list  # 振り分け前の beads.Issue（番号・difficulty・loopable が無い）
    issues: dict  # 見せる ID → beads.Issue
    claims: set  # in_progress の見せる ID


def _beads_snapshot(toplevel: str) -> BeadsSnapshot:
    tasks: dict[str, taskfile.Task] = {}
    invalid: dict[str, str] = {}
    triage: list[beads.Issue] = []
    issues: dict[str, beads.Issue] = {}
    claims: set[str] = set()
    for issue in beads.list_issues(toplevel):
        shown = beads.to_task_id(issue.bd_id)
        issues[shown] = issue
        task, err = beads.to_task(issue)
        if err is not None:
            invalid[shown] = err
            continue
        if task is None:
            triage.append(issue)
            continue
        tasks[shown] = task
        if issue.status == "in_progress":
            claims.add(shown)
    return BeadsSnapshot(tasks, invalid, triage, issues, claims)


def _beads_classify(toplevel: str, issue: beads.Issue, worktree_names: set[str], base: str) -> tuple[str, str]:
    """着手の印の判定（WORKFLOW.md「status と着手の印」の取り残しの表を Beads の欄で）。"""
    owner = issue.assignee
    if owner is None:
        return "STALE:no-owner", ""
    shown = beads.to_task_id(issue.bd_id)
    if beads.ship_mark(issue) is not None and _task_commit_on_base(toplevel, shown, base, issue.started_at):
        return "STALE:shipped", owner
    if owner not in worktree_names:
        return "STALE:gone", owner
    age = _age_seconds(issue.started_at)
    return "CLAIMED", f"{owner} {format_elapsed(age) if age is not None else '?'}"


def _task_commit_on_base(toplevel: str, task_id: str, base: str, since: str | None) -> bool:
    """主ブランチに、着手より後の `T-xxx:`（`T-xxx, …` を含む）の件名のコミットがあるか。"""
    args = ["log", base, "-E", f"--grep=^{task_id}[:,]", "--format=%H", "-1"]
    age = _age_seconds(since)
    if age is not None:
        # コミットの時刻は秒で丸まるので、着手と同じ秒のコミットを落とさないよう1秒さかのぼる。
        args.insert(2, f"--since={int(age) + 1} seconds ago")
    r = _run_git(toplevel, args)
    return r.returncode == 0 and r.stdout.strip() != ""


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - at).total_seconds()


def cmd_beads_status(toplevel: str, show_all: bool, check: bool) -> None:
    snap = _beads_snapshot(toplevel)
    if check:
        if snap.invalid:
            print("INVALID\t" + "; ".join(f"{k}:{v}" for k, v in snap.invalid.items()))
            raise SystemExit(3)
        print("OK")
        return

    base = ledger.base_branch(toplevel)
    worktree_names = {os.path.basename(w.path) for w in ledger.list_worktrees(cwd=toplevel)}
    labels = {tid: _beads_classify(toplevel, snap.issues[tid], worktree_names, base) for tid in snap.claims}

    def marker_of(tid: str) -> str:
        if tid not in labels:
            return "-"
        label, detail = labels[tid]
        return detail if label == "CLAIMED" else f"{label}({detail})"

    stale_entries = [
        f"{tid}:{label}({detail})" if detail else f"{tid}:{label}"
        for tid, (label, detail) in sorted(labels.items())
        if label != "CLAIMED"
    ]
    open_triage = [i for i in snap.triage if i.status != "closed"]
    triage_rows = [
        [beads.to_task_id(i.bd_id), "todo", "-", "-", ",".join(beads.to_task_id(d) for d in i.dependencies) or "-",
         "TRIAGE", i.assignee or "-", " ".join(i.title.split()) or "-"]
        for i in open_triage
    ]
    _print_status_table(
        snap.tasks, snap.invalid, snap.claims, show_all, marker_of, stale_entries, triage_rows, beads.sort_key
    )
    triage_ids = [row[0] for row in triage_rows]
    print(f"triage\t{len(triage_ids)}\t" + (",".join(triage_ids) or "-"))
    if tracker.read_tracker(toplevel).kind == "jira":
        waiting = [tid for tid, i in sorted(snap.issues.items()) if beads.JIRA_CLOSE_LABEL in i.labels]
        print(f"jira_close\t{len(waiting)}\t" + (",".join(waiting) or "-"))
    _print_legacy_progress(toplevel)


def cmd_beads_new(toplevel: str, args: argparse.Namespace) -> None:
    summary = args.summary.strip()
    if summary == "" or "\n" in args.summary:
        print("usage: --summary は改行を含まない1行にする", file=sys.stderr)
        raise SystemExit(2)
    deps = tuple(d for d in (x.strip() for x in args.deps.split(",")) if d) if args.deps else ()
    for d in deps:
        if not layout.ANY_ID_PATTERN.match(d):
            print(f"usage: --deps の {d!r} が T-999・GH-5 の形式でない", file=sys.stderr)
            raise SystemExit(2)
    body = read_body(args.body_file)
    error = taskfile.validate_new_body(body)
    if error is not None:
        print(f"usage: {error}", file=sys.stderr)
        raise SystemExit(2)

    snap = _beads_snapshot(toplevel)
    missing = [d for d in deps if d not in snap.issues]
    if missing:
        print(f"usage: --deps の {','.join(missing)} が Beads に無い（解決済みなら外す）", file=sys.stderr)
        raise SystemExit(2)

    parts = beads.split_body(body)
    actor = _actor(toplevel)
    labels = f"{beads.DIFFICULTY_LABEL}{args.difficulty},{beads.LOOPABLE_LABEL}{args.loopable}"

    def create_cmd(bd_id: str) -> list[str]:
        cmd = ["create", "--id", bd_id, "--title", summary, "--body-file", "-", "-l", labels, "--silent"]
        if parts.acceptance:
            cmd += ["--acceptance", parts.acceptance]
        if args.hold:
            cmd += ["-s", beads.HOLD_STATUS]
        if deps:
            cmd += ["--deps", ",".join(beads.to_bd_id(d) for d in deps)]
        return cmd

    trk = tracker.session(toplevel)
    if trk.bidirectional:
        # 番号は Issue を立てるまで決まらないので、仮の ID で作ってから `gh-<Issue 番号>` へ付け替える。
        provisional = f"{beads.PROVISIONAL_PREFIX}{re.sub(r'[^0-9a-z]+', '-', actor.lower()).strip('-')}-{time.time_ns()}"
        beads.run_ok(toplevel, create_cmd(provisional), actor, parts.description)
        bd_id, lines = trk.register(provisional)
        print(f"CREATED\t{beads.to_task_id(bd_id)}\tbeads:{bd_id}")
        _print_lines(lines)
        return

    number = _next_number(toplevel, snap)
    for _ in range(NEW_ATTEMPTS):
        bd_id = beads.format_bd_id(number)
        r = beads.run(toplevel, create_cmd(bd_id), actor, parts.description)
        if r.returncode == 0:
            beads.write_last_id(toplevel, number)
            print(f"CREATED\t{beads.to_task_id(bd_id)}\tbeads:{bd_id}")
            _print_lines(trk.after([bd_id]))
            return
        if "already exists" not in (r.stderr + r.stdout):
            raise beads.BeadsError(f"bd create が失敗: {(r.stderr or r.stdout).strip()}")
        number += 1
    print(f"LOCKED\t{NEW_ATTEMPTS}回続けて番号を取られた")
    raise SystemExit(4)


# 番号の取り合いに続けて負けたら諦める回数（`bd create --id` は同じ番号を1つしか作らない）。
NEW_ATTEMPTS = 20


def _next_number(toplevel: str, snap: BeadsSnapshot) -> int:
    """Beads の番号・`bd kv` の最後の番号・主ブランチの `develop/task/` と `docs/history/tasks.md`・
    ファイル方式の台帳の `last-id`（残っていれば）のうち最大の次。"""
    candidates = [0]
    candidates += [n for n in (beads.id_number(i.bd_id) for i in snap.issues.values()) if n is not None]
    last = beads.read_last_id(toplevel)
    if last is not None:
        candidates.append(last)
    base = ledger.base_branch(toplevel)
    candidates += [
        taskfile.id_number(os.path.splitext(f)[0])
        for f in _list_base_task_filenames(toplevel, base)
        if taskfile.ID_PATTERN.match(os.path.splitext(f)[0])
    ]
    candidates += [taskfile.id_number(i) for i in _history_ids_at_base(toplevel)]
    ledger_last = ledger.read_last_id(ledger.ledger_root(cwd=toplevel))
    if ledger_last is not None:
        candidates.append(ledger_last)
    return max(candidates) + 1


def cmd_beads_claim(toplevel: str, task_id: str) -> None:
    bd_id = _bd_task_id(task_id)
    shown = beads.to_task_id(bd_id)
    branch_setting, base = _claim_preflight(toplevel)

    trk = tracker.session(toplevel)
    pulled = trk.before([bd_id])
    issue = beads.show(toplevel, bd_id)
    if issue is None:
        print(f"NOT_READY\t{shown}\t存在しない")
        raise SystemExit(4)
    task, err = beads.to_task(issue)
    if err is not None:
        print(f"INVALID\t{err}")
        raise SystemExit(3)
    if task is None:
        print(f"NOT_READY\t{shown}\tTRIAGE")
        raise SystemExit(4)
    if issue.status == "in_progress":
        _print_taken(shown, issue)
    if task.status != "todo":
        print(f"NOT_READY\t{shown}\t{task.status}")
        raise SystemExit(4)
    blocked = [beads.to_task_id(d) for d in issue.dependencies if not _beads_resolved(toplevel, d)]
    if blocked:
        print(f"NOT_READY\t{shown}\tBLOCKED:{','.join(blocked)}")
        raise SystemExit(4)

    # `bd update --claim` は依存を見ないので、上で依存を確かめてから取る。取り合いの勝ち負けは Beads が決める。
    actor = _actor(toplevel)
    branch_after_sync = ledger.current_branch(cwd=toplevel)
    claim_args = ["update", bd_id, "--claim", "--set-metadata", f"{beads.CLAIM_BRANCH_KEY}={branch_after_sync}"]
    head = ledger.head_sha_or_none(cwd=toplevel)
    if head is not None:
        claim_args += ["--set-metadata", f"{beads.CLAIM_HEAD_KEY}={head}"]
    r = beads.run(toplevel, claim_args, actor)
    if r.returncode != 0:
        again = beads.show(toplevel, bd_id)
        if again is not None and again.status == "in_progress":
            _print_taken(shown, again)
        raise beads.BeadsError(f"bd update --claim が失敗: {(r.stderr or r.stdout).strip()}")
    _claim_branch_out(toplevel, shown, branch_setting, base, branch_after_sync, f"beads:{bd_id}")
    _print_lines(pulled + trk.after([bd_id]))


def _print_taken(shown: str, issue: beads.Issue) -> None:
    age = _age_seconds(issue.started_at)
    print(f"TAKEN\t{shown}\t{issue.assignee or '?'}\t{format_elapsed(age) if age is not None else '?'}")
    raise SystemExit(4)


def _beads_resolved(toplevel: str, bd_id: str) -> bool:
    dep = beads.show(toplevel, bd_id)
    return dep is None or dep.status == "closed"


def cmd_beads_release(toplevel: str, task_id: str, force: bool) -> None:
    bd_id = _bd_task_id(task_id)
    shown = beads.to_task_id(bd_id)
    trk = tracker.session(toplevel)
    pulled = trk.before([bd_id])
    issue = beads.show(toplevel, bd_id)
    if issue is None or issue.status != "in_progress":
        print(f"NOT_CLAIMED\t{shown}")
        _print_lines(pulled)
        return
    actor = _actor(toplevel)
    if not force and issue.assignee != actor:
        print(f"NOT_OWNER\t{shown}")
        raise SystemExit(4)
    beads.run_ok(toplevel, ["unclaim", bd_id] + (["--force"] if force else []), actor)
    marks = [v for v in beads.SHIP_LABELS.values() if v in issue.labels]
    if marks:
        beads.run_ok(toplevel, ["update", bd_id] + [x for m in marks for x in ("--remove-label", m)], actor)
    print(f"RELEASED\t{shown}")
    _print_lines(pulled + trk.after([bd_id]))


def cmd_beads_done(toplevel: str, task_id: str, dropped: bool, result_path: str) -> None:
    bd_id = _bd_task_id(task_id)
    shown = beads.to_task_id(bd_id)
    actor = _actor(toplevel)
    result = read_body(result_path).strip()
    if result == "":
        print("usage: --result-file の中身が空", file=sys.stderr)
        raise SystemExit(2)
    trk = tracker.session(toplevel)
    pulled = trk.before([bd_id])
    issue = beads.show(toplevel, bd_id)
    if issue is None or issue.status != "in_progress" or issue.assignee != actor:
        print(f"NOT_OWNER\t{shown}")
        _print_lines(pulled)
        raise SystemExit(4)
    kind = "dropped" if dropped else "done"
    beads.run_ok(toplevel, ["comment", bd_id, "--stdin"], actor, f"{beads.RESULT_HEADING}\n\n{result}\n")
    other = beads.SHIP_LABELS["done" if dropped else "dropped"]
    beads.run_ok(
        toplevel, ["update", bd_id, "--add-label", beads.SHIP_LABELS[kind], "--remove-label", other], actor
    )
    print(f"DONE\t{shown}\tbeads:{bd_id}\tship で閉じる")
    metadata = issue.raw.get("metadata")
    head = metadata.get(beads.CLAIM_HEAD_KEY) if isinstance(metadata, dict) else None
    _print_commits_since_claim(toplevel, shown, head)
    _print_lines(pulled + trk.after([bd_id]))


def _beads_ship_hooks(toplevel: str) -> ShipHooks:
    actor = _actor(toplevel)
    not_closed: list[str] = []

    def release_shipped() -> list[str]:
        closed: list[str] = []
        for issue in beads.list_issues(toplevel):
            mark = beads.ship_mark(issue)
            if issue.status != "in_progress" or issue.assignee != actor or mark is None:
                continue
            reason = "cancelled" if mark == "dropped" else "done"
            r = beads.run(toplevel, ["close", issue.bd_id, "--reason", reason], actor)
            if r.returncode != 0:
                not_closed.append(f"NOT_CLOSED\t{beads.to_task_id(issue.bd_id)}\t{(r.stderr or r.stdout).strip()}")
                continue
            update = ["update", issue.bd_id, "--remove-label", beads.SHIP_LABELS[mark]]
            if mark == "dropped":
                update += ["--add-label", beads.CANCELLED_LABEL]
            if issue.external_ref and tracker.read_tracker(toplevel).kind == "jira":
                update += ["--add-label", beads.JIRA_CLOSE_LABEL]
            beads.run_ok(toplevel, update, actor)
            closed.append(beads.to_task_id(issue.bd_id))
        return closed

    def claimed_branch(task_id: str) -> str | None:
        issue = beads.show(toplevel, beads.to_bd_id(task_id))
        metadata = issue.raw.get("metadata") if issue is not None else None
        return metadata.get(beads.CLAIM_BRANCH_KEY) if isinstance(metadata, dict) else None

    def after_send() -> list[str]:
        return not_closed + tracker.session(toplevel).sync_all(pull=False) + beads.backup(toplevel)

    return ShipHooks(release_shipped, claimed_branch, after_send)


def cmd_show(toplevel: str, task_id: str, store: str) -> None:
    """タスク1件をタスクファイルの形で出す（読むだけ）。"""
    if store == layout.STORE_FILES:
        if not taskfile.ID_PATTERN.match(task_id):
            print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
            raise SystemExit(2)
        path = taskfile.task_path(os.path.join(toplevel, layout.TASK_DIR), task_id)
        text = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                text = f.read()
        else:
            text = _read_base_task_text(toplevel, ledger.base_branch(toplevel), f"{task_id}.md")
        if text is None:
            print(f"NOT_READY\t{task_id}\t存在しない")
            raise SystemExit(4)
        sys.stdout.write(text)
        return
    bd_id = _bd_task_id(task_id)
    issue = beads.show(toplevel, bd_id)
    if issue is None:
        print(f"NOT_READY\t{beads.to_task_id(bd_id)}\t存在しない")
        raise SystemExit(4)
    task, err = beads.to_task(issue)
    if err is not None:
        print(f"INVALID\t{err}")
        raise SystemExit(3)
    if task is None:
        task = taskfile.Task(beads.to_task_id(bd_id), issue.title or "-", "todo", "-", "-", (), "")
    result = beads.last_result(beads.comments(toplevel, bd_id))
    sys.stdout.write(beads.render_task(task, issue, result))


def cmd_beads_edit(toplevel: str, args: argparse.Namespace) -> None:
    """本文・summary・difficulty・loopable・todo↔hold を書き換える（ファイル方式で手で直していたもの）。"""
    bd_id = _bd_task_id(args.task_id)
    shown = beads.to_task_id(bd_id)
    if not any([args.body_file, args.summary, args.difficulty, args.loopable, args.status]):
        print("usage: 直すもの（--body-file・--summary・--difficulty・--loopable・--status）が無い", file=sys.stderr)
        raise SystemExit(2)
    trk = tracker.session(toplevel)
    pulled = trk.before([bd_id])
    issue = beads.show(toplevel, bd_id)
    if issue is None:
        print(f"NOT_READY\t{shown}\t存在しない")
        raise SystemExit(4)
    cmd = ["update", bd_id]
    stdin = None
    if args.body_file:
        body = read_body(args.body_file)
        error = taskfile.validate_body(body)
        if error is not None:
            print(f"usage: {error}", file=sys.stderr)
            raise SystemExit(2)
        parts = beads.split_body(body)
        cmd += ["--body-file", "-", "--acceptance", parts.acceptance, "--notes", parts.notes]
        stdin = parts.description
        metadata = issue.raw.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        if (
            issue.status == "in_progress"
            and issue.assignee == _actor(toplevel)
            and taskfile.has_plan(body)
            and not metadata.get(beads.PLAN_KEY)
        ):
            state = _plan_state(toplevel, metadata.get(beads.CLAIM_HEAD_KEY), args.body_file, None)
            cmd += ["--set-metadata", f"{beads.PLAN_KEY}={state}"]
    if args.summary:
        if "\n" in args.summary or not args.summary.strip():
            print("usage: --summary は改行を含まない1行にする", file=sys.stderr)
            raise SystemExit(2)
        cmd += ["--title", args.summary.strip()]
    for value, prefix in ((args.difficulty, beads.DIFFICULTY_LABEL), (args.loopable, beads.LOOPABLE_LABEL)):
        if value:
            cmd += [x for l in issue.labels if l.startswith(prefix) for x in ("--remove-label", l)]
            cmd += ["--add-label", f"{prefix}{value}"]
    if args.status:
        if issue.status not in ("open", *beads.HOLD_STATUSES):
            print(f"NOT_READY\t{shown}\t{issue.status}（todo↔hold は着手前だけ）")
            raise SystemExit(4)
        cmd += ["--status", "open" if args.status == "todo" else beads.HOLD_STATUS]
    r = beads.run(toplevel, cmd, _actor(toplevel), stdin)
    if r.returncode != 0:
        raise beads.BeadsError(f"bd update が失敗: {(r.stderr or r.stdout).strip()}")
    print(f"EDITED\t{shown}")
    _print_lines(pulled + trk.after([bd_id]))


def cmd_beads_plan_check(toplevel: str, task_id: str) -> None:
    bd_id = _bd_task_id(task_id)
    shown = beads.to_task_id(bd_id)
    issue = beads.show(toplevel, bd_id)
    if issue is None or issue.status != "in_progress" or issue.assignee != _actor(toplevel):
        print(f"NOT_OWNER\t{shown}")
        raise SystemExit(4)
    metadata = issue.raw.get("metadata")
    mark = metadata.get(beads.PLAN_KEY) if isinstance(metadata, dict) else None
    _print_plan_check(shown, not taskfile.is_blank(str(issue.raw.get("notes") or "")), mark)


def cmd_beads_adopt(toplevel: str, args: argparse.Namespace) -> None:
    """振り分け前の課題（トラッカーから取り込んだものなど）に番号・difficulty・loopable を付ける。"""
    old = beads.to_bd_id(args.bd_id)
    body = read_body(args.body_file)
    error = taskfile.validate_new_body(body)
    if error is not None:
        print(f"usage: {error}", file=sys.stderr)
        raise SystemExit(2)
    trk = tracker.session(toplevel)
    pulled = trk.before([old])
    issue = beads.show(toplevel, old)
    if issue is None:
        print(f"NOT_READY\t{args.bd_id}\t存在しない")
        raise SystemExit(4)
    actor = _actor(toplevel)
    new_id = old
    # github（`issue_prefix` が `gh`）は取り込みの時点で Issue 番号の ID になっているので番号を振らない。
    if not beads.is_numbered(old) and not trk.bidirectional:
        number = _next_number(toplevel, _beads_snapshot(toplevel))
        for _ in range(NEW_ATTEMPTS):
            new_id = beads.format_bd_id(number)
            r = beads.run(toplevel, ["rename", old, new_id], actor)
            if r.returncode == 0:
                beads.write_last_id(toplevel, number)
                break
            number += 1
        else:
            print(f"LOCKED\t{NEW_ATTEMPTS}回続けて番号を取られた")
            raise SystemExit(4)
    parts = beads.split_body(body)
    cmd = ["update", new_id, "--body-file", "-", "--acceptance", parts.acceptance]
    cmd += [x for l in issue.labels if l.startswith((beads.DIFFICULTY_LABEL, beads.LOOPABLE_LABEL)) for x in ("--remove-label", l)]
    cmd += ["--add-label", f"{beads.DIFFICULTY_LABEL}{args.difficulty}", "--add-label", f"{beads.LOOPABLE_LABEL}{args.loopable}"]
    if args.summary:
        cmd += ["--title", args.summary.strip()]
    beads.run_ok(toplevel, cmd, actor, parts.description)
    print(f"ADOPTED\t{args.bd_id}\t{beads.to_task_id(new_id)}")
    _print_lines(pulled + trk.after([new_id]))


def cmd_beads_sync(toplevel: str) -> None:
    lines = tracker.session(toplevel).sync_all(pull=True)
    if not lines:
        print("NOTHING\t(トラッカーなし)")
        return
    _print_lines(lines)
    if any(l.startswith("TRACKER\tFAILED") for l in lines):
        raise SystemExit(10)


def cmd_beads_backup(toplevel: str) -> None:
    lines = beads.backup(toplevel)
    _print_lines(lines)
    if any("\tFAILED\t" in l for l in lines):
        raise SystemExit(10)


def cmd_beads_jira_closed(toplevel: str, task_ids: list[str]) -> None:
    """Jira で閉じたのを人が確かめたものから `jira:close` を外す。"""
    actor = _actor(toplevel)
    for task_id in task_ids:
        bd_id = _bd_task_id(task_id)
        beads.run_ok(toplevel, ["update", bd_id, "--remove-label", beads.JIRA_CLOSE_LABEL], actor)
        print(f"CLEARED\t{beads.to_task_id(bd_id)}")


def _doctor_store(toplevel: str) -> int:
    """`config-doctor` の検査5。`store`・（Beads 方式なら）`beads`・`tracker` の行を出し、終了コードを返す。"""
    try:
        store = layout.read_store(toplevel)
    except layout.StoreSettingError as e:
        print(f"store\tINVALID\t{e}")
        return 3
    print(f"store\tOK\t{store}")
    if store != layout.STORE_BEADS:
        return 0
    code = 0
    if beads.is_initialized(toplevel):
        print(f"beads\tOK\t{beads.beads_dir(toplevel)}")
    else:
        print(f"beads\tMISSING\t{beads.beads_dir(toplevel)}\tinit.py（bd init --stealth）")
        code = 1
    try:
        t = tracker.read_tracker(toplevel)
    except tracker.TrackerSettingError as e:
        print(f"tracker\tINVALID\t{e}")
        return 3
    detail = f"\t{t.project_owner}/{t.project_number}" if t.kind == "github" else ""
    print(f"tracker\tOK\t{t.kind}{detail}")
    return code


# --- 入口 -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="task.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--all", dest="show_all", action="store_true")
    p_status.add_argument("--check", action="store_true")

    p_new = sub.add_parser("new")
    p_new.add_argument("--summary", required=True)
    p_new.add_argument("--difficulty", required=True, choices=taskfile.DIFFICULTY_VALUES)
    p_new.add_argument("--loopable", required=True, choices=taskfile.LOOPABLE_VALUES)
    p_new.add_argument("--deps", default="")
    p_new.add_argument("--hold", action="store_true")
    p_new.add_argument("--body-file", required=True)

    p_claim = sub.add_parser("claim")
    p_claim.add_argument("task_id")

    p_release = sub.add_parser("release")
    p_release.add_argument("task_id")
    p_release.add_argument("--force", action="store_true")

    p_done = sub.add_parser("done")
    p_done.add_argument("task_id")
    p_done.add_argument("--dropped", action="store_true")
    p_done.add_argument("--result-file", required=True)

    sub.add_parser("ship")

    p_prune = sub.add_parser("prune")
    p_prune.add_argument("--dry-run", dest="dry_run", action="store_true")
    p_prune.add_argument("--min", dest="minimum", type=int, default=PRUNE_MIN_DEFAULT)

    p_migrate = sub.add_parser("migrate")
    p_migrate.add_argument("--dry-run", dest="dry_run", action="store_true")

    sub.add_parser("config-doctor")

    p_show = sub.add_parser("show")
    p_show.add_argument("task_id")

    p_plan_check = sub.add_parser("plan-check")
    p_plan_check.add_argument("task_id")

    # ファイル方式は --body-file だけ（ほかはタスクファイルを直に直す）。
    p_edit = sub.add_parser("edit")
    p_edit.add_argument("task_id")
    p_edit.add_argument("--body-file", default=None)
    p_edit.add_argument("--summary", default=None)
    p_edit.add_argument("--difficulty", default=None, choices=taskfile.DIFFICULTY_VALUES)
    p_edit.add_argument("--loopable", default=None, choices=taskfile.LOOPABLE_VALUES)
    p_edit.add_argument("--status", default=None, choices=("todo", "hold"))

    # 以下は Beads 方式だけ。

    p_adopt = sub.add_parser("adopt")
    p_adopt.add_argument("bd_id")
    p_adopt.add_argument("--difficulty", required=True, choices=taskfile.DIFFICULTY_VALUES)
    p_adopt.add_argument("--loopable", required=True, choices=taskfile.LOOPABLE_VALUES)
    p_adopt.add_argument("--summary", default=None)
    p_adopt.add_argument("--body-file", required=True)

    sub.add_parser("sync")
    sub.add_parser("backup")

    p_jira_closed = sub.add_parser("jira-closed")
    p_jira_closed.add_argument("task_ids", nargs="+")

    return parser


BEADS_ONLY_COMMANDS = ("adopt", "sync", "backup", "jira-closed")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        toplevel = ledger.git_toplevel()
    except ledger.GitCommandError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    if args.command not in ("migrate", "config-doctor"):
        kind, detail = detect_format(toplevel)
        if kind == "INVALID":
            print(f"INVALID\t{detail}")
            raise SystemExit(3)
        if kind == "LEGACY":
            print("LEGACY\ttask migrate --dry-run")
            raise SystemExit(5)
        if kind == "MISSING":
            print("MISSING")
            raise SystemExit(6)

    # 主ブランチは要る道でだけ問い合わせる（`ledger.base_branch`。決まらなければ INVALID）。
    try:
        store = layout.read_store(toplevel) if args.command not in ("migrate", "config-doctor") else None
        if store == layout.STORE_BEADS:
            _main_beads(toplevel, args)
            return
        if args.command in BEADS_ONLY_COMMANDS:
            print(f"usage: {args.command} は Beads 方式だけ（ファイル方式では develop/task/ を直に直す）", file=sys.stderr)
            raise SystemExit(2)
        if args.command == "status":
            cmd_status(toplevel, args.show_all, args.check)
        elif args.command == "new":
            cmd_new(toplevel, args)
        elif args.command == "claim":
            cmd_claim(toplevel, args.task_id)
        elif args.command == "release":
            cmd_release(toplevel, args.task_id, args.force)
        elif args.command == "done":
            cmd_done(toplevel, args.task_id, args.dropped, args.result_file)
        elif args.command == "ship":
            cmd_ship(toplevel)
        elif args.command == "prune":
            cmd_prune(toplevel, args.dry_run, max(args.minimum, 1))
        elif args.command == "migrate":
            cmd_migrate(toplevel, args.dry_run)
        elif args.command == "config-doctor":
            cmd_config_doctor(toplevel)
        elif args.command == "show":
            cmd_show(toplevel, args.task_id, layout.STORE_FILES)
        elif args.command == "edit":
            cmd_edit(toplevel, args)
        elif args.command == "plan-check":
            cmd_plan_check(toplevel, args.task_id)
    except (ledger.NoBaseBranch, layout.ConfigConflict, layout.StoreSettingError, tracker.TrackerSettingError) as e:
        print(f"INVALID\t{e}")
        raise SystemExit(3)


def _main_beads(toplevel: str, args: argparse.Namespace) -> None:
    if not beads.is_initialized(toplevel):
        print(f"MISSING\t{beads.beads_dir(toplevel)}")
        raise SystemExit(6)
    tracker.read_tracker(toplevel)  # 読めない設定はどのサブコマンドでも先に INVALID にする
    try:
        if args.command == "status":
            cmd_beads_status(toplevel, args.show_all, args.check)
        elif args.command == "new":
            cmd_beads_new(toplevel, args)
        elif args.command == "claim":
            cmd_beads_claim(toplevel, args.task_id)
        elif args.command == "release":
            cmd_beads_release(toplevel, args.task_id, args.force)
        elif args.command == "done":
            cmd_beads_done(toplevel, args.task_id, args.dropped, args.result_file)
        elif args.command == "ship":
            cmd_ship(toplevel, _beads_ship_hooks(toplevel))
        elif args.command == "prune":
            print("NOTHING\t(Beads 方式には消すタスクファイルが無い)")
        elif args.command == "show":
            cmd_show(toplevel, args.task_id, layout.STORE_BEADS)
        elif args.command == "edit":
            cmd_beads_edit(toplevel, args)
        elif args.command == "plan-check":
            cmd_beads_plan_check(toplevel, args.task_id)
        elif args.command == "adopt":
            cmd_beads_adopt(toplevel, args)
        elif args.command == "sync":
            cmd_beads_sync(toplevel)
        elif args.command == "backup":
            cmd_beads_backup(toplevel)
        elif args.command == "jira-closed":
            cmd_beads_jira_closed(toplevel, args.task_ids)
    except beads.BeadsError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
