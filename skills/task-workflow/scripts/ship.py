"""`task ship` の git 操作（rebase → 検証 → 送る）。

正典は `docs/task-workflow-redesign.md` の5.8・6章。**merge commit は作らない**——
取り込みは `git rebase`、送るのは `git merge --ff-only`（本体がある場合）か比較付きの
`git update-ref`（無い場合）だけ（6.2手順5）。取り合い（`--ff-only`／`update-ref` の失敗）は
「相手に先を越された」合図として、最大 `MAX_TRIES` 回まで rebase からやり直す。

クレームの後始末・出力の組み立て・終了コードは呼び出し側（`task.py` の `cmd_ship`）が持つ。
ここは1回の `ship` にかかる git の手順だけを持つ。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

import ledger

MAX_TRIES = 3


@dataclass(frozen=True)
class ShipOutcome:
    kind: str  # "SENT" | "CONFLICT" | "VERIFY_FAILED" | "RACE"
    rebased: bool = False
    verify_state: str = "none"  # "ran" | "skipped" | "none"（6.3）
    tries: int = 0
    conflict_files: tuple[str, ...] = field(default_factory=tuple)
    verify_command: str | None = None
    verify_tail: str = ""


def read_verify_command(toplevel: str) -> str | None:
    """CLAUDE.md の `- 検証コマンド:` 行の最初の `` `…` `` を読む（6.3）。

    行が無い、または値が `なし` で始まるなら `None`（打たない。`verify=none`）。
    """
    path = os.path.join(toplevel, "CLAUDE.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^- 検証コマンド:\s*(.*)$", text, flags=re.MULTILINE)
    if m is None:
        return None
    value = m.group(1).strip()
    if value.startswith("なし"):
        return None
    cmd_m = re.search(r"`([^`]+)`", value)
    return cmd_m.group(1) if cmd_m else None


def find_main_worktree(worktrees: list[ledger.Worktree], own_path: str) -> ledger.Worktree | None:
    """`main` を出している別の作業ツリー（本体）を探す（6.2手順4）。自分自身は数えない。"""
    return next((w for w in worktrees if w.branch == "main" and w.path != own_path), None)


def _run(cwd: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def attempt(
    toplevel: str,
    main_worktree: ledger.Worktree | None,
    verify_command: str | None,
) -> ShipOutcome:
    """最大 `MAX_TRIES` 回、rebase → 検証（付け替えた回だけ）→ 送る、を繰り返す（6.2手順5・6）。

    送る先は `main_worktree` があれば `git -C <本体> merge --ff-only <HEAD のコミット>`、無ければ
    比較付きの `git update-ref`。失敗（相手に先を越された）は次の回の rebase からやり直す。
    """
    rebased_any = False
    verify_state = "none" if verify_command is None else "skipped"

    for tries in range(1, MAX_TRIES + 1):
        rebased_this_round = False
        is_ancestor = _run(toplevel, ["merge-base", "--is-ancestor", "main", "HEAD"]).returncode == 0
        if not is_ancestor:
            r = _run(toplevel, ["rebase", "main"])
            if r.returncode != 0:
                conflicts = _run(toplevel, ["diff", "--name-only", "--diff-filter=U"]).stdout.splitlines()
                _run(toplevel, ["rebase", "--abort"])
                return ShipOutcome(kind="CONFLICT", conflict_files=tuple(f for f in conflicts if f))
            rebased_this_round = True
            rebased_any = True

        if rebased_this_round and verify_command is not None:
            vr = subprocess.run(["sh", "-c", verify_command], cwd=toplevel, capture_output=True, text=True)
            verify_state = "ran"
            if vr.returncode != 0:
                tail = "\n".join(((vr.stdout or "") + (vr.stderr or "")).splitlines()[-40:])
                return ShipOutcome(
                    kind="VERIFY_FAILED",
                    rebased=rebased_any,
                    verify_state=verify_state,
                    tries=tries,
                    verify_command=verify_command,
                    verify_tail=tail,
                )

        # 枝の名前ではなくコミットで送る（detached HEAD の `HEAD` は本体の側では本体自身を指す）。
        head = _run(toplevel, ["rev-parse", "HEAD"]).stdout.strip()
        if main_worktree is not None:
            sent = _run(main_worktree.path, ["merge", "--ff-only", head]).returncode == 0
        else:
            seen_main = _run(toplevel, ["rev-parse", "main"]).stdout.strip()
            sent = _run(toplevel, ["update-ref", "refs/heads/main", head, seen_main]).returncode == 0

        if sent:
            return ShipOutcome(kind="SENT", rebased=rebased_any, verify_state=verify_state, tries=tries)

    return ShipOutcome(kind="RACE", rebased=rebased_any, verify_state=verify_state, tries=MAX_TRIES)
