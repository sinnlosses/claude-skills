# 未対応の指示メモ

## ユーザーから

## エージェントのドラフト

**開発フローとスキルの汎用化（2026-09-26 の調査）**

承認: 「よろしく。あと、既存の適用しているリポジトリの移行方法の実装も含めてね」

調査で分かった前提（タスク化するときに再確認する）:

- このワークフローを適用しているのは5リポジトリ。claude-skills・tsukumo が新形式、
  Git-Bulk-Maestro・gitlab-watari-dori・helm-yadokari は**まだ旧形式**（`develop/tasks.json` あり、
  `develop/task/` は0件）
- **5リポジトリとも主ブランチは `main`**。よって主ブランチの汎用化は既存リポジトリの移行を伴わない
- `- ブランチ:` の実際の値は `作業ブランチを切る`（GBM）、`切らない。直接 main にコミットする`
  （gitlab-watari-dori・helm-yadokari）、`切らない（自分でブランチを切らない）`（tsukumo）、`既定`（ここ）
- `AGENTS.md` を置いているリポジトリは無い

- **主ブランチ `main` の固定をやめ、自動で決める。** `task.py` に15箇所、`ship.py` に5箇所、
  `selftest_task.py` に13箇所の `"main"` リテラルがある（`git ls-tree main`・`git show main:…`・
  `main..HEAD`・`merge --ff-only main`・`checkout -b feature/T-xxx main`・`if branch != "main"`・
  `w.branch == "main"`・`update-ref refs/heads/main`）。`master` や `trunk` のリポジトリでは
  `task claim` が即 `INVALID` になる。`ledger.py` に `base_branch(cwd)` を1つ作り全箇所をそれ経由にする。
  決め方の順は ①設定ファイルの `- 主ブランチ:` 行（保護ブランチや複数リモートの逃げ道。任意）→
  ②`git symbolic-ref --short refs/remotes/origin/HEAD` の枝名 → ③`main`・`master`・`trunk` のうち
  `git rev-parse --verify` で**実在する**もの → ④どれも無ければ `INVALID`（黙って `main` を作らない）。
  **`selftest_task.py` のリテラルを引数にして、`master` のリポジトリで一式を通すケースを1本足す**
  ところまでが完了条件（テストが `main` のままなら汎用化できたことにならない）

- **設定ファイルを `AGENTS.md` → `CLAUDE.md` の順で探す。** いま `## タスク運用` の3行を読むのは
  `task.py` の `read_branch_setting`・`ship.py` の検証コマンド読み取り・`init.py` の点検・
  maintenance-docs の `check_docs.py` の4箇所で、すべて `CLAUDE.md` 決め打ち。Claude Code 以外の
  環境で設定が読めない。**`## タスク運用` 節を持つ最初のファイル**を設定とし、両方にあれば
  `INVALID`（二重化を黙って選ばない）。読み取りは1つの関数に寄せて4箇所から呼ぶ

- **`- 送り方:` を足して、push と PR を選べるようにする。** 正典はいま「merge commit を作る運用は
  選べない。push はどのプロジェクトでもスキルからは行わない」で固定していて、PR 必須・保護ブランチの
  リポジトリでは `task ship` が使えない。先頭語を読む語彙は `ローカル`（既定＝いまの挙動）／`push`
  （ff マージ後に `git push`）／`PR`（枝を push して `gh pr create` で止め、マージは人）。
  `PR` のとき `ship` は `SHIPPED` ではなく `PR_OPENED` を返し、**未マージの枝を `UNSHIPPED` に
  しない**（次の `claim` は主ブランチから切る）。終了コードの表と自己テストに1行ずつ増える。
  **既存の3行と同じ「行を消さない」規約に入れるが、移行のあいだ行が無いのは `ローカル` として扱い、
  いきなり `INVALID` にしない**（5リポジトリが一斉に止まる）

- **置き場の定義を1箇所に集める（設定にはしない）。** `develop/task/`・`develop/direction.md` と
  その節名・`develop/retrospective.md`・`docs/history/tasks.md`・`T-\d{3,}`・`feature/` が
  `task.py`・`taskfile.py`・`init.py`・`retrospect/scripts/*.py` の5ファイルに散っている。
  WORKFLOW.md が「置き場は規約で固定する（設定で変えられない）」と決めているのは**正しい**ので、
  設定化せず `skills/task-workflow/scripts/layout.py` に定数として集約し、各所はそこから読む。
  汎用性の中身は「設定できること」ではなく「1箇所直せば全部追随すること」で足りる。
  `scripts/check_repo.py` に「スクリプトにこれらのリテラルが直書きされていない」検査を1つ足して戻らないようにする。
  **tsukumo の `src/shared/task-summary.ts` も `develop/task/` を自分で読んでいる**ので、
  WORKFLOW.md「両方のテストに写す」に従って tsukumo 側の追随タスクも要る

