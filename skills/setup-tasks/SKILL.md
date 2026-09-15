---
name: setup-tasks
description: "タスク運用に要る develop/tasks.json・develop/progress.md・develop/direction.md をプロジェクトに用意し、検証コマンドなどプロジェクト固有の値を develop/workflow.json に書く。ユーザーが「タスク運用を始めたい」「develop/ を用意して」「このプロジェクトでもタスク管理を使いたい」と言ったとき、/next-task・/plan-tasks・/list-tasks が MISSING を返したときに使う。既にあるファイルは上書きしない。"
---

`/next-task` `/plan-tasks` `/list-tasks` が読む**プロジェクト側のファイルを用意する**スキル。
置き場と役割は `task-workflow` スキルの `WORKFLOW.md`（以下「正典」）「ファイル配置と
`develop/workflow.json`」。

**タスクは登録しない**（登録は `/plan-tasks`、実行は `/next-task`）。
**既にあるファイルは上書きしない**（中身の点検結果だけ出して、直すかどうかは下の手順で決める）。

## 手順

1. **作る**。骨組みは決まりきっているので手で書かない（`progress.md` の節名がズレると
   アーカイブが節を見つけられず、`direction.md` に見出し以外の行が混ざると `/plan-tasks` が
   「未対応の指示がある」と誤判定する）:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/init.py develop
   ```

   出力は1行1ファイル:

   | 行                                      | 意味                                                             |
   | --------------------------------------- | ---------------------------------------------------------------- |
   | `CREATED`                               | 無かったので骨組みで作った                                       |
   | `KEPT` + `OK:`                          | 既にあり、中身も筋が通っている。触っていない                     |
   | `KEPT` + `INVALID:`/`MISSING_SECTION:`/`PENDING:` | 既にあるが手当てが要る（下の「`KEPT` が `OK:` でないとき」） |
   | `ABSENT`                                | `workflow.json` が無い。既定値で動くので、手順2で要るときだけ作る |

2. **`develop/workflow.json` を書く**。**既定値と違う値だけ**書く（キーと既定値は正典）。
   実質ここで決めるのは検証まわりの2つで、残りは既定のままにする（変える理由ができてから）:

   | キー            | 探す先                                                                 |
   | --------------- | ---------------------------------------------------------------------- |
   | `checkCommand`  | `package.json` の `scripts`、`Makefile`、`justfile`、`pyproject.toml`、`CLAUDE.md` |
   | `formatCommand` | 同上                                                                   |

   - **推測で書かない。** 候補を見つけたら**実際に走らせて通ることを確かめてから**書く。
     `checkCommand` は `/next-task` が受け入れ判定に毎回使うので、通らないコマンドを
     書くと全タスクが落ちる
   - 候補が複数あって決め手が無いとき、1つも見つからないときは**ユーザーに聞く**。
     聞いても決まらなければ**書かない**（`checkCommand` が無い場合は、タスク本文の完了条件
     だけで判定する運用になる。正典の既定どおり）
   - 1つも書くものが無ければ `develop/workflow.json` は**作らない**。空の `{}` を置くと、
     「このプロジェクトは設定を検討済み」と「まだ何も無い」が見分けられなくなる

3. **通しで確かめる**。ここまでで `/list-tasks` が動く状態になっているはず:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/status.py develop/tasks.json develop/workflow.json
   ```

   まっさらなら `EMPTY` と `progress` 行の2行が出る。`MISSING` が出たら手順1が効いていない。

4. **コミットする**。件名は正典「コミットメッセージ」。push はしない。

5. **報告する**。作ったファイル、`develop/workflow.json` に書いた値（と、その根拠にした
   コマンドが通ったこと）、点検で見つかった問題。最後に**次の一歩**を1行:
   やりたいことを `develop/direction.md` に書いて `/plan-tasks` を呼ぶとタスクになる。

## `KEPT` が `OK:` でないとき

| 点検結果          | すること                                                                     |
| ----------------- | ---------------------------------------------------------------------------- |
| `INVALID:`        | **直さない。** 壊れた `tasks.json` は運用中のデータなので、内容を確かめずに作り直すと進行中のタスクを失う。エラーをそのまま報告し、どうするかをユーザーに聞く |
| `MISSING_SECTION:`| 足りない節を**見出し行だけ**足す（`## 未解決` `## 注意`）。既存の中身は動かさない |
| `PENDING:`        | セットアップとしては完了。**未タスク化の指示が残っている**ので、`/plan-tasks` が先だと報告する |

## やらないこと

- **タスクの登録・実行。** 登録は `/plan-tasks`、実行は `/next-task`
- **`<historyDir>/` を掘る。** アーカイブが要るときに `archive.py` が作る。空ディレクトリは
  git が追跡しないので、先に作っても残らない
- **`develop/` を `.gitignore` に足す。** タスクの正典はコミットして共有するファイル
- **`CLAUDE.md` の書き換え。** ブランチ運用など、プロジェクトの決めごとはユーザーのもの
- **`~/.claude/skills/` へのリンク。** スキル自体の導入は、このリポジトリの `install.sh`
