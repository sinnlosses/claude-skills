---
name: webapp-testing
description: Playwright でローカルの Web アプリを操作・テストするための道具一式。フロントエンドの動作確認、UI の挙動のデバッグ、ブラウザのスクリーンショット取得、ブラウザログの確認に使う。
license: 全文は LICENSE.txt を参照
---

# Web アプリケーションのテスト

ローカルの Web アプリをテストするには、**Playwright の Python スクリプトをそのまま書く**。

**利用できるヘルパースクリプト**:

- `scripts/with_server.py` - サーバのライフサイクルを管理する（複数サーバに対応）

**スクリプトはまず `--help` を付けて実行し、使い方を見る。** 実際に実行してみて、どうしてもカスタマイズが必要だと分かるまで、ソースを読まないこと。これらのスクリプトは非常に大きくなりうるので、コンテキストウィンドウを汚染する。**コンテキストに取り込むためではなく、ブラックボックスとして直接呼び出すために存在している。**

## 判断のためのツリー: どの進め方を選ぶか

```
ユーザーのタスク → 静的な HTML か？
    ├─ はい → HTML ファイルを直接読んでセレクタを特定する
    │         ├─ 成功 → そのセレクタを使って Playwright スクリプトを書く
    │         └─ 失敗・不完全 → 動的なものとして扱う（下へ）
    │
    └─ いいえ（動的な webapp）→ サーバは既に動いているか？
        ├─ いいえ → `python scripts/with_server.py --help` を実行し、
        │            ヘルパーを使ったうえで簡素な Playwright スクリプトを書く
        │
        └─ はい → 偵察してから行動する:
            1. ページを開き、networkidle を待つ
            2. スクリーンショットを撮るか DOM を調べる
            3. 描画された状態からセレクタを特定する
            4. 見つけたセレクタで操作を実行する
```

## 例: with_server.py の使い方

サーバを起こすときは、まず `--help` を実行してからヘルパーを使う。

**サーバ1つ:**

```bash
python scripts/with_server.py --server "npm run dev" --port 5173 -- python your_automation.py
```

**サーバ複数（バックエンド＋フロントエンドなど）:**

```bash
python scripts/with_server.py \
  --server "cd backend && python server.py" --port 3000 \
  --server "cd frontend && npm run dev" --port 5173 \
  -- python your_automation.py
```

自動化スクリプトを書くときは、**Playwright のロジックだけ**を入れる（サーバは自動で管理される）。

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # chromium は常にヘッドレスで起動する
    page = browser.new_page()
    page.goto('http://localhost:5173')  # サーバは既に起動し、準備できている
    page.wait_for_load_state('networkidle')  # 重要: JS の実行を待つ
    # ... 自動化のロジック
    browser.close()
```

## 「偵察してから行動する」パターン

1. **描画された DOM を調べる**:

   ```python
   page.screenshot(path='/tmp/inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```

2. 調べた結果から**セレクタを特定する**

3. 見つけたセレクタで**操作を実行する**

## よくある落とし穴

- ❌ 動的なアプリで、`networkidle` を待つ前に DOM を調べる
- ✅ 調べる前に `page.wait_for_load_state('networkidle')` を待つ

## 指針

- **同梱のスクリプトはブラックボックスとして使う。** タスクを片付けるとき、`scripts/` にあるスクリプトのどれかが役に立たないかをまず考える。これらはよくある複雑な作業を、コンテキストウィンドウを散らかさずに確実に処理する。`--help` で使い方を見て、直接呼び出す
- 同期スクリプトには `sync_playwright()` を使う
- 終わったら必ずブラウザを閉じる
- 説明的なセレクタを使う: `text=`、`role=`、CSS セレクタ、ID
- 適切な待ちを入れる: `page.wait_for_selector()` または `page.wait_for_timeout()`

## 参照ファイル

- **examples/** - よくあるパターンの例:
  - `element_discovery.py` - ページ上のボタン・リンク・入力欄を見つける
  - `static_html_automation.py` - ローカルの HTML に `file://` URL でアクセスする
  - `console_logging.py` - 自動化の最中にコンソールログを捕まえる
