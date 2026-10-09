#!/bin/sh
# install.sh と uninstall.sh の自己テスト。本物の ~/.claude には触れない。
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fails=0
check() {
  if [ "$2" -eq 0 ]; then
    echo "  ok   $1"
  else
    echo "  FAIL $1"
    fails=$((fails + 1))
  fi
}

export HOME="$tmp/home"
export CLAUDE_CONFIG_DIR="$tmp/cfg"
dest="$tmp/dest"
mkdir -p "$HOME" "$dest"
inst() { "$here/install.sh" --dest "$dest" "$@"; }
uninst() { "$here/uninstall.sh" --dest "$dest" "$@"; }

# 張る先にあらかじめ置く実ディレクトリ、他所を指すリンク、このリポジトリに無いスキルのリンク、
# このリポジトリの消えたスキルを指す切れたリンク
mkdir "$dest/grilling"
ln -s "$tmp" "$dest/tdd"
mkdir -p "$tmp/elsewhere/skills/task-workflow"
ln -s "$tmp/elsewhere" "$dest/wizard"
ln -s "$tmp/elsewhere/skills/task-workflow" "$dest/task-workflow"
ln -s "$here/skills/retrospect" "$dest/retrospect"

inst >"$tmp/out" 2>"$tmp/err"
check "全件で張る: 終了コード 0" $?
[ "$(readlink "$dest/code-review")" = "$here/skills/code-review" ]
check "全件で張る: このリポジトリのスキルが張られる" $?
[ ! -e "$dest/retrospect" ] && [ ! -L "$dest/retrospect" ]
check "全件で張る: このリポジトリを指す切れたリンクが消える" $?
[ "$(readlink "$dest/task-workflow")" = "$tmp/elsewhere/skills/task-workflow" ]
check "全件で張る: このリポジトリに無いスキルのリンクは残る" $?

uninst >"$tmp/out" 2>"$tmp/err"
check "全件で外す: 終了コード 0" $?
left=$(find "$dest" -type l -exec readlink {} \; | grep -c "^$here/" || true)
check "全件で外す: このリポジトリを指すリンクが残らない" "$left"
[ -d "$dest/grilling" ] && [ ! -L "$dest/grilling" ]
check "実ディレクトリが残る" $?
[ "$(readlink "$dest/tdd")" = "$tmp" ] && [ "$(readlink "$dest/wizard")" = "$tmp/elsewhere" ] \
  && [ "$(readlink "$dest/task-workflow")" = "$tmp/elsewhere/skills/task-workflow" ]
check "他所を指すリンクが残る" $?
grep -q "skipped grilling" "$tmp/err" && grep -q "skipped tdd" "$tmp/err"
check "残したものは警告される" $?

rm -rf "$dest"
mkdir "$dest"
inst >/dev/null 2>&1
uninst tdd >"$tmp/out" 2>"$tmp/err"
[ ! -e "$dest/tdd" ] && [ -L "$dest/code-review" ] && [ -L "$dest/dispatching-parallel-agents" ]
check "名前を渡すとそのスキルだけ消える" $?

uninst dispatching-parallel-agents >"$tmp/out" 2>"$tmp/err"
[ ! -e "$dest/dispatching-parallel-agents" ]
check "依存先を名前で外せる" $?
grep -q "warning: code-review は dispatching-parallel-agents に依存" "$tmp/err"
check "依存元が残るときに警告が出る" $?

rm -rf "$dest"
mkdir "$dest"
inst >/dev/null 2>&1
uninst code-review dispatching-parallel-agents >"$tmp/out" 2>"$tmp/err"
! grep -q "warning: code-review" "$tmp/err"
check "依存元も一緒に外せば、その依存元の警告は出ない" $?

[ "$fails" -eq 0 ] || { echo "$fails 件落ちた"; exit 1; }
