#!/usr/bin/env python3
"""done タスクと過去の進捗をアーカイブへ機械的に移す。

使い方: archive.py <tasks.json> [workflow.json] [--dry-run]

正典（task-workflow の WORKFLOW.md「肥大化したときのアーカイブ」）が定める転記を
そのまま行う。転記は判断を含まないので、モデルが手で書き写さずこれを使う。

- `develop/tasks.json` の `status: "done"` を全件 `<historyDir>/tasks-archive.md` へ移す
- `develop/progress.md` の「完了したこと」から、新しい順に残す予算を超えたぶんを
  `<historyDir>/progress-archive.md` へ移す
- 2つは独立に判定する（片方だけ該当したら、その片方だけを移す）

判定そのものは `taskfiles.py` にあり、`status.py` と共有している。
`--dry-run` を付けると何も書かず、移す対象だけを報告する。
"""

from __future__ import annotations

import json
import os
import sys

import taskfiles

TASKS_ARCHIVE_HEADER = "# 完了タスクのアーカイブ"
PROGRESS_ARCHIVE_HEADER = "# 過去セッションの「完了したこと」"


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    if not args:
        print("usage: archive.py <tasks.json> [workflow.json] [--dry-run]", file=sys.stderr)
        raise SystemExit(2)

    tasks_path = args[0]
    config = taskfiles.load_config(args[1] if len(args) > 1 else None)
    lim = taskfiles.limits(config)
    history = taskfiles.history_dir(config)

    moved = archive_tasks(tasks_path, history, lim, dry_run)
    moved |= archive_progress(taskfiles.progress_path_for(tasks_path), history, lim, dry_run)
    if not moved:
        print("NOOP\t移すものは無い")


# --- tasks.json ---------------------------------------------------------


def archive_tasks(tasks_path: str, history: str, lim: dict, dry_run: bool) -> bool:
    if not os.path.exists(tasks_path):
        print(f"tasks\tMISSING\t{tasks_path}")
        return False
    with open(tasks_path, encoding="utf-8") as f:
        tasks = json.load(f)

    done, size, hit = taskfiles.done_plan(tasks, lim["doneCount"], lim["doneBytes"])
    if not hit:
        print(
            f"tasks\tSKIP\tトリガー未達 (done {len(done)}/{lim['doneCount']}件, "
            f"{size}/{lim['doneBytes']}B)"
        )
        return False

    ids = ",".join(t["id"] for t in done)
    if dry_run:
        print(f"tasks\tDRY-RUN\t{len(done)}件 ({size}B): {ids}")
        return True

    before = os.path.getsize(tasks_path)
    archive_path = os.path.join(history, "tasks-archive.md")
    append_section(archive_path, TASKS_ARCHIVE_HEADER, "\n".join(render_task(t) for t in done))
    with open(tasks_path, "w", encoding="utf-8") as f:
        f.write(dump_tasks([t for t in tasks if t.get("status") != "done"]))

    after = os.path.getsize(tasks_path)
    print(f"tasks\tMOVED\t{len(done)}件\t{ids}\t{before}B -> {after}B\t{archive_path}")
    return True


def dump_tasks(tasks: list[dict]) -> str:
    """既存ファイルと同じ体裁（インデント2、1フィールド1行、短い配列はインライン）で書く。

    `json.dump(indent=2)` は `["T-003"]` を3行に開いてしまい、消したタスク以外も
    差分に載る。キーの並びは読み込んだ順をそのまま保つ（このスクリプトは消すだけで、
    フィールドを足さない）。
    """
    if not tasks:
        return "[]\n"
    out = ["["]
    for i, t in enumerate(tasks):
        items = list(t.items())
        out.append("  {")
        for j, (k, v) in enumerate(items):
            comma = "," if j < len(items) - 1 else ""
            key = json.dumps(k, ensure_ascii=False)
            val = json.dumps(v, ensure_ascii=False)
            out.append(f"    {key}: {val}{comma}")
        out.append("  }" + ("," if i < len(tasks) - 1 else ""))
    out.append("]")
    return "\n".join(out) + "\n"


def render_task(t: dict) -> str:
    """正典「何を移すか」のエントリ形式。tasks.json の値だけから組み立てる。"""
    deps = ", ".join(t.get("dependencies") or []) or "なし"
    lines = [
        f"## {t['id']}",
        "",
        f"**タスク**: {t.get('summary') or '(summaryなし)'}",
        "",
        f"**difficulty**: {t.get('difficulty', '?')} / **loopable**: {t.get('loopable', '?')}"
        f" / **dependencies**: {deps} / **passes**: {t.get('passes')}",
        "",
    ]
    evidence = (t.get("evidence") or "").strip()
    if evidence:
        lines += ["**evidence**:", "", evidence, ""]
    body = (t.get("task") or "").strip()
    if body:
        lines += [body, ""]
    return "\n".join(lines)


# --- progress.md --------------------------------------------------------


def archive_progress(progress_path: str, history: str, lim: dict, dry_run: bool) -> bool:
    if not os.path.exists(progress_path):
        print(f"progress\tMISSING\t{progress_path}")
        return False
    with open(progress_path, encoding="utf-8") as f:
        text = f.read()

    head, sections, tail = taskfiles.split_done_section(text)
    if sections is None:
        print(f"progress\tSKIP\t「{taskfiles.DONE_SECTION}」節が無い")
        return False
    if not taskfiles.is_newest_first(sections):
        print(
            "progress\tERROR\t小節が新しい順に並んでいない。移すと新しいほうを捨てるので"
            "何もしない（正典「progress.md の構成」）"
        )
        return False

    keep, move = taskfiles.progress_plan(sections, lim["progressCount"], lim["progressBytes"])
    total = sum(len(s) for s in sections)
    if not move:
        print(
            f"progress\tSKIP\t予算内 ({len(sections)}/{lim['progressCount']}件, "
            f"{total}/{lim['progressBytes']}B)"
        )
        return False

    moved_text = "".join(s.text for s in move).rstrip() + "\n"
    if dry_run:
        print(f"progress\tDRY-RUN\t{len(move)}小節 ({len(moved_text)}文字)")
        return True

    before = os.path.getsize(progress_path)
    archive_path = os.path.join(history, "progress-archive.md")
    prepend_section(archive_path, PROGRESS_ARCHIVE_HEADER, moved_text)
    with open(progress_path, "w", encoding="utf-8") as f:
        f.write(head + "".join(s.text for s in keep) + tail)

    after = os.path.getsize(progress_path)
    print(
        f"progress\tMOVED\t{len(move)}小節\t{len(keep)}小節を残した\t"
        f"{before}B -> {after}B\t{archive_path}"
    )
    return True


# --- 共通 ---------------------------------------------------------------


def append_section(path: str, header: str, body: str) -> None:
    ensure_archive(path, header)
    with open(path, encoding="utf-8") as f:
        current = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(current.rstrip() + "\n\n" + body.rstrip() + "\n")


def prepend_section(path: str, header: str, body: str) -> None:
    """既存のエントリより前（見出しの直後）に差し込む。新しいものが上に来る並びを保つ。"""
    ensure_archive(path, header)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    cut = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), -1) + 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines[:cut]).rstrip() + "\n\n" + body.rstrip() + "\n\n")
        f.write("".join(lines[cut:]).lstrip())


def ensure_archive(path: str, header: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + "\n")


if __name__ == "__main__":
    main()
