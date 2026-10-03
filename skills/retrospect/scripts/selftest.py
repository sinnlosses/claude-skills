#!/usr/bin/env python3
"""`tally.py`（`docs/history/direction.md` から札を数える）の自己テスト。

使い方: python3 selftest.py

標準ライブラリだけで動く。落ちたら非0で終わる。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tally  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def run(*args: str) -> subprocess.CompletedProcess:
    root = args[0]
    return subprocess.run(
        [sys.executable, os.path.join(HERE, "tally.py"), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": os.path.dirname(os.path.realpath(root))},
    )


def done_row(at: str, task: str, dropped: bool = False) -> str:
    return json.dumps({"t": at, "event": "done", "task": task, "difficulty": "opus", "dropped": dropped, "reflection": "none"}) + "\n"


def write(path: str, body: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


# SKILL.md「1件だけ振り返る」の「ドラフトに積む」の雛形をそのまま写したもの（角括弧の穴だけ実物に差し替える）。
DRAFT_ITEM_TEMPLATE = """# 検証コマンドが不安定（振り返り: T-302, T-318）

- 札: 黄 揺れ（3回目）
- 根: flaky-check
- 根拠: pnpm run check を2回打ち直して通った
- 出し先: docs/coding-standards.md「テスト」節
"""


def test_parse_and_tally() -> None:
    print("tally.parse / tally.tally")
    text = (
        "### 見出しA（振り返り: T-100, T-200）\n\n"
        "- 札: 黄 揺れ\n"
        "- 根拠: ...\n"
        "- 出し先: ...\n\n"
        "### 見出しB（振り返り: T-300）\n\n"
        "- 札: 赤 制約違反\n"
        "- 根拠: ...\n\n"
        "### 見出しC（振り返り: T-400）\n\n"
        "- 札: 黄 揺れ\n"
        "- 根拠: ...\n\n"
        "### 旧い見出し（T-050 の記録）\n\n"
        "- 札: 揺れ\n"
    )
    rows = tally.parse(text)
    check(
        "2トークンの行だけ拾う（旧い1トークンの行は落とす）",
        len(rows) == 3,
        str(rows),
    )
    occ = tally.tally(rows)
    check("同じ札は複数回に分けて数える", len(occ["揺れ"]) == 2, str(occ))
    check("見出しのタスクIDがそのまま付く", occ["揺れ"][0] == ["T-100", "T-200"], str(occ))
    rows = tally.parse(
        "# 見出しD（振り返り: T-500）\n\n- 札: 黄 揺れ（2回目）\n\n"
        "## 見出しE（振り返り: T-600）\n\n- 札: 赤 制約違反（1回目）\n"
    )
    check("見出しの深さを問わず、後ろの（N回目）は札に含めない", rows == [("揺れ", ["T-500"]), ("制約違反", ["T-600"])], str(rows))
    check("1トークンの旧い記述は数えない", "揺れ" in occ and len(occ["揺れ"]) == 2 and "T-050" not in [t for g in occ["揺れ"] for t in g], str(occ))
    rows = tally.parse(DRAFT_ITEM_TEMPLATE)
    check("SKILL.md の雛形をそのまま写した入力を読める", rows == [("揺れ", ["T-302", "T-318"])], str(rows))
    rows = tally.parse(
        "## 見出しF（振り返り: T-700）\n\n- 札: 黄 揺れ（1回目）\n\n"
        "## 見出しG\n\n- 出典: ドラフト「…（振り返り: T-800）」\n- 札: 黄 道具（1回目）\n\n"
        "## 見出しH\n\n- 札: 黄 道具（2回目）\n"
    )
    check(
        "（振り返り:）の無い見出しは節の中の（振り返り:）から取り、直前の見出しのタスクIDを引き継がない",
        rows == [("揺れ", ["T-700"]), ("道具", ["T-800"]), ("道具", [])],
        str(rows),
    )


HISTORY = (
    "# 指示の履歴\n\n"
    + DRAFT_ITEM_TEMPLATE.replace("\n\n", "\n\n（GH-60 にした）\n\n", 1)
    + "\n## 2026-10-03 範囲で束ねた手（振り返り: GH-11）\n\n（GH-50〜GH-52 にした）\n\n- 札: 黄 道具（1回目）\n- 根: slow-capture\n\n"
    "## 2026-10-02 検証を安定させる（振り返り: GH-10）\n\n（GH-20・GH-21 にした）\n\n"
    "- 札: 黄 揺れ（2回目）\n- 根: flaky-check\n- 根拠: …\n- 出し先: …\n\n"
    "## 2026-10-02 手がまだ無い（振り返り: GH-12）\n\n- 札: 黄 道具（2回目）\n- 根: no-hand-yet\n\n"
    "## 2026-10-01 根の無い古い行（振り返り: GH-5）\n\n- 札: 黄 揺れ（1回目）\n- 根: Not A Key\n"
)


def test_roots_and_effect() -> None:
    print("tally.py --roots / --effect")
    sections = tally.parse_sections(HISTORY)
    check(
        "雛形をそのまま写した節から根と「にした」の手を拾う",
        sections[1].roots == ("flaky-check",) and sections[1].hand == ("GH-60",) and sections[1].reviewed == ("T-302", "T-318"),
        str(sections[1]),
    )
    check("「GH-n〜GH-m にした」は範囲を展開する", sections[2].hand == ("GH-50", "GH-51", "GH-52"), str(sections[2]))
    check("「GH-n・GH-m にした」は2つで1つの手", sections[3].hand == ("GH-20", "GH-21"), str(sections[3]))
    check("キーの形でない根の行は拾わない", sections[5].roots == (), str(sections[5]))

    with tempfile.TemporaryDirectory() as d:
        write(os.path.join(d, "docs", "history", "direction.md"), HISTORY)

        r = run(d, "--roots")
        check(
            "--roots は根ごとの件数とタスクID（根の無い古い行は数えない）",
            r.stdout.splitlines() == ["flaky-check\t2\tT-302,T-318,GH-10", "no-hand-yet\t1\tGH-12", "slow-capture\t1\tGH-11"],
            r.stdout,
        )

        r = run(d, "--effect")
        check("git のリポジトリでなければ完了の時刻は - で落ちない", r.returncode == 0 and "flaky-check\tGH-60\t-\t-" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr)

        subprocess.run(["git", "init", "-q", d], check=True)
        r = run(d, "--effect", "flaky-check")
        check("flow/ が無ければ手は未完了（PENDING）", r.stdout.strip() == "PENDING\tflaky-check\tGH-60,GH-20,GH-21", r.stdout + r.stderr)

        write(
            os.path.join(d, ".git", "task-workflow", "flow", "2026-10.jsonl"),
            done_row("2026-10-01T09:00:00+00:00", "GH-10")
            + done_row("2026-10-02T09:00:00+00:00", "GH-20")
            + done_row("2026-10-02T10:00:00+00:00", "GH-21")
            + done_row("2026-10-04T09:00:00+00:00", "T-318")
            + done_row("2026-10-03T09:00:00+00:00", "GH-50")
            + done_row("2026-10-03T09:30:00+00:00", "GH-51")
            + done_row("2026-10-03T10:00:00+00:00", "GH-52", dropped=True),
        )
        r = run(d, "--effect")
        lines = r.stdout.splitlines()
        check(
            "--effect は手ごとに完了の時刻と、完了のあとに同じ根が出た件数",
            lines
            == [
                "flaky-check\tGH-60\t-\t-",
                "flaky-check\tGH-20,GH-21\t2026-10-02T10:00:00+00:00\t1",
                "no-hand-yet\t-\t-\t-",
                "slow-capture\tGH-50,GH-51,GH-52\t-\t-",
            ],
            r.stdout,
        )

        r = run(d, "--effect", "flaky-check")
        check("完了した手のある根は RECUR", r.stdout.strip() == "RECUR\tflaky-check\tGH-20,GH-21", r.stdout)
        r = run(d, "--effect", "slow-capture")
        check("手の1つが dropped なら未完了（PENDING）", r.stdout.strip() == "PENDING\tslow-capture\tGH-50,GH-51,GH-52", r.stdout)
        r = run(d, "--effect", "no-hand-yet")
        check("「にした」の行が無い根は NO_HAND", r.stdout.strip() == "NO_HAND\tno-hand-yet\t-", r.stdout)
        r = run(d, "--effect", "never-seen")
        check("履歴に無い根も NO_HAND", r.stdout.strip() == "NO_HAND\tnever-seen\t-", r.stdout)

        r = run(d)
        check("札の一覧は根の行があっても今の形のまま", r.stdout.splitlines()[0] == "揺れ\t3\tT-302,T-318,GH-10,GH-5", r.stdout)

    with tempfile.TemporaryDirectory() as d:
        for flag in ("--roots", "--effect"):
            r = run(d, flag)
            check(f"docs/history/direction.md が無ければ {flag} も MISSING", r.stdout.strip() == "MISSING", r.stdout)
        write(os.path.join(d, "docs", "history", "direction.md"), "# 指示の履歴\n\n## 古い（振り返り: T-100）\n\n- 札: 黄 揺れ\n")
        for flag in ("--roots", "--effect"):
            r = run(d, flag)
            check(f"根の行が無ければ {flag} は EMPTY", r.stdout.strip() == "EMPTY", r.stdout)


def test_cli() -> None:
    print("tally.py（CLI）")
    with tempfile.TemporaryDirectory() as d:
        r = run(d)
        check("docs/history/direction.md が無ければ MISSING", r.stdout.strip() == "MISSING", r.stdout)

        write(
            os.path.join(d, "docs", "history", "direction.md"),
            "# 指示メモの履歴\n\n"
            "### 見出しA（振り返り: T-100）\n\n- 札: 黄 揺れ\n\n"
            "### 見出しB（振り返り: T-200）\n\n- 札: 赤 制約違反\n\n"
            "### 見出しC（振り返り: T-300）\n\n- 札: 黄 揺れ\n",
        )
        r = run(d)
        lines = r.stdout.strip().splitlines()
        check("件数の多い順に並ぶ（揺れ2件が先頭）", lines[0].startswith("揺れ\t2\t"), r.stdout)
        check("2件目は制約違反1件", lines[1].startswith("制約違反\t1\tT-200"), r.stdout)

        r = run(d, "揺れ")
        check("札を1つ指定すると件数とタスクIDだけ返す", r.stdout.strip() == "揺れ\t2\tT-100,T-300", r.stdout)

        r = run(d, "頼まれていない拡張")
        check("該当が無い札は件数0", r.stdout.strip() == "頼まれていない拡張\t0\t-", r.stdout)

    with tempfile.TemporaryDirectory() as d:
        write(os.path.join(d, "docs", "history", "direction.md"), "# 指示メモの履歴\n\n本文だけで札が無い\n")
        r = run(d)
        check("該当する行が無ければ EMPTY", r.stdout.strip() == "EMPTY", r.stdout)


def main() -> None:
    for t in (test_parse_and_tally, test_cli, test_roots_and_effect):
        t()
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
