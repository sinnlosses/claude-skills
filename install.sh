#!/bin/sh
# skills/ 配下の各スキルを、張る先にシンボリックリンクする。
#
# - 張る先は `--dest DIR` → `CLAUDE_CONFIG_DIR`（設定されていればその下の `skills/`）→
#   `$HOME/.claude/skills` の順で決める
# - `--dest` の後ろに残った引数はスキル名で、渡せば対象を絞る（無ければ従来どおり全件）
# - 既にこのリポジトリを指すリンクは張り替える
# - **実ディレクトリ・他所を指すリンクは触らず警告する**。`ln -sfn` は相手が実ディレクトリだと
#   エラーにならず *その中に* リンクを作り（`<name>/<name>`）、壊れたスキルが黙って生まれる
# - このリポジトリを指していたのに解決できなくなったリンク（スキルを消した・改名した跡）は消す。
#   **対象を絞ったときはこの掃除を走らせない**（対象外のスキルを消さないため）
# - **対象を絞ったときは依存も見る**（`skills/<name>/REQUIRES` に1行で書かれた兄弟スキル名）。
#   張る先に依存先が無ければ警告するだけで、自動では足さない（絞り込みの意図を守るため）
set -e
here=$(cd "$(dirname "$0")" && pwd)
. "$here/scripts/links.sh"

resolve_dests
parse_dest_args "$@"
shift "$parsed_args"

filtered=0
[ $# -gt 0 ] && filtered=1

mkdir -p "$dest"
warned=0
nested="中に入れ子のリンクを作らないため触らない"

for d in "$here"/skills/*/; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  if [ "$filtered" -eq 1 ]; then
    if ! name_in "$n" "$@"; then
      continue
    fi
  fi
  link="$dest/$n"
  if link_refuse "$link" "$n" "$here/skills/" "$nested"; then
    continue
  fi
  ln -sfn "${d%/}" "$link"
  echo "linked $n"
done

if [ "$filtered" -eq 0 ]; then
  prune_links "$dest" "$here/skills/"
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

[ "$warned" -eq 0 ] || echo "※ skipped があります。上の理由を確認してから手で片付けてください。" >&2
