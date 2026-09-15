#!/usr/bin/env python3
"""タスク運用に要るファイルをプロジェクトに用意する（既にあるものは触らない）。

使い方: init.py [develop-dir]   （既定: develop）

正典（task-workflow の WORKFLOW.md「ファイル配置と `develop/workflow.json`」）が定める
3ファイルを、決まった骨組みで作る。骨組みは決まりきっているのでモデルに書かせない
（`progress.md` の節名がズレると archive.py が節を見つけられず、`direction.md` に
見出し以外の行が混ざると `/plan-tasks` が「未対応の指示がある」と誤判定する）。

**既存ファイルは上書きしない。** 中身の点検結果だけを出し、直すかどうかは呼び出し側が決める。
`workflow.json` は作らない（無ければ全部既定値で動くため、空の設定ファイルは置かない）。
`<historyDir>/` も掘らない（archive.py が移すときに作る）。
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

    workflow = os.path.join(root, "workflow.json")
    if os.path.exists(workflow):
        print(f"KEPT\t{workflow}\t（プロジェクト固有の値あり）")
    else:
        print(f"ABSENT\t{workflow}\t（無くてよい。既定値と違う値があるときだけ作る）")


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


def check_direction(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        body = [l for l in f.read().splitlines() if l.strip() and not l.startswith("#")]
    if body:
        return f"PENDING: 未タスク化の指示が{len(body)}行ある（/plan-tasks が先）"
    return "OK: 未対応の指示は無い"


if __name__ == "__main__":
    main()
