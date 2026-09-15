# claude-skills

Claude Code のユーザー単位スキル（`~/.claude/skills/`）のソース。各スキルは `skills/<name>/` に
置き、`./install.sh` で `~/.claude/skills/<name>` へシンボリックリンクを張る。
ここを直接 `~/.claude/skills` にしないのは、Claude Code が `~/.claude/skills/synced/` を
claude.ai 同期用に予約していて、git 管理下に混ざるのを避けるため。

## 由来

- [mattpocock/skills](https://github.com/mattpocock/skills) を日本語化したもの:
  `code-review` `codebase-design` `diagnosing-bugs` `domain-modeling` `grilling`
  `grill-with-docs` `implement` `research` `resolving-merge-conflicts` `tdd`
- [anthropics/skills](https://github.com/anthropics/skills) を日本語化したもの（Apache-2.0。
  各スキルの `LICENSE.txt` を同梱）: `frontend-design` `webapp-testing` `mcp-builder`
  `skill-creator`
- [obra/superpowers](https://github.com/obra/superpowers) を日本語化したもの（MIT。
  `LICENSE.txt` を同梱）: `writing-skills`
- 自作（`develop/` 配下でタスクを管理する運用）: `task-workflow`（正典・参照専用）
  `setup-tasks` `next-task` `plan-tasks` `list-tasks`

翻訳の方針: **散文とコメントは日本語にし、コード例・スキーマ・識別子・URL・引用文献は原文のまま**
残す。`writing-skills` が参照していた superpowers 固有のスキル名（`superpowers:test-driven-development`
など）は、このリポジトリの `tdd` / `diagnosing-bugs` に読み替えてある。

## 外部依存

- `webapp-testing` は **Python + Playwright** を要求する（`scripts/` と `examples/` が
  Python スクリプト）。使う前に `pip install playwright && playwright install chromium`
- `mcp-builder` の `scripts/`（評価ハーネス）と `skill-creator` の `scripts/` `eval-viewer/`
  も Python。SKILL.md を読むだけなら不要で、実際にスクリプトを走らせるときにだけ要る

## プロジェクト側に要るもの

タスク系スキルを使うプロジェクトは、`develop/tasks.json` `develop/progress.md`
`develop/direction.md` を置き、検証コマンドと整形コマンドを CLAUDE.md の「## タスク運用」節に
書く。**用意するのは `/setup-tasks`**（既にあるファイルは上書きしない）。置き場と節の形は
`skills/task-workflow/WORKFLOW.md`「ファイル配置と CLAUDE.md」。

## 制約

- ユーザー単位スキルはプロジェクト単位の同名スキルより優先される。プロジェクト側で同名の
  スキルを置いても効かないので、プロジェクト差分は CLAUDE.md の「## タスク運用」節で表す
- ユーザー単位スキルはクラウド/Web セッションには同期されない
- SKILL.md 内の `` !`コマンド` `` はスキル読み込み時に実行され、非0で終わるとスキル全体が
  失敗する。設定ファイルの読み込みは `|| echo '{}'` でガードしてある
