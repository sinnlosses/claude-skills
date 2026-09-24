#!/bin/sh
# このリポジトリの検証コマンド。`/next-task` が受け入れ判定に使う。
#
# 1. install.sh の構文
# 2. task-workflow のスクリプトの自己テスト
# 3. リポジトリ全体の整合（frontmatter・README の索引・参照先の実在）
set -e
here=$(cd "$(dirname "$0")" && pwd)

echo "== install.sh の構文 =="
sh -n "$here/install.sh" && echo "  ok"

echo
echo "== task-workflow scripts の自己テスト =="
python3 "$here/skills/task-workflow/scripts/selftest.py"

echo
echo "== task-workflow: task コマンド（develop/task/ + 台帳）の自己テスト =="
python3 "$here/skills/task-workflow/scripts/selftest_task.py"

echo
echo "== リポジトリの整合 =="
python3 "$here/scripts/check_repo.py"
