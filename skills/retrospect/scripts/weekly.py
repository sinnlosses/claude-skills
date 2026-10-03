#!/usr/bin/env python3
"""横断の振り返り（retrospect の SKILL.md「週ごとに振り返る」）の材料を、数だけで1回に出す。

使い方: weekly.py <リポジトリの根> [--days N]

期間は `--days` が無ければ、最後の記録（`layout.RETROSPECT_RECORD_PATH`）の日付から今日までの日数を
7〜28日に丸めたもの（記録が無ければ7日）。節は `===== <名前> =====` で区切り、行は先頭語で読む:

- **期間**: `PERIOD\t<N>d\t<開始日>\t<終了日>\tlast=<最後の記録の日付|->`
- **根の束ね**: 期間内の札1件につき `TAG\t<札>\t<根|->\t<タスクID|->\t<出どころ>`。承認済みの
  `docs/history/direction.md` の節は振り返りのタスクの完了（台帳の `flow/` の done）が期間内のもの、
  `develop/draft/` のドラフトはファイル名の日付が期間内のもの。同じ根が2件以上なら
  `BUNDLE\t<根>\t<件数>\t<タスクID>`
- **効かなかった手**: 期間内の根のうち、手の完了のあとに期間内でまた出たものだけ
  `RECUR\t<根>\t<手>\t<完了の時刻>\t<期間内の再発件数>`
- **流れの数**: `<名前>\t<今>\t<前>`（`tw metrics --days N` と同じ数）。前より悪くなった数は
  `WORSE\t<名前>\t<今>\t<前>`。`WORSE` があれば、期間内に主ブランチへ入ったやり方の変更
  `CHANGE\t<project|skills>\t<短い SHA>\t<件名>`（プロジェクトは設定ファイル・`.claude/`・`docs/`
  （`docs/history/` を除く）を触ったコミット、skills はこのスクリプトのあるリポジトリ。各20件まで）
- **規則の棚卸し**: 設定ファイルの「## タスク運用」の `- 規則の発火の集計:` の最初の `` `…` `` を
  リポジトリの根で `sh -c` で打った標準出力をそのまま。行が無い・`なし`・落ちた・60秒で終わらない
  ときは `-\t<理由>`

材料が無い節は `EMPTY`（読めたが該当なし）・`MISSING`（ファイルが無い）・`-\t<理由>` を出す。
会話の中身は読まない（読むのは履歴・ドラフト・台帳・コミットの件名だけ）。

**データの不備で traceback を出さない。**
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_TASK_WORKFLOW_SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "..", "task-workflow", "scripts"))
if _TASK_WORKFLOW_SCRIPTS not in sys.path:
    sys.path.insert(0, _TASK_WORKFLOW_SCRIPTS)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cross_review  # noqa: E402
import layout  # noqa: E402
import ledger  # noqa: E402
import metrics  # noqa: E402
import tally  # noqa: E402

MIN_DAYS = 7
MAX_DAYS = 28
HOOK_TALLY_KEY = "規則の発火の集計"
HOOK_TALLY_TIMEOUT_SECONDS = 60
CHANGE_LIMIT = 20
PROJECT_CHANGE_PATHS = ("CLAUDE.md", "AGENTS.md", ".claude", "docs", ":(exclude)docs/history")
DRAFT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-.*\.md$")


@dataclass(frozen=True)
class Drafted:
    section: tally.Section
    at: datetime | None
    source: str


def main() -> None:
    root, days_arg = parse_args(sys.argv[1:])
    last = cross_review.last_date(root)
    days = days_arg if days_arg is not None else period_days(last)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    section("期間")
    today = date.today()
    print(f"PERIOD\t{days}d\t{(today - timedelta(days=days)).isoformat()}\t{today.isoformat()}\tlast={last.isoformat() if last else '-'}")

    done = tally.done_times(root)
    history = read_history(root)
    drafted = history_in_period(history, done, start) + read_drafts(root, done, start)

    section("根の束ね")
    print_bundles(history, drafted)

    section("効かなかった手")
    print_recurrences(history, drafted, done)

    section("流れの数")
    if print_flow(root, days):
        print_changes(root, start)

    section("規則の棚卸し")
    print_hook_tally(root)


def parse_args(argv: list[str]) -> tuple[str, int | None]:
    if not argv:
        print("USAGE\tweekly.py <root> [--days N]", file=sys.stderr)
        raise SystemExit(2)
    root, rest = argv[0], argv[1:]
    if not rest:
        return root, None
    if rest[0] != "--days" or len(rest) != 2 or not rest[1].isdigit() or int(rest[1]) < 1:
        print("USAGE\tweekly.py <root> [--days N]（N は1以上）", file=sys.stderr)
        raise SystemExit(2)
    return root, int(rest[1])


def period_days(last: date | None) -> int:
    if last is None:
        return MIN_DAYS
    return min(MAX_DAYS, max(MIN_DAYS, (date.today() - last).days))


def read_history(root: str) -> list[tally.Section] | None:
    path = os.path.join(root, tally.DIRECTION_HISTORY_PATH)
    try:
        with open(path, encoding="utf-8") as f:
            return tally.parse_sections(f.read())
    except (OSError, UnicodeDecodeError):
        return None


def history_in_period(history: list[tally.Section] | None, done: dict[str, datetime], start: datetime) -> list[Drafted]:
    found: list[Drafted] = []
    for s in history or []:
        at = _drafted_at(s, done)
        if not s.cross and s.tags and at is not None and at >= start:
            found.append(Drafted(s, at, tally.DIRECTION_HISTORY_PATH))
    return found


def read_drafts(root: str, done: dict[str, datetime], start: datetime) -> list[Drafted]:
    draft_dir = os.path.join(root, layout.DRAFT_DIR)
    try:
        names = sorted(os.listdir(draft_dir))
    except OSError:
        return []
    found: list[Drafted] = []
    for name in names:
        m = DRAFT_NAME.match(name)
        if m is None:
            continue
        try:
            written = datetime.combine(date.fromisoformat(m.group(1)), time(), timezone.utc)
            with open(os.path.join(draft_dir, name), encoding="utf-8") as f:
                sections = tally.parse_sections(f.read())
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        if written < start.replace(hour=0, minute=0, second=0, microsecond=0):
            continue
        for s in sections:
            if not s.cross and s.tags:
                found.append(Drafted(s, _drafted_at(s, done) or written, f"{layout.DRAFT_DIR}/{name}"))
    return found


def print_bundles(history: list[tally.Section] | None, drafted: list[Drafted]) -> None:
    if history is None:
        print(f"-\t{tally.DIRECTION_HISTORY_PATH} が無い（承認済みの札は読まない）")
    if not drafted:
        print("EMPTY")
        return
    by_root: dict[str, list[str]] = defaultdict(list)
    for d in drafted:
        tasks = ",".join(d.section.reviewed) or "-"
        for tag in d.section.tags:
            print(f"TAG\t{tag}\t{','.join(d.section.roots) or '-'}\t{tasks}\t{d.source}")
        for root in d.section.roots:
            by_root[root].append(tasks)
    for root in sorted(by_root, key=lambda k: (-len(by_root[k]), k)):
        if len(by_root[root]) >= 2:
            print(f"BUNDLE\t{root}\t{len(by_root[root])}\t{','.join(by_root[root])}")


def print_recurrences(history: list[tally.Section] | None, drafted: list[Drafted], done: dict[str, datetime]) -> None:
    if history is None:
        print("MISSING")
        return
    sections = history + [d.section for d in drafted if d.source != tally.DIRECTION_HISTORY_PATH]
    roots = sorted({root for d in drafted for root in d.section.roots})
    printed = False
    for root in roots:
        for hand, finished, _ in tally.effect(sections, root, done):
            if finished is None:
                continue
            recurred = sum(1 for d in drafted if root in d.section.roots and d.at is not None and d.at > finished)
            if recurred:
                print(f"RECUR\t{root}\t{','.join(hand)}\t{finished.isoformat()}\t{recurred}")
                printed = True
    if not printed:
        print("EMPTY")


def print_flow(root: str, days: int) -> bool:
    """数を出し、悪くなった数があれば True。"""
    try:
        events, _ = metrics.read_events(ledger.ledger_root(cwd=root))
    except (ledger.GitCommandError, OSError):
        print("-\t台帳が読めない（git のリポジトリでない）")
        return False
    if not events:
        print("EMPTY")
        return False
    current, previous = metrics.columns(events, days)
    for name, value in current.items():
        print(f"{name}\t{value}\t{previous[name]}")
    worse = [name for name in current if metrics.worse(name, current[name], previous[name])]
    for name in worse:
        print(f"WORSE\t{name}\t{current[name]}\t{previous[name]}")
    return bool(worse)


def print_changes(root: str, start: datetime) -> None:
    since = f"--since={start.isoformat()}"
    try:
        base = ledger.base_branch(root)
    except (ledger.GitCommandError, ledger.NoBaseBranch):
        base = "HEAD"
    project = _git_lines(root, "log", since, f"-n{CHANGE_LIMIT}", "--format=%h%x09%s", base, "--", *PROJECT_CHANGE_PATHS)
    for line in project:
        print(f"CHANGE\tproject\t{line}")
    skills_top = _git_lines(HERE, "rev-parse", "--show-toplevel")
    project_top = _git_lines(root, "rev-parse", "--show-toplevel")
    if skills_top and skills_top != project_top:
        for line in _git_lines(HERE, "log", since, f"-n{CHANGE_LIMIT}", "--format=%h%x09%s", "HEAD"):
            print(f"CHANGE\tskills\t{line}")


def print_hook_tally(root: str) -> None:
    try:
        value = layout.read_setting_value(root, HOOK_TALLY_KEY)
    except (layout.ConfigConflict, OSError, UnicodeDecodeError) as e:
        print(f"-\t設定ファイルが読めない（{e}）")
        return
    if value is None or value.startswith("なし"):
        print(f"-\t「{layout.TASK_SECTION_HEADING}」に「- {HOOK_TALLY_KEY}:」の行が無い（この観点は飛ばす）")
        return
    m = re.search(r"`([^`]+)`", value)
    if m is None:
        print(f"-\t「- {HOOK_TALLY_KEY}:」の値に `…` で囲んだコマンドが無い")
        return
    try:
        r = subprocess.run(
            ["sh", "-c", m.group(1)], cwd=root, capture_output=True, text=True, timeout=HOOK_TALLY_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        print(f"-\t{HOOK_TALLY_TIMEOUT_SECONDS}秒で打ち切った")
        return
    except OSError as e:
        print(f"-\t打てない（{e}）")
        return
    if r.returncode != 0:
        print(f"-\t終了コード {r.returncode}")
        return
    print(r.stdout.rstrip() or "EMPTY")


def section(title: str) -> None:
    print()
    print(f"===== {title} =====")


def _drafted_at(s: tally.Section, done: dict[str, datetime]) -> datetime | None:
    known = [done[t] for t in s.reviewed if t in done]
    return max(known) if known else None


def _git_lines(cwd: str, *args: str) -> list[str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except OSError:
        return []
    return r.stdout.splitlines() if r.returncode == 0 else []


if __name__ == "__main__":
    main()
