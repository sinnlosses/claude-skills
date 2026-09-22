# claude-skills

Claude Code のユーザー単位スキル（`~/.claude/skills/`）のソース。各スキルは `skills/<name>/` に
置き、`./install.sh` で `~/.claude/skills/<name>` へシンボリックリンクを張る
（実ディレクトリや他所を指すリンクがあれば触らず警告し、消したスキルの残骸は掃除する）。
ここを直接 `~/.claude/skills` にしないのは、Claude Code が `~/.claude/skills/synced/` を
claude.ai 同期用に予約していて、git 管理下に混ざるのを避けるため。

## 由来

全21スキル。`skills/` にあるものが全てで、この一覧がその索引。

- [mattpocock/skills](https://github.com/mattpocock/skills) を日本語化したもの（10件）:
  `code-review` `codebase-design` `diagnosing-bugs` `domain-modeling` `grilling`
  `grill-with-docs` `implement` `research` `resolving-merge-conflicts` `tdd`
- [anthropics/skills](https://github.com/anthropics/skills) を日本語化したもの（3件。Apache-2.0。
  各スキルの `LICENSE.txt` を同梱）: `frontend-design` `webapp-testing` `skill-creator`
- 自作（8件）: `architecture-proposal`（様式とディレクトリ構造の提案書を書く）、
  `maintenance-docs`（`docs/` と CLAUDE.md がスキルの記載とズレていないか点検して直す）、
  `retrospect`（どのコミットまで振り返ったかを記録し、未振り返りのタスクから次に効く改善を
  取り出して指示メモのドラフトに積む）と、
  `develop/` 配下でタスクを管理する運用の `task-workflow`（正典・参照専用）
  `setup-tasks` `next-task` `plan-tasks` `list-tasks`

翻訳の方針: **散文とコメントは日本語にし、コード例・スキーマ・識別子・URL・引用文献は原文のまま**
残す。スキル同士の相互参照は**スキル名で書く**（`~/.claude/skills/...` の絶対パスを埋めない。
リポジトリを別の場所に置くと壊れるため）。

## 外部依存

- `webapp-testing` は **Python + Playwright** を要求する（`scripts/` と `examples/` が
  Python スクリプト）。使う前に `pip install playwright && playwright install chromium`
- `skill-creator` の `scripts/` `eval-viewer/`、`architecture-proposal` の
  `scripts/import_edges.py`、`maintenance-docs` の `scripts/check_docs.py`、
  `task-workflow` の `scripts/` も Python（標準ライブラリのみ）。
  SKILL.md を読むだけなら不要で、実際にスクリプトを走らせるときにだけ要る

## プロジェクト側に要るもの

タスク系スキルを使うプロジェクトは、`develop/tasks.json` `develop/progress.md`
`develop/direction.md` を置き、検証コマンドと整形コマンドを CLAUDE.md の「## タスク運用」節に
書く。**用意するのは `/setup-tasks`**（既にあるファイルは上書きしない）。置き場と節の形は
`skills/task-workflow/WORKFLOW.md`「ファイル配置と CLAUDE.md」。

`docs/` 系は逆に、**新規プロジェクトでは何も作らない**（遅延作成。最初に書くべき内容ができた
スキルが、そのとき作る）。育つ順序と置き場は次の「## docs/ の育て方」。

## docs/ の育て方

**最初は0件**（遅延作成）。書くべき内容ができた順に、次の梯子で呼ぶ。

1. **構造で迷ったら** → `architecture-proposal`
2. **用語がブレ始めたら** → `domain-modeling`（`CONTEXT.md`）
3. **覆すのが高くつく決定をしたら** → `domain-modeling`（ADR）
4. **調べ物をしたら** → `research`
5. **置き場や索引がズレてきたら** → `maintenance-docs`（書き足さず、位置と索引と CLAUDE.md の
   契約だけを点検して直す）

置き場は次の表のとおり（各スキルの SKILL.md に固定してある）。

| 何を書くか | 置き場 | スキル |
| --- | --- | --- |
| 様式とディレクトリ構造の提案書 | `docs/architecture-proposal.md` | `architecture-proposal` |
| 採用後の正典 | `docs/architecture.md`（提案書とは別ファイル。反映は人の作業で、このリポジトリのスキルは書かない） | — |
| 用語集 | `CONTEXT.md`（複数コンテキストなら `CONTEXT-MAP.md` と各所の `CONTEXT.md`） | `domain-modeling` |
| 決定事項（ADR） | `docs/adr/000N-*.md` | `domain-modeling` |
| 調査メモ | `docs/research/<topic>.md` | `research` |

`docs/` にファイルを足したスキル（`architecture-proposal` `domain-modeling` `research`）は、
索引 `docs/README.md` にパスと一行説明を1行足す（索引も遅延的に作るもので、空のまま
先回りして置かない）。この指示の有無は `scripts/check_repo.py` の `DOCS_WRITING_SKILLS` が検査する。

## 検証

```sh
./check.sh
```

1. `install.sh` の構文、2. `skills/task-workflow/scripts/` の自己テスト
（`selftest.py`。判定と転記の経路を実ファイルで通す）、3. リポジトリの整合
（`scripts/check_repo.py`。frontmatter の `name` とディレクトリ名の一致、この README の
由来一覧と `skills/` の一致、`${CLAUDE_SKILL_DIR}` で書かれた参照先の実在、スキル名の
相互参照の実在、`docs/` に書くスキル（`architecture-proposal` `domain-modeling` `research`。
`check_repo.py` の `DOCS_WRITING_SKILLS`）が索引 `docs/README.md` に1行足す指示を
持っていること）。**由来の一覧が索引なので、スキルを足したり消したりしたらここも直す**
（直し忘れは `./check.sh` が落として教える）。標準ライブラリだけで動く。

## 制約

- ユーザー単位スキルはプロジェクト単位の同名スキルより優先される。プロジェクト側で同名の
  スキルを置いても効かないので、プロジェクト差分は CLAUDE.md の「## タスク運用」節で表す
- ユーザー単位スキルはクラウド/Web セッションには同期されない
- SKILL.md 内の `` !`コマンド` `` はスキル読み込み時に実行され、非0で終わるとスキル全体が
  失敗する。`/next-task` と `/plan-tasks` が CLAUDE.md の「## タスク運用」節を読む箇所は、
  節が無くても非0で終わらないよう `2>/dev/null | grep . || echo '（…）'` でガードしてある
- スキルとワークフロー文書には、出力スタイル由来の呼び名（一人称・ユーザーへの呼びかけなど）
  を書かず、『ユーザー』『エージェント』で書く。出力スタイルは差し替わるため、スタイル依存の
  呼び名を使うと文書が意味を失う
