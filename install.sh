#!/bin/sh
# skills/ 配下の各スキルを ~/.claude/skills/<name> にシンボリックリンクする。
#
# - 既にこのリポジトリを指すリンクは張り替える
# - **実ディレクトリ・他所を指すリンクは触らず警告する**。`ln -sfn` は相手が実ディレクトリだと
#   エラーにならず *その中に* リンクを作り（`<name>/<name>`）、壊れたスキルが黙って生まれる
# - このリポジトリを指していたのに解決できなくなったリンク（スキルを消した・改名した跡）は消す
set -e
here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.claude/skills"
mkdir -p "$dest"
warned=0

for d in "$here"/skills/*/; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  link="$dest/$n"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "skipped $n （$link が実ファイル/実ディレクトリ。中に入れ子のリンクを作らないため触らない）" >&2
    warned=1
    continue
  fi
  if [ -L "$link" ]; then
    current=$(readlink "$link")
    case "$current" in
      "$here"/skills/*) ;;  # このリポジトリのもの。張り替えてよい
      *)
        echo "skipped $n （$link は別の場所 $current を指している）" >&2
        warned=1
        continue
        ;;
    esac
  fi
  ln -sfn "${d%/}" "$link"
  echo "linked $n"
done

# 消したスキルの残骸を掃除する。**このリポジトリを指していたリンクだけ**が対象で、
# 解決できるもの・他所を指すものには触らない。
for link in "$dest"/*; do
  [ -L "$link" ] || continue
  [ -e "$link" ] && continue
  case "$(readlink "$link")" in
    "$here"/skills/*)
      rm "$link"
      echo "pruned $(basename "$link") （リンク先が無くなっていた）"
      ;;
  esac
done

[ "$warned" -eq 0 ] || echo "※ skipped があります。上の理由を確認してから手で片付けてください。" >&2
