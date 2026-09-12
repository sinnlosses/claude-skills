# claude-skills

Claude Code のユーザー単位スキル（`~/.claude/skills/`）のソース。各スキルは `skills/<name>/` に
置き、`./install.sh` で `~/.claude/skills/<name>` へシンボリックリンクを張る。
ここを直接 `~/.claude/skills` にしないのは、Claude Code が `~/.claude/skills/synced/` を
claude.ai 同期用に予約していて、git 管理下に混ざるのを避けるため。

## 由来

- [mattpocock/skills](https://github.com/mattpocock/skills) を日本語化したもの:
  `code-review` `codebase-design` `diagnosing-bugs` `domain-modeling` `grilling` `implement`
  `research` `resolving-merge-conflicts` `tdd`
- 自作（`develop/` 配下でタスクを管理する運用）: `task-workflow`（正典・参照専用）
  `next-task` `plan-tasks` `list-tasks`

## プロジェクト側に要るもの

タスク系4スキルを使うプロジェクトは、`develop/tasks.json` `develop/progress.md`
`develop/direction.md` を置き、検証コマンドなどプロジェクト固有の値を `develop/workflow.json`
に書く。キーと既定値は `skills/task-workflow/WORKFLOW.md`「ファイル配置と
`develop/workflow.json`」。

## 制約

- ユーザー単位スキルはプロジェクト単位の同名スキルより優先される。プロジェクト側で同名の
  スキルを置いても効かないので、プロジェクト差分は `develop/workflow.json` で表す
- ユーザー単位スキルはクラウド/Web セッションには同期されない
- SKILL.md 内の `` !`コマンド` `` はスキル読み込み時に実行され、非0で終わるとスキル全体が
  失敗する。設定ファイルの読み込みは `|| echo '{}'` でガードしてある
