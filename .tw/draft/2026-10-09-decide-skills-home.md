# claude-skills の skills/ と tsukumo-plugins の skills/ のどちらを正にするかを決める（振り返り: T-061）

- 観点: 赤 道案内
- 根拠: いま動いている `tw` とタスク運用のスキルは tsukumo-plugins にあり、`task.py` はそちらだけ `tw_*.py` に分かれている。claude-skills の T-061 は登録時の計画が claude-skills のファイルを名指していて使えず、作業先を利用者に決めてもらった。T-063・T-057 は両方へ手で写した
- 出し先: 利用者が決めることを `/plan-tasks` で問うタスク（tsukumo-plugins に移ったスキルを claude-skills から消すか、写しを自動で揃えるか、今のまま手で写すか）
