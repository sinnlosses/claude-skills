#!/usr/bin/env python3
"""変異（わざと入れる壊し方）を1つずつ入れて対象テストを走らせ、落ちた it 名の表を出す。

使い方:
  python3 mutate_and_run.py mutations.json [--cwd DIR] [--fail-pattern REGEX]

mutations.json は配列で、1要素が1つの壊し方:
  {"name": "上限を 9_000 に", "file": "src/a.ts", "old": "10_000", "new": "9_000",
   "command": "pnpm exec vitest run test/a.test.ts"}
`file` は `--cwd`（既定はカレント）からの相対。`old` は1回だけ現れる文字列で、
0回や2回以上のときはその行を壊さず「当たらず」と出す。

1行ごとに、壊す → `command` を走らせる → 落ちた it 名を控える → バイト単位で戻す、を繰り返す。
コマンドが非0で終われば「落ちた」、0なら「落ちず」。it 名は出力のうち `--fail-pattern`
（既定は行頭が FAIL・×・✗・✕ の行）に当たる行。
途中の中断（SIGINT・SIGTERM・例外）でも、壊したファイルは元のバイト列へ戻してから終わる。
終わりに `git status --porcelain` を実行前と比べ、増えた差分があれば「戻し忘れ」として非0で終わる。
テストの出力の全文は出さず、当たった行だけを出す。標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys

DEFAULT_FAIL_PATTERN = r"^\s*(FAIL|×|✗|✕)\s"
EXIT_NOT_RESTORED = 3


def git_status(cwd: str) -> str | None:
    r = subprocess.run(
        ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=False
    )
    return r.stdout if r.returncode == 0 else None


def failed_names(output: str, pattern: str) -> list[str]:
    rx = re.compile(pattern)
    names: list[str] = []
    for line in output.splitlines():
        if rx.search(line) and line.strip() not in names:
            names.append(line.strip())
    return names


def run_one(m: dict, cwd: str, pattern: str, originals: dict[str, bytes]) -> tuple[str, list[str]]:
    path = os.path.join(cwd, m["file"])
    with open(path, "rb") as f:
        original = f.read()
    count = original.decode("utf-8").count(m["old"])
    if count != 1:
        return f"当たらず（置換前が {count} 回）", []
    originals[path] = original
    try:
        with open(path, "wb") as f:
            f.write(original.decode("utf-8").replace(m["old"], m["new"], 1).encode("utf-8"))
        r = subprocess.run(
            m["command"], shell=True, cwd=cwd, capture_output=True, text=True, check=False
        )
    finally:
        with open(path, "wb") as f:
            f.write(original)
        del originals[path]
    names = failed_names(r.stdout + "\n" + r.stderr, pattern)
    return ("落ちた" if r.returncode != 0 else "落ちず"), names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mutations")
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--fail-pattern", default=DEFAULT_FAIL_PATTERN)
    args = ap.parse_args()
    cwd = os.path.abspath(args.cwd)
    with open(args.mutations, encoding="utf-8") as f:
        mutations = json.load(f)

    originals: dict[str, bytes] = {}

    def on_signal(signum: int, _frame: object) -> None:
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    before = git_status(cwd)
    rows: list[tuple[str, str, list[str]]] = []
    interrupted = False
    try:
        for m in mutations:
            verdict, names = run_one(m, cwd, args.fail_pattern, originals)
            rows.append((m["name"], verdict, names))
    except KeyboardInterrupt:
        interrupted = True
    finally:
        for path, data in originals.items():
            with open(path, "wb") as f:
                f.write(data)

    print("| 壊し方 | 判定 | 落ちた it 名 |")
    print("| --- | --- | --- |")
    for name, verdict, names in rows:
        print(f"| {name} | {verdict}（{len(names)} 件） | {' ; '.join(names) or '-'} |")

    after = git_status(cwd)
    leftover = before is not None and after is not None and after != before
    if leftover:
        print("\n戻し忘れ: git status が実行前と違う")
        print(after)
    if interrupted:
        print("\n中断: 元のバイト列へ戻して終わった")
        return 130
    return EXIT_NOT_RESTORED if leftover else 0


if __name__ == "__main__":
    sys.exit(main())
