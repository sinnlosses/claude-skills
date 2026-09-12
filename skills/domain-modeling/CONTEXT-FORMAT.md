# CONTEXT.md の書式

## 構造

```md
# {コンテキスト名}

{このコンテキストが何であり、なぜ存在するのかを1〜2文で説明する。}

## Language

**Order**:
{その用語の1〜2文の説明}
_Avoid_: Purchase, transaction

**Invoice**:
配送後に顧客へ送られる支払い請求。
_Avoid_: Bill, payment request

**Customer**:
注文を行う個人または組織。
_Avoid_: Client, buyer, account
```

## ルール

- **意見を持つこと。** 同じ概念に複数の言葉が存在する場合、最良のものを1つ選び、他は `_Avoid_` に列挙する。
- **定義は簡潔に保つ。** 最大でも1〜2文。それが「何をするか」ではなく「何であるか」を定義する。
- **このプロジェクトのコンテキストに固有の用語だけを含める。** タイムアウトやエラー型、ユーティリティパターンといった一般的なプログラミング概念は、そのプロジェクトで多用されていても含めない。用語を追加する前に、「これはこのコンテキスト特有の概念か、それとも一般的なプログラミング概念か」を自問する。前者だけがここに属する。
- **自然なまとまりが生まれたら、サブ見出しで用語をグループ化する。** すべての用語が1つのまとまりに属するなら、フラットなリストで問題ない。

## 単一コンテキスト vs 複数コンテキストのリポジトリ

**単一コンテキスト（ほとんどのリポジトリ）:** リポジトリのルートに `CONTEXT.md` を1つ置く。

**複数コンテキスト:** リポジトリのルートの `CONTEXT-MAP.md` に、各コンテキストの一覧、それらがどこにあるか、互いにどう関係しているかを記載する:

```md
# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md): 顧客の注文を受け付け、追跡する
- [Billing](./src/billing/CONTEXT.md): 請求書を発行し、支払いを処理する
- [Fulfillment](./src/fulfillment/CONTEXT.md): 倉庫のピッキングと出荷を管理する

## Relationships

- **Ordering → Fulfillment**: Orderingが `OrderPlaced` イベントを発行し、Fulfillmentがそれを購読してピッキングを開始する
- **Fulfillment → Billing**: Fulfillmentが `ShipmentDispatched` イベントを発行し、Billingがそれを購読して請求書を発行する
- **Ordering ↔ Billing**: `CustomerId` と `Money` の型を共有している
```

このスキルは、どの構造が該当するかを次のように推測する:

- `CONTEXT-MAP.md` が存在すれば、それを読んでコンテキストを把握する
- ルートに `CONTEXT.md` だけが存在すれば、単一コンテキスト
- どちらも存在しなければ、最初の用語が確定した時点でルートに `CONTEXT.md` を遅延的に作成する

複数コンテキストが存在する場合、現在の話題がどのコンテキストに関係するかを推測する。不明な場合は確認する。
