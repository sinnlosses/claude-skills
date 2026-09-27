#!/usr/bin/env python3
"""タスク運用に要るファイルをプロジェクトに用意する（既にあるものは触らない）。

使い方: init.py [develop-dir]   （既定: develop）

作るのは `develop/direction.md` の骨組み（見出しと `## ユーザーから` の節）だけ（正典は
task-workflow の WORKFLOW.md「ファイル配置と設定ファイル（AGENTS.md → CLAUDE.md の順）」）。
`develop/task/` は最初の `task new` が、`develop/draft/` は最初のドラフトが作り、`direction.md` が
新形式の目印になる（空のディレクトリは git に載らないため）。骨組みは決まりきっているのでモデルに書かせない
（`direction.md` に見出し以外の行が混ざると `/plan-tasks` が「未対応の指示がある」と誤判定する）。

**旧形式（`develop/tasks.json` がある）なら何も作らず `LEGACY` で止まる**（終了コード5。
`task.py` と同じ）。移すのは `task migrate` で、ここでは骨組みを混ぜない。

**既存ファイルは上書きしない。** 中身の点検結果だけを出し、直すかどうかは呼び出し側が決める。
設定ファイル（`AGENTS.md`／`CLAUDE.md`）は**点検するだけで書かない**（節に入る値は検証コマンドの
選定そのもので、判断が要る。書くのは `/setup-tasks` の手順2）。
"""

from __future__ import annotations

import os
import re
import sys

import beads
import layout

# direction.md の節（正典「指示メモ」）。前方一致で探す。値は layout.py の正典を読む。
SECTION_USER = layout.SECTION_USER
LEGACY_SECTION_DRAFT = layout.LEGACY_SECTION_DRAFT
# 見出しの行は数えないので、ドラフトの置き場は見出しの括弧に書く。
DIRECTION = f"# 未対応の指示メモ（エージェントのドラフトは {layout.DRAFT_DIR}/ に1件1ファイル）\n\n{SECTION_USER}\n"

# 設定ファイル側の正典（正典「ファイル配置と設定ファイル」）。スキルと task.py はこの節を読む。
# ファイルの探索そのものは layout.find_config_file（`AGENTS.md` → `CLAUDE.md` の順）に寄せる。
CLAUDE_MD = "CLAUDE.md"
CLAUDE_SECTION = layout.TASK_SECTION_HEADING
CLAUDE_KEYS = ("- 検証コマンド:", "- 整形コマンド:", "- ブランチ:")
# `- ブランチ:` の値の先頭語（正典「ファイル配置と設定ファイル」の語彙。task.py の read_branch_setting と同じ）。
BRANCH_WORDS = ("既定", "作業ブランチを切る", "切らない")


def main() -> None:
    args = sys.argv[1:]
    # ディレクトリ名として受け取る引数なので、`--help` のような打ち間違いをそのまま
    # ディレクトリにして掘らない（実際に `--help/` を作ってしまった）。
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("usage: init.py [develop-dir]   （既定: develop）", file=sys.stderr)
        raise SystemExit(2)
    root = args[0] if args else "develop"

    if os.path.exists(os.path.join(root, "tasks.json")):
        print(f"LEGACY\t{os.path.join(root, 'tasks.json')}\ttask migrate --dry-run")
        raise SystemExit(5)

    os.makedirs(root, exist_ok=True)
    create(os.path.join(root, os.path.basename(layout.DIRECTION_PATH)), DIRECTION, check_direction)
    print(check_claude_md())
    code = prepare_beads(".")
    if code:
        raise SystemExit(code)


def prepare_beads(root: str) -> int:
    """設定が Beads 方式（`- タスクの置き場: beads`）なら `.beads` を用意する。終了コードを返す。

    `bd init --stealth` は `.git/info/exclude` で `.beads` を外し、コミットも `AGENTS.md`・
    `CLAUDE.md` への書き足しもしない（`--stealth` なしでは両方をして自動でコミットする）。
    `.beads` は主ブランチを出している作業ツリーの根に置くので、別の作業ツリーからは作らない。
    ファイル方式（行が無い）なら何もしない。
    """
    try:
        value = layout.read_setting_value(root, layout.STORE_KEY)
    except layout.ConfigConflict:
        return 0
    if value is None or layout.setting_word(value) != layout.STORE_BEADS:
        return 0
    target = beads.beads_dir(root)
    if os.path.isdir(target):
        print(f"KEPT\t{target}")
    else:
        toplevel = os.path.realpath(os.path.abspath(root))
        if os.path.realpath(os.path.dirname(target)) != toplevel:
            print(f"NOT_MAIN_WORKTREE\t{os.path.dirname(target)}\t（.beads はそこで作る）")
            return 4
        # トラッカーが github なら ID は Issue 番号（`gh-<n>`）、それ以外は `task` の採番（`t-<n>`）。
        tracker_value = layout.read_setting_value(root, layout.TRACKER_KEY)
        github = tracker_value is not None and layout.setting_word(tracker_value) == "github"
        prefix = beads.PREFIX_GITHUB if github else beads.PREFIX_LOCAL
        r = beads.run(root, ["init", "--stealth", "-p", prefix, "--non-interactive", "--skip-hooks", "--quiet"])
        if r.returncode != 0:
            print(f"FAILED\tbd init\t{(r.stderr or r.stdout).strip()}")
            return 1
        print(f"CREATED\t{target}\t(bd init --stealth -p {prefix})")
    return 0


