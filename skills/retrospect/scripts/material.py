#!/usr/bin/env python3
"""1件のタスクについて、振り返りの材料をまとめて出す。

使い方: material.py <リポジトリの根> <T-XXX> [--diff] [--diff-bytes N] [--signals]

出すのは4つ（`--signals` のときは「手数」だけ。`/next-task` の中の1件ごとの振り返りが、
兆候に当たったかを数だけで見るのに使う。本文と diff はメインが受け入れで読み終えている）。

- **タスク**: `develop/task/T-XXX.md`（`HEAD` の版。front matter と本文、`## 結果`）。
  無ければ旧形式の `develop/tasks.json`、それも無ければ `docs/history/tasks.md` から本文と evidence。
  Beads 方式（task-workflow の WORKFLOW.md「Beads 方式」）では Beads の課題（`task show` と同じ形）
- **登録から完了までの差分**: `develop/task/T-XXX.md` を足したコミットの版と `HEAD` の版の差
  （着手時に書き足した `## やること`・`## 注意` の量が出る）。旧タスクは代わりに
  `develop/progress.md`・`docs/history/progress.md` の該当の小節。Beads 方式では `bd history` の
  最初の版と最後の版の差
- **コミット**: 件名とファイルごとの増減（`--diff` を付けたときだけ中身も）
- **手数**: サブエージェントのトランスクリプトから取った**数だけ**

**会話の中身は1文字も出さない。** トランスクリプトから読むのはツール名・ファイルパス・
コマンドの先頭2語・件数・時刻に限る（CLAUDE.md「会話内容の扱い」）。本文を出したい誘惑が
出たら、それは振り返りに要る材料ではなく引用したいだけなので、諦める。

**データの不備で traceback を出さない。** 見つからないものは `-` と欠席の理由を出して先へ進む。
"""

from __future__ import annotations

import difflib
import json
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

DEFAULT_DIFF_BYTES = 40000


def main() -> None:
    root, task_id, want_diff, diff_bytes, signals_only = parse_args(sys.argv[1:])
    if not layout.ANY_ID_PATTERN.fullmatch(task_id):
        print(f"INVALID\t{task_id}\tタスクIDは T- + 3桁以上か GH- + 番号")
        return

    if signals_only:
        section("手数（トランスクリプトから取った数だけ）")
        print_signals(root, task_id)
        return

    if is_beads(root):
        section("タスク")
        print_beads_task(root, task_id)
        section("登録から完了までの差分（Beads の版）")
        print_beads_history(root, task_id)
        is_file_task = None
    else:
        section("タスク")
        is_file_task = print_task(root, task_id)

    if is_file_task is None:
        pass
    elif is_file_task:
        section("登録から完了までの差分（タスクファイル）")
        print_task_file_diff(root, task_id)
    else:
        section("progress の小節（旧形式のタスク）")
        print_progress(root, task_id)

    section("コミット")
    revs = print_commits(root, task_id, want_diff, diff_bytes)

    section("手数（トランスクリプトから取った数だけ）")
    print_signals(root, task_id)

    if not revs:
        print()
        print(f"注意\t{task_id} を件名に含むコミットが見つからない（件名の書き方が違う可能性）")


# ---- タスク本文と evidence ----------------------------------------------------


def print_task(root: str, task_id: str) -> bool:
    """タスクの本文を出す。新しい形（`develop/task/`）で見つかれば True。

    振り返り後にファイルを消したタスクは `HEAD` に無いので、最後に存在した版
    （`last_existing_ref`）を代わりに読む。
    """
    rel = f"{layout.TASK_DIR}/{task_id}.md"
    text, _ = git_out(root, "show", f"HEAD:{rel}")
    if text is not None:
        print(f"出典\t{rel}（HEAD）")
        print()
        print(text.rstrip())
        return True

    ref = last_existing_ref(root, rel)
    if ref is not None:
        text, _ = git_out(root, "show", f"{ref}:{rel}")
        if text is not None:
            print(f"出典\t{rel}（{ref}、削除前の最後の版）")
            print()
            print(text.rstrip())
            return True

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
                return False

    archive = os.path.join(root, layout.HISTORY_TASKS_PATH)
    body = find_archived_task(archive, task_id)
    if body is None:
        print(f"-\t{task_id} が {layout.TASK_DIR}/ にも tasks.json にもアーカイブにも無い")
        return False
    print(f"出典\t{archive}")
    print()
    print(body)
    return False


