# `tw edit` が空の `--body-file -` で節や本文を空にするのを拒む（振り返り: T-069）

- 観点: 赤 機械の検査
- 根拠: T-069 の委譲先が空の標準入力で `tw edit T-069 --section '決まっていること（蒸し返さない）'` を打ち、節の中身が消えた（friction log の赤1件。委譲先が元の2行を書き直して戻した）。戻せなければ決まったことが黙って消えていた
- 出し先: tsukumo-plugins の `tw edit`（`skills/task-workflow/scripts/` の edit の処理）で、渡された本文が空白だけなら書き換えずに終了コード2で拒むタスク（作業先は tsukumo-plugins）
