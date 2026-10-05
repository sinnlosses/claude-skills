# claude-skills

Claude Code のユーザー単位スキル（`~/.claude/skills/`）のソース。各スキルは `skills/<name>/` に
置き、`./install.sh` で `<張る先>/<name>` へシンボリックリンクを張る
（実ディレクトリや他所を指すリンクがあれば触らず警告し、消したスキルの残骸は掃除する）。
張る先は `--dest DIR` → `CLAUDE_CONFIG_DIR`（設定されていればその下の `skills/`）→
`$HOME/.claude/skills` の順で決まる。引数にスキル名を渡すと対象を絞れる（絞ったときは
残骸の掃除は走らない）。**対象を絞ったときは**、渡したスキルの `REQUIRES`（依存する兄弟スキル名を
1行ずつ書いたファイル）を読み、依存先が張る先に無ければ警告する（自動では足さない。絞り込みの
意図を裏切らないため）。ここを直接 `~/.claude/skills` にしないのは、Claude Code が
`~/.claude/skills/synced/` を claude.ai 同期用に予約していて、git 管理下に混ざるのを避けるため。

`./uninstall.sh [--dest DIR] [--bin-dir DIR] [スキル名...]` は張ったものを外す。張る先の決め方と
リンクの判定は `scripts/links.sh` を `install.sh` と共有し、外すのは**このリポジトリを指すリンクだけ**
（実ファイル・他所を指すリンクは触らず警告する）。スキル名を省けば全スキルと `agents/` のリンクと `tw`
を外し、渡せばそのスキルだけ（`task-workflow` を含むときは `tw` も。エージェント定義は残す）。
外したスキルに依存するスキルが張る先に残るなら警告する。

`agents/` にはサブエージェントの定義（1ファイル1エージェント）を置き、`./install.sh` が同じ安全策で
`~/.claude/agents/`（`CLAUDE_CONFIG_DIR` があればその下の `agents/`）へ張る。スキル名の絞り込みは
効かず常に全件が対象。`no-delegate` は frontmatter の hooks で `tw commit-guard`・`tw handback-guard` を呼ぶので、`tw` も
張っておく（`task-workflow` を対象に含める。`tw` が無ければ hook は何もせずに通す）。`reviewer` は
読むだけのレビュアーで、書き換えの道具を持たず hook も掛けない。

`task-workflow` が対象なら、`./install.sh` はタスク運用のコマンド `tw`（`skills/task-workflow/scripts/task.py`
へのシンボリックリンク）も `--bin-dir DIR`（無ければ `~/.local/bin`）に張る。`--dest`・`CLAUDE_CONFIG_DIR`
の影響は受けない。既にある実ファイル・他所を指すリンクの `tw` は触らず警告し、張る先が PATH に無い・
別の `tw` が先に見つかるときも警告する（PATH への追加はシェルの設定で行う）。

## 由来

全28スキル。`skills/` にあるものが全てで、この一覧がその索引。