def print_task_file_diff(root: str, task_id: str) -> None:
    """登録した版（ファイルを足したコミット）と最後の版の差を出す。

    登録の粗さと、着手までにどれだけ前提が動いたかがここに出る（`## やること` は着手直後に
    書く節なので、登録時の版には無い）。`HEAD` に無いタスクは、最後に存在した版
    （`last_existing_ref`）までの差にする。
    """
    rel = f"{layout.TASK_DIR}/{task_id}.md"
    added, err = git_out(root, "log", "--diff-filter=A", "--format=%h", "--", rel)
    first = (added or "").split()
    if not first:
        print(f"-\t{rel} を足したコミットが見つからない（{err or '履歴に無い'}）")
        return
    base = first[-1]
    print(f"登録\t{base}")
    registered, _ = git_out(root, "show", f"{base}:{rel}")
    end_ref = "HEAD"
    current, _ = git_out(root, "show", f"HEAD:{rel}")
    if current is None:
        ref = last_existing_ref(root, rel)
        if ref is not None:
            end_ref = ref
            current, _ = git_out(root, "show", f"{end_ref}:{rel}")
    if end_ref != "HEAD":
        print(f"最後の版\t{end_ref}（HEAD に無いので、消える直前の版までの差）")
    for label, text in (("登録時の節", registered), ("いまの節", current)):
        heads = [ln for ln in (text or "").splitlines() if ln.startswith("## ")]
        print(f"{label}\t" + (", ".join(f"{h[3:]}" for h in heads) or "-"))
    diff, _ = git_out(root, "diff", f"{base}", end_ref, "--", rel)
    print()
    print((diff or "（差分なし）").rstrip())


def last_existing_ref(root: str, rel: str) -> str | None:
    """`rel` が `HEAD` に無いとき、最後に存在した版を指す ref を返す。

    「そのパスを最後に消したコミット」の親が、消える直前＝最後に存在した版。パスが一度も
    消えていなければ（そもそも作られていない等）`None`。
    """
    deleted, _ = git_out(root, "log", "-1", "--diff-filter=D", "--format=%H", "--", rel)
    deleted_hash = (deleted or "").strip()
    if not deleted_hash:
        return None
    return f"{deleted_hash}^"


def find_archived_task(path: str, task_id: str) -> str | None:
    """`## T-XXX ...` から次の `## T-XXX ...` までを切り出す。

    本文の中にも `## 目的・背景` のような見出しが入っているので、区切りは
    **タスクIDを持つ見出しだけ**で見る。
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    start = None
    for i, ln in enumerate(lines):
        m = layout.HISTORY_HEADING_PATTERN.match(ln)
        if not m:
            continue
        if m.group(1) == task_id:
            start = i
        elif start is not None:
            return "\n".join(lines[start:i]).rstrip()
    return "\n".join(lines[start:]).rstrip() if start is not None else None


# ---- Beads 方式 ---------------------------------------------------------------


def is_beads(root: str) -> bool:
    try:
        return layout.read_store(root) == layout.STORE_BEADS
    except (layout.ConfigConflict, layout.StoreSettingError):
        return False


def print_beads_task(root: str, task_id: str) -> None:
    bd_id = beads.to_bd_id(task_id)
    try:
        issue = beads.show(root, bd_id)
        result = beads.last_result(beads.comments(root, bd_id)) if issue is not None else None
    except beads.BeadsError as e:
        print(f"-\t{e}")
        return
    if issue is None:
        print(f"-\t{task_id} が Beads に無い")
        return
    task, err = beads.to_task(issue)
    if task is None:
        print(f"-\t{task_id} を読めない（{err or '振り分け前'}）")
        return
    print(f"出典\tBeads {bd_id}")
    print()
    print(beads.render_task(task, issue, result).rstrip())


def print_beads_history(root: str, task_id: str) -> None:
    """登録した版（`bd history` の最初）と最後の版の本文の差。"""
    try:
        snaps = beads.history(root, beads.to_bd_id(task_id))
    except beads.BeadsError as e:
        print(f"-\t{e}")
        return
    if not snaps:
        print(f"-\t{task_id} の版が無い")
        return

    def text_of(snap: dict) -> str:
        return beads.compose_body(
            str(snap.get("description") or ""),
            str(snap.get("acceptance_criteria") or ""),
            str(snap.get("notes") or ""),
            None,
        )

    first, last = text_of(snaps[0]), text_of(snaps[-1])
    print(f"版\t{len(snaps)}")
    for label, text in (("登録時の節", first), ("いまの節", last)):
        heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
        print(f"{label}\t" + (", ".join(h[3:] for h in heads) or "-"))
    diff = difflib.unified_diff(first.splitlines(), last.splitlines(), "登録時", "いま", lineterm="")
    print()
    print("\n".join(diff) or "（差分なし）")


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
        stats = transcript.read_signals(p, root)
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


def parse_args(argv: list[str]) -> tuple[str, str, bool, int, bool]:
    positional: list[str] = []
    want_diff = False
    signals_only = False
    diff_bytes = DEFAULT_DIFF_BYTES
    i = 0
    while i < len(argv):
        if argv[i] == "--diff":
            want_diff = True
        elif argv[i] == "--signals":
            signals_only = True
        elif argv[i] == "--diff-bytes" and i + 1 < len(argv):
            diff_bytes = int(argv[i + 1])
            i += 1
        else:
            positional.append(argv[i])
        i += 1
    if len(positional) != 2:
        print("usage: material.py <リポジトリの根> <T-XXX> [--diff] [--diff-bytes N] [--signals]",
              file=sys.stderr)
        raise SystemExit(2)
    return positional[0], positional[1], want_diff, diff_bytes, signals_only


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
