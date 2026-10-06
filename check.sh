#!/bin/sh
# このリポジトリの検証コマンド。`/next-task` が受け入れ判定に使う。
#
# 1. install.sh・uninstall.sh・scripts/links.sh の構文
# 2. install.sh・uninstall.sh の自己テスト
# 3. task-workflow のスクリプトの自己テスト
# 4. retrospect のスクリプトの自己テスト
# 5. comment-audit のスクリプトの自己テスト
# 6. next-task のスクリプトの自己テスト
# 7. リポジトリ全体の整合（frontmatter・README の索引・参照先の実在）
set -e
here=$(cd "$(dirname "$0")" && pwd)

echo "== install.sh・uninstall.sh・scripts/links.sh の構文 =="
sh -n "$here/install.sh" && sh -n "$here/uninstall.sh" && sh -n "$here/scripts/links.sh" && echo "  ok"

echo
echo "== install.sh・uninstall.sh の自己テスト =="
sh "$here/scripts/selftest_links.sh"

echo
echo "== task-workflow scripts の自己テスト =="
python3 "$here/skills/task-workflow/scripts/selftest.py"

echo
echo "== task-workflow: task コマンド（develop/task/ + 台帳）の自己テスト =="
python3 "$here/skills/task-workflow/scripts/selftest_task.py"

echo
echo "== task-workflow: task コマンド（Beads 方式。bd が無ければ飛ばす）の自己テスト =="
python3 "$here/skills/task-workflow/scripts/selftest_beads.py"

echo
echo "== retrospect scripts の自己テスト =="
python3 "$here/skills/retrospect/scripts/selftest.py"

echo
echo "== comment-audit scripts の自己テスト =="
python3 "$here/skills/comment-audit/scripts/selftest_diff_added_comment_lines.py"

echo
echo "== next-task scripts の自己テスト =="
python3 "$here/skills/next-task/scripts/selftest_review_needed.py"
python3 "$here/skills/next-task/scripts/selftest_context_size.py"

echo
echo "== リポジトリの整合 =="
python3 "$here/scripts/check_repo.py"
