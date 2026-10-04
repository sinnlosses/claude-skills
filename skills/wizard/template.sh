#!/usr/bin/env bash
#
# ウィザードは、手作業の手順を人間に1歩ずつ案内する。
# /wizard スキルが生成した。
#
# 「STAGES」の目印より上はウィザードのライブラリなので、手で書き換えない。
# 各ステップの段階は目印より下に書く。

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# ウィザードのライブラリ: 心地よく一貫した操作感。どのウィザードでも同一。
# ──────────────────────────────────────────────────────────────────────────

if [[ -t 1 ]] && command -v tput >/dev/null 2>&1 && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  BOLD=$(tput bold); DIM=$(tput dim); RESET=$(tput sgr0)
  BLUE=$(tput setaf 4); GREEN=$(tput setaf 2); YELLOW=$(tput setaf 3); RED=$(tput setaf 1)
else
  BOLD=""; DIM=""; RESET=""; BLUE=""; GREEN=""; YELLOW=""; RED=""
fi

# 作者が、段階の節の先頭で設定する。
TOTAL_STAGES=0

_STAGE_INDEX=0
ENV_FILE="${ENV_FILE:-.env}"
WRITTEN_ENV=()    # 今回の実行で ENV_FILE に書いた KEY
WRITTEN_SECRET=() # 今回の実行で設定したシークレットの NAME
SKIPPED=()        # できなかったこと(例: gh が無い)

# _clear は端末を消去して、いまのステップだけが画面に出るようにする。
# 出力が端末でないときは何もしないので、パイプしたログは読めるまま。
_clear() {
  [[ -t 1 ]] || return 0
  if command -v tput >/dev/null 2>&1; then tput clear; else printf '\033[2J\033[3J\033[H'; fi
}

# banner "タイトル" は最初の画面を出す: このウィザードが何をするか。
banner() {
  _clear
  printf '\n%s%s  %s%s\n' "$BOLD" "$BLUE" "$1" "$RESET"
  printf '%s  全 %s 段階%s\n\n' "$DIM" "$TOTAL_STAGES" "$RESET"
  printf '%s  ブラウザの操作はあなたが行います。このウィザードが何をすればよいかを正確に伝え、\n' "$DIM"
  printf '  コピーした値を受け取ります。Ctrl-C でいつでも止められ、保存済みの値は\n'
  printf '  覚えているので、あとで再実行できます。%s\n' "$RESET"
  pause "始めますか？ (Enter で開始)"
}

# stage "名前" は画面を消去してから、段階を告げて進捗を示す。
# 消去するので、いまのステップだけが画面に残る。
stage() {
  _clear
  _STAGE_INDEX=$((_STAGE_INDEX + 1))
  printf '\n%s%s▸ 段階 %s/%s · %s%s\n' \
    "$BOLD" "$BLUE" "$_STAGE_INDEX" "$TOTAL_STAGES" "$1" "$RESET"
}

# say "..." は説明の1行をそのまま出す。
say()  { printf '  %s\n' "$1"; }
# step "..." は人間がブラウザで行う操作を示す。
step() { printf '  %s•%s %s\n' "$BLUE" "$RESET" "$1"; }
note() { printf '  %s%s%s\n' "$DIM" "$1" "$RESET"; }
warn() { printf '  %s⚠ %s%s\n' "$YELLOW" "$1" "$RESET"; }

# open_url URL は人間のブラウザで開く。WSL を含め、OS をまたいで動く。
open_url() {
  local url="$1"
  printf '  %s↗ 開きます%s %s\n' "$GREEN" "$RESET" "$url"
  { if   command -v wslview     >/dev/null 2>&1; then wslview "$url"
    elif command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$url"
    elif command -v xdg-open    >/dev/null 2>&1; then xdg-open "$url"
    elif command -v open        >/dev/null 2>&1; then open "$url"
    else warn "ブラウザを開けませんでした。手で開いてください: $url"; fi
  } >/dev/null 2>&1 || warn "ブラウザを開けませんでした。手で開いてください: $url"
}

# pause "メッセージ" は、人間が手作業を終えたと確認するまで待つ。
pause() {
  printf '  %s%s%s ' "$DIM" "${1:-Enter で続けます}" "$RESET"
  read -r _ || true
}

# confirm "質問" は y/N の関門で、yes のとき成功を返す。
confirm() {
  local reply=""
  printf '  %s? %s [y/N] ' "$YELLOW" "$1"
  read -r reply || true
  [[ "$reply" =~ ^[Yy] ]]
}

# _existing KEY: ENV_FILE にある KEY の現在の値(あれば)。
_existing() {
  [[ -f "$ENV_FILE" ]] || return 1
  local line; line=$(grep -E "^${1}=" "$ENV_FILE" | tail -n1) || return 1
  printf '%s' "${line#*=}"
}

