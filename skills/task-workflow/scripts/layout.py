"""置き場と ID の形の正典（値そのもの）。

正典は WORKFLOW.md「ファイル配置と CLAUDE.md」。**置き場は規約で固定**（設定で変えられない）
と決めているのはそこで、ここは同じ値がスクリプトに何箇所も直書きされているのをやめるための
1箇所化（設定ファイルにしない・値は変えない）。ここを直せば `task.py`・`taskfile.py`・
`init.py`・`legacy.py`・`retrospect` の同梱スクリプトが全部追随する。

`retrospect` は別スキルなので、`skills/retrospect/scripts/*.py` は `sys.path` にこのファイルの
ディレクトリを足してから `import layout` する（`selftest.py`・`selftest_task.py` が兄弟モジュールを
素の `import` 名で読むのと同じ形）。`task-workflow` が入っていない環境では `ImportError` で
止まる（データの不備ではなく環境の不備として扱う。他のスクリプトの docstring の「環境の故障」の
扱いと同じ）。
"""

from __future__ import annotations

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

# 作業ブランチの接頭辞（`claim` が切る `feature/T-xxx`。正典「ファイル配置と CLAUDE.md」6.1）
FEATURE_BRANCH_PREFIX = "feature/"
FEATURE_BRANCH_PATTERN = re.compile(rf"{FEATURE_BRANCH_PREFIX}({ID_FRAGMENT})")
