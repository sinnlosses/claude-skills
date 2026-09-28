#!/usr/bin/env python3
"""`tally.py`（`docs/history/direction.md` から札を数える）の自己テスト。

使い方: python3 selftest.py

標準ライブラリだけで動く。落ちたら非0で終わる。
"""

from __future__ import annotations

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
    return subprocess.run(
        [sys.executable, os.path.join(HERE, "tally.py"), *args],
        capture_output=True,
        text=True,
    )


def write(path: str, body: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


# SKILL.md「1件だけ振り返る」の「ドラフトに積む」の雛形をそのまま写したもの（角括弧の穴だけ実物に差し替える）。
DRAFT_ITEM_TEMPLATE = """# 検証コマンドが不安定（振り返り: T-302, T-318）

- 札: 黄 揺れ（3回目）
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
    for t in (test_parse_and_tally, test_cli):
        t()
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
