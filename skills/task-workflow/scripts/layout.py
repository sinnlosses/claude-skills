"""置き場と ID の形の正典（値そのもの）。

正典は WORKFLOW.md「ファイル配置と設定ファイル（AGENTS.md → CLAUDE.md の順）」。**置き場は
規約で固定**（設定で変えられない）と決めているのはそこで、ここは同じ値がスクリプトに何箇所も
直書きされているのをやめるための1箇所化（設定ファイルにしない・値は変えない）。ここを直せば
`task.py`・`taskfile.py`・`init.py`・`legacy.py`・`ledger.py`・`retrospect` の同梱スクリプトと
`maintenance-docs` の `check_docs.py` が全部追随する。

`retrospect`・`maintenance-docs` は別スキルなので、それぞれの `scripts/*.py` は `sys.path` に
このファイルのディレクトリを足してから `import layout` する（`selftest.py`・`selftest_task.py` が
兄弟モジュールを素の `import` 名で読むのと同じ形）。`task-workflow` が入っていない環境では
`ImportError` で止まる（データの不備ではなく環境の不備として扱う。他のスクリプトの docstring の
「環境の故障」の扱いと同じ）。
"""

from __future__ import annotations

import os
import re

# develop/task/T-xxx.md（正典3章）
TASK_DIR = "develop/task"

# develop/direction.md とその2節（正典「指示メモ」）
DIRECTION_PATH = "develop/direction.md"
SECTION_USER = "## ユーザーから"
SECTION_DRAFT = "## エージェントのドラフト"

# develop/retrospective.md（正典「振り返り」）
RETROSPECTIVE_PATH = "develop/retrospective.md"

# docs/history/tasks.md（旧形式の履歴・採番の下限。正典5.3）
HISTORY_TASKS_PATH = "docs/history/tasks.md"

# タスクID: "T-" + 3桁以上の数字（正典3.1）
ID_FRAGMENT = r"T-\d{3,}"
ID_PATTERN = re.compile(rf"^{ID_FRAGMENT}$")  # 全体一致（front matter の id・--deps の各要素）
ID_SEARCH_PATTERN = re.compile(rf"\b{ID_FRAGMENT}\b")  # 文中から拾う（コミット件名・トランスクリプト）
HISTORY_HEADING_PATTERN = re.compile(rf"^## ({ID_FRAGMENT})\b", re.MULTILINE)  # docs/history/tasks.md の見出し

# 作業ブランチの接頭辞（`claim` が切る `feature/T-xxx`。正典「ファイル配置と設定ファイル」6.1）
FEATURE_BRANCH_PREFIX = "feature/"
FEATURE_BRANCH_PATTERN = re.compile(rf"{FEATURE_BRANCH_PREFIX}({ID_FRAGMENT})")

# 設定ファイル（`## タスク運用` 節の置き場。正典「ファイル配置と設定ファイル」）。
# `AGENTS.md` → `CLAUDE.md` の順で探し、節を持つ最初のファイルを設定とする（T-020）。
CONFIG_FILENAMES = ("AGENTS.md", "CLAUDE.md")
TASK_SECTION_HEADING = "## タスク運用"


class ConfigConflict(RuntimeError):
    """`AGENTS.md` と `CLAUDE.md` の両方に `## タスク運用` 節がある。

    どちらに従うか機械が決められないため、黙って片方を選ばない。呼ぶ側が `INVALID`
    （終了コード3）にする。
    """


def has_task_section(text: str) -> bool:
    """本文に `## タスク運用` の見出し行があるか（行頭一致）。"""
    return any(line.startswith(TASK_SECTION_HEADING) for line in text.splitlines())


def find_config_file(root: str) -> tuple[str, str] | None:
    """`## タスク運用` 節を持つファイルを `AGENTS.md` → `CLAUDE.md` の順で探す（1箇所化）。

    見つかった `(パス, 中身)` を返す。両方に節があれば `ConfigConflict`。どちらにも節が
    無ければ `None`（無い／節が無いときの扱いは呼ぶ側に委ねる。従来通り既定・MISSING）。
    """
    hits: list[tuple[str, str]] = []
    for name in CONFIG_FILENAMES:
        path = os.path.normpath(os.path.join(root, name))
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if has_task_section(text):
            hits.append((path, text))
    if len(hits) > 1:
        raise ConfigConflict(
            "AGENTS.md と CLAUDE.md の両方に「## タスク運用」節がある"
        )
    return hits[0] if hits else None
