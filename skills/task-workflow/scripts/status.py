#!/usr/bin/env python3
"""tasks.json の一覧を TSV で出し、末尾にアーカイブ判定を付ける。

使い方: status.py <tasks.json>

`task` 本文は出力しない。一覧を見るためにコンテキストへ本文を読み込まないための道具。
progress.md（tasks.json と同じディレクトリ）の判定も併せて出す。

**データの不備で traceback を出さない。** 呼び出し側のスキルは「`MISSING`・`EMPTY`・TSV の
いずれでもない出力」を「`python3` が使えない」の合図として扱うので、ここが落ちると
*データの不備が環境の故障として報告される*。読めないファイルは `INVALID` 行で、
フィールドの欠けは `missing_field` 行で、どちらも「データの話だ」と分かる形で返す。
"""

from __future__ import annotations

import os
import sys

import taskfiles

# TSV に出すのに要るフィールド。欠けていても落とさず `?` を出し、末尾でまとめて報告する。
REQUIRED = ("id", "status", "difficulty", "dependencies", "passes")


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: status.py <tasks.json>", file=sys.stderr)
        raise SystemExit(2)
    tasks_path = sys.argv[1]
    lim = taskfiles.LIMITS

    if not os.path.exists(tasks_path):
        print("MISSING")
        return

    tasks, err = taskfiles.load_tasks(tasks_path)
    if err:
        # データの不備。`python3` は動いているので、そう分かる語で返す。
        print(f"INVALID\t{tasks_path}\t{err}")
        return
    if not tasks:
        # tasks.json が空でも progress.md には中身がありうるので、判定だけは出す。
        print("EMPTY")
        print(progress_line(taskfiles.progress_path_for(tasks_path), lim))
        return

    ids = {t.get("id") for t in tasks}
    done_ids = {t.get("id") for t in tasks if t.get("status") == "done"}
    long_summaries = []
    incomplete = []
    for i, t in enumerate(tasks):
        tid = t.get("id") or f"(id無し#{i})"
        missing = [k for k in REQUIRED if k not in t]
        if missing:
            incomplete.append(f"{tid}:{'+'.join(missing)}")

        status = t.get("status", "?")
        deps = t.get("dependencies") or []
        blocked = [d for d in deps if d in ids and d not in done_ids]
        if status != "todo":
            ready = "-"
        elif blocked:
            ready = "BLOCKED:" + ",".join(blocked)
        else:
            ready = "READY"
        summary = t.get("summary", "(summaryなし)").replace("\t", " ")
        # 警告は**まだ直せるタスクだけ**。`done` の summary は履歴なので遡って書き換えない
        # （正典「difficulty」の「完了済みには遡って付けない」と同じ立場）。
        if status != "done" and taskfiles.display_width(summary) > taskfiles.LONG_SUMMARY_WIDTH:
            long_summaries.append(tid)
        print(
            "\t".join(
                [
                    tid,
                    status,
                    t.get("difficulty", "?"),
                    t.get("loopable", "?"),
                    ",".join(deps) or "-",
                    ready,
                    passes_cell(t),
                    summary,
                ]
            )
        )

    done, done_chars, hit = taskfiles.done_plan(tasks, lim["doneCount"], lim["doneChars"])
    print("---")
    print(
        "counts\t"
        + "\t".join(
            f"{s}={sum(1 for t in tasks if t.get('status') == s)}" for s in ("todo", "doing", "done")
        )
    )
    todo_no_loop = sum(
        1 for t in tasks if t.get("status") == "todo" and t.get("loopable", "Y") == "N"
    )
    print(f"todo_loopable\tN={todo_no_loop}")
    print(
        f"long_summary\t{len(long_summaries)}\t"
        + (",".join(long_summaries) if long_summaries else "-")
        + f"\t(未完了で表示幅 {taskfiles.LONG_SUMMARY_WIDTH}桁超。正典「summary」は一行に収める)"
    )
    done_failed = [
        t.get("id") for t in tasks if t.get("status") == "done" and not t.get("passes")
    ]
    print(f"done_failed\t{len(done_failed)}\t" + (",".join(done_failed) if done_failed else "-"))
    print(
        f"missing_field\t{len(incomplete)}\t"
        + (",".join(incomplete) if incomplete else "-")
        + "\t(TSV に要るフィールドが欠けたタスク。`?` で出してある)"
    )
    print(f"done_size\t{done_chars}文字\tfile_size\t{os.path.getsize(tasks_path)}B")
    print(
        f"archive\t{'YES' if hit else 'NO'}"
        f"\t(done {len(done)}/{lim['doneCount']}件, {done_chars}/{lim['doneChars']}文字)"
    )
    print(progress_line(taskfiles.progress_path_for(tasks_path), lim))


def passes_cell(t: dict) -> str:
    if "passes" not in t:
        return "?"
    return "yes" if t["passes"] else "no"


def progress_line(path: str, lim: dict) -> str:
    if not os.path.exists(path):
        return "progress\tMISSING\t" + path
    with open(path, encoding="utf-8") as f:
        _, sections, _ = taskfiles.split_done_section(f.read())
    if sections is None:
        return f"progress\tNO\t（「{taskfiles.DONE_SECTION}」節が無い）"
    if not taskfiles.is_newest_first(sections):
        return "progress\tERROR\t（小節が新しい順に並んでいない。正典「progress.md の構成」）"

    keep, move = taskfiles.progress_plan(sections, lim["progressCount"], lim["progressChars"])
    total = sum(len(s) for s in sections)
    return (
        f"progress\t{'YES' if move else 'NO'}"
        f"\t({len(sections)}小節/{lim['progressCount']}件, {total}/{lim['progressChars']}文字"
        f"{f', 移す{len(move)}小節' if move else ''})"
    )


if __name__ == "__main__":
    main()
