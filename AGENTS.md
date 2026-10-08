# claude-skills

Claude Code のユーザー単位スキルのソース。構成と導入は [README.md](README.md)。

## タスク運用

設定は `.tw/config.toml`（検証コマンドは `./check.sh`。構文とリポジトリの整合はいつも、各スキルの自己テストは変えたファイルに当たるものだけ。`./check.sh --full` で全段。受け入れ判定に使う）。
タスクは Beads（`.beads`。git の外で、`tw show` で読む）と `.tw/direction.md` で管理する。
指示は `.tw/direction.md` に溜め、`/plan-tasks` でタスク化して `/next-task` で進める。
ルールの正典は [skills/task-workflow/WORKFLOW.md](skills/task-workflow/WORKFLOW.md)。
