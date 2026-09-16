# 過去セッションの「完了したこと」

### 2026-09-16 docs/ の置き場を規約で固定し、索引の検査を足した（T-002）

提案書（`docs/architecture-proposal.md`）と採用後の正典（`docs/architecture.md`）を別ファイルに分け、調査メモを `docs/research/<topic>.md` に固定。`check_repo.py` に「索引に1行足す指示を持っているか」の検査を追加し、落ちることを実測した。

### 2026-09-16 /next-task が direction.md で止まらないようにした（T-001）

未タスク化の指示が残っていても `READY` な `todo` は進め、`READY` が0件のときだけ `/plan-tasks` を促す形に変えた。指示の有無と行数は完了報告に添える。`./check.sh` 通過。