def create(path: str, body: str, check) -> None:
    """無ければ骨組みで作り、在れば中身を点検して報告する。"""
    if os.path.exists(path):
        print(f"KEPT\t{path}\t{check(path)}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"CREATED\t{path}")


def check_claude_md(root: str = ".") -> str:
    """「## タスク運用」節と3行が在るか、`- ブランチ:` の先頭語が語彙に当たるかを見る。書き換えはしない。

    設定ファイルは `layout.find_config_file`（`AGENTS.md` → `CLAUDE.md` の順）で決める。
    両方に節があれば `INVALID`（`SystemExit` はしない。他の返り値と同じ「印字するだけ」の形）。
    どちらにも節が無ければ、実在する最初のファイル（無ければ `CLAUDE.md`）を指して報告する
    （従来どおり `MISSING`／`NO_SECTION` を区別する）。

    `root` は既定でカレントディレクトリ（`init.py` 自身の呼び方）。`task config-doctor`
    （T-021）はリポジトリの根の絶対パスを渡す（toplevel を渡す呼び方に対応するための引数で、
    判定そのものは変えない）。
    """
    try:
        found = layout.find_config_file(root)
    except layout.ConfigConflict as e:
        return f"INVALID\t{'/'.join(layout.CONFIG_FILENAMES)}\t{e}"
    if found is not None:
        path, text = found
        lines = text.splitlines()
        missing = [k for k in CLAUDE_KEYS if not any(l.startswith(k) for l in lines)]
        if missing:
            return f"MISSING_LINE\t{path}\t" + ", ".join(missing)
        branch_line = next(l for l in lines if l.startswith("- ブランチ:"))
        m = re.match(r"- ブランチ:\s*(\S+)", branch_line)
        word = m.group(1).rstrip("。、") if m else ""
        if not any(word.startswith(w) for w in BRANCH_WORDS):
            return f"BAD_BRANCH\t{path}\t（- ブランチ: の先頭語 {word!r} が {' / '.join(BRANCH_WORDS)} のどれでもない）"
        return f"OK\t{path}\t（{CLAUDE_SECTION} 節あり）"

    existing = next((n for n in layout.CONFIG_FILENAMES if os.path.exists(os.path.join(root, n))), None)
    if existing is None:
        return f"MISSING\t{CLAUDE_MD}\t（「{CLAUDE_SECTION}」節ごと作る）"
    # 実測した3プロジェクトとも、検証コマンド自体は CLAUDE.md の別の節に書いてあった。
    # 拾い直せるので、足す前に既存の記述を読むこと。
    return f"NO_SECTION\t{existing}\t（「{CLAUDE_SECTION}」節が無い。既存の記述を読んでから足す）"


def check_direction(path: str) -> str:
    """`## ユーザーから` の本文行数と、隣の `draft/` のドラフトの件数を数える（正典「指示メモ」）。

    **節見出しが1つも無い（古い）ファイルは、全体を `## ユーザーから` とみなす**（後方互換）。
    ドラフトを積んでいた旧い節に行が残っていれば、それも数えて移すよう促す。
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    draft_n = _count_drafts(os.path.join(os.path.dirname(path), os.path.basename(layout.DRAFT_DIR)))

    known = (SECTION_USER, LEGACY_SECTION_DRAFT)
    if not any(l.startswith(k) for l in lines for k in known):
        body = [l for l in lines if l.strip() and not l.startswith("#")]
        return _direction_result(len(body), draft_n, 0)

    counts = {"user": 0, "legacy": 0}
    current: str | None = None
    for l in lines:
        if l.startswith(SECTION_USER):
            current = "user"
        elif l.startswith(LEGACY_SECTION_DRAFT):
            current = "legacy"
        elif l.startswith("## "):
            current = None
        elif l.strip() and current is not None:
            counts[current] += 1
    return _direction_result(counts["user"], draft_n, counts["legacy"])


def _count_drafts(draft_dir: str) -> int:
    if not os.path.isdir(draft_dir):
        return 0
    return sum(1 for n in os.listdir(draft_dir) if n.endswith(".md"))


def _direction_result(user_n: int, draft_n: int, legacy_n: int) -> str:
    if not (user_n or draft_n or legacy_n):
        return "OK: 未対応の指示は無い"
    legacy = f"、旧ドラフト節{legacy_n}行（{layout.DRAFT_DIR}/ へ移す）" if legacy_n else ""
    return f"PENDING: ユーザーから{user_n}行、エージェントのドラフト{draft_n}件{legacy}（/plan-tasks が先）"


if __name__ == "__main__":
    main()
