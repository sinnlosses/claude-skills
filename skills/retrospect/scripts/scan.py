#!/usr/bin/env python3
"""前回の振り返り以降に進んだコミットを一覧し、タスクIDに割り付ける。

使い方: scan.py <リポジトリの根> [--since <hash>]

diff も本文も出さない。**どこまで振り返ったか**と**何が未振り返りか**だけを出す道具で、
1件ずつの材料は material.py が出す。

`/next-task` の中で1件ごとに振り返ったタスクは、`## 結果` に `- 振り返り:` の行を持つ
（retrospect の SKILL.md「1件だけ振り返る」）。範囲内のそのタスクのコミットの版にこの行が
あれば `reviewed` に回し、`tasks`（まとめての振り返りの対象）から外す。Beads 方式
（task-workflow の WORKFLOW.md「Beads 方式」）では `## 結果` は閉じるときの comment にあるので、
コミットの版ではなく Beads の comment を読む。
ただし件名が `Revert "` で始まるコミットを持つタスクは、振り返りのあとに人に戻されたので
`reverted` に出し、`tasks` に戻す。

**データの不備で traceback を出さない。** 呼び出し側のスキルは「`MISSING`・`EMPTY`・
`INVALID`・TSV のいずれでもない出力」を「`python3` が使えない」の合図として扱うので、
ここが落ちると *データの不備が環境の故障として報告される*。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

_TASK_WORKFLOW_SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "task-workflow", "scripts")
)
if _TASK_WORKFLOW_SCRIPTS not in sys.path:
    sys.path.insert(0, _TASK_WORKFLOW_SCRIPTS)

import beads  # noqa: E402
import layout  # noqa: E402
import transcript  # noqa: E402

# develop/retrospective.md の先頭付近にあるこの形の行だけが、機械の読む値。
HASH_LINE = re.compile(r"^最後に振り返ったコミット:\s*`([0-9a-f]{7,40})`")
TASK_ID = layout.ID_SEARCH_PATTERN
# 1件ごとの振り返りが済んだ印。`## 結果` の中のこの形の行（task-workflow の WORKFLOW.md
# 「結果の書き方と知見の置き場」）。
REVIEWED_LINE = re.compile(r"^- 振り返り:")
# 人の差し戻しの機械の跡。git revert の既定の件名（`Revert "T-XXX: ..."`）だけを見る。
REVERT_SUBJECT = re.compile(r'^Revert "')


def main() -> None:
    root, since = parse_args(sys.argv[1:])
    record = os.path.join(root, layout.RETROSPECTIVE_PATH)

    if since is None:
        if not os.path.exists(record):
            print("MISSING")
            return
        since, err = read_since(record)
        if err:
            print(f"INVALID\t{record}\t{err}")
            return

    ok, err = git(root, "cat-file", "-e", f"{since}^{{commit}}")
    if not ok:
        print(f"INVALID\t{record}\t記録にあるコミット {since} がこのリポジトリに無い: {err}")
        return

    head, err = git_out(root, "rev-parse", "--short", "HEAD")
    if head is None:
        print(f"INVALID\t{root}\tHEAD が読めない: {err}")
        return

    lines, err = git_out(root, "log", "--reverse", "--no-merges", f"{since}..HEAD",
                         "--pretty=format:%h\t%ad\t%s", "--date=short")
    if lines is None:
        print(f"INVALID\t{root}\tgit log が読めない: {err}")
        return
    commits = [ln for ln in lines.splitlines() if ln.strip()]
    if not commits:
        print(f"EMPTY\t{since}..{head}")
        return

    print(f"range\t{since}..{head}")
    tasks: list[str] = []
    reviewed: list[str] = []
    reverted: list[str] = []
    unmapped = 0
    for ln in commits:
        h, date, subject = ln.split("\t", 2)
        ids = TASK_ID.findall(subject)
        for i in ids:
            if i not in tasks:
                tasks.append(i)
            if i not in reviewed and has_review_line(root, h, i):
                reviewed.append(i)
            if i not in reverted and REVERT_SUBJECT.match(subject):
                reverted.append(i)
        if not ids:
            unmapped += 1
        files, ins, dele = diffstat(root, h)
        print(f"{h}\t{date}\t{','.join(ids) or '-'}\t{files}files\t+{ins}/-{dele}\t{subject}")

    print("---")
    print(f"commits\t{len(commits)}")
    # 戻されたタスクは、1件ごとの振り返りのあとに起きたことなので振り返り済みでも対象に戻す。
    todo = [t for t in tasks if t not in reviewed or t in reverted]
    done = [t for t in reviewed if t not in reverted]
    print(f"tasks\t{','.join(todo) or '-'}")
    print(f"reviewed\t{','.join(done) or '-'}\t(1件ごとに振り返り済み。材料を集め直さない)")
    print(f"reverted\t{','.join(reverted) or '-'}\t(Revert の件名で戻された。人の差し戻しの跡)")
    print(f"unmapped\t{unmapped}\t(タスクIDの無いコミット。振り返りの対象から外してよい)")
    print(f"transcripts\t{len(transcript.subagent_dirs(root))}\t(見つかったトランスクリプトの置き場)")


def parse_args(argv: list[str]) -> tuple[str, str | None]:
    root = None
    since = None
    i = 0
    while i < len(argv):
        if argv[i] == "--since" and i + 1 < len(argv):
            since = argv[i + 1]
            i += 2
            continue
        if root is None:
            root = argv[i]
        i += 1
    if root is None:
        print("usage: scan.py <リポジトリの根> [--since <hash>]", file=sys.stderr)
        raise SystemExit(2)
    return root, since


def read_since(path: str) -> tuple[str, str]:
    """記録ファイルから最後に振り返ったコミットを読む。形が違えば理由を返す。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = HASH_LINE.match(line.strip())
                if m:
                    return m.group(1), ""
    except OSError as e:
        return "", f"読めない: {e}"
    return "", "「最後に振り返ったコミット: `<hash>`」の行が無い"