# ask KEY "プロンプト" は値を読み取って $KEY に入れる。再実行時は、
# .env にある既存の値を既定として示す(Enter で維持)。入力は見える(秘密でない値用)。
ask() {
  local key="$1" prompt="$2" current input
  current=$(_existing "$key" || true)
  if [[ -n "$current" ]]; then
    printf '  %s%s%s %s[Enter で現在の値を維持]%s ' "$BOLD" "$prompt" "$RESET" "$DIM" "$RESET"
  else
    printf '  %s%s%s ' "$BOLD" "$prompt" "$RESET"
  fi
  read -r input || true
  [[ -z "$input" && -n "$current" ]] && input="$current"
  printf -v "$key" '%s' "$input"
}

# ask_secret KEY "プロンプト" は ask と同じだが、入力が隠れる。
ask_secret() {
  local key="$1" prompt="$2" current input
  current=$(_existing "$key" || true)
  if [[ -n "$current" ]]; then
    printf '  %s%s%s %s[Enter で現在の値を維持]%s ' "$BOLD" "$prompt" "$RESET" "$DIM" "$RESET"
  else
    printf '  %s%s%s ' "$BOLD" "$prompt" "$RESET"
  fi
  read -rs input || true
  printf '\n'
  [[ -z "$input" && -n "$current" ]] && input="$current"
  printf -v "$key" '%s' "$input"
}

# write_env KEY VALUE は KEY=VALUE を ENV_FILE に upsert する(無ければ作り、
# 既存の行は置き換える)。冪等。
write_env() {
  local key="$1" value="$2" tmp
  touch "$ENV_FILE"
  tmp=$(mktemp)
  grep -vE "^${key}=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" "$ENV_FILE"
  WRITTEN_ENV+=("$key")
  printf '  %s✓ 書き込み%s %s → %s\n' "$GREEN" "$RESET" "$key" "$ENV_FILE"
}

# set_secret NAME VALUE は gh で GitHub Actions のリポジトリシークレットを設定する。
# gh が無い・未認証のときは、警告を出して(記録して)先へ進む。
set_secret() {
  local name="$1" value="$2"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if printf '%s' "$value" | gh secret set "$name" >/dev/null 2>&1; then
      WRITTEN_SECRET+=("$name")
      printf '  %s✓ 設定%s GitHub シークレット %s\n' "$GREEN" "$RESET" "$name"
      return
    fi
  fi
  SKIPPED+=("GitHub シークレット $name (手で設定する: gh secret set $name)")
  warn "GitHub シークレット $name を飛ばしました。gh の準備ができていません。あとで設定してください"
}

# set_var NAME VALUE は GitHub Actions のリポジトリ変数(秘密でないもの)を設定する。
set_var() {
  local name="$1" value="$2"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh variable set "$name" --body "$value" >/dev/null 2>&1; then
      printf '  %s✓ 設定%s GitHub 変数 %s\n' "$GREEN" "$RESET" "$name"
      return
    fi
  fi
  SKIPPED+=("GitHub 変数 $name")
  warn "GitHub 変数 $name を飛ばしました。gh の準備ができていません。あとで設定してください"
}

# finish は画面を消去してから、設定したことすべてを締めのまとめとして示す。
finish() {
  _clear
  printf '\n%s%s  ✓ セットアップが完了しました%s\n' "$BOLD" "$GREEN" "$RESET"
  (( ${#WRITTEN_ENV[@]} ))    && note "$ENV_FILE に ${#WRITTEN_ENV[@]} 件の値を書き込みました: ${WRITTEN_ENV[*]}"
  (( ${#WRITTEN_SECRET[@]} )) && note "GitHub シークレットを ${#WRITTEN_SECRET[@]} 件設定しました: ${WRITTEN_SECRET[*]}"
  if (( ${#SKIPPED[@]} )); then
    printf '\n'; warn "手で残っている作業:"
    for s in "${SKIPPED[@]}"; do note "  - $s"; done
  fi
  printf '\n'
}

# ──────────────────────────────────────────────────────────────────────────
# STAGES: ここから下を書く。人間が踏むステップごとに stage() を1つ置く。
# 下の例は置き換える。TOTAL_STAGES は、書いた段階の数に合わせる。
# ──────────────────────────────────────────────────────────────────────────

TOTAL_STAGES=1

banner "Stripe のセットアップ"

# ── 例の段階: 本物のステップに置き換える ───────────────────────────────
stage "Stripe: API キー"
say "Stripe のテスト用キーを取得して、ローカル開発と CI のために保存します。"
open_url "https://dashboard.stripe.com/test/apikeys"
step "API keys のページで、Publishable key(pk_test_ で始まる)をコピーしてください。"
ask STRIPE_PUBLISHABLE_KEY "公開可能キーを貼り付けてください:"
step "Secret key の行で「Reveal test key」をクリックし、コピーしてください。"
ask_secret STRIPE_SECRET_KEY "シークレットキーを貼り付けてください:"
write_env STRIPE_PUBLISHABLE_KEY "$STRIPE_PUBLISHABLE_KEY"
write_env STRIPE_SECRET_KEY "$STRIPE_SECRET_KEY"
set_secret STRIPE_SECRET_KEY "$STRIPE_SECRET_KEY"   # CI にはこちらが必要
# ──────────────────────────────────────────────────────────────────────────

finish
