---
name: setup-tasks
description: "タスク運用に要る develop/direction.md（## ユーザーから・## エージェントのドラフト）をプロジェクトに用意し、検証コマンド・整形コマンド・ブランチの3行を CLAUDE.md の「## タスク運用」節に書く。ユーザーが「タスク運用を始めたい」「develop/ を用意して」「このプロジェクトでもタスク管理を使いたい」と言ったとき、/next-task・/plan-tasks・/list-tasks が MISSING を返したときに使う。既にあるファイルは上書きしない。旧形式（develop/tasks.json）なら作らずに移行を案内する。"
---

`/next-task` `/plan-tasks` `/list-tasks` が読む**プロジェクト側のファイルを用意する**。置き場と役割は
`task-workflow` スキルの `WORKFLOW.md`（以下「正典」）「ファイル配置と CLAUDE.md」。
**タスクは登録しない。既にあるファイルは上書きしない**（点検結果を出し、直すかは下で決める）。

## 手順

1. **作る**。骨組みは決まりきっているので手で書かない（見出し以外の行が混ざると `/plan-tasks` が
   「未対応の指示がある」と誤判定する）:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/init.py develop
   ```

   | 行 | 意味 |
   | --- | --- |
   | `LEGACY`（終了コード5） | **旧形式**（`develop/tasks.json` がある）。何も作っていない。「正典「旧形式からの移行」の手順で `task migrate --dry-run` から移す（全作業ツリーの手を止めてから）」と案内して終了する |
   | `CREATED` | `develop/direction.md` を骨組みで作った |
   | `KEPT` + `OK:` | 既にあり、筋が通っている。触っていない |
   | `KEPT` + `PENDING:` | セットアップとしては完了。未タスク化の指示が残っているので `/plan-tasks` が先と報告する |
   | 最終行 `MISSING`/`NO_SECTION`/`MISSING_LINE`/`BAD_BRANCH`/`OK` | CLAUDE.md の点検結果。手順2で使う |

   `develop/task/` は最初の `task new` が作る（空のディレクトリは git に載らない。新形式の目印は
   `develop/direction.md`）。`docs/history/` も掘らない。

2. **CLAUDE.md の「## タスク運用」節を用意する**。プロジェクトごとに変わる値は3行だけ。まず値を
   決める。**推測で書かない**:

   - 検証コマンド・整形コマンドは `package.json` の `scripts`、`Makefile`、`justfile`、`pyproject.toml`、
     **既にある CLAUDE.md の記述**から探し、**実際に走らせて通ることを確かめてから**書く（受け入れと
     `task ship` の付け替え後に毎回打たれる）。決め手が無い・見つからないときはユーザーに聞く。
     無いと決まったら `なし` と書き、行ごと消さない
   - `- ブランチ:` は語彙の先頭語で書く（正典「ファイル配置と CLAUDE.md」の表）。既定は `既定`
     （タスクごとに `feature/T-xxx` を切る）。`main` に直接積む・作業ツリーの枝のまま送るなら
     `切らない`。先頭語の後ろは説明を自由に書いてよい

   ```markdown
   ## タスク運用

   - 検証コマンド: `pnpm check`（変更後は必ずこれを通す。受け入れ判定に使う）
   - 整形コマンド: `pnpm format`
   - ブランチ: 既定

   タスクは `develop/task/` に1件1ファイル、指示は `develop/direction.md` に溜め、
   `/plan-tasks` でタスク化して `/next-task` で進める。
   ```

   | 点検結果 | すること |
   | --- | --- |
   | `MISSING` | CLAUDE.md ごと作る。**タスク運用の節だけ**を書き、プロジェクトの説明を書き足さない |
   | `NO_SECTION` | **既存の記述を先に読む**（検証コマンドが別の節にあることが多い）。節は末尾に足し、内容をユーザーに見せて確認を取ってから書く。別の節は消さない |
   | `MISSING_LINE` | 足りない行だけ足す。既にある行は書き換えない |
   | `BAD_BRANCH` | `- ブランチ:` の先頭語が語彙に無い（`task` が `INVALID` で止まる）。どの語にするかユーザーに聞いてから直す |
   | `OK` | 触らない |

3. **通しで確かめる**: `python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py status`。
   まっさらなら `---` と末尾の集計行だけが出る（終了コード0）。`MISSING` なら手順1が効いていない。

4. **コミットする**（件名にタスクIDは付けない。push はしない）。作業ツリーの枝に居るなら
   `python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py ship` で `main` へ送る。

5. **報告する**: 作ったファイル、CLAUDE.md に書いた値（と、そのコマンドが実際に通ったこと）、
   CLAUDE.md の扱い（新規／末尾に追記／触らず）、点検で見つかった問題。最後に次の一歩を1行:
   やりたいことを `develop/direction.md` の `## ユーザーから` に書いて `/plan-tasks` を呼ぶとタスクになる。

## やらないこと

- タスクの登録・実行（`/plan-tasks`・`/next-task`）。旧形式の移行（`task migrate` は人が打つ）
- `develop/` を `.gitignore` に足す（タスクの正典はコミットして共有する）
- CLAUDE.md の「## タスク運用」節より外の書き換え
- `~/.claude/skills/` へのリンク（スキル自体の導入は claude-skills の `install.sh`）
