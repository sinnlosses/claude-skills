---
name: next-task
description: "develop/tasks.jsonから未着手タスクを1件選んで実行し、develop/tasks.json・develop/progress.mdを更新してコミットする。ユーザーが「次のタスクを進めて」「tasks.jsonのタスクをやって」と言ったとき、または/loopと組み合わせて全タスク完了までの自動進行に使う。"
---

`develop/tasks.json` を1サイクルぶん前に進める。フィールドの定義・`difficulty` の意味・
evidence の書き方・アーカイブのトリガーは `task-workflow` スキルの `WORKFLOW.md`
（以下「正典」）にあるのでここでは繰り返さない。このスキルは**1タスク分**を実行して終わる。
全件 `done` になるまで繰り返したい場合は `/loop /next-task` として使う（`/loop` 側が
続行/停止を判断する）。

## このプロジェクトの設定（`develop/workflow.json`）

!`cat develop/workflow.json 2>/dev/null || echo '{}'`

`{}` なら既定値で動く（正典「ファイル配置と `develop/workflow.json`」）。以下で
`checkCommand`・`formatCommand`・`historyDir` と書いたところは、この設定の値に読み替える。
`develop/tasks.json` が無いプロジェクトなら、タスク運用を始めていない旨を報告して終了する
（勝手にファイルを作らない）。

## タスク本文を読み込まない

1タスクの `task` 本文は数KBある。**1件を選ぶために全件の本文を読まない**。選ぶのに要る値
（`status`・`dependencies`・`difficulty`・`loopable`・`summary`）は全部 `status.py` の TSV に
出るので、**本文を読むのは選んだ1件だけ**にする。`develop/progress.md` も同じで、このスキルが
するのは「完了したこと」の先頭への追記だけなので、全文を読まない（判定は `status.py` の
`progress` 行が出す）。

`/list-tasks` と同じ方針。tasks.json が数万文字まで育つ運用なので、ここを守るかどうかで
1サイクルのコンテキスト消費が一桁変わる。

## スクリプトが動かないとき

`status.py` / `archive.py` は `python3` を使う。**`python3` が無い・エラーで落ちる環境では、
tasks.json を全文読んで代用しない。** 節約の仕組みが死んでいることに気づけないまま、
毎サイクル数万文字を読む状態になるため。

スクリプトが `MISSING`・`EMPTY`・TSV のいずれでもない出力で終わったら、**その場で止めて
`python3` が使えない旨とエラー出力をユーザーに報告する**（`/loop` 側はこれを「続行不要」の
合図として扱う）。

## 手順

1. **見渡す**: 一覧と判定はスクリプトが出す。**`develop/tasks.json` を Read ツールで開いたり
   `cat` したりしない**（理由は下の「タスク本文を読み込まない」）。

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/status.py develop/tasks.json develop/workflow.json
   ```

   `MISSING` ならタスク運用を始めていない旨を報告して終了する。`EMPTY` なら登録されている
   タスクは0件。TSVの読み方は `/list-tasks` と同じ（列は `id / status / difficulty /
   loopable / dependencies / 着手可否 / passes / summary / summary_short`）。

   末尾の `archive` 行（`tasks.json` の判定）か `progress` 行（`progress.md` の判定）が
   `YES` なら、**着手前にアーカイブする**（正典「いつ移すか（トリガー）」）。転記は判断を
   含まないので手で書き写さず、スクリプトに任せる:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/archive.py develop/tasks.json develop/workflow.json
   ```

   出力の `MOVED` 行に、移したタスクIDとファイルサイズの前後が出る。完了報告にそのまま載せる。

   あわせて `develop/direction.md` を見る。見出し行以外に中身があれば
   （`grep -v '^#' develop/direction.md | grep -v '^\s*$'` が空でなければ）、**未タスク化の
   指示が残っている**。タスクを実行せず、`/plan-tasks` でのタスク化が先だと報告して終了する
   （`/loop` 側はこれを「続行不要」の合図として扱う）。分解は方針決めを含むので、このスキルが
   その場で代行しない。

