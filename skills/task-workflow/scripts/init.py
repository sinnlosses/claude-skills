#!/usr/bin/env python3
"""タスク運用に要るファイルをプロジェクトに用意する（既にあるものは触らない）。

使い方: init.py [develop-dir]   （既定: develop）

正典（task-workflow の WORKFLOW.md「ファイル配置と CLAUDE.md」）が定める
3ファイルを、決まった骨組みで作る。骨組みは決まりきっているのでモデルに書かせない
（`progress.md` の節名がズレると archive.py が節を見つけられず、`direction.md` に
見出し以外の行が混ざると `/plan-tasks` が「未対応の指示がある」と誤判定する）。

**既存ファイルは上書きしない。** 中身の点検結果だけを出し、直すかどうかは呼び出し側が決める。
CLAUDE.md は**点検するだけで書かない**（節に入る値は検証コマンドの選定そのもので、
判断が要る。書くのは `/setup-tasks` の手順2）。
`docs/history/` も掘らない（archive.py が移すときに作る）。
"""

from __future__ import annotations

import json
import os
import sys

import taskfiles

TASKS = "[]\n"
PROGRESS = """# 進捗

## 完了したこと

## 未解決

## 注意
"""
DIRECTION = "# 未対応の指示メモ\n"

# progress.md に在るべき節。DONE_SECTION と同じく前方一致で探す（補足付きの表記が実在する）。
PROGRESS_SECTIONS = (taskfiles.DONE_SECTION, "## 未解決", "## 注意")

# CLAUDE.md 側の正典（正典「ファイル配置と CLAUDE.md」）。スキルはこの節を読む。
CLAUDE_MD = "CLAUDE.md"
CLAUDE_SECTION = "## タスク運用"
CLAUDE_KEYS = ("- 検証コマンド:", "- 整形コマンド:")


def main() -> None:
    args = sys.argv[1:]
    # ディレクトリ名として受け取る引数なので、`--help` のような打ち間違いをそのまま
    # ディレクトリにして掘らない（実際に `--help/` を作ってしまった）。
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("usage: init.py [develop-dir]   （既定: develop）", file=sys.stderr)
        raise SystemExit(2)
    root = args[0] if args else "develop"
    os.makedirs(root, exist_ok=True)

    create(os.path.join(root, "tasks.json"), TASKS, check_tasks)
    create(os.path.join(root, "progress.md"), PROGRESS, check_progress)
    create(os.path.join(root, "direction.md"), DIRECTION, check_direction)

    print(check_claude_md(CLAUDE_MD))


def create(path: str, body: str, check) -> None:
    """無ければ骨組みで作り、在れば中身を点検して報告する。"""
    if os.path.exists(path):
        print(f"KEPT\t{path}\t{check(path)}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"CREATED\t{path}")


def check_tasks(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            tasks = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return f"INVALID: JSONとして読めない（{e}）"
    if not isinstance(tasks, list):
        return "INVALID: 配列ではない"
    return f"OK: {len(tasks)}件"


def check_progress(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    missing = [s for s in PROGRESS_SECTIONS if not any(l.startswith(s) for l in lines)]
    return "OK: 3節そろっている" if not missing else "MISSING_SECTION: " + ", ".join(missing)


def check_claude_md(path: str) -> str:
    """検証コマンドの置き場（正典の「## タスク運用」節）が在るかを見る。書き換えはしない。"""
    if not os.path.exists(path):
        return f"MISSING\t{path}\t（「{CLAUDE_SECTION}」節ごと作る）"
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not any(l.startswith(CLAUDE_SECTION) for l in lines):
        # 実測した3プロジェクトとも、検証コマンド自体は CLAUDE.md の別の節に書いてあった。
        # 拾い直せるので、足す前に既存の記述を読むこと。
        return f"NO_SECTION\t{path}\t（「{CLAUDE_SECTION}」節が無い。既存の記述を読んでから足す）"
    missing = [k for k in CLAUDE_KEYS if not any(l.startswith(k) for l in lines)]
    if missing:
        return f"MISSING_LINE\t{path}\t" + ", ".join(missing)
    return f"OK\t{path}\t（{CLAUDE_SECTION} 節あり）"


def check_direction(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        body = [l for l in f.read().splitlines() if l.strip() and not l.startswith("#")]
    if body:
        return f"PENDING: 未タスク化の指示が{len(body)}行ある（/plan-tasks が先）"
    return "OK: 未対応の指示は無い"


if __name__ == "__main__":
    main()