- [mattpocock/skills](https://github.com/mattpocock/skills) を日本語化したもの（15件）:
  `code-review` `codebase-design` `diagnosing-bugs` `domain-modeling` `grilling`
  `grill-with-docs` `implement` `improve-codebase-architecture` `prototype` `research`
  `resolving-merge-conflicts` `retro` `tdd` `wizard` `writing-for-agents`
  （`retro` は札・色・ドラフトの形を `retrospect` に合わせ、選ばれた改善案を `develop/draft/` に積む）
- [anthropics/skills](https://github.com/anthropics/skills) を日本語化したもの（3件。Apache-2.0。
  各スキルの `LICENSE.txt` を同梱）: `frontend-design` `webapp-testing` `skill-creator`
- [openclaw/openclaw](https://github.com/openclaw/openclaw/tree/main/.agents/skills/test-audit) を
  日本語化したもの（1件。MIT。`LICENSE.txt` を同梱。openclaw 固有のコマンドとスキル参照は
  プロジェクトの `CLAUDE.md` と `code-review` への参照に置き換えた）: `test-audit`
- 自作（9件）: `architecture-proposal`（様式とディレクトリ構造の提案書を書く）、
  `comment-audit`（コメントを種類で判定して消す・縮める・正典へ移す）、
  `maintenance-docs`（`docs/` と CLAUDE.md がスキルの記載とズレていないか点検して直す）、
  `retrospect`（`/next-task` の中で1件ごとに振り返り、兆候に当たったときと、コード・文書の変更量を
  減らせる形が見つかったときだけ次に効く改善を取り出して指示メモのドラフトに積む。正典・参照専用）と、
  `develop/` 配下でタスクを管理する運用の `task-workflow`（正典・参照専用）
  `setup-tasks` `next-task` `plan-tasks` `list-tasks`

翻訳の方針:
1. **散文とコメントは日本語にし、コード例・スキーマ・識別子・URL・引用文献は原文のまま**残す
2. スキル同士の相互参照は**スキル名で書く**（`~/.claude/skills/...` の絶対パスを埋めない。
   リポジトリを別の場所に置くと壊れるため）
3. `disable-model-invocation: true` のスキルの `description` は1文とし、トリガーになる言い回しを詰め込まない
4. スキルが**生成する成果物**（HTMLレポート・翻訳ドキュメントなど）の文章も日本語にする。
   ただし識別子・色や値に対応づいた語は原文のまま

## 外部依存

- `webapp-testing` は **Python + Playwright** を要求する（`scripts/` と `examples/` が
  Python スクリプト）。使う前に `pip install playwright && playwright install chromium`
- `skill-creator` の `scripts/` `eval-viewer/`、`architecture-proposal` の
  `scripts/import_edges.py`、`maintenance-docs` の `scripts/check_docs.py`、
  `task-workflow` の `scripts/` も Python（標準ライブラリのみ）。
  SKILL.md を読むだけなら不要で、実際にスクリプトを走らせるときにだけ要る
- タスク系スキルを **Beads 方式**（`- タスクの置き場: beads`）で使うプロジェクトは `bd`（Beads）と
  Dolt、トラッカーが `github` なら `gh` も要る（`skills/task-workflow/WORKFLOW.md`「Beads 方式」）。
  既定のファイル方式では要らない

## プロジェクト側に要るもの

タスク系スキルを使うプロジェクトは、`develop/direction.md` を置き（タスクは `develop/task/` に
1件1ファイルで `tw new` が作る）、検証コマンド・整形コマンド・ブランチの3行を CLAUDE.md の
「## タスク運用」節に書く。**用意するのは `/setup-tasks`**（既にあるファイルは上書きしない）。
置き場と節の形は `skills/task-workflow/WORKFLOW.md`「ファイル配置と設定ファイル（AGENTS.md → CLAUDE.md の順）」。旧形式
（`develop/tasks.json`）のプロジェクトでは、タスク系のスキルが `LEGACY` で止まって
`tw migrate` を案内する（同「旧形式からの移行」）。「## タスク運用」節に
`- タスクの置き場: beads` を足したプロジェクトは、錠と本文・履歴を Beads に置く（同「Beads 方式」）。

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

1. `install.sh`・`uninstall.sh`・`scripts/links.sh` の構文、2. 一時ディレクトリを張る先にした
`install.sh`・`uninstall.sh` の自己テスト（`scripts/selftest_links.sh`。全件で張って外すとこのリポジトリを
指すリンクだけが消えること、名前を渡した外し方と依存の警告を確かめる）、3. `skills/task-workflow/scripts/` の自己テスト
（`selftest.py` が旧形式の読み取りと `init.py`、`selftest_task.py` が `tw` コマンドを一時リポジトリと
作業ツリー2本で通す。`selftest_beads.py` は Beads 方式を本物の `bd` と偽の `gh`・トラッカー同期で通し、
`bd` が無ければ飛ばす）、4. リポジトリの整合
（`scripts/check_repo.py`。frontmatter の `name` とディレクトリ名の一致、この README の
由来一覧と `skills/` の一致、`${CLAUDE_SKILL_DIR}` で書かれた参照先の実在、スキル名の
相互参照の実在、`docs/` に書くスキル（`architecture-proposal` `domain-modeling` `research`。
`check_repo.py` の `DOCS_WRITING_SKILLS`）が索引 `docs/README.md` に1行足す指示を
持っていること、`agents/*.md` の frontmatter の `name` とファイル名の一致・`description` の有無、`tw` の張り先の
`task.py` が実行できることとスキルに `task.py` の長い呼び方・`` `task …` `` の略記が残っていないこと）。
**由来の一覧が索引なので、スキルを足したり消したりしたらここも直す**
（直し忘れは `./check.sh` が落として教える）。標準ライブラリだけで動く。

## 制約

- ユーザー単位スキルはプロジェクト単位の同名スキルより優先される。プロジェクト側で同名の
  スキルを置いても効かないので、プロジェクト差分は設定ファイル（AGENTS.md → CLAUDE.md）の「## タスク運用」節で表す
- ユーザー単位スキルはクラウド/Web セッションには同期されない
- SKILL.md 内の `` !`コマンド` `` はスキル読み込み時に実行され、非0で終わるとスキル全体が
  失敗する。`/next-task` と `/plan-tasks` が設定ファイル（AGENTS.md → CLAUDE.md）の「## タスク運用」節を読む箇所は、
  git の外や節が無いときも非0で終わらないよう、結果を変数に溜めて `if` で出し分けてガードしてある
- スキルとワークフロー文書には、出力スタイル由来の呼び名（一人称・ユーザーへの呼びかけなど）
  を書かず、『ユーザー』『エージェント』で書く。出力スタイルは差し替わるため、スタイル依存の
  呼び名を使うと文書が意味を失う
