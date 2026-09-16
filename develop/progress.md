# 進捗

## 完了したこと

### 2026-09-16 loopable の N を「聞いても解けなかったもの」に定義し直した（T-006）

`N` になる理由を「事前に聞けば解けるか」で4行の表に分け、残るのは「対話的な検証が必要」だけにした。`/plan-tasks` には `N` を付ける前に聞く手順と、聞いた結果を焼き込む `## 決まっていること（蒸し返さない）` 節を足した。

### 2026-09-16 develop/ と docs/history/ の役割を正典化し、履歴を改名した（T-004）

`develop/<名前>` が生きている状態・`docs/history/<名前>` がその履歴という規約を `WORKFLOW.md` に据え、指示の入口をファイルと会話の2つにした（会話は明示の指示のときだけ、`/loop` 下では使わない）。`tasks-archive.md` → `tasks.md`、`progress-archive.md` → `progress.md` の改名をスキル4ファイルに反映。

### 2026-09-16 README に docs/ の育て方を書いた（T-003）

新規プロジェクトでは何も作らない（遅延作成）ところから、`architecture-proposal` → `domain-modeling`（CONTEXT.md → ADR）→ `research` の順に呼ぶ梯子と、T-002 で固定した置き場の表を `README.md` に足した。参照はスキル名で書き、絶対パスは埋めていない。

### 2026-09-16 docs/ の置き場を規約で固定し、索引の検査を足した（T-002）

提案書（`docs/architecture-proposal.md`）と採用後の正典（`docs/architecture.md`）を別ファイルに分け、調査メモを `docs/research/<topic>.md` に固定。`check_repo.py` に「索引に1行足す指示を持っているか」の検査を追加し、落ちることを実測した。

### 2026-09-16 /next-task が direction.md で止まらないようにした（T-001）

未タスク化の指示が残っていても `READY` な `todo` は進め、`READY` が0件のときだけ `/plan-tasks` を促す形に変えた。指示の有無と行数は完了報告に添える。`./check.sh` 通過。

## 未解決

- なし

## 注意

- T-005 は3リポジトリ中 Git-Bulk-Maestro だけ完了（`a02cac4`、push なし）。helm-yadokari と tsukumo は 2026-09-16 時点で別セッションが作業中（未コミット33件ずつ）のため着手していない。詳細と再開時の手掛かりは T-005 の本文「## 進捗」に書いた
- `develop/workflow.json` の廃止が未反映なのは helm-yadokari と tsukumo の2つ（Git-Bulk-Maestro は `a02cac4` で移行済み）。2つとも `workflow.json` が残り、CLAUDE.md に `- 検証コマンド:` の行が無い。今は `/next-task` のフォールバックが別の節から拾って動いている。移行は T-005。
- ブランチ運用は T-008 で `feature/T-<タスクID>` + main への ff マージ + ブランチ削除に変わる。T-008 が done になるまでは `CLAUDE.md` の `- ブランチ: 作業ブランチを切る` が有効
