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

## 手順

1. **読む**: `develop/progress.md` と `develop/tasks.json` を読む。正典「いつ移すか（トリガー）」
   に該当していたら、着手前にアーカイブする。**2ファイルをここでまとめて判定する**:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/status.py develop/tasks.json develop/workflow.json | tail -1
   grep '^### ' develop/progress.md
   ```

   1行目の `archive` が `YES` なら `tasks.json` が該当。2行目で最新の日付以外の小節が
   あれば `progress.md` が該当。移し方は正典「何を移すか」。

   あわせて `develop/direction.md` を見る。見出し行以外に中身があれば
   （`grep -v '^#' develop/direction.md | grep -v '^\s*$'` が空でなければ）、**未タスク化の
   指示が残っている**。タスクを実行せず、`/plan-tasks` でのタスク化が先だと報告して終了する
   （`/loop` 側はこれを「続行不要」の合図として扱う）。分解は方針決めを含むので、このスキルが
   その場で代行しない。

2. **選ぶ**: `status: "todo"` かつ `dependencies` が全て `status: "done"`（または
   `tasks.json` に存在しない＝アーカイブ済み扱い）のタスクを1件選ぶ。該当が無ければ
   （全件 done、または残りが全て未解決の依存で止まっている）その旨を報告して終了する
   （`/loop` 側はこれを「続行不要」の合図として扱う）。

3. **ブランチ**: プロジェクトの `CLAUDE.md` のGit運用に従う（作業ブランチを切るかどうかは
   そこで決まる。書いてなければデフォルトブランチで作業する）。

4. **実行**: Agentツールで、選んだタスクの `difficulty` と同じモデルを指定した
   サブエージェントに委譲する（正典「difficulty に応じたモデルの切り替え方」）:
   - `haiku` / `sonnet` / `opus` のいずれでも委譲する。**メインセッションが今どのモデルで
     動いているかは判断材料にしない**
   - `tasks.json` の `task` 本文だけで作業が完結するよう、対象ファイル・完了条件・
     `checkCommand` を通すことを明記して渡す（サブエージェントはまっさらな文脈で起動する）
   - ユーザーへの確認が必要な判断・会話中の文脈に依存する判断は委譲しない。これは
     モデル選択とは別の軸の話。`opus` のタスクはこれに当たりやすいので、該当したら
     委譲せずユーザーに預けて次のタスクへ進む
   - 着手後に想定より判断が重いと分かったら、`difficulty` を上げてから改めて進める

5. **受け入れ**: 委譲した場合は完了報告をそのまま信用せず、自分で差分（`git diff`）を確認し、
   `formatCommand` があれば実行してから `checkCommand` を実行して通ることを確かめる。
   `checkCommand` が未設定なら、タスク本文の完了条件を1つずつ目視で確かめ、報告に
   「検証コマンド未設定」と書く。方針からズレた実装（例: コメントの動機がすり替わっている、
   命名が既存規約と衝突する）があればその場で直してから次に進む。

6. **記録してコミット**: `develop/tasks.json` の対象タスクの `status`/`passes`/`evidence` を
   更新する（evidence は3行以内、後から検証できる形で。正典「良いevidenceの書き方」）。
   `develop/progress.md` の「完了したこと」にも1〜2文で追記する。**追記先の小節が無ければ
   `### YYYY-MM-DD 〜` の形で今日の日付の小節を作る**（日付が無いとアーカイブの境界を
   決められない。正典「progress.md の構成」）。1タスク＝1コミットとし、件名の先頭に
   タスクIDを置く（正典「コミットメッセージ」）。コミットメッセージの末尾は現在のセッションの
   attribution 指示（Co-Authored-By 等）に従う。

7. **push はしない**: 外部への反映は明示的に頼まれたときだけ行う。このスキルはコミットまでで止める。

## 完了報告のフォーマット

最後に必ず次を1行ずつ示す（`/loop` が続行判断に使う）:

- 今回 done にしたタスクID
- `checkCommand` の結果（ファイル数・テスト件数。未設定なら「検証コマンド未設定」）
- 残りの `todo` 件数（0なら「全タスク完了」と明言する）
