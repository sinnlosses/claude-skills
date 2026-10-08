# `task` の略記検査を旧い `task <サブコマンド>` の形だけに絞る（振り返り: T-057）

- 観点: 黄 機械の検査
- 根拠: T-057 で `tw config` の `task` の行を `` `task` `` と書くと、`scripts/check_repo.py` の `old_abbrev`（`` `task[ `] ``）に当たり、`tw verify` が2回落ちた（9件、次に3件）。委譲先は正しい言及からバッククォートを外して避けた
- 出し先: `scripts/check_repo.py` の `old_abbrev` を、旧いコマンドの呼び方（`` `task <claim|done|ship|…> `` のようにサブコマンドが続く形）だけに当たる正規表現に絞る
