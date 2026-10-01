"""`develop/task/T-xxx.md` の読み書き（front matter の専用文法、本文の節の検査）。

正典は `docs/task-workflow-redesign.md` の3章。front matter は **YAML ではない**
専用の6行（`id` / `summary` / `status` / `difficulty` / `loopable` / `dependencies`）で、
この順・この綴りでなければそのファイルを INVALID にする（同章「front matter の文法」）。
YAML にしない理由・見出しの意味は正典を参照（同ファイル11章）。

読み手は例外を投げない。呼び出し側が「INVALID＝データの不備」と
「traceback＝環境の故障」を取り違えないよう、`(値, 理由)` の対を返す
（`legacy.load_tasks` と同じ形）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import layout

ID_PATTERN = layout.ID_PATTERN
STATUS_VALUES = ("todo", "hold", "done", "dropped")
DIFFICULTY_VALUES = ("haiku", "sonnet", "opus")
LOOPABLE_VALUES = ("Y", "N")

# 本文の枠（WORKFLOW.md「タスクファイル」）。7つの見出しを必ずこの順で置き、要らない欄は空か「なし」にする。
PURPOSE_HEADING = "## 目的・背景"
PLAN_HEADING = "## やること"
ACCEPTANCE_HEADING = "## 完了条件"
CAUTION_HEADING = "## 注意"
SECTION_HEADINGS = (
    PURPOSE_HEADING,
    "## 決まっていること（蒸し返さない）",
    "## 解くべき論点",
    PLAN_HEADING,
    ACCEPTANCE_HEADING,
    CAUTION_HEADING,
    "## 参考情報",
)
# 空・「なし」にできない欄。
FILLED_SECTIONS = (PURPOSE_HEADING, ACCEPTANCE_HEADING)
EMPTY_MARK = "なし"

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

    # `render` と同じ形（前後の空行を落とし、末尾は改行1つ）に揃え、往復で本文が変わらないようにする。
    body = "\n".join(lines[8:]).strip("\n")
    body = f"{body}\n" if body else ""
    return Task(id_value, summary, status, difficulty, loopable, dependencies, body), None


def render(task: Task) -> str:
    """`parse` の逆。front matter を6行ちょうどで書く。

    本文は「閉じる `---` の次に空行1行、末尾は改行1つ」に揃える。Markdown の整形ツール
    （oxfmt・prettier）は見出しの前に空行を求めるので、`## 目的・背景` から始まる本文をそのまま
    連結すると、登録した直後のファイルが整形の検査で落ちる。
    """
    body = task.body.strip("\n")
    return (
        "---\n"
        f"id: {task.id}\n"
        f"summary: {task.summary}\n"
        f"status: {task.status}\n"
        f"difficulty: {task.difficulty}\n"
        f"loopable: {task.loopable}\n"
        f"dependencies: [{', '.join(task.dependencies)}]\n"
        "---\n"
        + (f"\n{body}\n" if body else "")
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
    """`task new`・`task adopt` の本文検査。枠の検査に加え、`## やること` は空か「なし」に限る
    （登録時に書いた手順は着手までに古くなる）。問題が無ければ `None`。"""
    error = validate_body(body)
    if error is not None:
        return error
    if has_plan(body):
        return f"{PLAN_HEADING} は着手直後に書く（登録時は空か「{EMPTY_MARK}」）"
    return None


def validate_body(body: str) -> str | None:
    """本文が枠（`SECTION_HEADINGS` をこの順に1つずつ）に沿っているか。`## 結果` は枠の外で拒む。

    見出しは行頭の `## ` だけを数える（本文の説明文で節名に言及するのは許す）。
    """
    preamble, sections = _frame_sections(body)
    if body.startswith("---"):
        return "本文の先頭に front matter がある（front matter は除き、最初の `## ` 見出しから渡す）"
    if preamble.strip():
        return "本文の最初の見出しより前に文がある"
    headings = tuple(h for h, _ in sections)
    if RESULT_HEADING in headings:
        return f"{RESULT_HEADING} は tw done が書く（本文に入れない）"
    if headings != SECTION_HEADINGS:
        return "本文の見出しが枠と違う（この順に1つずつ置く）: " + "、".join(SECTION_HEADINGS)
    contents = dict(sections)
    blank = [h for h in FILLED_SECTIONS if is_blank(contents[h])]
    if blank:
        return f"空・「{EMPTY_MARK}」にできない節: " + "、".join(blank)
    return None


def _frame_sections(body: str) -> tuple[str, list[tuple[str, str]]]:
    """`(見出しより前, [(見出しの行, 中身), ...])`。行末の空白は見出しから落とす。"""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in body.split("\n"):
        if line.startswith("## "):
            sections.append((line.rstrip(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return "\n".join(preamble), [(h, "\n".join(c).strip()) for h, c in sections]


def is_blank(content: str) -> bool:
    return content.strip() in ("", EMPTY_MARK)


def has_plan(body: str) -> bool:
    """`## やること` に中身があるか（空でも「なし」でもない）。"""
    return not is_blank(dict(_frame_sections(body)[1]).get(PLAN_HEADING, ""))


def changed_frame_sections(old_body: str, new_body: str) -> list[str]:
    """`## 目的・背景`・`## 完了条件` のうち、中身が `old_body` と違う節の見出し。

    行末の空白と連続する空行の数は無視する。`old_body` に節が無いときは比べない。
    """
    old = dict(_frame_sections(old_body)[1])
    new = dict(_frame_sections(new_body)[1])
    return [h for h in FILLED_SECTIONS if h in old and _squeeze(old[h]) != _squeeze(new.get(h, ""))]


def _squeeze(content: str) -> str:
    lines = [line.rstrip() for line in content.split("\n")]
    kept = [line for i, line in enumerate(lines) if line or (i > 0 and lines[i - 1])]
    return "\n".join(kept).strip()


def set_result_section(body: str, content: str) -> str:
    """本文の `## 結果` 節を `content` に置き換える（無ければ末尾に足す。3.3・3.4・5.7）。

    節の並びは固定で `## 結果` は常に最後（3.3）なので、既存の節があれば丸ごと外し、
    改めて末尾に置き直す（順の入れ替えは起きない）。
    """
    content = content.strip("\n")
    body = strip_result_section(body).rstrip("\n")
    prefix = f"{body}\n\n" if body else ""
    return f"{prefix}{RESULT_HEADING}\n\n{content}\n"


def strip_result_section(body: str) -> str:
    """本文から `## 結果` 節を丸ごと外す（無ければそのまま）。"""
    lines = body.split("\n")
    start = next((i for i, l in enumerate(lines) if l == RESULT_HEADING), None)
    if start is None:
        return body
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[:start] + lines[end:])


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
    return {m.group(1) for m in layout.HISTORY_HEADING_PATTERN.finditer(text)}