- **`docs/` の構造への依存を引数で開ける。** maintenance-docs の `check_docs.py` は `docs/`・
  索引 `docs/README.md`・`docs/adr/`・`docs/research/`・`docs/history/`・`docs/history/maintenance/`・
  `README.md`・`CLAUDE.md` を42箇所で前提にしている。既にある `--skills-dir` と同じ形で
  `--docs-dir`（既定 `docs`）・`--index`（既定 `README.md`）を足す。あわせて domain-modeling の
  `CONTEXT.md`・`docs/adr/` にも、research と architecture-proposal にある
  「ユーザーが場所を指定したらそれに従う」の1文を入れる（この2つだけ逃げ道が無い）

- **スキルの依存を宣言して、`install.sh` が一緒に張る。** next-task・plan-tasks・list-tasks・
  retrospect・setup-tasks は `${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py` を打つので、
  **兄弟スキルとして `task-workflow` が入っていることが前提**なのに、それはどこにも宣言されていない。
  `next-task` だけ入れると実行時に「そんなファイルは無い」で初めて壊れる。frontmatter に
  `requires: task-workflow` を足し、`install.sh` がそれを読んで依存も張る（または警告する）。
  各 SKILL.md の手順0に「`task.py` が無ければ `MISSING` として止まる」を足す。あわせて
  `install.sh` は `$HOME/.claude/skills` 決め打ちをやめて `CLAUDE_CONFIG_DIR` を尊重し、
  `--dest DIR` とスキル名を引数で絞る口を足す。`retrospect/scripts/transcript.py` の
  `~/.claude/projects` も `CLAUDE_CONFIG_DIR` → `~/.claude` の順で探す（無ければ材料が1つ減るだけ、はそのまま）

- **既存リポジトリの移行を実装する（コマンドにする。手順書で済ませない）。** `task.py` に
  `config-doctor`（`--fix` / `--dry-run`）を足す。見るのは ①主ブランチが何に決まったか（①〜③の
  どの根拠で決まったか）②設定ファイルは `AGENTS.md` か `CLAUDE.md` か、二重になっていないか
  ③`## タスク運用` の3行＋`- 送り方:` の有無 ④旧形式（`develop/tasks.json`）が残っていないか。
  出力は検査1つに1行のタブ区切り、終了コードは 0（全部OK）／1（直せる差分あり）／3（`INVALID`）。
  **`--fix` が書き換えるのは `- ブランチ:` の次に `- 送り方: ローカル` を1行足すことだけ**で、
  既存行・節の文章には触らない（`init.py` の「CLAUDE.md は点検するだけで書かない」方針から外れる
  のはこの1行に限る。検証コマンドの選定のような判断を機械にさせない）。
  **旧形式が残っているリポジトリでは順番が要る**: `task migrate` が先、`config-doctor --fix` が後
  （`migrate` は `tasks.json` と `progress.md` だけを触り CLAUDE.md には触らないので独立だが、
  CLAUDE.md の本文に残っている `develop/tasks.json` の記述を直すのは移行後）。
  完了条件は**5リポジトリすべてで `config-doctor` が 0 で通ること**。claude-skills 以外は別リポジトリ
  なので、各リポジトリのコミットをタスクの `## 結果` に書く（push はしない）

- **入れる順番**（この順で別タスクにする）: ①主ブランチの自動判定（単独で完結し、`master` の
  リポジトリが即使えるようになる。`opus`）→ ②依存宣言と `install.sh`（他と干渉しない。`sonnet`）→
  ③`layout.py` への集約（純粋なリファクタ。検査つき。`sonnet`）→ ④`AGENTS.md` と `- 送り方:`
  （正典・終了コードの表・自己テスト・maintenance-docs まで波及するので最後。`opus`）→
  ⑤`config-doctor` と5リポジトリの移行（②〜④が入ってから。`sonnet`）

- **汎用化しないと決めたもの**（タスクにしない。判断だけ残す）:
  `difficulty` の値が実在のモデル名（`haiku`/`sonnet`/`opus`）なのは、語彙を「軽/中/重」に変えると
  台帳・スキル・tsukumo の表示まで動くので**変えない**。代わりに WORKFLOW.md に「3段 → 実際の
  model 名」の対応表を1つ置き、ラインナップが変わったらその表だけ直す。
  設定の語彙が日本語（`## タスク運用`・`既定`・`切らない`）なのは、英語化が `AGENTS.md` 対応と
  衝突する別の大仕事なので**いま混ぜない**。`scripts/check_repo.py` は claude-skills 自身の検査で
  汎用化の対象外。`python3` 直打ちは実害が出ていないので、出たときに `PYTHON` 環境変数で足りる

- **`init.py` の `check_direction` が `###` 見出しで数えるのをやめてしまう。** このドラフトを
  書いていて踏んだ。`develop/direction.md` の `## エージェントのドラフト` の中に `###` の小見出しを
  置くと、`elif l.startswith("#"): current = None`（`skills/task-workflow/scripts/init.py`）が
  そこで節から出たと判断し、**以降の本文を1行も数えない**。結果 `PENDING` ではなく
  `OK: 未対応の指示は無い` が出て、`/plan-tasks` の入口の検知が黙って外れる。リセットするのは
  `## ` で始まる行だけにする（`###` 以下は節の中の小見出しとして数える）。自己テストに
  「`###` を含むドラフトが `PENDING` になる」を1本足す
