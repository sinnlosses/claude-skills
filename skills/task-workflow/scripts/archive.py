#!/usr/bin/env python3
"""done タスクと過去セッションの進捗をアーカイブへ機械的に移す。

使い方: archive.py <tasks.json> [workflow.json] [--dry-run]

正典（task-workflow の WORKFLOW.md「肥大化したときのアーカイブ」）が定める転記を
そのまま行う。転記は判断を含まないので、モデルが手で書き写さずこれを使う。

- `develop/tasks.json` の `status: "done"` を全件 `<historyDir>/tasks-archive.md` へ移す
- `develop/progress.md` の「完了したこと」から、最新の日付以外の小節を
  `<historyDir>/progress-archive.md` へ移す
- 2つは独立に判定する（片方だけ該当したら、その片方だけを移す）

`--dry-run` を付けると何も書かず、移す対象だけを報告する。
"""

from __future__ import annotations

import json
import os
import re
import sys

DEFAULT_DONE_COUNT = 10
DEFAULT_DONE_BYTES = 30720
DEFAULT_HISTORY_DIR = "docs/history"

TASKS_ARCHIVE_HEADER = "# 完了タスクのアーカイブ"
PROGRESS_ARCHIVE_HEADER = "# 過去セッションの「完了したこと」"

# 「## 完了したこと（このセッション）」のように後ろに補足が付いた表記が実在するので前方一致で拾う。
DONE_SECTION = "## 完了したこと"
DATE_HEADING = re.compile(r"^### (\d{4}-\d{2}-\d{2})\b")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    if not args:
        print("usage: archive.py <tasks.json> [workflow.json] [--dry-run]", file=sys.stderr)
        raise SystemExit(2)

    tasks_path = args[0]
    config = load_config(args[1] if len(args) > 1 else None)
    archive_cfg = config.get("archive", {}) if isinstance(config.get("archive"), dict) else {}
    history_dir = config.get("historyDir", DEFAULT_HISTORY_DIR)
    done_count_limit = int(archive_cfg.get("doneCount", DEFAULT_DONE_COUNT))
    done_bytes_limit = int(archive_cfg.get("doneBytes", DEFAULT_DONE_BYTES))

    progress_path = os.path.join(os.path.dirname(tasks_path) or ".", "progress.md")

    moved_any = False
    moved_any |= archive_tasks(
        tasks_path, history_dir, done_count_limit, done_bytes_limit, dry_run
    )
    moved_any |= archive_progress(progress_path, history_dir, dry_run)
    if not moved_any:
        print("NOOP\t移すものは無い")


# --- tasks.json ---------------------------------------------------------


def archive_tasks(
    tasks_path: str, history_dir: str, count_limit: int, bytes_limit: int, dry_run: bool
) -> bool:
    if not os.path.exists(tasks_path):
        print(f"tasks\tMISSING\t{tasks_path}")
        return False
    with open(tasks_path, encoding="utf-8") as f:
        tasks = json.load(f)

    done = [t for t in tasks if t.get("status") == "done"]
    done_bytes = len(json.dumps(done, ensure_ascii=False))
    if not (len(done) >= count_limit or done_bytes > bytes_limit):
        print(
            f"tasks\tSKIP\tトリガー未達 (done {len(done)}/{count_limit}件, "
            f"{done_bytes}/{bytes_limit}B)"
        )
        return False

    remaining = [t for t in tasks if t.get("status") != "done"]
    before = os.path.getsize(tasks_path)
    entries = "\n".join(render_task(t) for t in done)

    if dry_run:
        print(f"tasks\tDRY-RUN\t{len(done)}件 ({done_bytes}B): {','.join(t['id'] for t in done)}")
        return True

    archive_path = os.path.join(history_dir, "tasks-archive.md")
    append_section(archive_path, TASKS_ARCHIVE_HEADER, entries)
    with open(tasks_path, "w", encoding="utf-8") as f:
        f.write(dump_tasks(remaining))

    after = os.path.getsize(tasks_path)
    print(
        f"tasks\tMOVED\t{len(done)}件\t{','.join(t['id'] for t in done)}\t"
        f"{before}B -> {after}B\t{archive_path}"
    )
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


def archive_progress(progress_path: str, history_dir: str, dry_run: bool) -> bool:
    if not os.path.exists(progress_path):
        print(f"progress\tMISSING\t{progress_path}")
        return False
    with open(progress_path, encoding="utf-8") as f:
        text = f.read()

    head, sections, tail = split_done_section(text)
    if sections is None:
        print(f"progress\tSKIP\t「{DONE_SECTION}」節が無い")
        return False

    dated = [s for s in sections if s[0] is not None]
    undated = len(sections) - len(dated)
    if not dated:
        print("progress\tSKIP\t日付つきの小節が無い")
        return False

    latest = max(d for d, _ in dated)
    keep = [s for s in sections if s[0] is None or s[0] == latest]
    move = [s for s in sections if s[0] is not None and s[0] != latest]
    if not move:
        note = f"（最新 {latest} のみ）"
        if undated:
            note += f" 日付の無い小節が{undated}件ある（正典「progress.md の構成」）"
        print(f"progress\tSKIP\t移す小節が無い{note}")
        return False

    moved_text = "".join(body for _, body in move).rstrip() + "\n"
    if dry_run:
        print(f"progress\tDRY-RUN\t{len(move)}小節 ({len(moved_text)}文字)")
        return True

    before = os.path.getsize(progress_path)
    new_text = head + "".join(body for _, body in keep) + tail
    archive_path = os.path.join(history_dir, "progress-archive.md")
    prepend_section(archive_path, PROGRESS_ARCHIVE_HEADER, moved_text)
    with open(progress_path, "w", encoding="utf-8") as f:
        f.write(new_text)

    after = os.path.getsize(progress_path)
    extra = f"\t日付なしの小節{undated}件は残した" if undated else ""
    print(
        f"progress\tMOVED\t{len(move)}小節\t最新 {latest} を残した\t"
        f"{before}B -> {after}B\t{archive_path}{extra}"
    )
    return True


def split_done_section(text: str) -> tuple[str, list[tuple[str | None, str]] | None, str]:
    """「完了したこと」節を (前, 小節リスト, 後) に割る。小節は (日付, 本文) の組。"""
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith(DONE_SECTION)), None)
    if start is None:
        return text, None, ""
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )

    sections: list[tuple[str | None, list[str]]] = []
    head_end = end
    for i in range(start + 1, end):
        if lines[i].startswith("### "):
            head_end = min(head_end, i)
            m = DATE_HEADING.match(lines[i])
            sections.append((m.group(1) if m else None, [lines[i]]))
        elif sections:
            sections[-1][1].append(lines[i])

    head = "".join(lines[:head_end])
    tail = "".join(lines[end:])
    return head, [(d, "".join(b)) for d, b in sections], tail


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
    head_idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), -1)
    cut = head_idx + 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines[:cut]).rstrip() + "\n\n" + body.rstrip() + "\n\n")
        f.write("".join(lines[cut:]).lstrip())


def ensure_archive(path: str, header: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + "\n")


def load_config(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    return loaded if isinstance(loaded, dict) else {}


if __name__ == "__main__":
    main()
