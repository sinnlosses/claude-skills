#!/bin/sh
# skills/ 配下の各スキルを張る先にシンボリックリンクする。
#
# - 張る先は `--dest DIR` → `CLAUDE_CONFIG_DIR`（設定されていればその下の `skills/`）→
#   `$HOME/.claude/skills` の順で決める
# - `--dest` の後ろに残った引数はスキル名で、渡せば対象を絞る（無ければ従来どおり全件）
# - 既にこのリポジトリを指すリンクは張り替える
# - **実ディレクトリ・他所を指すリンクは触らず警告する**。`ln -sfn` は相手が実ディレクトリだと
#   エラーにならず *その中に* リンクを作り（`<name>/<name>`）、壊れたスキルが黙って生まれる
# - このリポジトリを指していたのに解決できなくなったリンク（スキルを消した・改名した跡）は消す。
#   **対象を絞ったときはこの掃除を走らせない**（対象外のスキルを消さないため）
set -e
here=$(cd "$(dirname "$0")" && pwd)

if [ -n "$CLAUDE_CONFIG_DIR" ]; then
  dest="$CLAUDE_CONFIG_DIR/skills"
else
  dest="$HOME/.claude/skills"
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --dest)
      shift
      if [ $# -eq 0 ]; then
        echo "--dest には値が要ります" >&2
        exit 2
      fi
      dest="$1"
      shift
      ;;
    --dest=*)
      dest="${1#--dest=}"
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "unknown option: $1" >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

filtered=0
[ $# -gt 0 ] && filtered=1

mkdir -p "$dest"
warned=0

for d in "$here"/skills/*/; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  if [ "$filtered" -eq 1 ]; then
    match=0
    for want in "$@"; do
      [ "$n" = "$want" ] && match=1 && break
    done
    [ "$match" -eq 1 ] || continue
  fi
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

if [ "$filtered" -eq 0 ]; then
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
fi

[ "$warned" -eq 0 ] || echo "※ skipped があります。上の理由を確認してから手で片付けてください。" >&2
