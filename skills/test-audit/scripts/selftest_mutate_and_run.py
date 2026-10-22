#!/usr/bin/env python3
"""`mutate_and_run.py` の自己テスト。

使い方: python3 selftest_mutate_and_run.py

一時の git リポジトリで、落ちる壊し方と落ちない壊し方・当たらない行・戻し忘れの検出・
中断での復元を見る。標準ライブラリだけで動く。落ちたら非0で終わる。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "mutate_and_run.py")

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def git(cwd: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(root: str) -> str:
    cwd = os.path.join(root, "repo")
    os.makedirs(cwd)
    git(cwd, "init", "-q")
    git(cwd, "config", "user.email", "t@example.com")
    git(cwd, "config", "user.name", "t")
    with open(os.path.join(cwd, "src.txt"), "w", encoding="utf-8") as f:
        f.write("limit=10\nlimit=10x\ncap=5\n")
    git(cwd, "add", "src.txt")
    git(cwd, "commit", "-q", "-m", "init")
    return cwd


def fake_test(needle: str, extra: str = "") -> str:
    code = (
        "import sys;s=open('src.txt',encoding='utf-8').read();"
        f"{extra}"
        f"bad={needle!r} not in s;"
        "print(' FAIL  t > 上限を守る') if bad else None;"
        "sys.exit(1 if bad else 0)"
    )
    return f"{sys.executable} -c \"{code}\"".replace("'", "'")


def read(cwd: str) -> str:
    with open(os.path.join(cwd, "src.txt"), encoding="utf-8") as f:
        return f.read()


def write_spec(root: str, mutations: list[dict]) -> str:
    path = os.path.join(root, "m.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mutations, f)
    return path


def run(spec: str, cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", SCRIPT, spec, "--cwd", cwd],
        capture_output=True,
        text=True,
        check=False,
    )


with tempfile.TemporaryDirectory() as root:
    cwd = make_repo(root)
    original = read(cwd)
    cmd = fake_test("cap=5")

    print("落ちる・落ちない・当たらず")
    spec = write_spec(
        root,
        [
            {"name": "cap を消す", "file": "src.txt", "old": "cap=5", "new": "cap=9", "command": cmd},
            {"name": "効かない壊し", "file": "src.txt", "old": "limit=10x", "new": "limit=11x", "command": cmd},
            {"name": "複数当たる", "file": "src.txt", "old": "limit=10", "new": "limit=1", "command": cmd},
            {"name": "当たらない", "file": "src.txt", "old": "zzz", "new": "y", "command": cmd},
        ],
    )
    r = run(spec, cwd)
    rows = {line.split("|")[1].strip(): line for line in r.stdout.splitlines() if line.startswith("| ")}
    check("落ちた行と it 名", "落ちた（1 件）" in rows["cap を消す"] and "上限を守る" in rows["cap を消す"], r.stdout)
    check("落ちない行", "落ちず（0 件）" in rows["効かない壊し"], r.stdout)
    check("複数当たる行は壊さない", "当たらず（置換前が 2 回）" in rows["複数当たる"], r.stdout)
    check("当たらない行は壊さない", "当たらず（置換前が 0 回）" in rows["当たらない"], r.stdout)
    check("終わったら元のバイト列", read(cwd) == original)
    check("戻し忘れなしで 0", r.returncode == 0, str(r.returncode))

    print("戻し忘れの検出")
    leaker = f"{sys.executable} -c \"open('leak.txt','w').write('x')\""
    spec = write_spec(
        root, [{"name": "漏らす", "file": "src.txt", "old": "cap=5", "new": "cap=6", "command": leaker}]
    )
    r = run(spec, cwd)
    check("git status の増えを戻し忘れとして出す", "戻し忘れ" in r.stdout and "leak.txt" in r.stdout, r.stdout)
    check("非0で終わる", r.returncode == 3, str(r.returncode))
    check("壊したファイル自体は戻る", read(cwd) == original)
    os.remove(os.path.join(cwd, "leak.txt"))

    print("中断で元に戻る")
    slow = f"{sys.executable} -c \"import time;time.sleep(30)\""
    spec = write_spec(
        root, [{"name": "遅い", "file": "src.txt", "old": "cap=5", "new": "cap=7", "command": slow}]
    )
    p = subprocess.Popen(
        [sys.executable, "-I", SCRIPT, spec, "--cwd", cwd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + 10
    while time.time() < deadline and read(cwd) == original:
        time.sleep(0.05)
    check("壊した状態が一度は見える", read(cwd) != original)
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=20)
    check("SIGTERM のあと元のバイト列", read(cwd) == original)
    check("中断を表に出す", "中断" in out, out)

if failures:
    print(f"\n{len(failures)} 件落ちた")
    sys.exit(1)
print("\n全部通った")
