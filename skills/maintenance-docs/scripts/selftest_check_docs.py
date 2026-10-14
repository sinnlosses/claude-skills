#!/usr/bin/env python3
"""check_docs.py の検査5（タスク設定の読みと根の揃い）・検査8（検証コマンドの二重化）・検査9（太りすぎた文書）・検査11（どこからも参照されない文書）の自己テスト。

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
    write(root, "AGENTS.md", "# 規約\n")
    write(root, "CLAUDE.md", "# 規約\n")
    return root


def commit_all(root: str, *rels: str, date: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "add", *rels], cwd=root, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=root, check=True, env=env)


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
        expect("旧配置: /setup-tasks を促す", any("/setup-tasks" in l for l in got), str(got))
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

        root = make_config_project(tmp, "leftover")
        write(root, "develop/tasks.json", "[]\n")
        got = ng_lines(root, 5)
        expect("旧形式の残り: 検査5が指摘", any("develop/tasks.json" in l for l in got), str(got))

        root = make_config_project(tmp, "dup")
        write(root, "CLAUDE.md", "# 規約\n\n検証は make test で通す。\n")
        got = ng_lines(root, 8)
        expect("検証コマンドの値が文章にある: 検査8", any("make test" in l for l in got), str(got))

        root = make_config_project(tmp, "orphan")
        write(root, "docs/README.md", "# 索引\n\n- `docs/linked.md`\n")
        write(root, "docs/linked.md", "# 参照される\n")
        write(root, "docs/orphan-old.md", "# 孤立した古い文書\n")
        write(root, "docs/orphan-new.md", "# 孤立しているが新しい文書\n")
        write(root, "docs/adr/0001-x.md", "# 決定\n")
        write(root, "docs/research/memo.md", "# 調査\n")
        commit_all(root, "docs/orphan-new.md", "docs/README.md", "docs/linked.md", "docs/adr/0001-x.md", "docs/research/memo.md")
        commit_all(root, "docs/orphan-old.md", date="2020-01-01T00:00:00")
        got = ng_lines(root, 11)
        expect("参照0で古い文書: 検査11が出す", any("docs/orphan-old.md" in l for l in got), str(got))
        expect("参照されている文書: 検査11は出さない", not any("docs/linked.md" in l for l in got), str(got))
        expect("新しい文書: 検査11は出さない", not any("orphan-new" in l for l in got), str(got))
        expect("adr・research・索引: 検査11は対象外", not any(k in l for l in got for k in ("adr/", "research/", "README")), str(got))

        write(root, "docs/orphan-untracked.md", "# 履歴のあるリポジトリで未追跡\n")
        got = ng_lines(root, 11)
        expect("履歴のあるリポジトリの未追跡の文書: 検査11は出さない", not any("orphan-untracked" in l for l in got), str(got))

        root = make_config_project(tmp, "orphan-before-first-commit")
        write(root, "docs/orphan.md", "# 最初のコミット前\n")
        got = ng_lines(root, 11)
        expect("最初のコミット前の文書: 検査11は出さない", got == [], str(got))

        root = os.path.join(tmp, "orphan-outside-git")
        write(root, "docs/orphan.md", "# git の外\n")
        got = ng_lines(root, 11)
        expect("git の外: 参照0だけで出す", any("docs/orphan.md" in l and "測れない" in l for l in got), str(got))

        def fat(index: str, size: int) -> str:
            body = "# 太い文書\n\n" + index + "\n" + "".join(f"## 節{i}\n\n" for i in range(9))
            return body + "x" * (size - len(body.encode("utf-8")))

        root = make_config_project(tmp, "fat")
        write(root, "docs/huge-indexed.md", fat("節の索引", 102400))
        write(root, "docs/mid-indexed.md", fat("節の索引", 102399))
        write(root, "docs/big-noindex.md", fat("", 30000))
        write(root, "docs/huge-few-headings.md", "# 見出し少\n\n節の索引\n" + "x" * 110000)
        write(root, "README.md", fat("目次", 110000))
        commit_all(root, "docs/huge-indexed.md", "docs/mid-indexed.md", "docs/big-noindex.md", "docs/huge-few-headings.md", "README.md", date="2020-01-01T00:00:00")
        write(root, "docs/huge-untracked.md", fat("節の索引", 120000))
        got = ng_lines(root, 9)
        expect("目次あり・閾値ちょうど: 検査9が出す", any("docs/huge-indexed.md" in l and "目次はあるが太い" in l for l in got), str(got))
        expect("目次あり・閾値未満: 検査9は出さない", not any("mid-indexed" in l for l in got), str(got))
        expect("目次なし・20KB以上: 従来の文言で出す", any("docs/big-noindex.md" in l and "目次が無い" in l for l in got), str(got))
        expect("目次あり・見出しが少ない: 検査9は出さない", not any("huge-few-headings" in l for l in got), str(got))
        expect("入口の README.md は太くても検査9は出さない", not any("README.md" in l for l in got), str(got))
        expect("未追跡の太い文書: 検査9が出す（履歴の古さに依らない）", any("huge-untracked" in l for l in got), str(got))

        root = os.path.join(tmp, "fat-outside-git")
        write(root, "docs/huge-indexed.md", fat("節の索引", 102400))
        got = ng_lines(root, 9)
        expect("git の外でも目次あり・太い文書は検査9が出す", any("docs/huge-indexed.md" in l for l in got), str(got))

    if failures:
        print("\n失敗:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nすべて通った")
    return 0


if __name__ == "__main__":
    sys.exit(main())
