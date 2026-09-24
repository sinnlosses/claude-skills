#!/usr/bin/env python3
"""1件1ファイル＋台帳の形のタスク運用を操作する入口コマンド。

使い方: task.py <status|new|claim|release|done|ship> ...

正典は `docs/task-workflow-redesign.md`（5章が `task` コマンド、4章が状態と台帳、
3章がタスクファイル、6章が送り出し、5.9・10章が `migrate`）。スキルからは
`python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py <サブコマンド> …` で呼ぶ
（5.1。PATH には入れない）。**このファイルはまだどのスキルからも呼ばれない**
（12章: T-521〜T-523 は `task.py` 一式を足すだけで、切り替えは T-526）。

出力は常に stdout（先頭語で種類を判定する TSV）、stderr は使い方の誤りだけ、
終了コードは5.2の表のとおり。データの不備で traceback を出さない
（`status.py`/`taskfiles.py` と同じ立場）。`migrate` の実体は `legacy.py`（旧形式の
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

import ledger
import legacy
import ship
import taskfile

TASK_DIR_NAME = "task"


# --- 形式の判定（5.2） -----------------------------------------------------


def detect_format(toplevel: str) -> tuple[str, str | None]:
    tasks_json = os.path.join(toplevel, "develop", "tasks.json")
    task_dir = os.path.join(toplevel, "develop", TASK_DIR_NAME)
    direction = os.path.join(toplevel, "develop", "direction.md")
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


def _list_main_task_filenames(toplevel: str) -> list[str]:
    r = _run_git(toplevel, ["ls-tree", "--name-only", "-r", "main", "--", "develop/task"])
    if r.returncode != 0:
        return []
    return [os.path.basename(p) for p in r.stdout.splitlines() if p.endswith(".md")]


def _read_main_task_text(toplevel: str, filename: str) -> str | None:
    r = _run_git(toplevel, ["show", f"main:develop/task/{filename}"])
    return r.stdout if r.returncode == 0 else None


def _history_ids_at_main(toplevel: str) -> set[str]:
    r = _run_git(toplevel, ["show", "main:docs/history/tasks.md"])
    if r.returncode != 0:
        return set()
    return {m.group(1) for m in re.finditer(r"^## (T-\d{3,})\b", r.stdout, flags=re.MULTILINE)}


# --- タスクの読み取り（main を正とし、作業ツリーだけの分は local として足す） ---


def load_tasks(
    toplevel: str,
) -> tuple[dict[str, taskfile.Task], dict[str, str], list[str]]:
    """`(id→Task, id→INVALID理由, ローカルにしか無いID)` を返す（5.3: main を正とする）。"""
    tasks: dict[str, taskfile.Task] = {}
    invalid: dict[str, str] = {}

    for filename in _list_main_task_filenames(toplevel):
        stem = os.path.splitext(filename)[0]
        text = _read_main_task_text(toplevel, filename)
        if text is None:
            continue
        parsed, err = taskfile.parse(text)
        if err is not None or parsed is None or parsed.id != stem:
            invalid[stem] = err or f"ファイル名（{stem}）と id（{parsed.id if parsed else '?'}）が不一致"
            continue
        tasks[parsed.id] = parsed

    task_dir = os.path.join(toplevel, "develop", TASK_DIR_NAME)
    local_only: list[str] = []
    for stem in taskfile.local_task_ids(task_dir):
        if stem in tasks or stem in invalid:
            continue  # main にもある ID は main を正とする
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
    main_task: taskfile.Task | None,
    worktrees: list[ledger.Worktree],
) -> tuple[str, str]:
    """4.3の判定。`(表示語, 詳細)` を返す。表示語は `CLAIMED` か `STALE:*`。"""
    d = ledger.claim_dir(root, task_id)
    owner = ledger.read_owner(d)
    if owner is None:
        age = time.time() - os.stat(d).st_mtime
        return ("STALE:no-owner", "") if age > 60 else ("CLAIMED", "書き込み中")
    worktree = owner.get("worktree", "?")
    if main_task is not None and main_task.status in ("done", "dropped"):
        return "STALE:shipped", worktree
    if not any(w.path == worktree for w in worktrees):
        return "STALE:gone", worktree
    age = ledger.owner_age_seconds(d)
    elapsed = format_elapsed(age) if age is not None else "?"
    return "CLAIMED", f"{os.path.basename(worktree)} {elapsed}"


def read_branch_setting(toplevel: str) -> str:
    """CLAUDE.md の `- ブランチ:` 行の先頭語だけを読む（6.1）。無ければ `既定`。"""
    path = os.path.join(toplevel, "CLAUDE.md")
    if not os.path.exists(path):
        return "既定"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^- ブランチ:\s*(\S+)", text, flags=re.MULTILINE)
    return m.group(1) if m else "既定"


def _section_bullets(text: str, heading_prefix: str) -> int:
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(heading_prefix)), None)
    if start is None:
        return 0
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return sum(1 for l in lines[start + 1 : end] if l.strip().startswith("- "))


def count_backlog_items(toplevel: str) -> int:
    path = os.path.join(toplevel, "develop", "direction.md")
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        return _section_bullets(f.read(), "## 積み残し")


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
    history_path = os.path.join(toplevel, "docs", "history", "tasks.md")
    history = taskfile.history_ids(history_path)

    if check:
        problems = [f"{stem}:{reason}" for stem, reason in invalid.items()]
        problems += [
            f"{tid}:タスクファイルと docs/history/tasks.md の両方にある" for tid in tasks if tid in history
        ]
        if problems:
            print("INVALID\t" + "; ".join(problems))
            raise SystemExit(3)
        print("OK")
        return

    for tid in sorted(tasks, key=taskfile.id_number):
        t = tasks[tid]
        if not show_all and t.status in ("done", "dropped"):
            continue
        ready = readiness(t, tasks, claims)
        if tid in claims:
            label, detail = classify_claim(root, tid, t, worktrees)
            marker = detail if label == "CLAIMED" else f"{label}({detail})"
        elif tid in local_only:
            marker = "local"
        else:
            marker = "-"
        print(
            "\t".join(
                [
                    tid,
                    t.status,
                    t.difficulty,
                    t.loopable,
                    ",".join(t.dependencies) or "-",
                    ready,
                    marker,
                    t.summary,
                ]
            )
        )

    print("---")
    counts = {s: sum(1 for t in tasks.values() if t.status == s) for s in taskfile.STATUS_VALUES}
    counts["claimed"] = len(claims)
    print("counts\t" + "\t".join(f"{k}={v}" for k, v in counts.items()))

    cap = ledger.parallelism(cwd=toplevel) * 2
    ready_count = sum(
        1 for tid, t in tasks.items() if t.status == "todo" and readiness(t, tasks, claims) == "READY"
    )
    print(f"ready\t{ready_count}/{cap}\t(並列数 {ledger.parallelism(cwd=toplevel)})")

    todo_loopable_n = sum(1 for t in tasks.values() if t.status == "todo" and t.loopable == "N")
    print(f"todo_loopable\tN={todo_loopable_n}")

    stale_entries = []
    for tid in claims:
        label, detail = classify_claim(root, tid, tasks.get(tid), worktrees)
        if label != "CLAIMED":
            stale_entries.append(f"{tid}:{label}({detail})" if detail else f"{tid}:{label}")
    print(f"stale\t{len(stale_entries)}\t" + (",".join(stale_entries) if stale_entries else "-"))

    print(f"backlog\t{count_backlog_items(toplevel)}\t(develop/direction.md の ## 積み残し)")
    print(f"invalid\t{len(invalid)}\t" + (",".join(sorted(invalid)) if invalid else "-"))

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
        deps_resolved = all(is_resolved(d, tasks) for d in deps)
        counts_toward_cap = status == "todo" and deps_resolved
        if counts_toward_cap:
            cap = ledger.parallelism(cwd=toplevel) * 2
            claims = set(ledger.list_claims(root))
            ready_count = sum(
                1
                for tid, t in tasks.items()
                if t.status == "todo" and readiness(t, tasks, claims) == "READY"
            )
            if ready_count >= cap:
                print(
                    f"CAP\t{ready_count}/{cap}\t(並列数 {ledger.parallelism(cwd=toplevel)})"
                    "\t残りは develop/direction.md の ## 積み残し へ"
                )
                raise SystemExit(4)

        history_path = os.path.join(toplevel, "docs", "history", "tasks.md")
        candidate_ids = (
            list(tasks) + [i for i in invalid if taskfile.ID_PATTERN.match(i)]
            + list(taskfile.history_ids(history_path))
            + list(_history_ids_at_main(toplevel))
        )
        candidates = [0] + [taskfile.id_number(i) for i in candidate_ids]
        last_id = ledger.read_last_id(root)
        if last_id is not None:
            candidates.append(last_id)
        number = max(candidates) + 1
        task_id = taskfile.format_id(number)

        task_dir = os.path.join(toplevel, "develop", TASK_DIR_NAME)
        os.makedirs(task_dir, exist_ok=True)
        path = taskfile.task_path(task_dir, task_id)
        rendered = taskfile.render(
            taskfile.Task(task_id, summary, status, args.difficulty, args.loopable, deps, body)
        )
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(rendered)

        ledger.write_last_id(root, number)
        print(f"CREATED\t{task_id}\tdevelop/task/{task_id}.md")
    finally:
        ledger.release_lock(root)


# --- claim（5.5） -----------------------------------------------------------


def cmd_claim(toplevel: str, task_id: str) -> None:
    if not taskfile.ID_PATTERN.match(task_id):
        print(f"usage: {task_id!r} が T-999 の形式でない", file=sys.stderr)
        raise SystemExit(2)

    branch_setting = read_branch_setting(toplevel)
    if branch_setting not in ("既定", "作業ブランチを切る", "切らない"):
        print(f"INVALID\t- ブランチ: の値 {branch_setting!r} を機械が読めない")
        raise SystemExit(3)

    if not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    branch = ledger.current_branch(cwd=toplevel)
    if branch != "main":
        ahead = _run_git(toplevel, ["rev-list", "--count", "main..HEAD"])
        if ahead.returncode == 0 and ahead.stdout.strip() not in ("0", ""):
            print(f"UNSHIPPED\t{ahead.stdout.strip()}")
            raise SystemExit(4)
        r = _run_git(toplevel, ["merge", "--ff-only", "main"])
        if r.returncode != 0:
            print(f"INVALID\tmain へ追い付けない（{r.stderr.strip()}）")
            raise SystemExit(3)

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
    if not ledger.try_claim(root, task_id, toplevel, branch_after_sync):
        d = ledger.claim_dir(root, task_id)
        owner = ledger.read_owner(d) or {}
        age = ledger.owner_age_seconds(d)
        elapsed = format_elapsed(age) if age is not None else "?"
        print(f"TAKEN\t{task_id}\t{owner.get('worktree', '?')}\t{elapsed}")
        raise SystemExit(4)

    if branch_setting in ("既定", "作業ブランチを切る"):
        feature_branch = f"feature/{task_id}"
        r = _run_git(toplevel, ["checkout", "-b", feature_branch, "main"])
        if r.returncode != 0:
            print(f"CLAIMED\t{task_id}\tdevelop/task/{task_id}.md\tbranch=(切れない: {r.stderr.strip()})")
            return
        print(f"CLAIMED\t{task_id}\tdevelop/task/{task_id}.md\tbranch={feature_branch}")
    else:
        print(f"CLAIMED\t{task_id}\tdevelop/task/{task_id}.md\tbranch={branch_after_sync}")


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

    task_dir = os.path.join(toplevel, "develop", TASK_DIR_NAME)
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

    relpath = os.path.join("develop", TASK_DIR_NAME, f"{task_id}.md")
    _run_git(toplevel, ["add", relpath])
    print(f"DONE\t{task_id}\t{relpath}\tstaged")


# --- ship（5.8・6章） --------------------------------------------------------


def _release_own_claims_when_shipped(root: str, toplevel: str) -> list[str]:
    """4.4・5.8手順7: 自分の作業ツリーの印のうち、`main`（HEAD）で done/dropped に
    なったものを消す。`main` を正として読む（`load_tasks` は git show 経由なので、
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


