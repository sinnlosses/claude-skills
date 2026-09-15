"""tasks.json と progress.md の読み取りと、アーカイブ対象の判定。

`status.py`（判定を表示するだけ）と `archive.py`（実際に移す）の両方が使う。
**判定をこの1か所に置くのが目的**で、2つに分かれていると片方だけがズレたとき
「トリガーは鳴るのに移せるものが無い」状態になる（正典が `todo` の件で警告している
失敗と同じ形）。
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

DEFAULTS = {
    "doneCount": 10,
    "doneBytes": 30720,
    "progressCount": 5,
    "progressBytes": 8192,
}
DEFAULT_HISTORY_DIR = "docs/history"

# 「## 完了したこと（このセッション）」のように後ろに補足が付いた表記が実在するので前方一致で拾う。
DONE_SECTION = "## 完了したこと"
DATE_HEADING = re.compile(r"^### (\d{4}-\d{2}-\d{2})\b")


# 一覧テーブルの `内容` 列に許す表示幅。全角を2桁として数える。
# 他の列（ID・状態）と罫線を足して80桁の端末に収まる値。
SUMMARY_WIDTH = 44

# 正典「summary」の「1行に収める」に反していると見なす幅。**切り詰めの幅とは別物**。
# 切り詰めは表示の都合で常に起きるので、同じ閾値で警告を出すと実データの9割に火が点いて
# signal にならない（実測: 44桁超が52件中49件、80桁超は14件）。
# 80桁は「その一行だけで端末が折り返す」長さで、正典の言う「折り返しが必要な長さ」に当たる。
LONG_SUMMARY_WIDTH = 80


def display_width(s: str) -> int:
    """端末に出したときの桁数。日本語（East Asian Wide/Fullwidth）は2桁。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def ellipsize(s: str, limit: int = SUMMARY_WIDTH) -> str:
    """表示幅で切り詰めて `…` を付ける。収まっていればそのまま返す。

    モデルに桁数を数えさせない（全角混じりの幅は取り違えやすく、取り違えると
    テーブルが端末幅を超えて折り返し、表として読めなくなる）ためにここで行う。
    """
    if display_width(s) <= limit:
        return s
    out = ""
    for c in s:
        if display_width(out) + display_width(c) > limit - 1:
            break
        out += c
    return out + "…"


def load_config(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    return loaded if isinstance(loaded, dict) else {}


def limits(config: dict) -> dict:
    archive = config.get("archive")
    archive = archive if isinstance(archive, dict) else {}
    return {k: int(archive.get(k, v)) for k, v in DEFAULTS.items()}


def history_dir(config: dict) -> str:
    return config.get("historyDir", DEFAULT_HISTORY_DIR)


def progress_path_for(tasks_path: str) -> str:
    """progress.md の置き場は規約で固定（tasks.json と同じディレクトリ）。"""
    return os.path.join(os.path.dirname(tasks_path) or ".", "progress.md")


# --- tasks.json ---------------------------------------------------------


def done_plan(tasks: list[dict], count_limit: int, bytes_limit: int) -> tuple[list[dict], int, bool]:
    """アーカイブする `done` タスクと、そのサイズ、トリガーに該当するかを返す。

    `todo` は数えない（移す先が無いものを数えると、鳴るだけで何も起きないトリガーになる）。
    """
    done = [t for t in tasks if t.get("status") == "done"]
    size = len(json.dumps(done, ensure_ascii=False))
    return done, size, (len(done) >= count_limit or size > bytes_limit)


# --- progress.md --------------------------------------------------------


class Section:
    """「完了したこと」配下の `### 〜` 小節1つ。"""

    def __init__(self, date: str | None, text: str) -> None:
        self.date = date
        self.text = text

    def __len__(self) -> int:
        return len(self.text)


def split_done_section(text: str) -> tuple[str, list[Section] | None, str]:
    """「完了したこと」節を (前, 小節リスト, 後) に割る。節が無ければ小節リストは None。"""
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith(DONE_SECTION)), None)
    if start is None:
        return text, None, ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))

    bodies: list[tuple[str | None, list[str]]] = []
    head_end = end
    for i in range(start + 1, end):
        if lines[i].startswith("### "):
            head_end = min(head_end, i)
            m = DATE_HEADING.match(lines[i])
            bodies.append((m.group(1) if m else None, [lines[i]]))
        elif bodies:
            bodies[-1][1].append(lines[i])

    sections = [Section(d, "".join(b)) for d, b in bodies]
    return "".join(lines[:head_end]), sections, "".join(lines[end:])


def split_named_section(text: str, heading: str) -> tuple[str, str, str]:
    """`## <heading>` の節を (前, その節, 後) に割る。無ければ真ん中が空文字。"""
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith(heading)), None)
    if start is None:
        return text, "", ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "".join(lines[:start]), "".join(lines[start:end]), "".join(lines[end:])


def is_newest_first(sections: list[Section]) -> bool:
    """日付つきの小節が、新しい順（非増加）に並んでいるか。

    正典は「新しい小節を上に積む」と決めている。逆順のファイルにアーカイブをかけると
    **新しいほうを捨てる**ので、その場合は移さずに止めるための検査。
    """
    dates = [s.date for s in sections if s.date is not None]
    return all(a >= b for a, b in zip(dates, dates[1:]))


def progress_plan(
    sections: list[Section], count_limit: int, bytes_limit: int
) -> tuple[list[Section], list[Section]]:
    """新しい順に count_limit 件、かつ bytes_limit 以内を残し、残りを移す。

    セッションの識別は諦めて予算で切る。「このセッション分だけ残す」はファイルから
    機械的に決められない（新しいセッションは、上の小節を誰が書いたか判別できないし、
    `/loop` の1セッションは何小節も書く）。
    """
    keep: list[Section] = []
    size = 0
    for s in sections:
        if len(keep) >= count_limit:
            break
        if keep and size + len(s) > bytes_limit:
            break
        keep.append(s)
        size += len(s)
    return keep, sections[len(keep) :]
