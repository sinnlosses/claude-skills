#!/usr/bin/env python3
"""tasks.json の一覧を TSV で出し、末尾にアーカイブ判定を付ける。

使い方: status.py <tasks.json> [workflow.json]

workflow.json は無くてもよい（既定値は taskfiles.DEFAULTS）。
`task` 本文は出力しない。一覧を見るためにコンテキストへ本文を読み込まないための道具。
progress.md（tasks.json と同じディレクトリ）の判定も併せて出す。
"""

from __future__ import annotations

import json
import os
import sys

import taskfiles


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: status.py <tasks.json> [workflow.json]", file=sys.stderr)
        raise SystemExit(2)
    tasks_path = sys.argv[1]
    config = taskfiles.load_config(sys.argv[2] if len(sys.argv) > 2 else None)
    lim = taskfiles.limits(config)

    if not os.path.exists(tasks_path):
        print("MISSING")
        return
    with open(tasks_path, encoding="utf-8") as f:
        tasks = json.load(f)
    if not tasks:
        # tasks.json が空でも progress.md には中身がありうるので、判定だけは出す。
        print("EMPTY")
        print(progress_line(taskfiles.progress_path_for(tasks_path), lim))
        return

    ids = {t["id"] for t in tasks}
    done_ids = {t["id"] for t in tasks if t["status"] == "done"}
    for t in tasks:
        blocked = [d for d in t["dependencies"] if d in ids and d not in done_ids]
        if t["status"] != "todo":
            ready = "-"
        elif blocked:
            ready = "BLOCKED:" + ",".join(blocked)
        else:
            ready = "READY"
        print(
            "\t".join(
                [
                    t["id"],
                    t["status"],
                    t["difficulty"],
                    t.get("loopable", "?"),
                    ",".join(t["dependencies"]) or "-",
                    ready,
                    "yes" if t["passes"] else "no",
                    t.get("summary", "(summaryなし)").replace("\t", " "),
                ]
            )
        )

    done, done_bytes, hit = taskfiles.done_plan(tasks, lim["doneCount"], lim["doneBytes"])
    print("---")
    print(
        "counts\t"
        + "\t".join(
            f"{s}={sum(1 for t in tasks if t['status'] == s)}" for s in ("todo", "doing", "done")
        )
    )
    todo_no_loop = sum(
        1 for t in tasks if t["status"] == "todo" and t.get("loopable", "Y") == "N"
    )
    print(f"todo_loopable\tN={todo_no_loop}")
    print(f"done_size\t{done_bytes}\tfile_size\t{os.path.getsize(tasks_path)}")
    print(
        f"archive\t{'YES' if hit else 'NO'}"
        f"\t(done {len(done)}/{lim['doneCount']}件, {done_bytes}/{lim['doneBytes']}B)"
    )
    print(progress_line(taskfiles.progress_path_for(tasks_path), lim))


def progress_line(path: str, lim: dict) -> str:
    if not os.path.exists(path):
        return "progress\tMISSING\t" + path
    with open(path, encoding="utf-8") as f:
        _, sections, _ = taskfiles.split_done_section(f.read())
    if sections is None:
        return f"progress\tNO\t（「{taskfiles.DONE_SECTION}」節が無い）"
    if not taskfiles.is_newest_first(sections):
        return "progress\tERROR\t（小節が新しい順に並んでいない。正典「progress.md の構成」）"

    keep, move = taskfiles.progress_plan(sections, lim["progressCount"], lim["progressBytes"])
    total = sum(len(s) for s in sections)
    return (
        f"progress\t{'YES' if move else 'NO'}"
        f"\t({len(sections)}小節/{lim['progressCount']}件, {total}/{lim['progressBytes']}B"
        f"{f', 移す{len(move)}小節' if move else ''})"
    )


if __name__ == "__main__":
    main()
