# claude-skills

Claude Code のユーザー単位スキル（`~/.claude/skills/`）のソース。各スキルは `skills/<name>/` に
置き、`./install.sh` で `~/.claude/skills/<name>` へシンボリックリンクを張る
（実ディレクトリや他所を指すリンクがあれば触らず警告し、消したスキルの残骸は掃除する）。
ここを直接 `~/.claude/skills` にしないのは、Claude Code が `~/.claude/skills/synced/` を
claude.ai 同期用に予約していて、git 管理下に混ざるのを避けるため。

## 由来

全19スキル。`skills/` にあるものが全てで、この一覧がその索引。

- [mattpocock/skills](https://github.com/mattpocock/skills) を日本語化したもの（10件）:
  `code-review` `codebase-design` `diagnosing-bugs` `domain-modeling` `grilling`
  `grill-with-docs` `implement` `research` `resolving-merge-conflicts` `tdd`
- [anthropics/skills](https://github.com/anthropics/skills) を日本語化したもの（3件。Apache-2.0。
  各スキルの `LICENSE.txt` を同梱）: `frontend-design` `webapp-testing` `skill-creator`
- 自作（6件）: `architecture-proposal`（様式とディレクトリ構造の提案書を書く）と、
  `develop/` 配下でタスクを管理する運用の `task-workflow`（正典・参照専用）
  `setup-tasks` `next-task` `plan-tasks` `list-tasks`

翻訳の方針: **散文とコメントは日本語にし、コード例・スキーマ・識別子・URL・引用文献は原文のまま**
残す。スキル同士の相互参照は**スキル名で書く**（`~/.claude/skills/...` の絶対パスを埋めない。
リポジトリを別の場所に置くと壊れるため）。

## 外部依存

- `webapp-testing` は **Python + Playwright** を要求する（`scripts/` と `examples/` が
  Python スクリプト）。使う前に `pip install playwright && playwright install chromium`
- `skill-creator` の `scripts/` `eval-viewer/`、`architecture-proposal` の
  `scripts/import_edges.py`、`task-workflow` の `scripts/` も Python（標準ライブラリのみ）。
  SKILL.md を読むだけなら不要で、実際にスクリプトを走らせるときにだけ要る

## プロジェクト側に要るもの

タスク系スキルを使うプロジェクトは、`develop/tasks.json` `develop/progress.md`
`develop/direction.md` を置き、検証コマンドと整形コマンドを CLAUDE.md の「## タスク運用」節に
書く。**用意するのは `/setup-tasks`**（既にあるファイルは上書きしない）。置き場と節の形は
`skills/task-workflow/WORKFLOW.md`「ファイル配置と CLAUDE.md」。

## 検証

```sh
./check.sh
```

1. `install.sh` の構文、2. `skills/task-workflow/scripts/` の自己テスト
（`selftest.py`。判定と転記の経路を実ファイルで通す）、3. リポジトリの整合
（`scripts/check_repo.py`。frontmatter の `name` とディレクトリ名の一致、この README の
由来一覧と `skills/` の一致、`${CLAUDE_SKILL_DIR}` で書かれた参照先の実在、スキル名の
相互参照の実在）。**由来の一覧が索引なので、スキルを足したり消したりしたらここも直す**
（直し忘れは `./check.sh` が落として教える）。標準ライブラリだけで動く。

## 制約

- ユーザー単位スキルはプロジェクト単位の同名スキルより優先される。プロジェクト側で同名の
  スキルを置いても効かないので、プロジェクト差分は CLAUDE.md の「## タスク運用」節で表す
- ユーザー単位スキルはクラウド/Web セッションには同期されない
- SKILL.md 内の `` !`コマンド` `` はスキル読み込み時に実行され、非0で終わるとスキル全体が
  失敗する。`/next-task` と `/plan-tasks` が CLAUDE.md の「## タスク運用」節を読む箇所は、
  節が無くても非0で終わらないよう `2>/dev/null | grep . || echo '（…）'` でガードしてある
