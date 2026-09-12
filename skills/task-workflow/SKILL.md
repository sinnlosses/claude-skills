---
name: task-workflow
description: "develop/tasks.json・progress.md・direction.md でタスクを管理する運用の正典（フィールド定義、difficulty の基準、evidence の書き方、アーカイブのトリガー）。/next-task・/plan-tasks・/list-tasks が参照する。ユーザーが「タスク運用のルールを教えて」「difficulty の基準は？」「アーカイブの基準は？」と聞いたときに読む。手順は持たず、何も書き換えない。"
user-invocable: false
---

このスキルは**ルールの置き場**で、手順を持たない。実際の作業は次の3つが行う。

| やりたいこと                 | スキル         |
| ---------------------------- | -------------- |
| 未着手タスクを1件進める      | `/next-task`   |
| 指示メモをタスクに分解する   | `/plan-tasks`  |
| 一覧を見る（読み取り専用）   | `/list-tasks`  |

ルール本文は [WORKFLOW.md](WORKFLOW.md)。冒頭の目次で節を1つ選んで読む（通読しない）。
プロジェクト固有の値は、そのプロジェクトの `develop/workflow.json`（キーと既定値は
WORKFLOW.md「ファイル配置と `develop/workflow.json`」）。

一覧とアーカイブ判定は `scripts/status.py` が出す:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/status.py develop/tasks.json develop/workflow.json
```
