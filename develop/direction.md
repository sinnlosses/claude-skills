# 未対応の指示メモ

## ユーザーから

## エージェントのドラフト

- **`selftest_task.py` の ship の RACE テストを安定させる**（振り返り: T-023）
  - 根拠: 同じ作業ツリーで `./check.sh` を4回打ち、1回目だけ `FAILED 1件: RACEで終了コード9`
    （`task.py ship: 相手に先を越され続けるとRACEで終わる`）。残り3回は通った。検証コマンドが
    不定期に落ちると受け入れ判定が信用できず、`task ship` の付け替え後検証で偽の
    `VERIFY_FAILED` を出して人に預けてしまう
  - 出し先: `skills/task-workflow/scripts/selftest_task.py` の RACE のケースを、時間ではなく
    回数で決まる形に直すタスク
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
