#!/usr/bin/env python3
"""`removed_lines.py` の自己テスト。

使い方: python3 selftest_removed_lines.py

標準ライブラリだけで動く。落ちたら非0で終わる。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "removed_lines.py")

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def git(repo: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def write(repo: str, path: str, body: str) -> None:
    with open(os.path.join(repo, path), "w", encoding="utf-8") as f:
        f.write(body)


def run(repo: str) -> str:
    out = subprocess.run([sys.executable, SCRIPT], cwd=repo, capture_output=True, text=True)
    check("非0で終わらない", out.returncode == 0, out.stderr)
    return out.stdout


def init_repo(d: str, files: dict[str, str]) -> None:
    git(d, "init", "-q")
    git(d, "config", "user.email", "a@example.com")
    git(d, "config", "user.name", "a")
    for path, body in files.items():
        write(d, path, body)
        git(d, "add", path)
    git(d, "commit", "-q", "-m", "init")


def test_removed_line_listed() -> None:
    print("消した行を表の下書きで出す")
    with tempfile.TemporaryDirectory() as d:
        init_repo(d, {"a.md": "one\ntwo | pipe\nthree\n"})
        write(d, "a.md", "one\nthree\n")
        out = run(d)
        check("ファイルの見出しがある", "### a.md" in out, out)
        check("表の見出しがある", "| 消した行 | 残る先 |" in out, out)
        check("消した行が残る先の空欄つきで出る", "| two \\| pipe |  |" in out, out)
        check("残した行は出ない", "one" not in out and "three" not in out, out)


def test_moved_line_not_listed() -> None:
    print("動かしただけの行は出さない")
    with tempfile.TemporaryDirectory() as d:
        init_repo(d, {"a.md": "one\ntwo\nthree\n", "b.md": "x\n"})
        write(d, "a.md", "two\nthree\n")
        write(d, "b.md", "x\none\n")
        out = run(d)
        check("別のファイルへ動かした行は出ない", out == "", out)
        write(d, "a.md", "three\ntwo\n")
        write(d, "b.md", "x\n")
        out = run(d)
        check("同じファイルで順を変えた行は出ない", "two" not in out and "three" not in out, out)
        check("消えた行は出る", "| one |  |" in out, out)


def test_blank_only_removal_not_listed() -> None:
    print("空行だけ消した差分は出さない")
    with tempfile.TemporaryDirectory() as d:
        init_repo(d, {"a.md": "one\n\ntwo\n"})
        write(d, "a.md", "one\ntwo\n")
        out = run(d)
        check("出力が空", out == "", out)


def main() -> int:
    test_removed_line_listed()
    test_moved_line_not_listed()
    test_blank_only_removal_not_listed()
    if failures:
        print(f"\n{len(failures)} 件失敗")
        return 1
    print("\nすべて ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