2. **選ぶ**: 手順1のTSVで `着手可否` が `READY` の行から1件選ぶ（`status: "todo"` かつ
   依存が全て解決済み。`tasks.json` に存在しない依存＝アーカイブ済み＝完了扱いは
   スクリプトが織り込み済み）。`READY` が無ければ（全件 done、または残りが全て `BLOCKED:`）
   その旨を報告して終了する（`/loop` 側はこれを「続行不要」の合図として扱う）。

   選んだら、**その1件の本文だけ**を読む:

   ```bash
   python3 -c "import json,sys; print([t for t in json.load(open('develop/tasks.json')) if t['id']==sys.argv[1]][0]['task'])" T-XXX
   ```

   **`/loop` から回されているときは `loopable` が `"N"` のタスクを選ばない**
   （正典「loopable」。フィールドが無いタスクは `"Y"` 扱い）。残りが `"N"` だけになったら
   「ユーザーの判断が必要なタスクのみが残っている」と、そのタスクIDを添えて報告して終了する
   （`/loop` 側はこれを「続行不要」の合図として扱う）。**ユーザーが直接 `/next-task` を
   呼んだときは `"N"` も選んでよい**。その場合は着手前に、ユーザーの判断が要る点を先に確認する。

3. **ブランチ**: プロジェクトの `CLAUDE.md` のGit運用に従う（作業ブランチを切るかどうかは
   そこで決まる。書いてなければデフォルトブランチで作業する）。

4. **実行**: Agentツールで、選んだタスクの `difficulty` と同じモデルを指定した
   サブエージェントに委譲する（正典「difficulty に応じたモデルの切り替え方」）:
   - `haiku` / `sonnet` / `opus` のいずれでも委譲する。**メインセッションが今どのモデルで
     動いているかは判断材料にしない**
   - `tasks.json` の `task` 本文だけで作業が完結するよう、対象ファイル・完了条件・
     `checkCommand` を通すことを明記して渡す（サブエージェントはまっさらな文脈で起動する）
   - ユーザーへの確認が必要な判断・会話中の文脈に依存する判断は委譲しない。これは
     モデル選択とは別の軸の話で、登録時の見立ては `loopable` に入っている。着手して
     初めて分かった場合は `loopable` を `"N"` に直し、委譲せずユーザーに預けて次のタスクへ進む
   - 着手後に想定より判断が重いと分かったら、`difficulty` を上げてから改めて進める

5. **受け入れ**: 委譲した場合は完了報告をそのまま信用せず、自分で差分（`git diff`）を確認し、
   `formatCommand` があれば実行してから `checkCommand` を実行して通ることを確かめる。
   `checkCommand` が未設定なら、タスク本文の完了条件を1つずつ目視で確かめ、報告に
   「検証コマンド未設定」と書く。方針からズレた実装（例: コメントの動機がすり替わっている、
   命名が既存規約と衝突する）があればその場で直してから次に進む。

6. **記録してコミット**: `develop/tasks.json` の対象タスクの `status`/`passes`/`evidence` を
   更新する（evidence は3行以内、後から検証できる形で。正典「良いevidenceの書き方」）。
   `develop/progress.md` の「完了したこと」に、**そのタスクの小節を1つ、節の先頭に足す**
   （`### YYYY-MM-DD 何をしたか（T-xxx）` の形で、中身は1〜2文）。**既にある小節に
   混ぜず、上に積む**——並びが「新しい順」であることにアーカイブが依存していて、
   下に足すとスクリプトが `ERROR` を返して止まる（正典「progress.md の構成」）。

   1タスク＝1コミットとし、件名の先頭にタスクIDを置く（正典「コミットメッセージ」）。コミットメッセージの末尾は現在のセッションの
   attribution 指示（Co-Authored-By 等）に従う。

7. **push はしない**: 外部への反映は明示的に頼まれたときだけ行う。このスキルはコミットまでで止める。

## 完了報告のフォーマット

最後に必ず次を1行ずつ示す（`/loop` が続行判断に使う）:

- 今回 done にしたタスクID
- `checkCommand` の結果（ファイル数・テスト件数。未設定なら「検証コマンド未設定」）
- 残りの `todo` 件数（0なら「全タスク完了」と明言する）。うち `loopable: "N"` が
  何件かも添える（`/loop` では進まないので、ユーザーが自分で呼ぶ必要があるため）
