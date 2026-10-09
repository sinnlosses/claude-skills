# claude-skills

Claude Code のスキルのソース。各スキルは `skills/<name>/` に置く。入れ方は2通りあり、
**どちらか一方だけ**にする（両方で入れると同じスキルが二重に見える）。

タスク運用（`tw` コマンド、`task-workflow`・`next-task`・`plan-tasks`・`list-tasks`・`setup-tasks`・
`retro`・`retrospect` のスキル、`no-delegate`・`reviewer` のエージェント定義）は
[tsukumo-plugins](https://github.com/sinnlosses/tsukumo-plugins) にあり、そちらから入れる。
運用のルールの正典は tsukumo-plugins の `skills/task-workflow/WORKFLOW.md`。
以前にこのリポジトリの `install.sh` で張った `~/.local/bin/tw`・`~/.claude/agents/no-delegate.md`・
`~/.claude/agents/reviewer.md` が claude-skills を指していたら、先に外してから tsukumo-plugins の `install.sh` を打つ。

## plugin で入れる（主な入れ方）

このリポジトリは plugin `sinnlos-skills` で、同じリポジトリが marketplace でもある。

```
/plugin marketplace add sinnlosses/claude-skills
/plugin install sinnlos-skills@sinnlos-skills
```

スキルは `sinnlos-skills:<name>` の名前で入る。

開発中は `claude --plugin-dir .`（このリポジトリの根）で読ませ、`claude plugin validate .` で検査する。
リンクで入れていた環境を plugin に切り替えるときは、先に `./uninstall.sh` でリンクを外す。

## リンクで入れる（`install.sh`）

ユーザー単位スキル（`~/.claude/skills/`）へ、`./install.sh` で `<張る先>/<name>` へシンボリックリンクを張る
（実ディレクトリや他所を指すリンクがあれば触らず警告し、消したスキルの残骸は掃除する）。
張る先は `--dest DIR` → `CLAUDE_CONFIG_DIR`（設定されていればその下の `skills/`）→
`$HOME/.claude/skills` の順で決まる。引数にスキル名を渡すと対象を絞れる（絞ったときは
残骸の掃除は走らない）。**対象を絞ったときは**、渡したスキルの `REQUIRES`（依存する兄弟スキル名を
1行ずつ書いたファイル）を読み、依存先が張る先に無ければ警告する（自動では足さない。絞り込みの
意図を裏切らないため）。ここを直接 `~/.claude/skills` にしないのは、Claude Code が
`~/.claude/skills/synced/` を claude.ai 同期用に予約していて、git 管理下に混ざるのを避けるため。

`./uninstall.sh [--dest DIR] [スキル名...]` は張ったものを外す。張る先の決め方と
リンクの判定は `scripts/links.sh` を `install.sh` と共有し、外すのは**このリポジトリを指すリンクだけ**
（実ファイル・他所を指すリンクは触らず警告する。tsukumo-plugins から張ったタスク系スキルのリンクにも
触らない）。スキル名を省けば全スキルを外し、渡せばそのスキルだけ。
外したスキルに依存するスキルが張る先に残るなら警告する。

## 由来

全23スキル。`skills/` にあるものが全てで、この一覧がその索引。

- [mattpocock/skills](https://github.com/mattpocock/skills) を日本語化したもの（14件）:
  `code-review` `codebase-design` `diagnosing-bugs` `domain-modeling` `grilling`
  `grill-with-docs` `implement` `improve-codebase-architecture` `prototype` `research`
  `resolving-merge-conflicts` `tdd` `wizard` `writing-for-agents`
- [anthropics/skills](https://github.com/anthropics/skills) を日本語化したもの（3件。Apache-2.0。
  各スキルの `LICENSE.txt` を同梱）: `frontend-design` `webapp-testing` `skill-creator`
- [openclaw/openclaw](https://github.com/openclaw/openclaw/tree/main/.agents/skills/test-audit) を
  日本語化したもの（1件。MIT。`LICENSE.txt` を同梱。openclaw 固有のコマンドとスキル参照は
  プロジェクトの `CLAUDE.md` と `code-review` への参照に置き換えた）: `test-audit`
- 自作（5件）: `architecture-proposal`（様式とディレクトリ構造の提案書を書く）、
  `dispatching-parallel-agents`（独立した問題を、問題ごとに1体のサブエージェントへ並べて起こす手順）、
  `verifying-before-completion`（完了と言う前に、主張ごとの証拠のコマンドを打って出力を読む関門）、
  `comment-audit`（コメントを種類で判定して消す・縮める・正典へ移す）、
  `maintenance-docs`（`docs/` と CLAUDE.md がスキルの記載とズレていないか点検して直す）

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
  `scripts/import_edges.py`、`maintenance-docs` の `scripts/check_docs.py` も Python
  （標準ライブラリのみ）。SKILL.md を読むだけなら不要で、実際にスクリプトを走らせるときにだけ要る
- `maintenance-docs` はタスク設定を `tw config` で読む（`tw` は tsukumo-plugins から入れる）

## プロジェクト側に要るもの

タスク運用に要るもの（`.tw/` の置き場と設定）は、tsukumo-plugins の README と
tsukumo-plugins の `skills/task-workflow/WORKFLOW.md` を見る。

`docs/` 系は、**新規プロジェクトでは何も作らない**（遅延作成。最初に書くべき内容ができた
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
./check.sh          # 変えたファイルに当たる段だけ
./check.sh --full   # 全段
./check.sh --plan   # 段を流さず、流す段と飛ばす段だけを出す
```

自己テストの段は、main との merge-base からの差分と未コミット・未追跡のファイルに当たるものだけを流す
（構文と整合はいつも流す）。当たる段は `./check.sh --plan` で見る。`check.sh` が変わったとき、`--full`、main の上、
detached HEAD、差分が取れないときは全段を流す。

1. `install.sh`・`uninstall.sh`・`scripts/links.sh` の構文
2. `install.sh`・`uninstall.sh` の自己テスト（`scripts/selftest_links.sh`。全件で張って外すとこのリポジトリを指すリンクだけが消えること、名前を渡した外し方と依存の警告を確かめる）
3. `comment-audit` の自己テスト
4. `test-audit` の自己テスト
5. `maintenance-docs` の自己テスト
6. リポジトリの整合（`scripts/check_repo.py`。frontmatter の `name` とディレクトリ名の一致、この README の由来一覧と `skills/` の一致、`${CLAUDE_SKILL_DIR}` で書かれた参照先の実在、スキル名の相互参照の実在〔tsukumo-plugins のタスク系スキルは `check_repo.py` の `EXTERNAL_SKILLS` で認める〕、`docs/` に書くスキル（`architecture-proposal` `domain-modeling` `research`。`check_repo.py` の `DOCS_WRITING_SKILLS`）が索引 `docs/README.md` に1行足す指示を持っていること、スキルに `task.py` の長い呼び方・`` `task …` `` の略記が残っていないこと）。

**由来の一覧が索引なので、スキルを足したり消したりしたらここも直す**（直し忘れは `./check.sh` が落として教える）。標準ライブラリだけで動く。

## 制約

- ユーザー単位スキルはプロジェクト単位の同名スキルより優先される。プロジェクト側で同名の
  スキルを置いても効かないので、プロジェクト差分は `.tw/config.toml` で表す
- ユーザー単位スキルはクラウド/Web セッションには同期されない
- SKILL.md 内の `` !`コマンド` `` はスキル読み込み時に実行され、非0で終わるとスキル全体が
  失敗する。失敗しうるコマンドは `` !`… 2>&1 || true` `` の形で書く
- スキルとワークフロー文書には、出力スタイル由来の呼び名（一人称・ユーザーへの呼びかけなど）
  を書かず、『ユーザー』『エージェント』で書く。出力スタイルは差し替わるため、スタイル依存の
  呼び名を使うと文書が意味を失う
