# 部品の selftest_t_*.py を直に打ったら、入口の selftest_task.py を案内して落ちるようにする（振り返り: T-061）

- 観点: 赤 機械の検査
- 根拠: T-061 の段1で、委譲先が `selftest_t_ship.py`・`selftest_t_guards.py` を単独で打ち、何も流れないまま終了コード0を合格と報告した。段2で自分で気づいて `selftest_task.py` で打ち直した（`TESTS` を定義するだけの部品で、流すのは `selftest_task.py` の `MODULES`）
- 出し先: tsukumo-plugins の `skills/task-workflow/scripts/selftest_t_*.py` の末尾に、直に実行されたら `selftest_task.py` を打つよう案内して非0で終わる1行を足すタスク
