#!/usr/bin/env python3
"""承認済みの振り返りの札と根を `docs/history/direction.md` から数え、根に打った手の効き目を出す。

使い方:
  tally.py <リポジトリの根> [札]
  tally.py <リポジトリの根> --roots
  tally.py <リポジトリの根> --effect [根]

読むのは `docs/history/direction.md` だけ。`develop/draft/` の未承認のドラフトは数えない
（承認されると見出しごと中身がここへ移るので、ここを数えれば承認済みの回数がそのまま出る。
retrospect の SKILL.md「札と1行の書式」）。

見出し（深さは問わない）から次の見出しまでを1節として読む。節の振り返りのタスクIDは、見出しの
`（振り返り: T-xxx, T-yyy）`、無ければ節の中で最初に出た `（振り返り: ...）` から取る。

札として数えるのは `- 札: 赤 <札>` / `- 札: 黄 <札>` の2トークンの行だけ。後ろの `（N回目）` は札に
含めない。色を伴わない1トークンの `- 札: <札>` は今の書式になる前（T-779 より前）の記述なので数えない。
札を1つ指定すると、その札だけの件数とタスクIDを1行で返す（件数 + 1 が次に積む回）。指定が無ければ
見つかった札を全部、件数の多い順に一覧する。

根は `- 根: <キー>`（英小文字・数字・ハイフン）の行。キーの形でない行と、根の行の無い節は根に数えない。
`--roots` は根ごとの件数とタスクIDを、件数の多い順に `<根>\t<件数>\t<タスクID>` で出す。
見出しに `（横断の振り返り:` を持つ節は、札も根も件数に数えない（同じ引っかかりは1件ごとの節で
数え済み）。その節の手だけを、根の手として拾う。

手は、節の中の `（` で始まる行で `にした` の直前に並んだタスクID（`・`・`、`・`,` の区切りと
`GH-n〜GH-m` の範囲）。完了の時刻は台帳の `flow/` の `done`（`dropped` でないもの）の記録から取り、
並んだタスクが全部完了したときの遅いほうを手の完了とする。ドラフトの時刻は、その節の振り返りの
タスクの完了の遅いほう（振り返りは `tw done` の直前に積む）。時刻が取れないものは再発に数えない。
`--effect` は手1つにつき `<根>\t<手>\t<完了時刻>\t<再発件数>`（手の無い根は `<根>\t-\t-\t-`、
未完了の手は時刻と件数が `-`）。`--effect <根>` は、その根で今ドラフトを積むと再発に当たるかを
先頭語で返す: `RECUR`（完了した手がある）・`PENDING`（手はあるが未完了）・`NO_HAND`（手が無い）。

**データの不備で traceback を出さない。** ファイルが無ければ `MISSING`、該当する行が
1つも無ければ `EMPTY` を返す。git のリポジトリでない・台帳の記録が無いときは完了の時刻を `-` にする。
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

_TASK_WORKFLOW_SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "task-workflow", "scripts")
)
if _TASK_WORKFLOW_SCRIPTS not in sys.path:
    sys.path.insert(0, _TASK_WORKFLOW_SCRIPTS)

import ledger  # noqa: E402
import metrics  # noqa: E402

HEADING = re.compile(r"^#{1,6} ")
REVIEWED = re.compile(r"（振り返り:\s*([^）]+)）")
CROSS = re.compile(r"（横断の振り返り:")
TAG_LINE = re.compile(r"^- 札: (?:赤|黄) (.+?)(?:（\d+回目）)?\s*$")
ROOT_LINE = re.compile(r"^- 根: ([a-z0-9]+(?:-[a-z0-9]+)*)\s*$")
TASK_ID = r"(?:GH|T)-\d+"
HAND = re.compile(rf"({TASK_ID}(?:\s*[・、,〜]\s*{TASK_ID})*)\s*にした")
RANGE = re.compile(r"^((?:GH|T)-)(\d+)〜\1(\d+)$")

DIRECTION_HISTORY_PATH = os.path.join("docs", "history", "direction.md")


@dataclass(frozen=True)
class Section:
    reviewed: tuple[str, ...]
    tags: tuple[str, ...]
    roots: tuple[str, ...]
    hand: tuple[str, ...]
    cross: bool


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("USAGE\ttally.py <root> [札 | --roots | --effect [根]]", file=sys.stderr)
        raise SystemExit(2)
    root = args[0]
    rest = args[1:]

    path = os.path.join(root, DIRECTION_HISTORY_PATH)
    if not os.path.exists(path):
        print("MISSING")
        return
    with open(path, encoding="utf-8") as f:
        sections = parse_sections(f.read())

    if rest[:1] == ["--roots"]:
        print_rows(roots(sections))
        return
    if rest[:1] == ["--effect"]:
        done = done_times(root)
        if len(rest) > 1:
            print(verdict(sections, rest[1], done))
        else:
            print_effect(sections, done)
        return

    occurrences = tally(tag_rows(sections))
    if rest:
        print(format_row(rest[0], occurrences.get(rest[0], [])))
        return
    print_rows(occurrences)


def parse(text: str) -> list[tuple[str, list[str]]]:
    """`(札, その節の振り返りのタスクID一覧)` を、出た順に1件ずつ返す。"""
    return tag_rows(parse_sections(text))


def parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    lines: list[str] = []
    for line in text.splitlines():
        if HEADING.match(line) and lines:
            sections.append(_section(lines))
            lines = []
        lines.append(line)
    if lines:
        sections.append(_section(lines))
    return sections


def tag_rows(sections: list[Section]) -> list[tuple[str, list[str]]]:
    return [(tag, list(s.reviewed)) for s in sections if not s.cross for tag in s.tags]


def tally(rows: list[tuple[str, list[str]]]) -> dict[str, list[list[str]]]:
    """札ごとに、出現1回につき1つのタスクID一覧を集める（件数 = 一覧の長さ）。"""
    occurrences: dict[str, list[list[str]]] = defaultdict(list)
    for tag, tasks in rows:
        occurrences[tag].append(tasks)
    return occurrences


def roots(sections: list[Section]) -> dict[str, list[list[str]]]:
    """根ごとに、出現1回につき1つのタスクID一覧を集める（件数 = 一覧の長さ）。"""
    occurrences: dict[str, list[list[str]]] = defaultdict(list)
    for s in sections:
        if s.cross:
            continue
        for root in s.roots:
            occurrences[root].append(list(s.reviewed))
    return occurrences


def effect(sections: list[Section], root: str, done: dict[str, datetime]) -> list[tuple[tuple[str, ...], datetime | None, int | None]]:
    """根に打った手ごとに `(手, 完了の時刻, 完了のあとに同じ根が出た件数)`。未完了なら時刻と件数は None。"""
    same_root = [s for s in sections if root in s.roots]
    hands: list[tuple[str, ...]] = []
    for s in same_root:
        if s.hand and s.hand not in hands:
            hands.append(s.hand)
    results: list[tuple[tuple[str, ...], datetime | None, int | None]] = []
    for hand in hands:
        finished = _latest(done, hand, require_all=True)
        if finished is None:
            results.append((hand, None, None))
            continue
        recurred = 0
        for s in same_root:
            drafted = _latest(done, s.reviewed, require_all=False)
            if drafted is not None and drafted > finished:
                recurred += 1
        results.append((hand, finished, recurred))
    return results


def verdict(sections: list[Section], root: str, done: dict[str, datetime]) -> str:
    results = effect(sections, root, done)
    finished = [hand for hand, at, _ in results if at is not None]
    if finished:
        return f"RECUR\t{root}\t{_join(t for hand in finished for t in hand)}"
    if results:
        return f"PENDING\t{root}\t{_join(t for hand, _, _ in results for t in hand)}"
    return f"NO_HAND\t{root}\t-"


def done_times(repo_root: str) -> dict[str, datetime]:
    """台帳の `flow/` の `done`（`dropped` でないもの）の、タスクごとの最後の時刻。"""
    try:
        events, _ = metrics.read_events(ledger.ledger_root(repo_root))
    except (ledger.GitCommandError, OSError):
        return {}
    times: dict[str, datetime] = {}
    for e in events:
        if e.kind == "done" and e.fields.get("dropped") is False:
            times[e.task] = e.at
    return times


def format_row(tag: str, groups: list[list[str]]) -> str:
    tasks = [t for group in groups for t in group]
    return f"{tag}\t{len(groups)}\t{','.join(tasks) if tasks else '-'}"


def print_rows(occurrences: dict[str, list[list[str]]]) -> None:
    if not occurrences:
        print("EMPTY")
        return
    for key in sorted(occurrences, key=lambda k: (-len(occurrences[k]), k)):
        print(format_row(key, occurrences[key]))


def print_effect(sections: list[Section], done: dict[str, datetime]) -> None:
    occurrences = roots(sections)
    if not occurrences:
        print("EMPTY")
        return
    for root in sorted(occurrences, key=lambda k: (-len(occurrences[k]), k)):
        results = effect(sections, root, done)
        if not results:
            print(f"{root}\t-\t-\t-")
        for hand, at, recurred in results:
            print(f"{root}\t{_join(hand)}\t{at.isoformat() if at else '-'}\t{'-' if recurred is None else recurred}")


def _section(lines: list[str]) -> Section:
    reviewed: tuple[str, ...] = ()
    for line in lines:
        m = REVIEWED.search(line)
        if m:
            reviewed = tuple(t.strip() for t in m.group(1).split(",") if t.strip())
            break
    tags = tuple(m.group(1).strip() for m in map(TAG_LINE.match, lines) if m)
    roots_ = tuple(m.group(1) for m in map(ROOT_LINE.match, lines) if m)
    hand: list[str] = []
    for line in lines:
        if not line.startswith("（"):
            continue
        for m in HAND.finditer(line):
            for t in _expand(m.group(1)):
                if t not in hand:
                    hand.append(t)
    cross = bool(HEADING.match(lines[0]) and CROSS.search(lines[0]))
    return Section(reviewed, tags, roots_, tuple(hand), cross)


def _expand(listed: str) -> list[str]:
    """`GH-1・GH-3〜GH-5` を `[GH-1, GH-3, GH-4, GH-5]` にする。"""
    ids: list[str] = []
    for piece in re.split(r"\s*[・、,]\s*", listed):
        piece = re.sub(r"\s*〜\s*", "〜", piece)
        r = RANGE.match(piece)
        if r is None:
            ids.extend(re.findall(TASK_ID, piece))
            continue
        prefix, start, end = r.group(1), r.group(2), r.group(3)
        ids.extend(f"{prefix}{str(n).zfill(len(start))}" for n in range(int(start), int(end) + 1))
    return ids


def _latest(done: dict[str, datetime], tasks: tuple[str, ...], require_all: bool) -> datetime | None:
    known = [done[t] for t in tasks if t in done]
    if not known or (require_all and len(known) < len(tasks)):
        return None
    return max(known)


def _join(tasks: Iterable[str]) -> str:
    listed = list(tasks)
    return ",".join(listed) if listed else "-"


if __name__ == "__main__":
    main()
