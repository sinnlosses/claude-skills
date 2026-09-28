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

# develop/direction.md とその節（正典「指示メモ」）
DIRECTION_PATH = "develop/direction.md"
SECTION_USER = "## ユーザーから"
# ドラフトを direction.md に積んでいたころの節。移し忘れを数えるためだけに残す。
LEGACY_SECTION_DRAFT = "## エージェントのドラフト"

# エージェントのドラフト（1件1ファイル。正典「指示メモ」）
DRAFT_DIR = "develop/draft"

# docs/history/tasks.md（旧形式の履歴・採番の下限。正典5.3）
HISTORY_TASKS_PATH = "docs/history/tasks.md"

# タスクID: "T-" + 3桁以上の数字（正典3.1）
ID_FRAGMENT = r"T-\d{3,}"
ID_PATTERN = re.compile(rf"^{ID_FRAGMENT}$")  # 全体一致（front matter の id・--deps の各要素）
# Beads 方式でトラッカーが github なら、タスクID は Issue 番号の `GH-<n>`（ゼロ埋めしない。正典「Beads 方式」）。
GH_ID_FRAGMENT = r"GH-\d+"
ANY_ID_FRAGMENT = rf"(?:{ID_FRAGMENT}|{GH_ID_FRAGMENT})"
ANY_ID_PATTERN = re.compile(rf"^{ANY_ID_FRAGMENT}$")  # Beads 方式の --deps・retrospect の引数
ID_SEARCH_PATTERN = re.compile(rf"\b{ANY_ID_FRAGMENT}\b")  # 文中から拾う（コミット件名・トランスクリプト）
HISTORY_HEADING_PATTERN = re.compile(rf"^## ({ID_FRAGMENT})\b", re.MULTILINE)  # docs/history/tasks.md の見出し

# 作業ブランチの接頭辞（`claim` が切る `feature/T-xxx`。正典「ファイル配置と設定ファイル」6.1）
FEATURE_BRANCH_PREFIX = "feature/"
FEATURE_BRANCH_PATTERN = re.compile(rf"{FEATURE_BRANCH_PREFIX}({ANY_ID_FRAGMENT})")

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


def read_setting_value(root: str, key: str) -> str | None:
    """設定ファイルの「## タスク運用」節にある `- <key>:` 行の値（前後の空白を落とす）。

    行が無ければ `None`。見るのは節の中だけ（別の節の同名の箇条書きを拾わない）。両方の
    ファイルに節があれば `ConfigConflict`。
    """
    found = find_config_file(root)
    if found is None:
        return None
    _path, text = found
    in_section = False
    prefix = f"- {key}:"
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.startswith(TASK_SECTION_HEADING)
            continue
        if in_section and line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def setting_word(value: str) -> str:
    """設定の値の先頭語。`` `x` `` で囲めば中身、囲まなければ最初の語を括弧・句読点の前で切る。"""
    quoted = re.search(r"`([^`]+)`", value)
    word = quoted.group(1).strip() if quoted else (value.split() or [""])[0]
    return re.split(r"[（(、。]", word)[0].strip("`").strip()


# Beads 方式の任意行（正典「Beads 方式」）。どれも無いのが既定で、無ければファイル方式のまま。
STORE_KEY = "タスクの置き場"
STORE_FILES = "develop/task"
STORE_BEADS = "beads"
TRACKER_KEY = "トラッカー"
TRACKER_VALUES = ("なし", "github", "jira")
GITHUB_PROJECT_KEY = "GitHub Project"
BACKUP_KEY = "バックアップ"


class StoreSettingError(RuntimeError):
    """`- タスクの置き場:` 行が読めない（呼ぶ側が `INVALID`・終了コード3にする）。"""


def read_store(root: str) -> str:
    """設定ファイルの `- タスクの置き場:` 行の先頭語。無ければファイル方式（`develop/task`）。"""
    value = read_setting_value(root, STORE_KEY)
    if value is None:
        return STORE_FILES
    word = setting_word(value)
    if word not in (STORE_FILES, STORE_BEADS):
        raise StoreSettingError(f"- {STORE_KEY}: の値 {word!r} を機械が読めない（{STORE_FILES} / {STORE_BEADS}）")
    return word


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
