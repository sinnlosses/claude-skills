#!/usr/bin/env python3
"""承認済みの振り返りの札を `docs/history/direction.md` から数える。

使い方: tally.py <リポジトリの根> [札]

読むのは `docs/history/direction.md` だけ。`develop/draft/` の未承認のドラフトは数えない
（承認されると見出しごと中身がここへ移るので、ここを数えれば承認済みの回数がそのまま出る。
retrospect の SKILL.md「札と1行の書式」）。

数えるのは見出し `### ...（振り返り: T-xxx, T-yyy）` に続く `- 札: 赤 <札>` / `- 札: 黄 <札>`
の2トークンの行だけ。色を伴わない1トークンの `- 札: <札>` は今の書式になる前（T-779 より前）の
記述なので数えない。見出しの `（振り返り: ...）` に無いタスクIDは拾わない。

札を1つ指定すると、その札だけの件数とタスクIDを1行で返す（次のドラフトで「何回目か」を
決めるときに使う。件数 + 1 が次に積む回）。指定が無ければ見つかった札を全部、件数の多い順に
一覧する。

**データの不備で traceback を出さない。** ファイルが無ければ `MISSING`、該当する行が
1つも無ければ `EMPTY` を返す。
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

HEADING = re.compile(r"^### .*（振り返り:\s*([^）]+)）\s*$")
TAG_LINE = re.compile(r"^- 札: (?:赤|黄) (.+)$")

DIRECTION_HISTORY_PATH = os.path.join("docs", "history", "direction.md")


def parse(text: str) -> list[tuple[str, list[str]]]:
    """`(札, その見出しのタスクID一覧)` を、出た順に1件ずつ返す。"""
    rows: list[tuple[str, list[str]]] = []
    current_tasks: list[str] = []
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            current_tasks = [t.strip() for t in heading.group(1).split(",") if t.strip()]
            continue
        tag_line = TAG_LINE.match(line)
        if tag_line:
            rows.append((tag_line.group(1).strip(), current_tasks))
    return rows


def tally(rows: list[tuple[str, list[str]]]) -> dict[str, list[list[str]]]:
    """札ごとに、出現1回につき1つのタスクID一覧を集める（件数 = 一覧の長さ）。"""
    occurrences: dict[str, list[list[str]]] = defaultdict(list)
    for tag, tasks in rows:
        occurrences[tag].append(tasks)
    return occurrences


def format_row(tag: str, groups: list[list[str]]) -> str:
    tasks = [t for group in groups for t in group]
    return f"{tag}\t{len(groups)}\t{','.join(tasks) if tasks else '-'}"


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("USAGE\ttally.py <root> [札]", file=sys.stderr)
        raise SystemExit(2)
    root = args[0]
    only = args[1] if len(args) > 1 else None

    path = os.path.join(root, DIRECTION_HISTORY_PATH)
    if not os.path.exists(path):
        print("MISSING")
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()

    occurrences = tally(parse(text))

    if only is not None:
        print(format_row(only, occurrences.get(only, [])))
        return

    if not occurrences:
        print("EMPTY")
        return

    for tag in sorted(occurrences, key=lambda t: (-len(occurrences[t]), t)):
        print(format_row(tag, occurrences[tag]))


if __name__ == "__main__":
    main()
