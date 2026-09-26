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

import init
import layout
import ledger
import legacy
import ship
import taskfile


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

    ready_count = sum(
        1 for tid, t in tasks.items() if t.status == "todo" and readiness(t, tasks, claims) == "READY"
    )
    print(f"ready\t{ready_count}")

    todo_loopable_n = sum(1 for t in tasks.values() if t.status == "todo" and t.loopable == "N")
    print(f"todo_loopable\tN={todo_loopable_n}")

    long_ids = [
        tid
        for tid in sorted(tasks, key=taskfile.id_number)
        if tasks[tid].status in ("todo", "hold") and display_width(tasks[tid].summary) > LONG_SUMMARY_WIDTH
    ]
    print(f"long_summary\t{len(long_ids)}\t" + (",".join(long_ids) or "-"))

    stale_entries = []
    for tid in claims:
        label, detail = classify_claim(root, tid, tasks.get(tid), worktrees)
        if label != "CLAIMED":
            stale_entries.append(f"{tid}:{label}({detail})" if detail else f"{tid}:{label}")
    print(f"stale\t{len(stale_entries)}\t" + (",".join(stale_entries) if stale_entries else "-"))

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
        feature_branch = f"{layout.FEATURE_BRANCH_PREFIX}{task_id}"
        r = _run_git(toplevel, ["checkout", "-b", feature_branch, base])
        if r.returncode != 0:
            print(f"CLAIMED\t{task_id}\t{layout.TASK_DIR}/{task_id}.md\tbranch=(切れない: {r.stderr.strip()})")
            return
        print(f"CLAIMED\t{task_id}\t{layout.TASK_DIR}/{task_id}.md\tbranch={feature_branch}")
    else:
        print(f"CLAIMED\t{task_id}\t{layout.TASK_DIR}/{task_id}.md\tbranch={branch_after_sync}")


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


def cmd_ship(toplevel: str) -> None:
    if not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    root = ledger.ledger_root(cwd=toplevel)
    base = ledger.base_branch(toplevel)
    branch = ledger.current_branch(cwd=toplevel)

    if branch == base:
        # 4.4: 主ブランチを出している作業ツリーで起こしたときは送る段が無い。
        released = _release_own_claims_when_shipped(root, toplevel)
        print(f"SHIPPED\t{base}\t(送る段なし)\treleased={','.join(released) or '-'}")
        return

    ahead = _run_git(toplevel, ["rev-list", "--count", f"{base}..HEAD"])
    ahead_count = int(ahead.stdout.strip()) if ahead.returncode == 0 and ahead.stdout.strip().isdigit() else 0
    if ahead_count == 0:
        _release_own_claims_when_shipped(root, toplevel)
        print(f"NOTHING\t({base} に無いコミットが無い)")
        return

    worktrees = ledger.list_worktrees(cwd=toplevel)
    base_worktree = ship.find_base_worktree(worktrees, toplevel, base)
    if base_worktree is not None and not ledger.is_clean(cwd=base_worktree.path):
        print(f"MAIN_DIRTY\t{base_worktree.path}")
        raise SystemExit(4)

    old_base = _run_git(toplevel, ["rev-parse", base]).stdout.strip()
    verify_command = ship.read_verify_command(toplevel)
    outcome = ship.attempt(toplevel, base_worktree, verify_command, base)

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

    branch_note = f"branch={branch}"
    if read_branch_setting(toplevel) in ("既定", "作業ブランチを切る") and FEATURE_BRANCH.fullmatch(branch):
        # 印を消す前に読む（戻り先は印の owner にある）。
        branch_note = _leave_feature_branch(root, toplevel, branch)

    released = _release_own_claims_when_shipped(root, toplevel)
    new_base = _run_git(toplevel, ["rev-parse", base]).stdout.strip()
    print(
        f"SHIPPED\t{old_base}..{new_base}\trebased={'yes' if outcome.rebased else 'no'}"
        f"\tverify={outcome.verify_state}\ttries={outcome.tries}\treleased={','.join(released) or '-'}"
        f"\t{branch_note}"
    )


FEATURE_BRANCH = layout.FEATURE_BRANCH_PATTERN


