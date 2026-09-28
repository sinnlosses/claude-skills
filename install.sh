#!/bin/sh
# skills/ 配下の各スキルと、agents/ 配下の各エージェント定義を、張る先にシンボリックリンクする。
#
# - スキルの張る先は `--dest DIR` → `CLAUDE_CONFIG_DIR`（設定されていればその下の `skills/`）→
#   `$HOME/.claude/skills` の順で決める。エージェント定義の張る先は `CLAUDE_CONFIG_DIR`
#   （設定されていればその下の `agents/`）→ `$HOME/.claude/agents` で、`--dest` とスキル名の
#   絞り込みの影響を受けない（`--dest` はスキル用の張る先を指す引数のため）。エージェント定義は
#   常に全件張り替える
# - `--dest` の後ろに残った引数はスキル名で、渡せば対象を絞る（無ければ従来どおり全件）
# - 既にこのリポジトリを指すリンクは張り替える
# - **実ディレクトリ・他所を指すリンクは触らず警告する**。`ln -sfn` は相手が実ディレクトリだと
#   エラーにならず *その中に* リンクを作り（`<name>/<name>`）、壊れたスキルが黙って生まれる
# - このリポジトリを指していたのに解決できなくなったリンク（スキルを消した・改名した跡、
#   エージェント定義を消した跡）は消す。**スキルは対象を絞ったときこの掃除を走らせない**
#   （対象外のスキルを消さないため）。エージェント定義の掃除は絞り込みの対象が無いので常に走る
# - **対象を絞ったときは依存も見る**（`skills/<name>/REQUIRES` に1行で書かれた兄弟スキル名）。
#   張る先に依存先が無ければ警告するだけで、自動では足さない（絞り込みの意図を守るため）
set -e
here=$(cd "$(dirname "$0")" && pwd)

if [ -n "$CLAUDE_CONFIG_DIR" ]; then
  dest="$CLAUDE_CONFIG_DIR/skills"
  agents_dest="$CLAUDE_CONFIG_DIR/agents"
else
  dest="$HOME/.claude/skills"
  agents_dest="$HOME/.claude/agents"
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
else
  # 対象を絞ったときだけ、依存（`skills/<name>/REQUIRES` に1行で書かれた兄弟スキル名）が
  # 張る先に無ければ警告する。**自動では足さない**（黙って対象を増やすと `--dest` や
  # 絞り込みで決めた意図に反するため）。全件張るとき（絞り込みなし）は skills/*/ を丸ごと
  # 張るので依存は自然に満たされ、この検査は要らない。
  for n in "$@"; do
    req="$here/skills/$n/REQUIRES"
    [ -f "$req" ] || continue
    while IFS= read -r dep || [ -n "$dep" ]; do
      [ -n "$dep" ] || continue
      if [ ! -e "$dest/$dep" ]; then
        echo "warning: $n は $dep に依存するが $dest/$dep が無い（$dep も引数に渡すか、先に張ってください）" >&2
        warned=1
      fi
    done < "$req"
  done
fi

# agents/ 配下の各エージェント定義（1ファイル1つ）を張る。スキル名の絞り込みは効かず常に全件。
mkdir -p "$agents_dest"

for f in "$here"/agents/*.md; do
  [ -f "$f" ] || continue
  n=$(basename "$f")
  link="$agents_dest/$n"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "skipped $n （$link が実ファイル/実ディレクトリ。中に入れ子のリンクを作らないため触らない）" >&2
    warned=1
    continue
  fi
  if [ -L "$link" ]; then
    current=$(readlink "$link")
    case "$current" in
      "$here"/agents/*) ;;  # このリポジトリのもの。張り替えてよい
      *)
        echo "skipped $n （$link は別の場所 $current を指している）" >&2
        warned=1
        continue
        ;;
    esac
  fi
  ln -sfn "$f" "$link"
  echo "linked $n"
done

# 消したエージェント定義の残骸を掃除する。このリポジトリを指していたリンクだけが対象。
for link in "$agents_dest"/*; do
  [ -L "$link" ] || continue
  [ -e "$link" ] && continue
  case "$(readlink "$link")" in
    "$here"/agents/*)
      rm "$link"
      echo "pruned $(basename "$link") （リンク先が無くなっていた）"
      ;;
  esac
done

[ "$warned" -eq 0 ] || echo "※ skipped があります。上の理由を確認してから手で片付けてください。" >&2
