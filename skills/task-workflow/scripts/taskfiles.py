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

# アーカイブの予算と置き場は**規約で固定**する（プロジェクトごとの設定にしない）。
# 設定できるようにしてあった `develop/workflow.json` を実測したところ、3プロジェクトとも
# ここは1つも書いておらず、書かれていたのは検証コマンドと整形コマンドだけだった。
# その2つは CLAUDE.md にも同じ内容が書かれていて正典が二重になっていたので、
# CLAUDE.md の「## タスク運用」節に一本化した（正典「ファイル配置と CLAUDE.md」）。
# サイズは**文字数**で測る（`len`）。バイト数ではないのは、減らしたいのがディスク使用量では
# なくコンテキスト消費だから。日本語主体のタスク本文では実バイト数は約3倍になるので、
# 出力のラベルも「文字」で統一してある（`B` と書くと3倍ズレて読まれる）。
#
# `progress*` だけ「点火する閾値」と「残す量」が別の値になっている。同じ値にすると移した直後が
# ちょうど閾値で、次のサイクルで小節が1件増えただけでまた点く（`progress_plan` の docstring）。
# `done*` は閾値だけで足りる——移すときは**全件**なので、移した直後は0件になり、次に点くまで
# 5件ぶんの間隔が自然に空く。
LIMITS = {
    "doneCount": 5,
    "doneChars": 15000,
    "progressCount": 10,
    "progressChars": 16384,
    "progressKeepCount": 5,
    "progressKeepChars": 8192,
}
HISTORY_DIR = "docs/history"

# 「## 完了したこと（このセッション）」のように後ろに補足が付いた表記が実在するので前方一致で拾う。
DONE_SECTION = "## 完了したこと"
DATE_HEADING = re.compile(r"^### (\d{4}-\d{2}-\d{2})\b")


# 正典「summary」の「1行に収める」に反していると見なす幅。
# 80桁は「その一行だけで端末が折り返す」長さで、正典の言う「折り返しが必要な長さ」に当たる。
# （実測: 52件中14件が該当。ここを狭めると実データの9割に火が点いて signal にならない）
LONG_SUMMARY_WIDTH = 80


def display_width(s: str) -> int:
    """端末に出したときの桁数。日本語（East Asian Wide/Fullwidth）は2桁。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def progress_path_for(tasks_path: str) -> str:
    """progress.md の置き場は規約で固定（tasks.json と同じディレクトリ）。"""
    return os.path.join(os.path.dirname(tasks_path) or ".", "progress.md")


# --- tasks.json ---------------------------------------------------------


def load_tasks(path: str) -> tuple[list[dict], str | None]:
    """tasks.json を読む。読めなければ `(空リスト, 理由)` を返す（例外を投げない）。

    呼び出し側のスキルは「想定外の出力＝`python3` が使えない」と読む規約なので、
    データの不備で traceback を出すと環境の故障として報告されてしまう。理由を文字列で
    返して、呼び出し側が `INVALID` として扱えるようにする。
    """
    try:
        with open(path, encoding="utf-8") as f:
            tasks = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [], f"JSONとして読めない（{e}）"
    except OSError as e:
        return [], f"読めない（{e}）"
    if not isinstance(tasks, list):
        return [], f"配列ではない（{type(tasks).__name__}）"
    bad = [i for i, t in enumerate(tasks) if not isinstance(t, dict)]
    if bad:
        return [], f"配列の要素がオブジェクトではない（{len(bad)}件: index {bad[:5]}）"
    return tasks, None


def done_plan(tasks: list[dict], count_limit: int, chars_limit: int) -> tuple[list[dict], int, bool]:
    """アーカイブする `done` タスクと、その文字数、トリガーに該当するかを返す。

    `todo` は数えない（移す先が無いものを数えると、鳴るだけで何も起きないトリガーになる）。
    """
    done = [t for t in tasks if t.get("status") == "done"]
    size = len(json.dumps(done, ensure_ascii=False))
    return done, size, (len(done) >= count_limit or size > chars_limit)


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
    sections: list[Section],
    count_limit: int,
    chars_limit: int,
    keep_count: int,
    keep_chars: int,
) -> tuple[list[Section], list[Section]]:
    """点火したときだけ、新しい順に keep_count 件・keep_chars 文字ぶんを残して残りを移す。

    **点火する閾値（count_limit / chars_limit）と残す量（keep_count / keep_chars）を離す。**
    同じ値にすると移した直後がちょうど閾値なので、次のサイクルで小節が1件増えるだけでまた点き、
    毎サイクル1小節だけを移す振動になる（実測: 23コミット中6件がアーカイブ専用のコミットで、
    うち3件は小節1件を移しただけの `+4/-4` だった）。

    **点火した物差しがどちらでも、残す量は件数と文字数の両方で切る。** 点いたほうだけを
    戻すと、もう片方が閾値の際に残ったままになり、結局その片方が翌サイクルに鳴る。

    セッションの識別は諦めて予算で切る。「このセッション分だけ残す」はファイルから
    機械的に決められない（新しいセッションは、上の小節を誰が書いたか判別できないし、
    `/loop` の1セッションは何小節も書く）。
    """
    if len(sections) <= count_limit and sum(len(s) for s in sections) <= chars_limit:
        return sections, []

    keep: list[Section] = []
    size = 0
    for s in sections:
        if len(keep) >= keep_count:
            break
        if keep and size + len(s) > keep_chars:
            break
        keep.append(s)
        size += len(s)
    return keep, sections[len(keep) :]
