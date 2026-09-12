#!/bin/sh
# skills/ 配下の各スキルを ~/.claude/skills/<name> にシンボリックリンクする（既存のリンクは張り替える）。
set -e
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HOME/.claude/skills"
for d in "$here"/skills/*/; do
  n=$(basename "$d")
  ln -sfn "${d%/}" "$HOME/.claude/skills/$n"
  echo "linked $n"
done