def cmd_ship(toplevel: str) -> None:
    if not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    root = ledger.ledger_root(cwd=toplevel)
    branch = ledger.current_branch(cwd=toplevel)

    if branch == "main":
        # 4.4: main を出している作業ツリーで起こしたときは送る段が無い。
        released = _release_own_claims_when_shipped(root, toplevel)
        print(f"SHIPPED\tmain\t(送る段なし)\treleased={','.join(released) or '-'}")
        return

    ahead = _run_git(toplevel, ["rev-list", "--count", "main..HEAD"])
    ahead_count = int(ahead.stdout.strip()) if ahead.returncode == 0 and ahead.stdout.strip().isdigit() else 0
    if ahead_count == 0:
        _release_own_claims_when_shipped(root, toplevel)
        print("NOTHING\t(main に無いコミットが無い)")
        return

    worktrees = ledger.list_worktrees(cwd=toplevel)
    main_worktree = ship.find_main_worktree(worktrees, toplevel)
    if main_worktree is not None and not ledger.is_clean(cwd=main_worktree.path):
        print(f"MAIN_DIRTY\t{main_worktree.path}")
        raise SystemExit(4)

    old_main = _run_git(toplevel, ["rev-parse", "main"]).stdout.strip()
    verify_command = ship.read_verify_command(toplevel)
    outcome = ship.attempt(toplevel, branch, main_worktree, verify_command)

    if outcome.kind == "CONFLICT":
        print("CONFLICT\t" + (",".join(outcome.conflict_files) or "?"))
        raise SystemExit(7)
    if outcome.kind == "VERIFY_FAILED":
        print(f"VERIFY_FAILED\t{outcome.verify_command}")
        if outcome.verify_tail:
            print(outcome.verify_tail)
        raise SystemExit(8)
    if outcome.kind == "RACE":
        print("RACE\t3")
        raise SystemExit(9)

    branch_setting = read_branch_setting(toplevel)
    if branch_setting in ("既定", "作業ブランチを切る"):
        # 送った直後なので、この枝はどの作業ツリーにも要らない（6.2手順7）。
        r = _run_git(toplevel, ["checkout", "main"])
        if r.returncode == 0:
            _run_git(toplevel, ["branch", "-d", branch])

    released = _release_own_claims_when_shipped(root, toplevel)
    new_main = _run_git(toplevel, ["rev-parse", "main"]).stdout.strip()
    print(
        f"SHIPPED\t{old_main}..{new_main}\trebased={'yes' if outcome.rebased else 'no'}"
        f"\tverify={outcome.verify_state}\ttries={outcome.tries}\treleased={','.join(released) or '-'}"
    )


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

    p_migrate = sub.add_parser("migrate")
    p_migrate.add_argument("--dry-run", dest="dry_run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        toplevel = ledger.git_toplevel()
    except ledger.GitCommandError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    if args.command != "migrate":
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
    elif args.command == "migrate":
        cmd_migrate(toplevel, args.dry_run)


if __name__ == "__main__":
    main()
