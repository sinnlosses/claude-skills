# 未対応の指示メモ

## ユーザーから

## エージェントのドラフト

- **`selftest_task.py` の ship の RACE テストを安定させる**（振り返り: T-023, T-024）
  - 根拠: T-023 の受け入れで `./check.sh` を4回打って1回目だけ、T-024 の受け入れでも
    1回目だけ `FAILED 1件: RACEで終了コード9`（`task.py ship: 相手に先を越され続けるとRACEで
    終わる`）。**2タスク続けて「その回の1打目」で落ちた**。原因は
    `selftest_task.py:868-898` の作り: 0.1秒ごとにコミットする別スレッドと、検証が
    `sleep 0.4` の `ship` を競争させているので、機械が遅い/速いだけで勝敗が変わる。検証コマンドが
    不定期に落ちると受け入れ判定が信用できず、`task ship` の付け替え後検証で偽の
    `VERIFY_FAILED` を出して人に預けてしまう
  - 出し先: `skills/task-workflow/scripts/selftest_task.py` の RACE のケースを、時間ではなく
    「`ship` が ref を読んだあと必ず1回は先を越される」ことが決まる形（フック・待ち合わせ）に
    直すタスク
- **`material.py --signals` の「同じファイルを2回以上直した」がパスではなくファイル名で数える**
  （振り返り: T-024）
  - 根拠: T-024 は `skills/architecture-proposal/SKILL.md` を2回・
    `skills/improve-codebase-architecture/SKILL.md` を1回直しただけなのに、`SKILL.md×3` と出て
    「同じファイルを3回以上直した」の兆候に当たった。このリポジトリは全スキルが `SKILL.md` を
    持つので、この兆候は今後も当たり続けて意味を失う
  - 出し先: `skills/retrospect/scripts/material.py` の集計キーをリポジトリ相対パスにするタスク
- **翻訳したスキルについて、`description` と生成物の言語の2点を翻訳方針に足す**（振り返り: T-023）
  - 根拠: `disable-model-invocation: true` のスキルは先例（`skills/grill-with-docs/SKILL.md:2`・
    `skills/implement/SKILL.md:2`）では `description` が1文でトリガー語を持たないが、T-023 の
    `## 完了条件` に「トリガーになる言い回しを含む」と書いたため、サブエージェントは先例と違う
    description を書き、受け入れで直した。また「散文は日本語」はスキル本文の話で、スキルが
    **生成する成果物**（今回は HTML レポート）の言語は方針に無く、原文のまま英語で出す指示が
    残っていたので受け入れで直した
  - 出し先: `README.md` の「## 由来」末尾の翻訳方針に2行（明示呼び出し専用のスキルは
    `description` を1文にする／生成する成果物の文章も日本語にし、識別子と色に対応づいた値は
    原文のまま）
