#!/usr/bin/env python3
"""タスク運用に要るファイルをプロジェクトに用意する（既にあるものは触らない）。

使い方: init.py [develop-dir]   （既定: develop）

作るのは `develop/direction.md` の骨組み（`## ユーザーから`・`## エージェントのドラフト` の
2節）だけ（正典は task-workflow の WORKFLOW.md「ファイル配置と設定ファイル（AGENTS.md →
CLAUDE.md の順）」）。
`develop/task/` は最初の `task new` が作り、`direction.md` が新形式の目印になる（空の
ディレクトリは git に載らないため）。骨組みは決まりきっているのでモデルに書かせない
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

import layout

# direction.md の2節（正典「指示メモ」）。前方一致で探す。値は layout.py の正典を読む。
SECTION_USER = layout.SECTION_USER
SECTION_DRAFT = layout.SECTION_DRAFT
DIRECTION = f"# 未対応の指示メモ\n\n{SECTION_USER}\n\n{SECTION_DRAFT}\n"

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
    """`## ユーザーから`・`## エージェントのドラフト` の本文行数を数える（正典「指示メモ」）。

    **節見出しが1つも無い（古い）ファイルは、全体を `## ユーザーから` とみなす**（後方互換）。
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    known = (SECTION_USER, SECTION_DRAFT)
    if not any(l.startswith(k) for l in lines for k in known):
        body = [l for l in lines if l.strip() and not l.startswith("#")]
        return _direction_result(len(body), 0)

    counts = {"user": 0, "draft": 0}
    current: str | None = None
    for l in lines:
        if l.startswith(SECTION_USER):
            current = "user"
        elif l.startswith(SECTION_DRAFT):
            current = "draft"
        elif l.startswith("## "):
            current = None
        elif l.strip() and current is not None:
            counts[current] += 1
    return _direction_result(counts["user"], counts["draft"])


def _direction_result(user_n: int, draft_n: int) -> str:
    if user_n or draft_n:
        return f"PENDING: ユーザーから{user_n}行、エージェントのドラフト{draft_n}行（/plan-tasks が先）"
    return "OK: 未対応の指示は無い"


if __name__ == "__main__":
    main()
