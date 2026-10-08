# `tw migrate-layout` が移した direction の見出しの旧い置き場の言及を書き換え、節の文を config のコメントに写さない（振り返り: T-059）

- 観点: 赤 機械の検査
- 根拠: T-059 の受け入れのレビューで2点当たり、委譲先へ差し戻した。`.tw/direction.md` の1行目が移行後も `develop/draft/` を指したまま残った。AGENTS.md の検証コマンドの行の括弧書きが `.tw/config.toml` の2行目のコメントに写り、AGENTS.md の文と二重になった
- 出し先: `skills/task-workflow/scripts` の migrate-layout（と tsukumo-plugins の同じ口）を直すタスク。T-060 の移行より前に入れる。確かめは `selftest_t_migrate.py` に、見出しの書き換えとコメントを写さないことの2行を足す