def has_review_line(root: str, rev: str, task_id: str) -> bool:
    """`rev` の版のタスクファイルの `## 結果` に `- 振り返り:` の行があるか。

    いまの `HEAD` ではなくそのコミットの版を読むので、あとでファイルを消したタスクでも判定できる。
    Beads 方式ならタスクの `## 結果` の comment を読む（版は無い）。
    """
    if is_beads(root):
        if task_id not in _beads_reviewed:
            try:
                result = beads.last_result(beads.comments(root, beads.to_bd_id(task_id)))
            except beads.BeadsError:
                result = None
            _beads_reviewed[task_id] = any(REVIEWED_LINE.match(l) for l in (result or "").splitlines())
        return _beads_reviewed[task_id]
    text, _ = git_out(root, "show", f"{rev}:{layout.TASK_DIR}/{task_id}.md")
    in_result = False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            in_result = line.strip() == "## 結果"
        elif in_result and REVIEWED_LINE.match(line):
            return True
    return False


_beads_reviewed: dict[str, bool] = {}


def is_beads(root: str) -> bool:
    try:
        return layout.read_store(root) == layout.STORE_BEADS
    except (layout.ConfigConflict, layout.StoreSettingError):
        return False


def diffstat(root: str, rev: str) -> tuple[int, int, int]:
    out, _ = git_out(root, "show", "--numstat", "--format=", rev)
    files = ins = dele = 0
    for ln in (out or "").splitlines():
        parts = ln.split("\t")
        if len(parts) != 3:
            continue
        files += 1
        if parts[0].isdigit():
            ins += int(parts[0])
        if parts[1].isdigit():
            dele += int(parts[1])
    return files, ins, dele


def git(root: str, *args: str) -> tuple[bool, str]:
    try:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    except OSError as e:
        return False, str(e)
    return p.returncode == 0, p.stderr.strip()


def git_out(root: str, *args: str) -> tuple[str | None, str]:
    try:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    except OSError as e:
        return None, str(e)
    if p.returncode != 0:
        return None, p.stderr.strip()
    return p.stdout, ""


if __name__ == "__main__":
    main()
