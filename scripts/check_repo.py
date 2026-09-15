#!/usr/bin/env python3
"""リポジトリ全体の整合を見る（スキルの中身の良し悪しではなく、**ズレ**を見る）。

使い方: python3 scripts/check_repo.py

見るもの:
- 各 SKILL.md の frontmatter が読めて、`name` がディレクトリ名と一致すること
- README の「由来」一覧が `skills/` と過不足なく一致すること（README が索引なので）
- スキル同士の相互参照が実在するスキルを指していること
- スクリプトのパスが `${CLAUDE_SKILL_DIR}` 形で書かれ、実在するファイルを指していること
- 同梱スクリプトが構文として読めること
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")

problems: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def skill_names() -> list[str]:
    return sorted(
        n for n in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, n))
    )


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def frontmatter(text: str) -> dict:
    """`key: value` だけの浅い frontmatter を読む（YAML パーサに依存しない）。"""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[4:end].splitlines():
        if line.startswith(" ") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def check_frontmatter(names: list[str]) -> None:
    for n in names:
        path = os.path.join(SKILLS, n, "SKILL.md")
        if not os.path.exists(path):
            fail(f"{n}: SKILL.md が無い")
            continue
        fm = frontmatter(read(path))
        if not fm:
            fail(f"{n}: frontmatter を読めない")
            continue
        if fm.get("name") != n:
            fail(f"{n}: frontmatter の name が {fm.get('name')!r} でディレクトリ名と違う")
        if not fm.get("description"):
            fail(f"{n}: description が無い")


def check_readme_index(names: list[str]) -> None:
    text = read(os.path.join(ROOT, "README.md"))
    try:
        section = text.split("## 由来")[1].split("\n## ")[0]
    except IndexError:
        fail("README に「## 由来」節が無い")
        return
    listed = set(re.findall(r"`([a-z][a-z0-9-]+)`", section))
    listed &= set(names) | (listed - set(names))
    missing = sorted(set(names) - listed)
    extra = sorted(n for n in listed if n not in names and "-" in n)
    if missing:
        fail(f"README の由来一覧に載っていないスキル: {', '.join(missing)}")
    if extra:
        fail(f"README の由来一覧にあるが実在しない: {', '.join(extra)}")
    m = re.search(r"全(\d+)スキル", section)
    if not m:
        fail("README の由来節に「全Nスキル」の記載が無い")
    elif int(m.group(1)) != len(names):
        fail(f"README は全{m.group(1)}スキルと書いているが実際は{len(names)}件")


def markdown_files(name: str) -> list[str]:
    out = []
    for dirpath, _, files in os.walk(os.path.join(SKILLS, name)):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".md")]
    return out


def check_script_paths(names: list[str]) -> None:
    """`${CLAUDE_SKILL_DIR}/...` が実在するファイルを指しているか。"""
    pat = re.compile(r"\$\{CLAUDE_SKILL_DIR\}(/[\w./-]+)")
    for n in names:
        for md in markdown_files(n):
            for rel in pat.findall(read(md)):
                target = os.path.normpath(os.path.join(SKILLS, n, rel.lstrip("/")))
                if not os.path.exists(target):
                    fail(f"{os.path.relpath(md, ROOT)}: ${{CLAUDE_SKILL_DIR}}{rel} が実在しない")
    # 絶対パス・曖昧なプレースホルダは書かない（リポジトリを移すと壊れる）。
    for n in names:
        for md in markdown_files(n):
            body = read(md)
            for bad in ("<このスキルのパス>", "<task-workflowスキルのディレクトリ>"):
                if bad in body:
                    fail(f"{os.path.relpath(md, ROOT)}: {bad} は ${{CLAUDE_SKILL_DIR}} で書く")
            if re.search(r"python3 [^\n`]*/Users/", body):
                fail(f"{os.path.relpath(md, ROOT)}: スクリプトの実行に絶対パスを埋めている")


def check_cross_references(names: list[str]) -> None:
    """`` `skill-name` スキル`` の形の参照が実在するか。"""
    pat = re.compile(r"`([a-z][a-z0-9-]{2,})`\s*スキル")
    known = set(names)
    for n in names:
        for md in markdown_files(n):
            for ref in set(pat.findall(read(md))):
                if ref not in known:
                    fail(f"{os.path.relpath(md, ROOT)}: `{ref}` スキルは実在しない")


def check_python_syntax(names: list[str]) -> None:
    for n in names:
        for dirpath, _, files in os.walk(os.path.join(SKILLS, n)):
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(dirpath, f)
                try:
                    ast.parse(read(p))
                except SyntaxError as e:
                    fail(f"{os.path.relpath(p, ROOT)}: 構文エラー（{e}）")


def main() -> None:
    names = skill_names()
    check_frontmatter(names)
    check_readme_index(names)
    check_script_paths(names)
    check_cross_references(names)
    check_python_syntax(names)

    if problems:
        for p in problems:
            print(f"  FAIL {p}")
        print(f"\n{len(problems)}件の不整合")
        raise SystemExit(1)
    print(f"  ok   {len(names)}スキル、不整合なし")


if __name__ == "__main__":
    main()
