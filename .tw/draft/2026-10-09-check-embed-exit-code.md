# SKILL.md の `!` 埋め込みが非0で抜けうる形を check_repo.py で弾く（振り返り: T-057）

- 観点: 赤 機械の検査
- 根拠: T-057 で next-task・plan-tasks の埋め込みを `` !`tw config 2>&1` `` にした。設定が無いと終了コード6、git の外では1で抜け、スキルの読み込みが失敗する形のまま `tw verify` と1回目のレビューを通った。受け入れでメインが README の制約の項と WORKFLOW.md の `config` の行を突き合わせて見つけた
- 出し先: `scripts/check_repo.py` に、SKILL.md の `!` 埋め込みが `|| true` などで非0を潰していなければ落とす検査を足す。README.md の制約の項は、その検査を指す形に縮める
