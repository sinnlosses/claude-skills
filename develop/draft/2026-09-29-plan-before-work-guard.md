# `## やること` を書く前に作業ツリーが変わっていたら、task edit がその場で知らせる（振り返り: tsukumo の GH-92）

- 札: 黄 制約違反（4回目）
- 根拠: GH-92 の受け入れで `task plan-check` が `PLAN_NOT_FIRST after-work`。委譲の指示に「最初に `## やること` を書く」とあったが、2ファイルを直してから `task edit` した（最初の `task edit` は front matter ごと渡して弾かれ、書き直しが作業の後にずれた）。差分と中身は合っていたので受け入れでは直していない
- 出し先: `task-workflow` の `task.py`。`edit` で `## やること` が空から埋まるとき、claim 以降に作業ツリーの差分があれば警告を返す（委譲先がその場で順の誤りに気づく）。あわせて `edit --body-file -` が front matter 付きの入力を受けたら、剥がして受けるか、剥がし方をエラー文に書く
