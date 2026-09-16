# 進捗

## 完了したこと

### 2026-09-16 利用側3プロジェクトの移行を終えた（T-005）

Git-Bulk-Maestro・helm-yadokari・tsukumo の3つとも、履歴ファイルの改名・CLAUDE.md の「## タスク運用」節・`develop/workflow.json` の削除を済ませた。各リポジトリの検証コマンドはこちらで再実行して通過を確認。**3つとも作業ブランチ上にあり、main へは未マージ**。

### 2026-09-16 ブランチ運用を正典の既定にした（T-008）

`feature/T-<タスクID>` を切り、main へ fast-forward マージしてブランチを削除するまでをタスクのゴールにした。ff できないときは rebase して再試行し、rebase がコンフリクトしたら `--no-ff` に落とさずユーザーに預ける。`CLAUDE.md` の `- ブランチ:` 行で上書きできる。

### 2026-09-16 /next-task が着手時に status を doing にするようにした（T-007）

`doing` は定義と読む側だけあって書く側が無かったので、`/next-task` に手順4を新設した。書き換えはコミットせず作業ツリーにだけ置き、異常終了で残った `doing` は自動再開せずユーザーに預ける。遷移の書き手は `WORKFLOW.md` に明記した。

### 2026-09-16 loopable の N を「聞いても解けなかったもの」に定義し直した（T-006）

`N` になる理由を「事前に聞けば解けるか」で4行の表に分け、残るのは「対話的な検証が必要」だけにした。`/plan-tasks` には `N` を付ける前に聞く手順と、聞いた結果を焼き込む `## 決まっていること（蒸し返さない）` 節を足した。

### 2026-09-16 develop/ と docs/history/ の役割を正典化し、履歴を改名した（T-004）

`develop/<名前>` が生きている状態・`docs/history/<名前>` がその履歴という規約を `WORKFLOW.md` に据え、指示の入口をファイルと会話の2つにした（会話は明示の指示のときだけ、`/loop` 下では使わない）。`tasks-archive.md` → `tasks.md`、`progress-archive.md` → `progress.md` の改名をスキル4ファイルに反映。

### 2026-09-16 README に docs/ の育て方を書いた（T-003）

新規プロジェクトでは何も作らない（遅延作成）ところから、`architecture-proposal` → `domain-modeling`（CONTEXT.md → ADR）→ `research` の順に呼ぶ梯子と、T-002 で固定した置き場の表を `README.md` に足した。参照はスキル名で書き、絶対パスは埋めていない。

## 未解決

- なし

## 注意

- T-005 の成果は3リポジトリとも**作業ブランチに置いたままで main へマージしていない**（承認の範囲が「作業ブランチにコミットしてよい」だったため）。ブランチ名は3つとも `chore/docs-history-rename-workflow-cleanup`（Git-Bulk-Maestro のみ同名で `a02cac4`）。取り込みはユーザーの判断
- 3リポジトリとも `docs/workflow.md` に `develop/workflow.json` の値の表が残っている。Git-Bulk-Maestro のみ承認を得て削除済みで、helm-yadokari と tsukumo は範囲外として触っていない
- ブランチ運用は T-008 で `feature/T-<タスクID>` + main への ff マージ + ブランチ削除に変わる。T-008 が done になるまでは `CLAUDE.md` の `- ブランチ: 作業ブランチを切る` が有効
