#!/usr/bin/env python3
"""`docs/`・`README.md`・`CLAUDE.md` を10個の検査にかけ、指摘を出す。

使い方:
    python3 check_docs.py [プロジェクトのルート] [--skills-dir DIR]

ルートの既定はカレントディレクトリ。`--skills-dir` の既定はこのスクリプトを含むスキルの
親ディレクトリ（＝インストール済みスキルの置き場）で、検査10と `== 参考 canon ==` に使う。

指摘の頭は2種類:
    NG  確定群。正典が決めた形に反していて、直せば必ず正しくなる
    ?   候補群。「今の姿の説明か、昔の話か」で正否が決まる。人が判断する

**「無い」ことは指摘にしない。** `docs/` 系は遅延作成なので、`docs/` そのものが無い、
索引が無い、ADR が無いのはすべて正常。逆に「中身の無い索引が先回りして置かれている」は
指摘になる（検査3）。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# CLAUDE.md の「## タスク運用」節で行頭が固定されている行（task-workflow の WORKFLOW.md
# 「ファイル配置と CLAUDE.md」が正典）。
TASK_SECTION_KEYS = ("検証コマンド", "整形コマンド", "ブランチ")
# 行頭がズレているのか、行そのものが無いのかを見分けるための短い手がかり。
TASK_SECTION_STEMS = {"検証コマンド": "検証", "整形コマンド": "整形", "ブランチ": "ブランチ"}
DEVELOP_FILES = ("tasks.json", "progress.md", "direction.md")

# `docs/history/` は当時の記述をそのまま残すアーカイブなので、どの検査の対象にもしない。
HISTORY_DIR = "history"

# 索引 `docs/README.md` に載せる対象から外すもの。
INDEX_EXEMPT = ("README.md",)

# 検査9（索引の無い大きなドキュメント）のしきい値。
BIG_DOC_BYTES = 20480
BIG_DOC_HEADINGS = 8

# 検査8（見出しの重複）で無視する見出し。
#
# 2種類ある。どのドキュメントにも出る一般的なものと、**同じ種類のドキュメントが
# 共有する書式**（ADR の「状況と決定」、調査メモの「一次情報」など）。後者は
# ディレクトリが分かれていても揃うので、同じディレクトリかどうかでは弾けない。
COMMON_HEADINGS = {
    "目次", "索引", "概要", "はじめに", "手順", "使い方", "背景", "参考",
    "ライセンス", "制約", "検証", "前提", "まとめ", "注意", "例", "補足",
    "やること", "完了条件", "このドキュメントの読み方", "このファイルの読み方",
    # ADR の書式
    "状況", "状況と決定", "決定", "結果と影響", "文脈", "決定の背景",
    "Context", "Decision", "Consequences", "Status",
    # 調査メモの書式
    "一次情報", "調べた動機", "調べたこと", "分かったこと", "未解決のこと",
}

CHECKS = [
    (1, "索引の取りこぼし", "確定"),
    (2, "索引のリンク切れ", "確定"),
    (3, "先回りして置かれた空の索引", "確定"),
    (4, "相対リンク切れ", "確定"),
    (5, "タスク運用節の形", "確定"),
    (6, "実在しないパスの言及", "候補"),
    (7, "置き場の逸脱", "候補"),
    (8, "正典の二重化", "候補"),
    (9, "索引の無い大きなドキュメント", "候補"),
    (10, "スキル参照の不一致", "候補"),
]


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def headings(body: str) -> list[str]:
    return [
        line.lstrip("#").strip()
        for line in body.splitlines()
        if re.match(r"^#{2,4} ", line)
    ]


def first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line.strip():
            return line.strip()[:60]
    return ""


def docs_files(root: str) -> list[str]:
    """`docs/` 配下の Markdown（`docs/history/` は除く）。パスは posix 形式の相対。"""
    out: list[str] = []
    for dirpath, dirnames, files in os.walk(os.path.join(root, "docs")):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if rel_dir == f"docs/{HISTORY_DIR}" or rel_dir.startswith(f"docs/{HISTORY_DIR}/"):
            dirnames[:] = []
            continue
        for f in sorted(files):
            if f.endswith(".md") and not f.startswith("."):
                out.append(f"{rel_dir}/{f}")
    return sorted(out)


def targets(root: str) -> list[str]:
    """検査の対象。`docs/`（history 除く）＋ ルートの `README.md`・`CLAUDE.md`。"""
    out = docs_files(root)
    for f in ("README.md", "CLAUDE.md"):
        if os.path.exists(os.path.join(root, f)):
            out.append(f)
    return out


def index_entries(root: str) -> list[str]:
    """`docs/README.md` が名指ししているパス（`` `path` `` と `[..](path)` の両方）。"""
    body = read(os.path.join(root, "docs", "README.md"))
    found = [m.group(1) for m in re.finditer(r"`([^`\s]+\.\w+)`", body)]
    found += [m.group(1) for m in re.finditer(r"\]\(([^)\s]+)\)", body)]
    out: list[str] = []
    for p in found:
        if p.startswith(("http://", "https://", "#")):
            continue
        p = p.split("#")[0].lstrip("./")
        norm = p if p.startswith("docs/") else f"docs/{p}"
        if norm not in out:
            out.append(norm)
    return out


def task_section(body: str) -> list[str]:
    lines = body.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## タスク運用")), None)
    if start is None:
        return []
    out = [lines[start]]
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return out


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "target", "dist", "build", ".next"}

PATH_IN_TICKS = re.compile(r"`([^`\s]+)`")
LINK = re.compile(r"\]\(([^)\s]+)\)")
PATH_LIKE = re.compile(r"^[.]{0,2}/?[\w][\w./-]*$")
KNOWN_EXT = (".md", ".json", ".sh", ".py", ".ts", ".tsx", ".js", ".toml", ".yaml", ".yml")


def looks_like_path(p: str, top_dirs: set[str]) -> bool:
    """検査6 が見るのは「**ルートの実在するディレクトリから始まり、既知の拡張子で終わる**」ものだけ。

    ドキュメントは `values.yaml`・`lib/gitlab`・`/compare/a...b`・`owner/repo` のような、
    ファイルパスの形をした**概念や URL の断片**を大量に含む。緩く拾うと候補群が誤検知で
    埋まり、本物の1件が見えなくなる（実測したリポジトリで60件超が出た）。ルートからの
    パスに限れば、指しているものが1つに決まる。
    """
    if p.startswith(("http://", "https://", "#", "-", "/")) or " " in p:
        return False
    if any(c in p for c in "<>*?$"):
        return False  # `docs/research/<topic>.md` のようなプレースホルダ
    if not PATH_LIKE.match(p):
        return False
    if not p.endswith(KNOWN_EXT):
        return False
    head = p.lstrip("./").split("/")[0]
    return head in top_dirs


def top_level_dirs(root: str) -> set[str]:
    try:
        entries = os.listdir(root)
    except OSError:
        return set()
    return {
        e
        for e in entries
        if os.path.isdir(os.path.join(root, e)) and not e.startswith(".") and e not in SKIP_DIRS
    }


# Claude Code の組み込みコマンド。スキルとして探すと必ず「見つからない」になる。
BUILTIN_COMMANDS = {
    "loop", "clear", "compact", "help", "init", "review", "plan", "model", "agents",
    "resume", "config", "cost", "doctor", "memory", "status", "vim", "context", "fast",
    "artifacts", "rewind", "usage", "todos", "export", "login", "logout", "mcp",
}

SKILL_REF = re.compile(r"(?:^|[\s`（(、。])/([a-z][a-z0-9-]{2,})\b|`([a-z][a-z0-9-]{2,})`\s*スキル")
DOCS_PATH = re.compile(r"`?(docs/[\w./*<>-]*|CONTEXT(?:-MAP)?\.md)`?")

# 検査7（置き場の逸脱）で「中身が何か」を疑う手がかり。判定そのものは人が行う。
ADR_HINT = re.compile(r"(^|[^\w])(adr|decision|決定記録)|^\d{1,4}-", re.I)
ADR_BODY = re.compile(r"^#{2,3} *(決定|Decision|状況と決定|結果と影響)", re.M)
RESEARCH_HINT = re.compile(r"(research|investigation|survey|調査|調べ)", re.I)
PROPOSAL_BODY = re.compile(r"(採らなかった|候補の比較|移行の段階|採否)")


def canon_paths(skills_dir: str) -> list[tuple[str, str]]:
    """インストール済みスキルが名指ししている `docs/` 側のパス（＝置き場の正典の在り処）。"""
    rows: list[tuple[str, str]] = []
    if not os.path.isdir(skills_dir):
        return rows
    for name in sorted(os.listdir(skills_dir)):
        sdir = os.path.join(skills_dir, name)
        if not os.path.isdir(sdir):
            continue
        paths: list[str] = []
        for dirpath, dirnames, files in os.walk(sdir):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for f in files:
                if not f.endswith(".md"):
                    continue
                for m in DOCS_PATH.finditer(read(os.path.join(dirpath, f))):
                    p = m.group(1).rstrip("`。、）)")
                    if p and p not in paths:
                        paths.append(p)
        rows += [(name, p) for p in sorted(paths)]
    return rows


def basenames(root: str) -> set[str]:
    """リポジトリ内に実在するファイル名の集合。

    検査6で「別の場所からの相対参照」を弾くために使う。README が
    「`architecture-proposal` の `scripts/import_edges.py`」と書くとき、そのパスは
    スキルのディレクトリからの相対であってルートからではない。同じ名前のファイルが
    どこかに実在するなら、指しているものはある。
    """
    out: set[str] = set()
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        out.update(files)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--skills-dir", default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    skills_dir = args.skills_dir or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    canon = canon_paths(skills_dir)
    claude_path = os.path.join(root, "CLAUDE.md")
    claude_body = read(claude_path)
    docs = docs_files(root)
    tgts = targets(root)
    has_index = os.path.exists(os.path.join(root, "docs", "README.md"))
    entries = index_entries(root) if has_index else []
    indexable = [p for p in docs if os.path.basename(p) not in INDEX_EXEMPT]

    found: dict[int, list[str]] = {n: [] for n, _, _ in CHECKS}

    def note(n: int, msg: str) -> None:
        found[n].append(msg)

    # 検査1: docs/ にあるのに索引に載っていない。
    if has_index:
        for p in indexable:
            if p not in entries:
                note(1, f"{p} が docs/README.md に無い")

    # 検査2: 索引が指す先が無い。
    for p in entries:
        if not os.path.exists(os.path.join(root, p)):
            note(2, f"docs/README.md -> {p} が実在しない")

    # 検査3: 索引だけあって載せる中身が無い。
    if has_index and not indexable:
        note(3, "docs/README.md はあるが索引に載せるファイルが1件も無い")

    # 検査4: Markdown リンクの切れ（辿れる前提の記法なので、切れていれば必ず誤り）。
    for rel in tgts:
        body = read(os.path.join(root, rel))
        base = os.path.dirname(os.path.join(root, rel))
        for m in LINK.finditer(body):
            link = m.group(1).split("#")[0]
            if not link or link.startswith(("http://", "https://", "mailto:", "/")):
                continue
            if any(c in link for c in "<>*"):
                continue
            if os.path.exists(os.path.join(base, link)):
                continue
            if os.path.exists(os.path.join(root, link)):
                continue
            note(4, f"{rel} -> {link} が実在しない")

    # 検査5: 「## タスク運用」節の形と develop/ の揃い。
    sec = task_section(claude_body)
    develop_present = [f for f in DEVELOP_FILES if os.path.exists(os.path.join(root, "develop", f))]
    if not sec and develop_present:
        note(5, f"develop/ はあるが CLAUDE.md に「## タスク運用」節が無い（{len(develop_present)}/3ファイル）")
    if sec:
        for key in TASK_SECTION_KEYS:
            hit = [l for l in sec if l.startswith(f"- {key}:")]
            if not hit:
                stem = TASK_SECTION_STEMS[key]
                loose = [l for l in sec if stem in l and ":" in l and l.lstrip().startswith(("-", "*"))]
                if loose:
                    note(5, f"「- {key}:」の行頭が正典とズレている: {loose[0].strip()}")
                else:
                    note(5, f"「- {key}:」の行が無い（消さずに「なし」と書く）")
            elif not hit[0].split(":", 1)[1].strip():
                note(5, f"「- {key}:」の値が空（走らせるものが無ければ「なし」）")
        for f in DEVELOP_FILES:
            if not os.path.exists(os.path.join(root, "develop", f)):
                note(5, f"「## タスク運用」節はあるが develop/{f} が無い")

    # 検査6: バッククォートで名指ししたパスが実在しない（経緯の記録なら正当なので候補群）。
    #
    # 2つを先に差し引く。**どちらも「無いのが正しい」場合**で、残すと候補群が
    # 誤検知で埋まり、本物の1件が見えなくなる:
    #   - 正典が「ここに置く」と言っているパス（遅延作成。まだ書いていないだけ）
    #   - 同じ名前のファイルがリポジトリのどこかに実在するもの（別の場所からの相対参照）
    prescribed = {p.rstrip("/") for _, p in canon}
    names_in_repo = basenames(root)
    tops = top_level_dirs(root)
    for rel in tgts:
        body = read(os.path.join(root, rel))
        seen: set[str] = set()
        for m in PATH_IN_TICKS.finditer(body):
            p = m.group(1).rstrip("/")
            if p in seen or not looks_like_path(p, tops):
                continue
            seen.add(p)
            if os.path.exists(os.path.join(root, p)):
                continue
            if p in prescribed:
                continue
            if os.path.basename(p) in names_in_repo:
                continue
            note(6, f"{rel}: `{p}` が実在しない")

    # 検査7: 置き場の逸脱の疑い（種類は中身で決まるので、手がかりを出すだけ）。
    for rel in docs:
        name = os.path.basename(rel)
        body = read(os.path.join(root, rel))
        head = first_heading(body)
        if name in INDEX_EXEMPT:
            continue
        under = rel.split("/")
        if not rel.startswith("docs/adr/") and (ADR_BODY.search(body) or ADR_HINT.search(name)):
            note(7, f"{rel}: 中身が決定記録に見える（正典は docs/adr/000N-*.md）")
        if rel.startswith("docs/adr/") and not re.match(r"^\d{4}-[a-z0-9-]+\.md$", name):
            note(7, f"{rel}: ADR の名前が 000N-<slug>.md の形でない")
        if not rel.startswith("docs/research/") and RESEARCH_HINT.search(name + " " + head):
            note(7, f"{rel}: 調査メモに見える（正典は docs/research/<topic>.md）")
        if name == "architecture.md" and PROPOSAL_BODY.search(body):
            note(7, f"{rel}: 採用後の正典に提案の記述が混ざっている（提案は docs/architecture-proposal.md）")
        if len(under) > 2 and under[1] in ("archive", "old", "past", "backup"):
            note(7, f"{rel}: 履歴の置き場は docs/history/")
    for rel in docs:
        if os.path.basename(rel) in ("CONTEXT.md", "CONTEXT-MAP.md"):
            note(7, f"{rel}: CONTEXT.md はリポジトリのルート（または各コンテキストのルート）に置く")

    # 検査8: 同じ見出しが2ファイル以上にある＝正典が二重化している疑い。
    seen_head: dict[str, list[str]] = {}
    for rel in tgts:
        for h in set(headings(read(os.path.join(root, rel)))):
            if h in COMMON_HEADINGS or len(h) < 3:
                continue
            seen_head.setdefault(h, []).append(rel)
    for h, files in sorted(seen_head.items()):
        # 3ファイル以上に同じ見出しがあるのは、二重化ではなく**書式の規約**
        # （「このファイルは通読しない」「節の索引」など）。同じディレクトリに揃って
        # いるのも、そのディレクトリのテンプレート（`docs/research/` の「調べた動機」など）。
        # 正典の二重化を疑うのは、**別の場所にある2つが同じ見出しを持つとき**。
        if len(files) != 2:
            continue
        same_dir = os.path.dirname(files[0]) == os.path.dirname(files[1])
        if same_dir and files[0].startswith("docs/"):
            continue  # `docs/research/` などのテンプレート。ルートの README/CLAUDE は除外しない
        note(8, f"見出し「{h}」が {', '.join(files)} に重複")
    # `- ブランチ:` に既定の中身が書き写されていないか。既定は WORKFLOW.md が持っていて、
    # 従うなら `既定` の2文字でよい。写すと正典が2箇所になる。
    branch = next((l for l in sec if l.startswith("- ブランチ:")), "")
    value = branch.split(":", 1)[1].strip() if branch else ""
    if "feature/T-" in value and "既定" not in value:
        note(8, "`- ブランチ:` に既定の運用が書き写されている（従うだけなら「既定」と書く）")

    # 検証コマンドの値が節の外にも書かれていないか（同じ値の二重化）。
    for key in ("検証コマンド", "整形コマンド"):
        line = next((l for l in sec if l.startswith(f"- {key}:")), "")
        m = re.search(r"`([^`]+)`", line)
        if m and claude_body.count(f"`{m.group(1)}`") > 1:
            note(8, f"検証/整形コマンド `{m.group(1)}` が CLAUDE.md の複数箇所にある")

    # 検査9: 通読させる気が無い大きさなのに索引が無い。
    for rel in tgts:
        if rel in ("README.md", "CLAUDE.md"):
            continue  # 入口のファイルは通読される前提
        path = os.path.join(root, rel)
        body = read(path)
        if os.path.getsize(path) < BIG_DOC_BYTES:
            continue
        if len(headings(body)) < BIG_DOC_HEADINGS:
            continue
        if "目次" in body or "索引" in body:
            continue
        note(9, f"{rel}: {os.path.getsize(path)}B・見出し{len(headings(body))}個だが目次が無い")

    # 検査10: CLAUDE.md が名指ししているスキルの在り処。
    ref_skills: list[str] = []
    for m in SKILL_REF.finditer(claude_body):
        name = m.group(1) or m.group(2)
        if name and name not in ref_skills and name not in BUILTIN_COMMANDS:
            ref_skills.append(name)
    skill_where: list[tuple[str, str]] = []
    for name in ref_skills:
        user = os.path.isdir(os.path.join(skills_dir, name))
        project = os.path.isdir(os.path.join(root, ".claude", "skills", name))
        command = os.path.exists(os.path.join(root, ".claude", "commands", f"{name}.md"))
        if user and project:
            where = "SHADOWED"
            note(10, f"`{name}`: 同名のユーザー単位スキルが優先され、プロジェクト側は効かない")
        elif project:
            where = "project"
        elif command:
            where = "project-command" + ("+user" if user else "")
            if user:
                note(10, f"`{name}`: 同名のスラッシュコマンドとユーザー単位スキルが両方ある")
        elif user:
            where = "user"
        else:
            where = "NOT_FOUND"
            note(10, f"`{name}`: スキルもコマンドも見つからない")
        skill_where.append((name, where))

    # ---- 出力 ----
    for n, title, group in CHECKS:
        mark = "NG" if group == "確定" else "?"
        print(f"== 検査{n} {title}（{group}） ==")
        for msg in found[n]:
            print(f"  {mark} {msg}")

    print("\n== counts ==")
    print(" ".join(f"{n}={len(found[n])}" for n, _, _ in CHECKS))
    confirmed = sum(len(found[n]) for n, _, g in CHECKS if g == "確定")
    candidate = sum(len(found[n]) for n, _, g in CHECKS if g == "候補")
    print(f"確定群={confirmed} 候補群={candidate}")

    print("\n== 参考 対象 ==")
    print(f"root\t{root}")
    print(f"targets\t{len(tgts)}件\t{', '.join(tgts) if tgts else '(none)'}")
    print(f"docs/README.md\t{'YES' if has_index else 'NO'}")
    for f in DEVELOP_FILES:
        print(f"develop/{f}\t{'YES' if os.path.exists(os.path.join(root, 'develop', f)) else 'NO'}")
    for name, where in skill_where:
        print(f"skill-ref\t{name}\t{where}")

    print("\n== 参考 タスク運用節 ==")
    if not sec:
        print("(「## タスク運用」節が無い)")
    for line in sec:
        print(line)

    print("\n== 参考 canon（スキルが名指ししている docs 側のパス） ==")
    if not canon:
        print("(スキルの置き場が見つからない)")
    for name, p in canon:
        print(f"{name}\t{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
