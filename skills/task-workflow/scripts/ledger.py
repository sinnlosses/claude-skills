"""共有の `.git` の中に置く台帳（着手の印・採番の錠・最後の番号・登録時の計画の控え）。

正典は `docs/task-workflow-redesign.md` の4.2〜4.3。台帳はクローンに1つ
（`git rev-parse --path-format=absolute --git-common-dir` の下）で、コミットしないので
主ブランチを動かさない。取り合いの判定は `mkdir` の成否だけで決める（不可分な操作なので、
2プロセスが同時に呼んでも一方だけが成功する）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


def git_dir(cwd: str | None = None) -> str:
    """この作業ツリー**だけ**の git dir（共有の `git_common_dir` とは違う。連結した
    作業ツリーでは `<共通の git dir>/worktrees/<名前>`）。`verify_owed` の置き場に使う。"""
    return _git(["rev-parse", "--path-format=absolute", "--git-dir"], cwd)


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


PLAN_FILE_NAME = "plan"


def write_plan_mark(root: str, task_id: str, state: str) -> None:
    """印のディレクトリに `## やること` を初めて書いた時点の判定を残す。2回目以降は書き換えない。"""
    try:
        fd = os.open(os.path.join(claim_dir(root, task_id), PLAN_FILE_NAME), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"{state}\n")


def read_plan_mark(root: str, task_id: str) -> str | None:
    return _read_line(os.path.join(claim_dir(root, task_id), PLAN_FILE_NAME))


PLAN_TIP_FILE_NAME = "plan-tip"


def write_plan_tip(root: str, task_id: str, sha: str) -> None:
    """登録時の計画を判定した、着手時の主ブランチの先端を印のディレクトリに残す。"""
    with open(os.path.join(claim_dir(root, task_id), PLAN_TIP_FILE_NAME), "w", encoding="utf-8") as f:
        f.write(f"{sha}\n")


def read_plan_tip(root: str, task_id: str) -> str | None:
    return _read_line(os.path.join(claim_dir(root, task_id), PLAN_TIP_FILE_NAME))


# --- plan-base（登録時に `## やること` を書いたときの主ブランチの SHA） -----

PLAN_BASE_DIR_NAME = "plan-base"


def write_plan_base(root: str, task_id: str, sha: str) -> None:
    d = os.path.join(root, PLAN_BASE_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, task_id), "w", encoding="utf-8") as f:
        f.write(f"{sha}\n")


def read_plan_base(root: str, task_id: str) -> str | None:
    return _read_line(os.path.join(root, PLAN_BASE_DIR_NAME, task_id))


def clear_plan_base(root: str, task_id: str) -> None:
    try:
        os.remove(os.path.join(root, PLAN_BASE_DIR_NAME, task_id))
    except FileNotFoundError:
        pass


def _read_line(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().strip() or None


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


# --- verify-owed（`VERIFY_FAILED` のあと打ち直すまでの検証の借り）----------

VERIFY_OWED_FILE_NAME = "task-ship-verify-owed"


def _verify_owed_path(cwd: str | None = None) -> str:
    """**作業ツリー固有**の git dir に置く（`claim`／`lock` の共有台帳とは別）。
    検証を跨いだ枝を抱えているのはこの作業ツリーだけなので、共有すると
    無関係な作業ツリーの `ship` まで検証を強制してしまう。"""
    return os.path.join(git_dir(cwd), VERIFY_OWED_FILE_NAME)


def mark_verify_owed(verify_command: str, cwd: str | None = None) -> None:
    path = _verify_owed_path(cwd)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(verify_command + "\n")
    os.replace(tmp, path)


def is_verify_owed(cwd: str | None = None) -> bool:
    return os.path.exists(_verify_owed_path(cwd))


def clear_verify_owed(cwd: str | None = None) -> None:
    path = _verify_owed_path(cwd)
    if os.path.exists(path):
        os.remove(path)


# --- verify-stamp（検証コマンドが通った作業ツリーの中身の控え）------------

VERIFY_STAMP_FILE_NAME = "task-verify-stamp"
VERIFY_LOG_FILE_NAME = "task-verify.log"
SHIP_VERIFY_LOG_FILE_NAME = "task-ship-verify.log"
PAUSE_STAMP_FILE_NAME = "task-pause-stamp"
STEP_STAMP_FILE_NAME = "task-step-stamp"


@dataclass(frozen=True)
class ContentKey:
    head: str
    tree: str
    verify_command: str


def content_key(verify_command: str, cwd: str | None = None) -> ContentKey:
    """いまの作業ツリーの中身の鍵。"""
    toplevel = git_toplevel(cwd)
    head = head_sha_or_none(toplevel) or "-"
    return ContentKey(head, worktree_tree(toplevel), verify_command)


def worktree_tree(toplevel: str) -> str:
    """いまの作業ツリーの中身の木の SHA。

    index を一時ファイルに写して `git add -A` → `git write-tree` するので、`.gitignore` の対象でない
    未追跡のファイルまで入り、本物の index は変わらない。
    """
    real_index = _git(["rev-parse", "--path-format=absolute", "--git-path", "index"], toplevel)
    with tempfile.TemporaryDirectory() as tmp:
        temp_index = os.path.join(tmp, "index")
        if os.path.exists(real_index):
            # mtime を保たないと、同じ秒・同じ大きさの書き換えを git が無変更とみなす
            shutil.copy2(real_index, temp_index)
        env = {**os.environ, "GIT_INDEX_FILE": temp_index}
        for args in (["add", "-A"], ["write-tree"]):
            r = subprocess.run(["git", *args], cwd=toplevel, env=env, capture_output=True, text=True)
            if r.returncode != 0:
                raise GitCommandError(f"git {' '.join(args)} が失敗（{r.returncode}）: {r.stderr.strip()}")
        return r.stdout.strip()


def verify_log_path(cwd: str | None = None) -> str:
    return os.path.join(git_dir(cwd), VERIFY_LOG_FILE_NAME)


def ship_verify_log_path(cwd: str | None = None) -> str:
    return os.path.join(git_dir(cwd), SHIP_VERIFY_LOG_FILE_NAME)


def write_verify_stamp(key: ContentKey, cwd: str | None = None) -> None:
    _write_key(os.path.join(git_dir(cwd), VERIFY_STAMP_FILE_NAME), key)


def read_verify_stamp(cwd: str | None = None) -> ContentKey | None:
    return _read_key(os.path.join(git_dir(cwd), VERIFY_STAMP_FILE_NAME))


def clear_verify_stamp(cwd: str | None = None) -> None:
    path = os.path.join(git_dir(cwd), VERIFY_STAMP_FILE_NAME)
    if os.path.exists(path):
        os.remove(path)


def write_pause_stamp(key: ContentKey, cwd: str | None = None) -> None:
    """`tw pause` を打った時点の中身の鍵。"""
    _write_key(os.path.join(git_dir(cwd), PAUSE_STAMP_FILE_NAME), key)


def read_pause_stamp(cwd: str | None = None) -> ContentKey | None:
    return _read_key(os.path.join(git_dir(cwd), PAUSE_STAMP_FILE_NAME))


@dataclass(frozen=True)
class StepStamp:
    key: ContentKey
    task_id: str
    step: int


def write_step_stamp(stamp: StepStamp, cwd: str | None = None) -> None:
    """`tw step` を打った時点の中身の鍵と、済ませた段。"""
    _write_key(os.path.join(git_dir(cwd), STEP_STAMP_FILE_NAME), stamp.key, (stamp.task_id, str(stamp.step)))


def read_step_stamp(cwd: str | None = None) -> StepStamp | None:
    path = os.path.join(git_dir(cwd), STEP_STAMP_FILE_NAME)
    key = _read_key(path)
    if key is None:
        return None
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if len(lines) < 5 or not lines[4].isdigit():
        return None
    return StepStamp(key, lines[3], int(lines[4]))


def _write_key(path: str, key: ContentKey, extra: tuple[str, ...] = ()) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(f"{line}\n" for line in (key.head, key.tree, key.verify_command, *extra)))
    os.replace(tmp, path)


def _read_key(path: str) -> ContentKey | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if len(lines) < 3:
        return None
    return ContentKey(lines[0], lines[1], lines[2])


# --- flow（着手・検証・送り出し・完了の出来事。月ごとの JSONL）-------------

FLOW_DIR_NAME = "flow"


def flow_dir(root: str) -> str:
    return os.path.join(root, FLOW_DIR_NAME)


def record_event(
    cwd: str | None, event: str, task_id: str, difficulty: str, **fields: str | int | bool
) -> None:
    """1出来事を `flow/<YYYY-MM>.jsonl` に1行足す。会話・コマンド・パスは入れない。

    失敗しても例外を外へ出さない（呼ぶサブコマンドの出力と終了コードを変えない）。標準エラーに1行だけ出す。
    """
    try:
        at = now_iso()
        row = {"t": at, "event": event, "task": task_id, "difficulty": difficulty, **fields}
        d = flow_dir(ledger_root(cwd))
        os.makedirs(d, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(os.path.join(d, f"{at[:7]}.jsonl"), "a", encoding="utf-8") as f:
            f.write(line)
    except (OSError, GitCommandError) as e:
        print(f"flow: 記録を書けなかった（{type(e).__name__}）", file=sys.stderr)


# --- open-claim（`claim` から `done` までの作業ツリー固有の控え）------------

OPEN_CLAIMS_DIR_NAME = "task-open-claims"


def _open_claims_dir(cwd: str | None = None) -> str:
    """**作業ツリー固有**の git dir に置く（共有の台帳に置くと、別の作業ツリーのコミットまで拒む）。"""
    return os.path.join(git_dir(cwd), OPEN_CLAIMS_DIR_NAME)


def mark_open_claim(task_id: str, cwd: str | None = None) -> None:
    d = _open_claims_dir(cwd)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, task_id), "w", encoding="utf-8"):
        pass


def clear_open_claim(task_id: str, cwd: str | None = None) -> None:
    path = os.path.join(_open_claims_dir(cwd), task_id)
    if os.path.exists(path):
        os.remove(path)


def open_claims(cwd: str | None = None) -> list[str]:
    d = _open_claims_dir(cwd)
    if not os.path.isdir(d):
        return []
    return sorted(os.listdir(d))
