#!/usr/bin/env python3
"""前回の振り返り以降に進んだコミットを一覧し、タスクIDに割り付ける。

使い方: scan.py <リポジトリの根> [--since <hash>]

diff も本文も出さない。**どこまで振り返ったか**と**何が未振り返りか**だけを出す道具で、
1件ずつの材料は material.py が出す。

**データの不備で traceback を出さない。** 呼び出し側のスキルは「`MISSING`・`EMPTY`・
`INVALID`・TSV のいずれでもない出力」を「`python3` が使えない」の合図として扱うので、
ここが落ちると *データの不備が環境の故障として報告される*。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import transcript

# develop/retrospective.md の先頭付近にあるこの形の行だけが、機械の読む値。
HASH_LINE = re.compile(r"^最後に振り返ったコミット:\s*`([0-9a-f]{7,40})`")
TASK_ID = re.compile(r"\bT-\d{3}\b")


def main() -> None:
    root, since = parse_args(sys.argv[1:])
    record = os.path.join(root, "develop", "retrospective.md")

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
    unmapped = 0
    for ln in commits:
        h, date, subject = ln.split("\t", 2)
        ids = TASK_ID.findall(subject)
        for i in ids:
            if i not in tasks:
                tasks.append(i)
        if not ids:
            unmapped += 1
        files, ins, dele = diffstat(root, h)
        print(f"{h}\t{date}\t{','.join(ids) or '-'}\t{files}files\t+{ins}/-{dele}\t{subject}")

    print("---")
    print(f"commits\t{len(commits)}")
    print(f"tasks\t{','.join(tasks) or '-'}")
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
