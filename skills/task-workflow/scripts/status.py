#!/usr/bin/env python3
"""tasks.json の一覧を TSV で出し、末尾にアーカイブ判定を付ける。

使い方: status.py <tasks.json> [workflow.json]

workflow.json は無くてもよい（既定値: doneCount=10, doneBytes=30720）。
`task` 本文は出力しない。一覧を見るためにコンテキストへ本文を読み込まないための道具。
"""

from __future__ import annotations

import json
import os
import sys

DEFAULT_DONE_COUNT = 10
DEFAULT_DONE_BYTES = 30720


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: status.py <tasks.json> [workflow.json]", file=sys.stderr)
        raise SystemExit(2)
    tasks_path = sys.argv[1]
    config = load_config(sys.argv[2] if len(sys.argv) > 2 else None)
    archive = config.get("archive", {}) if isinstance(config, dict) else {}
    done_count_limit = int(archive.get("doneCount", DEFAULT_DONE_COUNT))
    done_bytes_limit = int(archive.get("doneBytes", DEFAULT_DONE_BYTES))

    if not os.path.exists(tasks_path):
        print("MISSING")
        return
    with open(tasks_path, encoding="utf-8") as f:
        tasks = json.load(f)
    if not tasks:
        print("EMPTY")
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
                    ",".join(t["dependencies"]) or "-",
                    ready,
                    "yes" if t["passes"] else "no",
                    t.get("summary", "(summaryなし)").replace("\t", " "),
                ]
            )
        )

    done = [t for t in tasks if t["status"] == "done"]
    done_bytes = len(json.dumps(done, ensure_ascii=False))
    print("---")
    print(
        "counts\t"
        + "\t".join(
            f"{s}={sum(1 for t in tasks if t['status'] == s)}" for s in ("todo", "doing", "done")
        )
    )
    print(f"done_size\t{done_bytes}\tfile_size\t{os.path.getsize(tasks_path)}")
    hit = len(done) >= done_count_limit or done_bytes > done_bytes_limit
    print(
        f"archive\t{'YES' if hit else 'NO'}"
        f"\t(done {len(done)}/{done_count_limit}件, {done_bytes}/{done_bytes_limit}B)"
    )


def load_config(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    return loaded if isinstance(loaded, dict) else {}


if __name__ == "__main__":
    main()
