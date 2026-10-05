# 手順5bの返りの異常系

手順5bの表のうち、通常の返り（`PLAN_REGISTERED`・`PLAN_FIRST`）以外の行。

   | 見たもの | すること |
   | --- | --- |
   | 「前提が誤り」の報告 | 手順7で `--dropped` にするか、`## 目的・背景` を直して手順4から着手し直すかを決める（直す `tw edit` には `--change-frame` を付ける。付けないと `FRAME_CHANGED` で拒まれる） |
   | `dropped` にすべき理由の報告 | 手順7へ（`--dropped`。理由を結果に書く） |
   | `PLAN_NOT_FIRST`（`missing`・`after-work`・`unrecorded`）か `PLAN_STALE` | `## やること` を作業より先に書かなかった。理由の語を一言メモしておく（手順6aの兆候「受け入れのときにメインが直したもの」。札は `制約違反`）。差分が完了条件を満たすなら活かして手順6へ進み、`## やること` はメインが差分から書き起こして `tw edit T-xxx --section 'やること' --after-work` で渡す。満たさなければ差分を退けて（自分の作業ツリー内の `git restore`）「書き直しから委譲する」で頼み直す |
   | `NOT_OWNER` | 自分の作業ツリーの印が無い（人が `tw release --force` した、など）。ID を添えて終了する |
