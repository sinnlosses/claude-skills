移行の残り。8章の表で振り分けたら消す。

# 進捗

## 未解決

- なし

## 注意

- T-005 の成果は3リポジトリとも main へ fast-forward マージ済み（Git-Bulk-Maestro `a02cac4`、helm-yadokari `4e230fc`、tsukumo `76400f3`）。作業ブランチは削除済みで、**push はしていない**
- **タスクの成果は作業ブランチで止めず、ローカルの main へマージするまで自動でやってよい**（2026-09-16 にユーザーが指示）。他のリポジトリを触るタスクでも同じ。push は含まない
- 3リポジトリとも `docs/workflow.md` に `develop/workflow.json` の値の表が残っている。Git-Bulk-Maestro のみ承認を得て削除済みで、helm-yadokari と tsukumo は範囲外として触っていない
- ブランチ運用は T-008 で `feature/T-<タスクID>` + main への ff マージ + ブランチ削除に変わる。T-008 が done になるまでは `CLAUDE.md` の `- ブランチ: 作業ブランチを切る` が有効
