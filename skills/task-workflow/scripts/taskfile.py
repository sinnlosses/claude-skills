"""`develop/task/T-xxx.md` の読み書き（front matter の専用文法、本文の節の検査）。

正典は `docs/task-workflow-redesign.md` の3章。front matter は **YAML ではない**
専用の6行（`id` / `summary` / `status` / `difficulty` / `loopable` / `dependencies`）で、
この順・この綴りでなければそのファイルを INVALID にする（同章「front matter の文法」）。
YAML にしない理由・見出しの意味は正典を参照（同ファイル11章）。

読み手は例外を投げない。呼び出し側が「INVALID＝データの不備」と
「traceback＝環境の故障」を取り違えないよう、`(値, 理由)` の対を返す
（`status.py` の `load_tasks` と同じ形）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

ID_PATTERN = re.compile(r"^T-\d{3,}$")
STATUS_VALUES = ("todo", "hold", "done", "dropped")
DIFFICULTY_VALUES = ("haiku", "sonnet", "opus")
LOOPABLE_VALUES = ("Y", "N")

# 登録時（`task new`）に必須の節と、登録時には書けない節（3.3）。
REQUIRED_NEW_SECTIONS = ("## 目的", "## 完了条件", "## 背景")
FORBIDDEN_NEW_SECTIONS = ("## やること", "## 結果")

RESULT_HEADING = "## 結果"  # done/dropped で必須（3.3）。常に本文の最後に置く。

_HEADER_LINE_COUNT = 8  # "---" + 6フィールド + "---"


@dataclass(frozen=True)
class Task:
    id: str
    summary: str
    status: str
    difficulty: str
    loopable: str  # "Y" | "N"（真偽値にしない。3.2 の文法どおりの文字を保つ）
    dependencies: tuple[str, ...]
    body: str


def parse(text: str) -> tuple[Task | None, str | None]:
    """front matter と本文を読む。壊れていれば `(None, 理由)`。

    行の位置で判定する（3.2 の文法は6行・この順・この綴りと決まっているので、
    欠け・重複・順の違い・知らないキーはどれも「その行が期待した接頭辞で始まらない」
    という1種類の失敗に落ちる）。
    """
    if "\r" in text:
        return None, "CRLFを含む"
    lines = text.split("\n")
    if len(lines) < _HEADER_LINE_COUNT or lines[0] != "---":
        return None, "front matter の形になっていない（1行目が --- でない、または行数が足りない）"

    def field(index: int, prefix: str) -> str | None:
        line = lines[index]
        return line[len(prefix) :] if line.startswith(prefix) else None

    id_value = field(1, "id: ")
    if id_value is None or not ID_PATTERN.match(id_value):
        return None, "id行が無い、または T-999 の形式でない"

    summary_raw = field(2, "summary: ")
    if summary_raw is None:
        return None, "summary行が無い"
    summary = summary_raw.strip()
    if summary == "":
        return None, "summaryが空"

    status = field(3, "status: ")
    if status is None or status not in STATUS_VALUES:
        return None, "status行が無い、または todo/hold/done/dropped のいずれでもない"

    difficulty = field(4, "difficulty: ")
    if difficulty is None or difficulty not in DIFFICULTY_VALUES:
        return None, "difficulty行が無い、または haiku/sonnet/opus のいずれでもない"

    loopable = field(5, "loopable: ")
    if loopable is None or loopable not in LOOPABLE_VALUES:
        return None, "loopable行が無い、または Y/N のいずれでもない"

    deps_raw = field(6, "dependencies: [")
    if deps_raw is None or not deps_raw.endswith("]"):
        return None, "dependencies行が無い、または [ ... ] の形になっていない"
    deps_content = deps_raw[:-1]
    if deps_content == "":
        dependencies: tuple[str, ...] = ()
    else:
        parts = deps_content.split(", ")
        if ", ".join(parts) != deps_content or any(not ID_PATTERN.match(p) for p in parts):
            return None, "dependenciesの区切りは', '固定、各要素はT-999の形式"
        dependencies = tuple(parts)

    if lines[7] != "---":
        return None, "front matter を閉じる2つ目の --- が無い"

    body = "\n".join(lines[8:])
    return Task(id_value, summary, status, difficulty, loopable, dependencies, body), None


def render(task: Task) -> str:
    """`parse` の逆。front matter を6行ちょうどで書く。"""
    return (
        "---\n"
        f"id: {task.id}\n"
        f"summary: {task.summary}\n"
        f"status: {task.status}\n"
        f"difficulty: {task.difficulty}\n"
        f"loopable: {task.loopable}\n"
        f"dependencies: [{', '.join(task.dependencies)}]\n"
        "---\n"
        f"{task.body}"
    )


def read_task_file(path: str) -> tuple[Task | None, str | None]:
    """ファイルを読み、ファイル名の語幹と `id` の一致まで見る（3.4 の見本）。"""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, f"読めない（{e}）"
    task, err = parse(text)
    if err is not None:
        return None, err
    assert task is not None
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem != task.id:
        return None, f"ファイル名（{stem}）と id（{task.id}）が不一致"
    return task, None


def validate_new_body(body: str) -> str | None:
    """`task new` の本文検査（3.3）。問題が無ければ `None`。"""
    missing = [s for s in REQUIRED_NEW_SECTIONS if s not in body]
    if missing:
        return "本文に必須の節が無い: " + "、".join(missing)
    present = [s for s in FORBIDDEN_NEW_SECTIONS if s in body]
    if present:
        return "本文に登録時にはまだ書けない節がある（着手直後に書く節）: " + "、".join(present)
    return None


def set_result_section(body: str, content: str) -> str:
    """本文の `## 結果` 節を `content` に置き換える（無ければ末尾に足す。3.3・3.4・5.7）。

    節の並びは固定で `## 結果` は常に最後（3.3）なので、既存の節があれば丸ごと外し、
    改めて末尾に置き直す（順の入れ替えは起きない）。
    """
    content = content.strip("\n")
    lines = body.split("\n")
    start = next((i for i, l in enumerate(lines) if l == RESULT_HEADING), None)
    if start is not None:
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
            len(lines),
        )
        lines = lines[:start] + lines[end:]
        body = "\n".join(lines)
    body = body.rstrip("\n")
    prefix = f"{body}\n\n" if body else ""
    return f"{prefix}{RESULT_HEADING}\n\n{content}\n"


def task_path(task_dir: str, task_id: str) -> str:
    return os.path.join(task_dir, f"{task_id}.md")


def id_number(task_id: str) -> int:
    """`T-521` → `521`。呼ぶ側で `ID_PATTERN` に通した値だけを渡す。"""
    return int(task_id[len("T-") :])


def format_id(number: int) -> str:
    """3桁未満はゼロ埋め、3桁以上はそのまま（3.1: ID は `T-` + 3桁以上の数字）。"""
    return f"T-{number:03d}" if number < 1000 else f"T-{number}"


def local_task_ids(task_dir: str) -> list[str]:
    """作業ツリーの `develop/task/` にあるファイル名の語幹（拡張子抜き）を返す。"""
    if not os.path.isdir(task_dir):
        return []
    return sorted(os.path.splitext(n)[0] for n in os.listdir(task_dir) if n.endswith(".md"))


def history_ids(history_tasks_path: str) -> set[str]:
    """`docs/history/tasks.md` の `## T-xxx` 見出しから ID の集合を作る（3.1・5.3）。"""
    if not os.path.exists(history_tasks_path):
        return set()
    with open(history_tasks_path, encoding="utf-8") as f:
        text = f.read()
    return {
        m.group(1)
        for m in re.finditer(r"^## (T-\d{3,})\b", text, flags=re.MULTILINE)
    }
