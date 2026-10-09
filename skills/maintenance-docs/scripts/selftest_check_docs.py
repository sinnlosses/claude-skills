#!/usr/bin/env python3
"""check_docs.py の検査5（タスク設定の読みと根の揃い）と検査8（検証コマンドの二重化）の自己テスト。

使い方: python3 selftest_check_docs.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "check_docs.py")

failures: list[str] = []


def write(root: str, rel: str, text: str = "") -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def ng_lines(root: str, check: int, env: dict[str, str] | None = None) -> list[str]:
    out = subprocess.run([sys.executable, CHECK, root], capture_output=True, text=True, check=True, env=env).stdout
    lines = out.splitlines()
    head = next(i for i, l in enumerate(lines) if l.startswith(f"== 検査{check} "))
    found = []
    for l in lines[head + 1 :]:
        if not l.startswith("  "):
            break
        found.append(l)
    return found


def expect(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok' if ok else 'NG'}  {name}")
    if not ok:
        failures.append(f"{name} {detail}")


def make_config_project(tmp: str, name: str) -> str:
    root = os.path.join(tmp, name)
    subprocess.run(["git", "init", "-q", root], check=True)
    write(root, ".tw/config.toml", 'verify = "make test"\n')
    write(root, ".tw/direction.md", "## ユーザーから\n")
    write(root, ".tw/task/.keep")
    write(root, "AGENTS.md", "# 規約\n")
    write(root, "CLAUDE.md", "# 規約\n")
    return root


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = make_config_project(tmp, "ok")
        expect("設定だけで節が無い: 検査5は指摘0", ng_lines(root, 5) == [], str(ng_lines(root, 5)))

        root = os.path.join(tmp, "legacy")
        subprocess.run(["git", "init", "-q", root], check=True)
        write(root, "AGENTS.md", "## タスク運用\n\n- 検証コマンド: `make test`\n- 整形コマンド: なし\n- ブランチ: 既定\n")
        write(root, "develop/direction.md", "## ユーザーから\n")
        write(root, "develop/task/.keep")
        got = ng_lines(root, 5)
        expect("旧配置: tw migrate-layout を促す", any("tw migrate-layout" in l for l in got), str(got))
        expect("旧配置の検証コマンドは検査8で二重化とされない", ng_lines(root, 8) == [], str(ng_lines(root, 8)))

        root = make_config_project(tmp, "legacy-section-with-config")
        write(root, "AGENTS.md", "## タスク運用\n\n- 検証コマンド: `make test`\n")
        expect("設定があり旧節も残る: 旧節の中は検査8で除く", ng_lines(root, 8) == [], str(ng_lines(root, 8)))

        root = make_config_project(tmp, "no-tw")
        got = ng_lines(root, 5, env={"PATH": "/nonexistent"})
        expect("tw が無い: 読めない指摘", any("tw が無い" in l for l in got), str(got))

        root = make_config_project(tmp, "broken")
        write(root, ".tw/config.toml", "verify = make test\n")
        got = ng_lines(root, 5)
        expect("壊れた設定: 読めない指摘", any("読めない" in l for l in got), str(got))

        root = make_config_project(tmp, "noroot")
        os.remove(os.path.join(root, ".tw/direction.md"))
        got = ng_lines(root, 5)
        expect("根の direction.md が無い", any("direction.md" in l for l in got), str(got))

        root = make_config_project(tmp, "notask")
        os.remove(os.path.join(root, ".tw/task/.keep"))
        os.rmdir(os.path.join(root, ".tw/task"))
        got = ng_lines(root, 5)
        expect("files 方式で task/ が無い", any("task/" in l for l in got), str(got))

        root = make_config_project(tmp, "dup")
        write(root, "CLAUDE.md", "# 規約\n\n検証は make test で通す。\n")
        got = ng_lines(root, 8)
        expect("検証コマンドの値が文章にある: 検査8", any("make test" in l for l in got), str(got))

    if failures:
        print("\n失敗:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nすべて通った")
    return 0


if __name__ == "__main__":
    sys.exit(main())
