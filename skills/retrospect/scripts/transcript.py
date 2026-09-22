"""サブエージェントのトランスクリプトを見つけ、そこから**数だけ**を取り出す。

Claude Code は作業ディレクトリのパスの英数字以外を `-` に潰した名前で
`~/.claude/projects/<slug>/<セッション>/subagents/<エージェント>.jsonl` に置く。

**会話の中身をここから外へ出さない。** 返すのはツール名・ファイル名・コマンドの先頭2語・
件数・時刻だけ（CLAUDE.md「会話内容の扱い」）。本文を返す関数をここに足さない。
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter


def subagent_dirs(root: str) -> list[str]:
    """このリポジトリの `subagents/` ディレクトリ。無ければ空（材料が1つ減るだけ）。"""
    base = project_dir(root)
    if base is None:
        return []
    found = []
    for entry in sorted(os.listdir(base)):
        sub = os.path.join(base, entry, "subagents")
        if os.path.isdir(sub):
            found.append(sub)
    return found


def project_dir(root: str) -> str | None:
    """`~/.claude/projects/` の下のこのリポジトリのディレクトリ。

    潰し方は版によって変わりうるので、**計算した名前で当ててから、外れたら総当たりで
    照合する**（見つからなければ None を返して先へ進む）。
    """
    projects = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(projects):
        return None
    want = _slug(os.path.abspath(root))
    direct = os.path.join(projects, want)
    if os.path.isdir(direct):
        return direct
    for entry in os.listdir(projects):
        if _slug(entry) == want and os.path.isdir(os.path.join(projects, entry)):
            return os.path.join(projects, entry)
    return None


def _slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def find_transcripts(root: str, task_id: str) -> list[str]:
    """先頭の数行にタスクIDが出てくる jsonl だけを拾う（mtime では当てにいかない）。"""
    hits = []
    for sub in subagent_dirs(root):
        for name in sorted(os.listdir(sub)):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(sub, name)
            if task_id in _head_text(path):
                hits.append(path)
    return hits


def _head_text(path: str, lines: int = 3) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(next(f, "") for _ in range(lines))
    except OSError:
        return ""


def read_signals(path: str) -> dict | None:
    """ツール名・ファイル名・コマンドの先頭2語・件数・時刻だけを数える。"""
    tools: Counter[str] = Counter()
    files: Counter[str] = Counter()
    commands: Counter[str] = Counter()
    calls = errors = out_tokens = 0
    first = last = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                ts = o.get("timestamp") or ""
                if ts:
                    first = first or ts
                    last = ts
                msg = o.get("message") or {}
                content = msg.get("content")
                blocks = content if isinstance(content, list) else []
                if o.get("type") == "assistant":
                    out_tokens += int((msg.get("usage") or {}).get("output_tokens") or 0)
                    for b in blocks:
                        if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                            continue
                        calls += 1
                        name = str(b.get("name") or "?")
                        tools[name] += 1
                        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                        if name in ("Edit", "Write", "NotebookEdit"):
                            fp = str(inp.get("file_path") or "")
                            if fp:
                                files[os.path.basename(fp)] += 1
                        elif name == "Bash":
                            head = " ".join(str(inp.get("command") or "").split()[:2])
                            if head:
                                commands[head] += 1
                elif o.get("type") == "user":
                    for b in blocks:
                        if (isinstance(b, dict) and b.get("type") == "tool_result"
                                and b.get("is_error")):
                            errors += 1
    except OSError:
        return None
    return {
        "elapsed": f"{first[:19]} → {last[:19]}" if first else "不明",
        "tool_calls": calls,
        "errors": errors,
        "tools": tools.most_common(8),
        "rewrites": [(k, v) for k, v in files.most_common(5) if v >= 2],
        "commands": [(k, v) for k, v in commands.most_common(6) if v >= 2],
        "output_tokens": out_tokens,
    }
