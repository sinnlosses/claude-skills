---
name: list-tasks
description: "develop/tasks.json に登録されているタスクの一覧を、テーブル形式の要約だけで表示する。ユーザーが「タスク一覧を見せて」「今どのタスクが残ってる？」「tasks.json の中身を教えて」と言ったときに使う。読み取り専用で、タスクの実行も登録もしない。"
---

`develop/tasks.json` の中身を**テーブル1つに要約して表示するだけ**のスキル。

**何も書き換えない。タスクを実行しない。** 実行は `/next-task`、登録は `/plan-tasks`。
運用のルールは `task-workflow` スキルの `WORKFLOW.md`（以下「正典」）。

## このプロジェクトの設定（`develop/workflow.json`）

!`cat develop/workflow.json 2>/dev/null || echo '{}'`

`{}` なら既定値（アーカイブ判定は `done` 10件以上または 30KB超。正典「ファイル配置と
`develop/workflow.json`」）。

## タスク本文を読み込まない

1タスクの `task` 本文は数KBあり、全件読むとそれだけでコンテキストを大きく消費する。
一行要約は `summary` フィールドに入っているので、**下のコマンドの出力だけを使う**。
`develop/tasks.json` を Read ツールで開いたり `cat` したりしない。

```bash
python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/status.py develop/tasks.json develop/workflow.json
```

出力は TSV。列は `id / status / difficulty / loopable / dependencies / 着手可否 / passes / summary`。
`loopable` 列の `?` は、フィールドが無い旧タスク（`Y` 扱い。正典「loopable」）。
末尾に `counts`・`todo_loopable`・`done_size`・`archive`（`YES`/`NO`）の4行が付く。

## 表示のしかた

1. 上のコマンドを実行する。`EMPTY` なら「登録されているタスクは0件」、`MISSING` なら
   「`develop/tasks.json` が無い（このプロジェクトはまだタスク運用を始めていない）」と
   伝えて終わる。
2. 次の形のテーブル**1つだけ**を出す。行の並びは `todo`（着手可能なものが先）→ `doing` → `done`。

   | ID | 状態 | 難易度 | loop | 依存 | 内容 |
   | --- | --- | --- | --- | --- | --- |

   - **`内容` 列は `summary` をそのまま使う。** 要約し直さない（書き方の正典は「summary」節）。
     `(summaryなし)` が出たタスクはそのまま `(summaryなし)` と表示し、テーブルの下の1行で
     「`summary` フィールドが無いタスク」と添える
   - `状態` は着手可否を織り込む。`todo` かつ `READY` は `todo（着手可）`、
     `BLOCKED:T-xxx` は `todo（T-xxx待ち）` と書く
   - `loop` 列は `loopable` の値をそのまま（`Y` / `N` / `?`）。`?` は旧タスクで `Y` 扱い
   - `passes` が `no` のまま `done` のタスクは、状態を `done（未達で終了）` と書く。
     「着手しない判断」をこの形で閉じる運用があるため、成功した `done` と混ぜない
3. テーブルの下に**1行だけ**添える。件数（`todo`/`doing`/`done`）、`todo_loopable` の `N` が
   1件以上ならそのうち `/loop` では進まない件数、`archive` 行が `YES` ならアーカイブの
   トリガーに該当することを書く（**判定を書くだけで、移す作業はしない**）。

## 出さないもの

- タスク本文（`## 背景`・`## やること` などの中身）。**要約だけ**が仕事
- `evidence` の内容。`done` の詳細を見たいときは `<historyDir>/tasks-archive.md`（既定 `docs/history/`）
- `develop/progress.md` の内容。あれは別のファイルで、このスキルは触らない
- 「次はこれをやりましょう」の提案。聞かれたら答えてよいが、一覧に混ぜない

特定のタスクの本文を読みたいと言われたら、このスキルの範囲外。
`python3 -c "import json; print([t for t in json.load(open('develop/tasks.json')) if t['id']=='T-XXX'][0]['task'])"`
でその1件だけを読む。
