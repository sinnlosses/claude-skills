# claude-skills

Claude Code のユーザー単位スキルのソース。構成と導入は [README.md](README.md)。

## タスク運用

- 検証コマンド: `./check.sh`（構文とリポジトリの整合はいつも、各スキルの自己テストは変えたファイルに当たるものだけ。`./check.sh --full` で全段。受け入れ判定に使う）
- 整形コマンド: なし
- ブランチ: 既定
- タスクの置き場: beads

タスクは Beads（`.beads`。git の外で、`tw show` で読む）と `develop/direction.md` で管理する。
指示は `develop/direction.md` に溜め、`/plan-tasks` でタスク化して `/next-task` で進める。
ルールの正典は [skills/task-workflow/WORKFLOW.md](skills/task-workflow/WORKFLOW.md)。
