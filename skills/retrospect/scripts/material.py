#!/usr/bin/env python3
"""1件のタスクについて、振り返りの材料をまとめて出す。

使い方: material.py <リポジトリの根> <T-XXX> [--diff] [--diff-bytes N]

出すのは4つ。

- **タスク**: `develop/tasks.json`、無ければ `docs/history/tasks.md` から本文と evidence
- **progress**: `develop/progress.md`、無ければ `docs/history/progress.md` から該当の小節
- **コミット**: 件名とファイルごとの増減（`--diff` を付けたときだけ中身も）
- **手数**: サブエージェントのトランスクリプトから取った**数だけ**

**会話の中身は1文字も出さない。** トランスクリプトから読むのはツール名・ファイルパス・
コマンドの先頭2語・件数・時刻に限る（CLAUDE.md「会話内容の扱い」）。本文を出したい誘惑が
出たら、それは振り返りに要る材料ではなく引用したいだけなので、諦める。

**データの不備で traceback を出さない。** 見つからないものは `-` と欠席の理由を出して先へ進む。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import transcript

DEFAULT_DIFF_BYTES = 40000


def main() -> None:
    root, task_id, want_diff, diff_bytes = parse_args(sys.argv[1:])
    if not re.fullmatch(r"T-\d{3}", task_id):
        print(f"INVALID\t{task_id}\tタスクIDは T- + 3桁")
        return

    section("タスク")
    print_task(root, task_id)

    section("progress の小節")
    print_progress(root, task_id)

    section("コミット")
    revs = print_commits(root, task_id, want_diff, diff_bytes)

    section("手数（トランスクリプトから取った数だけ）")
    print_signals(root, task_id)

    if not revs:
        print()
        print(f"注意\t{task_id} を件名に含むコミットが見つからない（件名の書き方が違う可能性）")


# ---- タスク本文と evidence ----------------------------------------------------


def print_task(root: str, task_id: str) -> None:
    live = os.path.join(root, "develop", "tasks.json")
    if os.path.exists(live):
        try:
            with open(live, encoding="utf-8") as f:
                tasks = json.load(f)
        except (OSError, ValueError) as e:
            print(f"INVALID\t{live}\t{e}")
            tasks = []
        for t in tasks if isinstance(tasks, list) else []:
            if isinstance(t, dict) and t.get("id") == task_id:
                print(f"出典\t{live}")
                for k in ("summary", "difficulty", "loopable", "dependencies", "passes"):
                    print(f"{k}\t{t.get(k, '?')}")
                print("evidence\t" + str(t.get("evidence", "")))
                print()
                print(t.get("task", ""))
                return

    archive = os.path.join(root, "docs", "history", "tasks.md")
    body = find_archived_task(archive, task_id)
    if body is None:
        print(f"-\t{task_id} が tasks.json にもアーカイブにも無い")
        return
    print(f"出典\t{archive}")
    print()
    print(body)


def find_archived_task(path: str, task_id: str) -> str | None:
    """`## T-XXX ...` から次の `## T-XXX ...` までを切り出す。

    本文の中にも `## 背景` のような見出しが入っているので、区切りは
    **タスクIDを持つ見出しだけ**で見る。
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    head = re.compile(r"^## (T-\d{3})\b")
    start = None
    for i, ln in enumerate(lines):
        m = head.match(ln)
        if not m:
            continue
        if m.group(1) == task_id:
            start = i
        elif start is not None:
            return "\n".join(lines[start:i]).rstrip()
    return "\n".join(lines[start:]).rstrip() if start is not None else None


# ---- progress.md --------------------------------------------------------------


def print_progress(root: str, task_id: str) -> None:
    found = False
    for path in (os.path.join(root, "develop", "progress.md"),
                 os.path.join(root, "docs", "history", "progress.md")):
        block = find_progress_section(path, task_id)
        if block:
            print(f"出典\t{path}")
            print(block)
            found = True
    if not found:
        print(f"-\t{task_id} を見出しに含む小節が progress.md に無い")


