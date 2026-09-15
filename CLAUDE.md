# claude-skills

Claude Code のユーザー単位スキルのソース。構成と導入は [README.md](README.md)。

## タスク運用

- 検証コマンド: なし（ビルドもテストも無いリポジトリ。受け入れ判定はタスク本文の「## 完了条件」で行う）
- 整形コマンド: なし
- ブランチ: 作業ブランチを切る

`develop/tasks.json`・`develop/progress.md`・`develop/direction.md` で管理する。
指示は `develop/direction.md` に溜め、`/plan-tasks` でタスク化して `/next-task` で進める。
ルールの正典は [skills/task-workflow/WORKFLOW.md](skills/task-workflow/WORKFLOW.md)。
