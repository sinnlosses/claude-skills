#!/usr/bin/env python3
"""テストファイルから `it`・`test` の宣言を抜き出し、台帳の下書きとして出す。

使い方:
  python3 list_test_declarations.py test/server            # ディレクトリは *.test.* と *.spec.* を再帰で探す
  python3 list_test_declarations.py a.test.ts b.test.ts    # ファイルはそのまま読む

出力は Markdown。ファイルごとの見出しに件数、`describe` の入れ子ごとの件数、
1宣言1行の表（印と証拠の欄は空）を出す。最後に全体の合計を出す。
表駆動（`.each`・`.for`）は1宣言として数える。`.skip`・`.only`・`.todo` と型引数 `<…>` 付き、
`.skipIf(条件)(名前, …)` のような2段呼びも数え、名前は2段目の最初の引数にする。
`test.describe` は `describe` として入れ子にする。
宣言名が文字列リテラルでないときは、引数の元の文字列を出す。
正規表現リテラルは、直前の字から推定して読み飛ばす。
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

TEST_FILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
HEAD = re.compile(
    r"(?<![\w$.])(describe|it|test)((?:\.(?:describe|each|skip|only|todo|concurrent|sequential|fails|fixme|parallel|serial|runIf|skipIf|for))*)(?![\w$])"
)
TWO_STAGE = re.compile(r"\.(?:each|for|runIf|skipIf)(?![\w$])")
REGEX_KEYWORDS = {"return", "typeof", "case", "in", "of", "yield", "await", "void", "delete", "else", "do", "throw"}
CLOSERS = {"(": ")", "[": "]", "{": "}"}


@dataclass
class Decl:
    kind: str
    name: str
    line: int
    start: int
    end: int


def regex_allowed(out: list[str], i: int) -> bool:
    """直前の字が式の始まりを示すとき、`/` は正規表現リテラルの開き。"""
    k = i - 1
    while k >= 0 and out[k].isspace():
        k -= 1
    if k >= 1 and out[k] == ">" and out[k - 1] == "=":
        return True
    word = re.search(r"[A-Za-z]+$", "".join(out[max(0, k - 10) : k + 1]))
    if word and word.group() in REGEX_KEYWORDS:
        return True
    return k < 0 or out[k] in "(,=:[!&|?{;+-*%~^"


def mask(src: str) -> str:
    """文字列・テンプレート・コメントの中身を空白にした、同じ長さの文字列を返す。"""
    out = list(src)
    n = len(src)
    i = 0
    stack: list[int] = []  # テンプレートの `${` の波括弧の深さ

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def template(j: int) -> int:
        """j は開きの backtick の次。閉じの次の位置か、`${` に入った位置を返す。"""
        start = j
        while j < n:
            c = src[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                blank(start, j)
                return j + 1
            if c == "$" and src[j + 1 : j + 2] == "{":
                blank(start, j)
                stack.append(0)
                return j + 2
            j += 1
        blank(start, n)
        return n

    while i < n:
        c = src[i]
        two = src[i : i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, min(j, n))
            i = j + 1
        elif c == "`":
            i = template(i + 1)
        elif c == "/" and regex_allowed(out, i):
            j = i + 1
            in_class = False
            while j < n and src[j] != "\n" and (in_class or src[j] != "/"):
                if src[j] == "\\":
                    j += 1
                elif src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                j += 1
            blank(i + 1, min(j, n))
            i = j + 1
        elif stack and c == "{":
            stack[-1] += 1
            i += 1
        elif stack and c == "}":
            if stack[-1] == 0:
                stack.pop()
                i = template(i + 1)
            else:
                stack[-1] -= 1
                i += 1
        else:
            i += 1
    return "".join(out)


def match(masked: str, i: int) -> int:
    """masked[i] の開き括弧に対応する閉じ括弧の位置。無ければ -1。"""
    stack: list[str] = []
    for j in range(i, len(masked)):
        c = masked[j]
        if c in CLOSERS:
            stack.append(CLOSERS[c])
        elif c in ")]}":
            if not stack or stack.pop() != c:
                return -1
            if not stack:
                return j
    return -1


def skip_space(masked: str, i: int) -> int:
    while i < len(masked) and masked[i].isspace():
        i += 1
    return i


def skip_type_args(masked: str, i: int) -> int:
    """`<…>` を読み飛ばす。`=>` は閉じに数えない。"""
    depth = 0
    j = i
    while j < len(masked):
        c = masked[j]
        if c == "<":
            depth += 1
        elif c == ">" and masked[j - 1] != "=":
            depth -= 1
            if depth == 0:
                return j + 1
        elif c in "([{":
            close = match(masked, j)
            if close < 0:
                return -1
            j = close
        j += 1
    return -1


def first_argument(src: str, masked: str, open_paren: int, close_paren: int) -> str:
    j = skip_space(masked, open_paren + 1)
    if j < close_paren and src[j] in "'\"`":
        quote = src[j]
        k = j + 1
        while k < close_paren and src[k] != quote:
            k += 2 if src[k] == "\\" else 1
        return src[j + 1 : k]
    depth = 0
    k = j
    while k < close_paren:
        c = masked[k]
        if c in CLOSERS:
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            break
        k += 1
    return re.sub(r"\s+", " ", src[j:k]).strip()


def parse_declarations(src: str) -> list[Decl]:
    masked = mask(src)
    decls: list[Decl] = []
    for m in HEAD.finditer(masked):
        kind = m.group(1) + m.group(2)
        j = skip_space(masked, m.end())
        if TWO_STAGE.search(m.group(2)):
            if masked[j : j + 1] == "<":
                j = skip_type_args(masked, j)
                if j < 0:
                    continue
                j = skip_space(masked, j)
            if masked[j : j + 1] == "(":
                close = match(masked, j)
                if close < 0:
                    continue
                j = skip_space(masked, close + 1)
            elif masked[j : j + 1] == "`":
                end = src.find("`", j + 1)
                while end >= 0 and src[end - 1] == "\\":
                    end = src.find("`", end + 1)
                if end < 0:
                    continue
                j = skip_space(masked, end + 1)
            else:
                continue
        elif masked[j : j + 1] == "<":
            j = skip_type_args(masked, j)
            if j < 0:
                continue
            j = skip_space(masked, j)
        if masked[j : j + 1] != "(":
            continue
        close = match(masked, j)
        if close < 0:
            continue
        line = src.count("\n", 0, m.start()) + 1
        decls.append(Decl(kind, first_argument(src, masked, j, close), line, m.start(), close))
    return decls


def is_describe(d: Decl) -> bool:
    return d.kind.startswith(("describe", "test.describe"))


def render_file(path: str, src: str) -> tuple[list[str], int]:
    decls = parse_declarations(src)
    stack: list[tuple[Decl, str]] = []
    rows: list[str] = []
    direct: dict[str, int] = {}
    total_by_scope: dict[str, int] = {}
    scope_order: list[str] = []
    count = 0
    for d in decls:
        while stack and d.start > stack[-1][0].end:
            stack.pop()
        scope = " > ".join(name for _, name in stack)
        if is_describe(d):
            stack.append((d, d.name))
            key = " > ".join(name for _, name in stack)
            if key not in total_by_scope:
                scope_order.append(key)
                total_by_scope[key] = 0
                direct[key] = 0
            continue
        count += 1
        keys = [" > ".join(name for _, name in stack[: k + 1]) for k in range(len(stack))]
        for key in keys:
            total_by_scope[key] += 1
        if keys:
            direct[keys[-1]] += 1
        label = f"{scope} > {d.name}" if scope else d.name
        rows.append(f"| {d.line} | {d.kind} | {escape(label)} |  |  |")
    lines = [f"## {path} ({count} 件)", ""]
    if scope_order:
        lines.append("describe ごとの件数（直下 / 配下）")
        lines.append("")
        for key in scope_order:
            depth = key.count(" > ")
            lines.append(f"{'  ' * depth}- {escape(key.split(' > ')[-1])}: {direct[key]} / {total_by_scope[key]}")
        lines.append("")
    lines += ["| 行 | 宣言 | 名前 | 印 | 証拠 |", "| --- | --- | --- | --- | --- |", *rows, ""]
    return lines, count


def escape(text: str) -> str:
    return text.replace("|", "\\|")


def collect(args: list[str]) -> list[str]:
    files: list[str] = []
    for arg in args:
        if os.path.isdir(arg):
            for root, dirs, names in os.walk(arg):
                dirs[:] = sorted(d for d in dirs if d != "node_modules" and not d.startswith("."))
                files += [os.path.join(root, n) for n in sorted(names) if TEST_FILE.search(n)]
        else:
            files.append(arg)
    return files


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    files = collect(argv)
    if not files:
        print("テストファイルが見つからない", file=sys.stderr)
        return 1
    out: list[str] = []
    total = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            lines, count = render_file(path, f.read())
        out += lines
        total += count
    out.append(f"合計: {len(files)} ファイル、{total} 件")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