def _leave_feature_branch(root: str, toplevel: str, branch: str) -> str:
    """送り終えた `feature/T-xxx` から降りて枝を消す（6.2手順7）。出力の `branch=…` 欄を返す。

    戻り先は `claim` した時点の枝（印の owner の `branch=`）→ 主ブランチの順に試す。主ブランチを
    別の作業ツリー（本体）が出していると `checkout` は通らないので、作業ツリー固有の枝が
    あればそこへ戻して主ブランチまで追い付かせる。どちらにも移れなければ主ブランチの位置で
    detached HEAD にする（枝を黙って残さない。detached のままでも次の `claim` は主ブランチから切る）。
    消せなかったときは `kept=<枝>` を添えて知らせる。
    """
    base = ledger.base_branch(toplevel)
    m = FEATURE_BRANCH.fullmatch(branch)
    owner = ledger.read_owner(ledger.claim_dir(root, m.group(1))) if m else None
    back = (owner or {}).get("branch")
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

# develop/retrospective.md の中で機械が読む1行（retrospect/scripts/scan.py と同じ形）。
RETROSPECT_LINE = re.compile(r"^最後に振り返ったコミット:\s*`([0-9a-f]{7,40})`")
# 1件ごとの振り返りが済んだ印。`## 結果` の中のこの形の行（WORKFLOW.md「結果の書き方と知見の置き場」）。
REVIEWED_LINE = re.compile(r"^- 振り返り:")
# 消せるものがこの件数に届くまでは消さない。毎サイクル1件ずつ消すと削除だけのコミットが
# タスクと同じ数だけ積もるため、まとめて1コミットにする。
PRUNE_MIN_DEFAULT = 10


def cmd_prune(toplevel: str, dry_run: bool, minimum: int) -> None:
    """振り返りが済んだ done/dropped のタスクファイルを `git rm` して stage する（コミットしない）。

    判定は `HEAD` の版で done/dropped・台帳に印が無い・次のどちらか:
    `reviewed` = `## 結果` に `- 振り返り:` の行がある（1件ごとの振り返り済み）、
    `retrospect` = `develop/retrospective.md` の基準点の版で既に done/dropped（まとめての振り返りが
    読み終えた）。印のあるタスクを除くのは、`ship` が主ブランチの版で done を見て印を消すため。
    対象が `minimum` 件に届かなければ何もしない（`NOTHING`）。
    """
    if not dry_run and not ledger.is_clean(cwd=toplevel):
        print("DIRTY")
        raise SystemExit(4)

    since, err = _retrospect_base(toplevel)
    if err is not None:
        print(f"INVALID\t{err}")
        raise SystemExit(3)

    claims = set(ledger.list_claims(ledger.ledger_root(cwd=toplevel)))
    targets: list[tuple[str, str]] = []
    for tid, task in sorted(_tasks_at(toplevel, "HEAD").items(), key=lambda kv: taskfile.id_number(kv[0])):
        if task.status not in ("done", "dropped") or tid in claims:
            continue
        if _has_review_line(task.body):
            targets.append((tid, "reviewed"))
        elif since is not None and _status_at(toplevel, since, tid) in ("done", "dropped"):
            targets.append((tid, "retrospect"))

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


def _retrospect_base(toplevel: str) -> tuple[str | None, str | None]:
    """`(基準点のハッシュ, INVALIDの理由)`。記録ファイルや1行が無ければ基準点なし（`reviewed` だけで判定）。"""
    path = os.path.join(toplevel, layout.RETROSPECTIVE_PATH)
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as f:
        m = next((m for m in (RETROSPECT_LINE.match(l.strip()) for l in f) if m), None)
    if m is None:
        return None, None
    since = m.group(1)
    if _run_git(toplevel, ["cat-file", "-e", f"{since}^{{commit}}"]).returncode != 0:
        return None, f"{layout.RETROSPECTIVE_PATH} の基準点 {since} がこのリポジトリに無い"
    return since, None


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


def _status_at(toplevel: str, rev: str, task_id: str) -> str | None:
    shown = _run_git(toplevel, ["show", f"{rev}:{layout.TASK_DIR}/{task_id}.md"])
    if shown.returncode != 0:
        return None
    parsed, err = taskfile.parse(shown.stdout)
    return parsed.status if err is None and parsed is not None else None


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

    if exit_code:
        raise SystemExit(exit_code)


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

    return parser


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
    except (ledger.NoBaseBranch, layout.ConfigConflict) as e:
        print(f"INVALID\t{e}")
        raise SystemExit(3)


if __name__ == "__main__":
    main()
