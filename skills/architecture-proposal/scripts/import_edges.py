#!/usr/bin/env python3
"""ディレクトリ同士の import の辺を数え、循環と、ディレクトリごとのファイル数を出す。

対象は JS / TS 系（import / export ... from、require、dynamic import）の相対 import と、
`--alias` で指定した接頭辞（例: `@/`→`src/`）。パッケージ名の import は「外部」として別に数える。

使い方:
    python3 import_edges.py <root> [--depth N] [--ext ts,tsx,js,jsx,mts,cts] [--alias @/=src/] [--markdown]

    root    走査の起点（例: src）。辺は root 直下から --depth 段のディレクトリ単位で集計する
    --depth 集計する階層の深さ（既定 1。`src/ui/<領域>` まで見たいなら 2）
    --markdown  表を Markdown で出す（提案書にそのまま貼る用）

他の言語（Python / Go / Rust）では import の書き方が違うので、この正規表現を1〜2行直して使う。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]"""
    r"""|(?:^|\n)\s*import\s*['"]([^'"]+)['"]"""
    r"""|\brequire\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|\bimport\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--ext", default="ts,tsx,js,jsx,mts,cts")
    ap.add_argument("--alias", action="append", default=[], help="prefix=dir  例: @/=src/")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--reach", metavar="UNIT", help="この単位の各ファイルが、どの上位単位から（推移的に）到達されるかを出す")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    exts = tuple("." + e.strip().lstrip(".") for e in args.ext.split(","))
    aliases = [a.split("=", 1) for a in args.alias if "=" in a]

    files = [
        os.path.join(d, f)
        for d, _, fs in os.walk(root)
        for f in fs
        if f.endswith(exts) and "node_modules" not in d
    ]

    def unit(path: str) -> str:
        rel = os.path.relpath(path, root)
        parts = rel.split(os.sep)
        if len(parts) == 1:
            return parts[0]  # root 直下のファイルはそれ自体を単位にする（cli.ts など）
        return "/".join(parts[: args.depth])

    def resolve(spec: str, frm: str) -> str | None:
        for prefix, target in aliases:
            if spec.startswith(prefix):
                spec = os.path.join(os.path.dirname(root), target, spec[len(prefix):])
                break
        else:
            if not spec.startswith("."):
                return None
            spec = os.path.join(os.path.dirname(frm), spec)
        spec = os.path.normpath(spec)
        candidates = [spec] + [spec + e for e in exts] + [os.path.join(spec, "index" + e) for e in exts]
        base, ext = os.path.splitext(spec)
        if ext in (".js", ".mjs", ".cjs"):  # TS が .js で書く相対 import
            candidates += [base + e for e in exts]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return spec

    edges: Counter[tuple[str, str]] = Counter()
    external: Counter[tuple[str, str]] = Counter()
    file_count: Counter[str] = Counter()
    line_count: Counter[str] = Counter()
    file_graph: dict[str, set[str]] = defaultdict(set)
    for path in files:
        src = unit(path)
        file_count[src] += 1
        text = open(path, encoding="utf-8", errors="replace").read()
        line_count[src] += text.count("\n")
        for m in IMPORT_RE.finditer(text):
            spec = next(g for g in m.groups() if g)
            target = resolve(spec, path)
            if target is None:
                external[(src, spec.split("/")[0] if not spec.startswith("@") else "/".join(spec.split("/")[:2]))] += 1
                continue
            if not target.startswith(root):
                external[(src, os.path.relpath(target, root))] += 1
                continue
            file_graph[path].add(target)
            dst = unit(target)
            if dst != src:
                edges[(src, dst)] += 1

    if args.reach:
        print_reach(args.reach, root, files, file_graph, unit)
        return 0

    graph: dict[str, set[str]] = defaultdict(set)
    for (a, b) in edges:
        graph[a].add(b)
    cycles = find_cycles(graph)

    out = print_markdown if args.markdown else print_plain
    out(edges, external, file_count, line_count, cycles)
    return 0


def print_reach(target_unit, root, files, file_graph, unit) -> None:
    """target_unit の各ファイルについて、他の単位のどのファイルから推移的に到達されるかを単位名で集計する。"""
    reverse: dict[str, set[str]] = defaultdict(set)
    for a, bs in file_graph.items():
        for b in bs:
            reverse[b].add(a)
    targets = sorted(f for f in files if unit(f) == target_unit)
    print(f"| `{target_unit}` のファイル | 到達してくる単位 |\n| --- | --- |")
    for t in targets:
        seen: set[str] = set()
        stack = [t]
        while stack:
            n = stack.pop()
            for p in reverse.get(n, ()):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        units = sorted({unit(p) for p in seen} - {target_unit})
        print(f"| `{os.path.relpath(t, root)}` | {', '.join(f'`{u}`' for u in units) or '（なし）'} |")


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    seen: set[str] = set()
    found: list[list[str]] = []

    def walk(node: str, stack: list[str]) -> None:
        if node in stack:
            cyc = stack[stack.index(node):] + [node]
            if sorted(cyc[:-1]) not in [sorted(c[:-1]) for c in found]:
                found.append(cyc)
            return
        if node in seen:
            return
        for nxt in sorted(graph.get(node, ())):
            walk(nxt, stack + [node])
        seen.add(node)

    for n in sorted(graph):
        walk(n, [])
    return found


def print_plain(edges, external, file_count, line_count, cycles) -> None:
    print("== files / lines per unit ==")
    for u, n in sorted(file_count.items()):
        print(f"{n:4d} files {line_count[u]:6d} lines  {u}")
    print("\n== internal edges (from -> to : count) ==")
    for (a, b), n in sorted(edges.items()):
        print(f"{a} -> {b} : {n}")
    print("\n== external imports (from -> package : count) ==")
    for (a, b), n in sorted(external.items()):
        print(f"{a} -> {b} : {n}")
    print("\n== cycles ==")
    print("\n".join(" -> ".join(c) for c in cycles) if cycles else "(none)")


def print_markdown(edges, external, file_count, line_count, cycles) -> None:
    print("| 単位 | ファイル数 | 行数 |\n| --- | ---: | ---: |")
    for u, n in sorted(file_count.items()):
        print(f"| `{u}` | {n} | {line_count[u]} |")
    print("\n| from | to | 本数 |\n| --- | --- | ---: |")
    for (a, b), n in sorted(edges.items()):
        print(f"| `{a}` | `{b}` | {n} |")
    print("\n| from | 外部 | 本数 |\n| --- | --- | ---: |")
    for (a, b), n in sorted(external.items()):
        print(f"| `{a}` | `{b}` | {n} |")
    print("\n循環: " + ("、".join(" → ".join(c) for c in cycles) if cycles else "なし"))


if __name__ == "__main__":
    sys.exit(main())