def find_progress_section(path: str, task_id: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    out: list[str] = []
    keep = False
    for ln in lines:
        if ln.startswith("### "):
            keep = task_id in ln
        elif ln.startswith("## "):
            keep = False
        if keep:
            out.append(ln)
    return "\n".join(out).strip()


# ---- コミット -----------------------------------------------------------------


def print_commits(root: str, task_id: str, want_diff: bool, diff_bytes: int) -> list[str]:
    # **件名だけ**で照合する（`--grep` は本文にも当たるので、タスクIDに言及しただけの
    # 別のコミットを拾ってしまう）。件名にIDを置く運用は task-workflow の
    # 「コミットメッセージ」が決めている。
    out, err = git_out(root, "log", "--reverse", "--no-merges",
                       "--pretty=format:%h\t%ad\t%s", "--date=short")
    if out is None:
        print(f"-\tgit log が読めない: {err}")
        return []
    revs = []
    for ln in out.splitlines():
        if not ln.strip():
            continue
        h, date, subject = ln.split("\t", 2)
        if not re.search(rf"\b{task_id}\b", subject):
            continue
        revs.append(h)
        print(f"{h}\t{date}\t{subject}")
        stat, _ = git_out(root, "show", "--numstat", "--format=", h)
        for s in (stat or "").splitlines():
            if s.strip():
                print("\t" + s)
    if not revs:
        print("-\t該当するコミットが無い")
        return revs
    if want_diff:
        print()
        print(f"--- diff（上限 {diff_bytes} バイト） ---")
        body, _ = git_out(root, "show", "--format=", "-p", *revs)
        body = body or ""
        print(body[:diff_bytes])
        if len(body) > diff_bytes:
            print(f"\n（ここで切った。残り {len(body) - diff_bytes} バイトは "
                  f"`git show <hash> -- <path>` でファイルを絞って読む）")
    return revs


# ---- トランスクリプトから取る数 ------------------------------------------------


def print_signals(root: str, task_id: str) -> None:
    paths = transcript.find_transcripts(root, task_id)
    if not paths:
        print("-\tトランスクリプトが見つからない（材料を1つ諦めて先へ進む）")
        return
    for p in paths:
        stats = transcript.read_signals(p)
        if stats is None:
            print(f"-\t読めない: {os.path.basename(p)}")
            continue
        print(f"出典\t{os.path.basename(p)}")
        print(f"経過\t{stats['elapsed']}")
        print(f"ツール呼び出し\t{stats['tool_calls']}件\tエラー\t{stats['errors']}件")
        print("内訳\t" + ", ".join(f"{k}={v}" for k, v in stats["tools"]))
        if stats["rewrites"]:
            print("同じファイルを2回以上直した\t"
                  + ", ".join(f"{k}×{v}" for k, v in stats["rewrites"]))
        if stats["commands"]:
            print("よく打ったコマンド\t"
                  + ", ".join(f"{k}×{v}" for k, v in stats["commands"]))
        print(f"出力トークン\t{stats['output_tokens']}")


# ---- 共通 ---------------------------------------------------------------------


def section(title: str) -> None:
    print()
    print(f"===== {title} =====")


def parse_args(argv: list[str]) -> tuple[str, str, bool, int]:
    positional: list[str] = []
    want_diff = False
    diff_bytes = DEFAULT_DIFF_BYTES
    i = 0
    while i < len(argv):
        if argv[i] == "--diff":
            want_diff = True
        elif argv[i] == "--diff-bytes" and i + 1 < len(argv):
            diff_bytes = int(argv[i + 1])
            i += 1
        else:
            positional.append(argv[i])
        i += 1
    if len(positional) != 2:
        print("usage: material.py <リポジトリの根> <T-XXX> [--diff] [--diff-bytes N]",
              file=sys.stderr)
        raise SystemExit(2)
    return positional[0], positional[1], want_diff, diff_bytes


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
