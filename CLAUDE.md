# claude-skills

Claude Code のユーザー単位スキルのソース。構成と導入は [README.md](README.md)。

## タスク運用

- 検証コマンド: `./check.sh`（install.sh の構文 → task-workflow スクリプトの自己テスト → リポジトリの整合。受け入れ判定に使う）
- 整形コマンド: なし
- ブランチ: 作業ブランチを切る

`develop/tasks.json`・`develop/progress.md`・`develop/direction.md` で管理する。
指示は `develop/direction.md` に溜め、`/plan-tasks` でタスク化して `/next-task` で進める。
ルールの正典は [skills/task-workflow/WORKFLOW.md](skills/task-workflow/WORKFLOW.md)。
