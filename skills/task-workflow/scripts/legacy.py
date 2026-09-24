"""旧形式（`develop/tasks.json` + `develop/progress.md`）の読み取りと `task migrate`。

正典は `docs/task-workflow-redesign.md` の5.9・10.1・10.2。`task.py` の `cmd_migrate` から
`migrate()` を呼ぶ（`ship.py` が `attempt()` を返し `task.py` が印字するのと同じ形。ここで
ファイル・git の実際の書き換えまで行い、`task.py` 側は結果を印字するだけにする）。

タスクの変換（10.1）は機械的な写しで、**登録時の本文の節の検査（`taskfile.validate_new_body`）
は受けない**（移行したファイルの本文はそのまま。正典3.3「移行したファイルは本文の節の検査を
受けない」）。`progress.md` の扱い（10.2）は「完了したこと」の小節を全部
`docs/history/progress.md` へ移し、「未解決」「注意」だけを残す。両方0件なら
`develop/progress.md` 自体を消す。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

import archive
import ledger
import taskfile
import taskfiles

TASK_DIR_NAME = "task"
UNRESOLVED_HEADING = "## 未解決"
NOTE_HEADING = "## 注意"
LEFTOVER_NOTICE = "移行の残り。8章の表で振り分けたら消す。\n"

RESULT_HEADING_LINE = re.compile(r"^## 結果\s*$", re.MULTILINE)


def _run_git(cwd: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


# --- タスクの変換（10.1） ----------------------------------------------------


def convert_task(raw: dict) -> tuple[taskfile.Task | None, str | None]:
    """旧 `tasks.json` の1要素を、新しいタスクファイルの `Task` に変換する（10.1の表）。"""
    tid = raw.get("id")
    if not isinstance(tid, str) or not taskfile.ID_PATTERN.match(tid):
        return None, f"idが無い、またはT-999の形式でない（{tid!r}）"

    status_raw = raw.get("status")
    if status_raw == "todo":
        status = "todo"
    elif status_raw == "done":
        status = "done" if raw.get("passes") else "dropped"
    else:
        # `doing` は呼び出し側（`migrate`）が先に検査して止める。それ以外の値は未知として拒む。
        return None, f"statusが未知（{status_raw!r}）"

    body = (raw.get("task") or "").strip("\n")
    body = f"{body}\n" if body else ""

    summary_raw = raw.get("summary")
    if isinstance(summary_raw, str) and summary_raw.strip():
        summary = summary_raw.replace("\n", " ").strip()
    else:
        summary = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if not summary:
        return None, "summaryが無く、taskの先頭行も取れない"

    difficulty = raw.get("difficulty")
    if difficulty not in taskfile.DIFFICULTY_VALUES:
        return None, f"difficultyが未知（{difficulty!r}）"

    loopable = raw.get("loopable") or "Y"
    if loopable not in taskfile.LOOPABLE_VALUES:
        return None, f"loopableが未知（{loopable!r}）"

    deps_raw = raw.get("dependencies") or []
    if not isinstance(deps_raw, list) or any(
        not isinstance(d, str) or not taskfile.ID_PATTERN.match(d) for d in deps_raw
    ):
        return None, "dependenciesがT-999の形式の配列でない"
    dependencies = tuple(deps_raw)

    evidence = (raw.get("evidence") or "").strip()
    if evidence:
        if RESULT_HEADING_LINE.search(body):
            return None, "本文に既に'## 結果'がある"
        body = taskfile.set_result_section(body, evidence)

    return taskfile.Task(tid, summary, status, difficulty, loopable, dependencies, body), None


# --- progress.md の振り分け（10.2） ------------------------------------------


def _count_bullets(section_text: str) -> int:
    lines = section_text.splitlines()
    return sum(1 for line in lines[1:] if line.strip().startswith("- "))


def progress_plan(text: str) -> tuple[int, str, str | None, int, int]:
    """`(移す小節数, 移す本文, 残すprogress.mdの本文（Noneなら消す）, 未解決件数, 注意件数)`。

    「完了したこと」の小節は全部移す（keepは無い。archive.pyの部分アーカイブとは違い、
    新しい順の検査もしない——全部移すので順は関係しない）。「未解決」「注意」は動かさず、
    その2節だけを先頭の1行つきで残す。両方0件（箇条書きが無い）なら残す本文は無し
    （呼び出し側が `develop/progress.md` 自体を消す）。
    """
    _, sections, _ = taskfiles.split_done_section(text)
    sections = sections or []
    moved_text = "".join(s.text for s in sections)

    _, unresolved_section, _ = taskfiles.split_named_section(text, UNRESOLVED_HEADING)
    _, note_section, _ = taskfiles.split_named_section(text, NOTE_HEADING)
    unresolved_count = _count_bullets(unresolved_section)
    note_count = _count_bullets(note_section)

    if unresolved_count == 0 and note_count == 0:
        leftover: str | None = None
    else:
        leftover = LEFTOVER_NOTICE + "\n" + unresolved_section + note_section

    return len(sections), moved_text, leftover, unresolved_count, note_count


# --- migrate（5.9） ----------------------------------------------------------


@dataclass(frozen=True)
class MigrateResult:
    kind: str  # "OK" | "DIRTY" | "INVALID" | "NOT_READY" | "NOTHING"
    detail: str = ""
    written: tuple[str, ...] = ()
    moved_sections: int = 0
    leftover_counts: tuple[int, int] | None = None  # (未解決, 注意)。Noneならprogress.md自体を消した/触っていない
    progress_removed: bool = False
    task_count: int = 0


def migrate(toplevel: str, dry_run: bool) -> MigrateResult:
    """`task migrate` の本体。`dry_run` なら判定だけ行い、何も書かない。"""
    if not ledger.is_clean(cwd=toplevel):
        return MigrateResult(kind="DIRTY")

    tasks_json_path = os.path.join(toplevel, "develop", "tasks.json")
    if not os.path.exists(tasks_json_path):
        direction_path = os.path.join(toplevel, "develop", "direction.md")
        detail = "develop/tasks.json が無い" + ("（既に新形式）" if os.path.exists(direction_path) else "")
        return MigrateResult(kind="NOTHING", detail=detail)

    raw_tasks, err = taskfiles.load_tasks(tasks_json_path)
    if err is not None:
        return MigrateResult(kind="INVALID", detail=f"develop/tasks.json\t{err}")

    doing = next((t for t in raw_tasks if t.get("status") == "doing"), None)
    if doing is not None:
        return MigrateResult(kind="NOT_READY", detail=f"{doing.get('id', '?')}\tdoing")

    converted: list[taskfile.Task] = []
    for raw in raw_tasks:
        task, conv_err = convert_task(raw)
        if conv_err is not None:
            return MigrateResult(kind="INVALID", detail=f"{raw.get('id', '?')}\t{conv_err}")
        converted.append(task)  # type: ignore[arg-type]

    written = tuple(f"develop/{TASK_DIR_NAME}/{t.id}.md" for t in converted)

    progress_path = os.path.join(toplevel, "develop", "progress.md")
    moved_sections = 0
    moved_text = ""
    leftover_text: str | None = None
    unresolved = note = 0
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as f:
            progress_text = f.read()
        moved_sections, moved_text, leftover_text, unresolved, note = progress_plan(progress_text)

    leftover_counts = (unresolved, note) if leftover_text is not None else None
    progress_removed = os.path.exists(progress_path) and leftover_text is None

    if dry_run:
        return MigrateResult(
            kind="OK",
            written=written,
            moved_sections=moved_sections,
            leftover_counts=leftover_counts,
            progress_removed=progress_removed,
            task_count=len(converted),
        )

    task_dir = os.path.join(toplevel, "develop", TASK_DIR_NAME)
    os.makedirs(task_dir, exist_ok=True)
    for t in converted:
        with open(taskfile.task_path(task_dir, t.id), "w", encoding="utf-8") as f:
            f.write(taskfile.render(t))
    _run_git(toplevel, ["add", os.path.join("develop", TASK_DIR_NAME)])

    if moved_sections > 0:
        archive_path = os.path.join(toplevel, taskfiles.HISTORY_DIR, "progress.md")
        archive.prepend_section(archive_path, archive.PROGRESS_ARCHIVE_HEADER, moved_text)
        _run_git(toplevel, ["add", os.path.join(taskfiles.HISTORY_DIR, "progress.md")])

    if os.path.exists(progress_path):
        if leftover_text is not None:
            with open(progress_path, "w", encoding="utf-8") as f:
                f.write(leftover_text)
            _run_git(toplevel, ["add", "develop/progress.md"])
        else:
            _run_git(toplevel, ["rm", "-q", "develop/progress.md"])

    _run_git(toplevel, ["rm", "-q", "develop/tasks.json"])

    root = ledger.ledger_root(cwd=toplevel)
    history_ids = taskfile.history_ids(os.path.join(toplevel, "docs", "history", "tasks.md"))
    max_id = max(
        [0] + [taskfile.id_number(t.id) for t in converted] + [taskfile.id_number(h) for h in history_ids]
    )
    ledger.write_last_id(root, max_id)

    return MigrateResult(
        kind="OK",
        written=written,
        moved_sections=moved_sections,
        leftover_counts=leftover_counts,
        progress_removed=progress_removed,
        task_count=len(converted),
    )
