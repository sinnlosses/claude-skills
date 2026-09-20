# 過去セッションの「完了したこと」

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

### 2026-09-16 docs/ の置き場を規約で固定し、索引の検査を足した（T-002）

提案書（`docs/architecture-proposal.md`）と採用後の正典（`docs/architecture.md`）を別ファイルに分け、調査メモを `docs/research/<topic>.md` に固定。`check_repo.py` に「索引に1行足す指示を持っているか」の検査を追加し、落ちることを実測した。

### 2026-09-16 /next-task が direction.md で止まらないようにした（T-001）

未タスク化の指示が残っていても `READY` な `todo` は進め、`READY` が0件のときだけ `/plan-tasks` を促す形に変えた。指示の有無と行数は完了報告に添える。`./check.sh` 通過。

