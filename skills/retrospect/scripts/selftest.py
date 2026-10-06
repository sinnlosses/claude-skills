#!/usr/bin/env python3
"""`tally.py`（`docs/history/direction.md` から札を数える）と `weekly.py`（横断の振り返りの材料）の自己テスト。

使い方: python3 selftest.py

標準ライブラリだけで動く。落ちたら非0で終わる。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tally  # noqa: E402

# 足場は共有の git dir の台帳に記録を置くので、利用者の値で置き場を移さない。
os.environ.pop("TW_STATE_DIR", None)

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


# SKILL.md「週ごとに振り返る」の横断の振り返りのドラフトの雛形をそのまま写したもの（角括弧の穴だけ実物に差し替える）。
CROSS_DRAFT_TEMPLATE = """# 検証の打ち直しを根から塞ぐ（横断の振り返り: 2026-09-27〜2026-10-04）

- 根: flaky-check
- 観点: 根の束ね
- 根拠: BUNDLE flaky-check 2
- 出し先: docs/coding-standards.md「テスト」節
"""


def test_cross_sections() -> None:
    print("tally.py: 横断の振り返りの節")
    text = HISTORY + "\n" + CROSS_DRAFT_TEMPLATE.replace("\n\n", "\n\n（GH-70 にした）\n\n", 1)
    sections = tally.parse_sections(text)
    cross = sections[-1]
    check("雛形をそのまま写した横断の節を読める", cross.cross and cross.roots == ("flaky-check",) and cross.hand == ("GH-70",) and cross.reviewed == (), str(cross))
    check("1件ごとの節は横断の節にならない", not any(s.cross for s in sections[:-1]), str(sections))
    check("横断の節は根の件数に数えない", len(tally.roots(sections)["flaky-check"]) == 2, str(tally.roots(sections)))
    check("横断の節は札の件数に数えない", len(tally.tally(tally.tag_rows(sections))["揺れ"]) == 3, str(tally.tag_rows(sections)))
    hands = [hand for hand, _, _ in tally.effect(sections, "flaky-check", {})]
    check("横断の節の手は根の手として拾う", ("GH-70",) in hands, str(hands))


def weekly(*args: str) -> subprocess.CompletedProcess:
    root = args[0]
    return subprocess.run(
        [sys.executable, os.path.join(HERE, "weekly.py"), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": os.path.dirname(os.path.realpath(root))},
    )


def ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def flow_row(at: str, event: str, task: str, **fields: object) -> str:
    return json.dumps({"t": at, "event": event, "task": task, "difficulty": "opus", **fields}) + "\n"


def git(cwd: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def lines_of(section_name: str, out: str) -> list[str]:
    body = out.split(f"===== {section_name} =====", 1)[-1]
    return [l for l in body.split("=====", 1)[0].splitlines() if l]


def test_weekly() -> None:
    print("weekly.py")
    today = date.today()
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q", "-b", "main")
        git(d, "config", "user.email", "test@example.com")
        git(d, "config", "user.name", "test")
        write(os.path.join(d, "hook.sh"), 'echo "直近 30 日の拒否の回数"\necho "deny-a: 0"\necho "deny-b: 12"\n')
        write(
            os.path.join(d, "CLAUDE.md"),
            "# x\n\n## タスク運用\n\n- 検証コマンド: なし\n- 規則の発火の集計: `sh hook.sh`（直近30日）\n",
        )
        write(
            os.path.join(d, "docs", "history", "direction.md"),
            "# 指示の履歴\n\n"
            "## 2026-09-01 手を打った（振り返り: GH-10）\n\n（GH-20 にした）\n\n- 札: 黄 揺れ（1回目）\n- 根: flaky-check\n\n"
            "## 2026-10-01 また出た（振り返り: GH-30）\n\n- 札: 黄 揺れ（2回目）\n- 根: flaky-check\n\n"
            + CROSS_DRAFT_TEMPLATE,
        )
        write(os.path.join(d, "develop", "draft", f"{today.isoformat()}-flaky.md"), DRAFT_ITEM_TEMPLATE)
        write(
            os.path.join(d, "develop", "draft", f"{today.isoformat()}-no-root.md"),
            "# 道具が足りない（振り返り: GH-31）\n\n- 札: 黄 道具（1回目）\n- 根拠: …\n- 出し先: …\n",
        )
        write(os.path.join(d, "develop", "draft", "2000-01-01-old.md"), "# 古い（振り返り: GH-1）\n\n- 札: 黄 道具（1回目）\n- 根: old-root\n")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "やり方を変える")
        write(
            os.path.join(d, ".git", "task-workflow", "flow", "2026-10.jsonl"),
            flow_row(ago(20), "done", "GH-10", dropped=False, reflection="some")
            + flow_row(ago(15), "done", "GH-20", dropped=False, reflection="none")
            + flow_row(ago(10), "ship", "GH-20", result="SHIPPED")
            + flow_row(ago(9), "ship", "GH-21", result="SHIPPED")
            + flow_row(ago(2), "done", "GH-30", dropped=False, reflection="some"),
        )

        r = weekly(d)
        out = r.stdout
        print("  --- weekly.py の出力（材料が全部ある） ---")
        for line in out.splitlines():
            print(f"  | {line}")
        check("材料が全部あれば終了コード0で traceback が無い", r.returncode == 0 and "Traceback" not in r.stderr, r.stderr)
        check("記録が無ければ期間は7日で last=-", lines_of("期間", out) == [f"PERIOD\t7d\t{(today - timedelta(days=7)).isoformat()}\t{today.isoformat()}\tlast=-"], out)
        bundles = lines_of("根の束ね", out)
        check(
            "期間内の札を1件ずつ並べ（期間の外・横断の節は出さない）、根が2件以上なら BUNDLE",
            bundles
            == [
                f"TAG\t揺れ\tflaky-check\tGH-30\t{tally.DIRECTION_HISTORY_PATH}",
                f"TAG\t揺れ\tflaky-check\tT-302,T-318\tdevelop/draft/{today.isoformat()}-flaky.md",
                f"TAG\t道具\t-\tGH-31\tdevelop/draft/{today.isoformat()}-no-root.md",
                "BUNDLE\tflaky-check\t2\tGH-30,T-302,T-318",
            ],
            "\n".join(bundles),
        )
        recur = lines_of("効かなかった手", out)
        check(
            "手の完了のあとに期間内で出た根は RECUR と期間内の再発件数",
            len(recur) == 1 and recur[0].startswith("RECUR\tflaky-check\tGH-20\t") and recur[0].endswith("\t2"),
            "\n".join(recur),
        )
        flow = lines_of("流れの数", out)
        check("悪くなった数に WORSE", "WORSE\tshipped\t0\t2" in flow, "\n".join(flow))
        check("WORSE があれば期間内のやり方の変更を CHANGE で並べる", any(l.startswith("CHANGE\tproject\t") and l.endswith("\tやり方を変える") for l in flow), "\n".join(flow))
        check("規則の発火の集計のコマンドの出力をそのまま出す", lines_of("規則の棚卸し", out) == ["直近 30 日の拒否の回数", "deny-a: 0", "deny-b: 12"], out)

        r = weekly(d, "--days", "30")
        check("--days で期間を変えられる", lines_of("期間", r.stdout)[0].startswith("PERIOD\t30d\t"), r.stdout)
        r = weekly(d, "--days", "0")
        check("--days が1未満なら終了コード2", r.returncode == 2, r.stdout + r.stderr)

        write(os.path.join(d, "CLAUDE.md"), "# x\n\n## タスク運用\n\n- 検証コマンド: なし\n- 規則の発火の集計: `exit 3`\n")
        r = weekly(d)
        check("集計のコマンドが落ちたら - と終了コード", lines_of("規則の棚卸し", r.stdout) == ["-\t終了コード 3"] and r.returncode == 0, r.stdout)

        write(os.path.join(d, "CLAUDE.md"), "# x\n\n## タスク運用\n\n- 検証コマンド: なし\n")
        r = weekly(d)
        check(
            "規則の発火の集計の行が無ければ - と理由で、traceback を出さない",
            r.returncode == 0
            and "Traceback" not in r.stderr
            and lines_of("規則の棚卸し", r.stdout) == ["-\t「## タスク運用」に「- 規則の発火の集計:」の行が無い（この観点は飛ばす）"],
            r.stdout + r.stderr,
        )

        write(os.path.join(d, "docs", "history", "retrospect.md"), f"# 横断の振り返りの記録\n\n## {(today - timedelta(days=10)).isoformat()}（x〜y）\n\n## 2000-01-01（x〜y）\n")
        r = weekly(d)
        check("最後の記録が10日前なら期間は10日", lines_of("期間", r.stdout)[0].startswith("PERIOD\t10d\t") and r.stdout.count(f"last={(today - timedelta(days=10)).isoformat()}") == 1, r.stdout)
        write(os.path.join(d, "docs", "history", "retrospect.md"), "# 横断の振り返りの記録\n\n## 2000-01-01（x〜y）\n")
        r = weekly(d)
        check("期間は28日で打ち切る", lines_of("期間", r.stdout)[0].startswith("PERIOD\t28d\t"), r.stdout)

    with tempfile.TemporaryDirectory() as d:
        r = weekly(d)
        print("  --- weekly.py の出力（記録の無い初回・材料なし） ---")
        for line in r.stdout.splitlines():
            print(f"  | {line}")
        check("git でも台帳でもない空のディレクトリでも終了コード0で traceback が無い", r.returncode == 0 and "Traceback" not in r.stderr, r.stderr)
        check("記録の無い初回は期間7日・last=-", lines_of("期間", r.stdout)[0].startswith("PERIOD\t7d\t") and r.stdout.count("last=-") == 1, r.stdout)
        check(
            "どの節も欠席の理由を出す",
            lines_of("根の束ね", r.stdout) == [f"-\t{tally.DIRECTION_HISTORY_PATH} が無い（承認済みの札は読まない）", "EMPTY"]
            and lines_of("効かなかった手", r.stdout) == ["MISSING"]
            and lines_of("流れの数", r.stdout) == ["-\t台帳が読めない（git のリポジトリでない）"]
            and lines_of("規則の棚卸し", r.stdout)[0].startswith("-\t"),
            r.stdout,
        )


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
    for t in (test_parse_and_tally, test_cli, test_roots_and_effect, test_cross_sections, test_weekly):
        t()
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
