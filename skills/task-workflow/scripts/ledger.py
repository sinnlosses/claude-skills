"""共有の `.git` の中に置く台帳（着手の印・採番の錠・最後の番号）。

正典は `docs/task-workflow-redesign.md` の4.2〜4.3。台帳はクローンに1つ
（`git rev-parse --path-format=absolute --git-common-dir` の下）で、コミットしないので
主ブランチを動かさない。取り合いの判定は `mkdir` の成否だけで決める（不可分な操作なので、
2プロセスが同時に呼んでも一方だけが成功する）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import layout

CLAIM_DIR_NAME = "claim"
LOCK_DIR_NAME = "lock"
LAST_ID_FILE_NAME = "last-id"


class GitCommandError(RuntimeError):
    """git を呼んで非0で終わった。環境の故障として扱う（データの不備ではない）。"""


class NoBaseBranch(RuntimeError):
    """主ブランチが決まらなかった。データの不備（呼ぶ側が `INVALID`・終了コード3 にする）。"""


def _git(args: list[str], cwd: str | None = None) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise GitCommandError(f"git {' '.join(args)} が失敗（{r.returncode}）: {r.stderr.strip()}")
    return r.stdout.strip()


def git_common_dir(cwd: str | None = None) -> str:
    return _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)


def git_toplevel(cwd: str | None = None) -> str:
    return _git(["rev-parse", "--show-toplevel"], cwd)


def current_branch(cwd: str | None = None) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)


def is_clean(cwd: str | None = None) -> bool:
    return _git(["status", "--porcelain"], cwd) == ""


def head_sha_or_none(cwd: str | None = None) -> str | None:
    """`git rev-parse HEAD`。引けなければ `None`（`try_claim` が `head` を控えずに済ませる）。"""
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


# --- 主ブランチ（`main`・`master`・`trunk` …） -----------------------------

BASE_BRANCH_CANDIDATES = ("main", "master", "trunk")
# 設定ファイル（`AGENTS.md`／`CLAUDE.md`）「## タスク運用」の**任意**行。3行（検証コマンド・
# 整形コマンド・ブランチ）とは違い、無いのが既定で、無くても `MISSING_LINE` にしない
# （保護ブランチや複数リモートの逃げ道）。
BASE_BRANCH_LINE = re.compile(r"^- 主ブランチ:[ \t]*(.*)$", re.MULTILINE)

_base_branch_cache: dict[str, tuple[str, int]] = {}


def _configured_base_branch(toplevel: str) -> str | None:
    """設定ファイル（`layout.find_config_file`。`AGENTS.md` → `CLAUDE.md` の順）の
    `- 主ブランチ:` 行の枝名。

    値は `` `master` `` のようにバッククォートで囲むのが推奨（囲んであればその中だけを読む）。
    囲んでいなければ最初の語を採り、`master（保護ブランチ）` のように説明が続いていても
    括弧・句読点の前で切る（`- ブランチ:` と同じく、後ろは人向けの説明として許す）。
    両方のファイルに「## タスク運用」節があれば `layout.ConfigConflict`（呼ぶ側が `INVALID`・
    終了コード3にする）。
    """
    found = layout.find_config_file(toplevel)
    if found is None:
        return None
    _path, text = found
    m = BASE_BRANCH_LINE.search(text)
    if m is None:
        return None
    value = m.group(1).strip()
    quoted = re.search(r"`([^`]+)`", value)
    word = quoted.group(1).strip() if quoted else (value.split() or [""])[0]
    word = re.split(r"[（(、。]", word)[0].strip("`").strip()
    return word or None


def _resolve_base_branch(cwd: str | None) -> tuple[str, int]:
    """`(主ブランチ名, 決まった順)` を1回だけ git に問い合わせて決める（`base_branch`・
    `base_branch_order` の共有部分。呼ぶ側を増やしても判定は1箇所のまま）。

    決め方の順:

    1. 設定ファイル（`AGENTS.md` → `CLAUDE.md` の順）の `- 主ブランチ:` 行（任意）
    2. `git symbolic-ref --short refs/remotes/origin/HEAD` の枝名。**`origin` だけを見る**
       （別名のリモートしか無いリポジトリは順3へ落ちる。唯一のリモートを `origin` 扱いすると、
       fork 元を指す `upstream` を主ブランチの出どころにしてしまう。逃げ道は順1の行）
    3. `main`・`master`・`trunk` のうち `rev-parse --verify` で実在するもの（この順）
    4. どれも無ければ `NoBaseBranch`。**黙って `main` を作らない**

    1プロセスで1回だけ git に問い合わせて覚える（`task status` は1回の実行で何度も要る）。
    """
    # 呼ぶ側はふつう toplevel を渡すので、覚えていればそのまま返す（git を呼ばない）。
    if cwd is not None and cwd in _base_branch_cache:
        return _base_branch_cache[cwd]
    toplevel = git_toplevel(cwd)
    cached = _base_branch_cache.get(toplevel)
    if cached is not None:
        return cached

    found = _configured_base_branch(toplevel)
    order = 1
    if found is None:
        order = 2
        r = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=toplevel,
            capture_output=True,
            text=True,
        )
        head = r.stdout.strip()
        if r.returncode == 0 and head.startswith("origin/"):
            found = head[len("origin/") :]
    if found is None:
        order = 3
        for name in BASE_BRANCH_CANDIDATES:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                cwd=toplevel,
                capture_output=True,
                text=True,
            )
            if r.returncode == 0:
                found = name
                break
    if found is None:
        raise NoBaseBranch(
            "主ブランチが決まらない（CLAUDE.md の `- 主ブランチ:` 行も、origin/HEAD も、"
            f"{'・'.join(BASE_BRANCH_CANDIDATES)} の枝も無い）"
        )

    _base_branch_cache[toplevel] = (found, order)
    return found, order


def base_branch(cwd: str | None = None) -> str:
    """このリポジトリの主ブランチ名（`main` に固定しない）。決め方の順は `_resolve_base_branch`。"""
    return _resolve_base_branch(cwd)[0]


def base_branch_order(cwd: str | None = None) -> int:
    """主ブランチが決まった順（1〜3。`_resolve_base_branch` の docstring）。`task config-doctor` 向け。"""
    return _resolve_base_branch(cwd)[1]


def clear_base_branch_cache() -> None:
    """覚えた主ブランチ名を捨てる（同じプロセスで別のリポジトリを作り替えるテスト用）。"""
    _base_branch_cache.clear()


@dataclass(frozen=True)
class Worktree:
    path: str
    branch: str | None  # detached HEAD なら None


def list_worktrees(cwd: str | None = None) -> list[Worktree]:
    """`git worktree list --porcelain` を読む（4.3 の取り残し判定に使う）。"""
    out = _git(["worktree", "list", "--porcelain"], cwd)
    worktrees: list[Worktree] = []
    path: str | None = None
    branch: str | None = None
    for line in out.splitlines() + [""]:
        if line == "":
            if path is not None:
                worktrees.append(Worktree(path, branch))
            path, branch = None, None
            continue
        if line.startswith("worktree "):
            path = line[len("worktree ") :]
            branch = None
        elif line.startswith("branch "):
            ref = line[len("branch ") :]
            branch = ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref
    return worktrees


def ledger_root(cwd: str | None = None) -> str:
    return os.path.join(git_common_dir(cwd), "task-workflow")


def _ensure_dirs(root: str) -> None:
    os.makedirs(os.path.join(root, CLAIM_DIR_NAME), exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_owner_file(dir_path: str, lines: dict[str, str]) -> None:
    """一時ファイル→rename で書く（4.2: 読み手はまだ無い owner を「書き込み中」として扱う）。"""
    tmp = os.path.join(dir_path, ".owner.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for k, v in lines.items():
            f.write(f"{k}={v}\n")
    os.replace(tmp, os.path.join(dir_path, "owner"))


def read_owner(dir_path: str) -> dict[str, str] | None:
    owner_path = os.path.join(dir_path, "owner")
    if not os.path.exists(owner_path):
        return None
    out: dict[str, str] = {}
    with open(owner_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


def owner_age_seconds(dir_path: str) -> float | None:
    owner = read_owner(dir_path)
    if owner is None:
        return None
    key = "claimed_at" if "claimed_at" in owner else "locked_at"
    try:
        claimed_at = datetime.fromisoformat(owner[key])
    except (KeyError, ValueError):
        return None
    return (datetime.now(timezone.utc) - claimed_at).total_seconds()


# --- claim（着手の印） ---------------------------------------------------


def claim_dir(root: str, task_id: str) -> str:
    return os.path.join(root, CLAIM_DIR_NAME, task_id)


def try_claim(root: str, task_id: str, worktree: str, branch: str, head: str | None = None) -> bool:
    """`mkdir claim/T-xxx` が不可分な取り合いの錠そのもの（4.2）。

    `head` は claim した時点の `HEAD` の SHA（`task done` が委譲先のコミットを知らせるのに使う。
    `git rev-parse HEAD` が引けなかったときは `None` のままにし、owner に `head=` を書かない
    （その印は古い形と同じに読める）。
    """
    _ensure_dirs(root)
    d = claim_dir(root, task_id)
    try:
        os.mkdir(d)
    except FileExistsError:
        return False
    lines = {"worktree": worktree, "branch": branch, "claimed_at": now_iso()}
    if head is not None:
        lines["head"] = head
    _write_owner_file(d, lines)
    return True


def release_claim(root: str, task_id: str, worktree: str, force: bool = False) -> str:
    """`RELEASED` / `NOT_CLAIMED` / `NOT_OWNER` を返す（5.6）。"""
    d = claim_dir(root, task_id)
    if not os.path.isdir(d):
        return "NOT_CLAIMED"
    if not force:
        owner = read_owner(d)
        if owner is None or owner.get("worktree") != worktree:
            return "NOT_OWNER"
    shutil.rmtree(d)
    return "RELEASED"


def list_claims(root: str) -> list[str]:
    d = os.path.join(root, CLAIM_DIR_NAME)
    if not os.path.isdir(d):
        return []
    return sorted(os.listdir(d))


# --- lock（採番の錠） -----------------------------------------------------


def acquire_lock(root: str, timeout: float = 10.0, interval: float = 0.1) -> bool:
    """`mkdir lock/` を `interval` おきに `timeout` 秒まで試す（4.2）。"""
    os.makedirs(root, exist_ok=True)
    d = os.path.join(root, LOCK_DIR_NAME)
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.mkdir(d)
        except FileExistsError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)
            continue
        _write_owner_file(d, {"pid": str(os.getpid()), "locked_at": now_iso()})
        return True


def release_lock(root: str) -> None:
    shutil.rmtree(os.path.join(root, LOCK_DIR_NAME), ignore_errors=True)


def lock_owner_age_seconds(root: str) -> float | None:
    return owner_age_seconds(os.path.join(root, LOCK_DIR_NAME))


# --- last-id ---------------------------------------------------------------


def read_last_id(root: str) -> int | None:
    path = os.path.join(root, LAST_ID_FILE_NAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    return int(text) if text.isdigit() else None


def write_last_id(root: str, number: int) -> None:
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(root, ".last-id.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"{number}\n")
    os.replace(tmp, os.path.join(root, LAST_ID_FILE_NAME))
