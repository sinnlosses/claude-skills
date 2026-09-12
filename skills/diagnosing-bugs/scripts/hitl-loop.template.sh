#!/usr/bin/env bash
# 人間参加型 (Human-in-the-loop) の再現ループ。
# このファイルをコピーし、以下の手順を編集してから実行する。
# エージェントがこのスクリプトを実行し、ユーザーは自分のターミナルでプロンプトに従う。
#
# 使い方:
#   bash hitl-loop.template.sh
#
# 2つのヘルパー:
#   step "<指示内容>"             → 指示を表示し、Enterキー入力を待つ
#   capture VAR "<質問内容>"      → 質問を表示し、回答を VAR に読み込む
#
# 最後に、取得した値が KEY=VALUE の形でエージェントが解析できるように出力される。
#
# `capture` はその値をターミナルに出力し直し、エージェントがそれを読み取る。
# そのため観測結果は `capture` で取得し、サインインなどはユーザーに任せる `step` にすること。

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [完了したらEnter] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- ここから下を編集する ---------------------------------------------------------

step "http://localhost:3000 でアプリを開き、サインインしてください。"

capture ERRORED "「Export」ボタンをクリックしてください。エラーが発生しましたか？ (y/n)"

capture ERROR_MSG "エラーメッセージを貼り付けてください（なければ 'none'）:"

# --- ここから上を編集する ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'ERRORED=%s\n' "$ERRORED"
printf 'ERROR_MSG=%s\n' "$ERROR_MSG"
