# 進捗

## 完了したこと

### 2026-09-16 /next-task が direction.md で止まらないようにした（T-001）

未タスク化の指示が残っていても `READY` な `todo` は進め、`READY` が0件のときだけ `/plan-tasks` を促す形に変えた。指示の有無と行数は完了報告に添える。`./check.sh` 通過。

## 未解決

- T-002 の提案書の置き場: 指示メモは `docs/architecture.md` と書いているが、`architecture-proposal` は「既存の設計書（正典）を直接書き換えない」と明記していて、`evals.json` は `docs/architecture.md` を既存の設計書の例として扱っている。`docs/architecture-proposal.md` に固定するほうが整合するので、着手時にユーザーへ確認する

## 注意

- 利用側3プロジェクト（Git-Bulk-Maestro・helm-yadokari・tsukumo）は、`develop/workflow.json` の廃止が反映されていない。3つとも `workflow.json` が残り、CLAUDE.md に `- 検証コマンド:` の行が無い。今は `/next-task` のフォールバックが別の節から拾って動いている。移行は T-005。
