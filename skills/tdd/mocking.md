# いつモックするか

**システム境界**でのみモックする:

- 外部API（決済、メールなど）
- データベース（場合による — できればテスト用DBを優先する）
- 時刻・乱数
- ファイルシステム（場合による）

モックしないもの:

- 自分たちのクラス/モジュール
- 内部の協力オブジェクト
- 自分たちが制御できるもの

## モックしやすい設計にする

システム境界では、モックしやすいインターフェースを設計する。

**1. 依存性注入を使う**

外部依存を内部で生成せず、外から渡す。

```typescript
// モックしやすい
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// モックしにくい
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

**2. 汎用フェッチャーより SDK スタイルのインターフェースを優先する**

条件分岐を持つ1つの汎用関数ではなく、外部操作ごとに専用の関数を用意する。

```typescript
// GOOD: 各関数を個別にモックできる
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: モックする際にモック内部で条件分岐が必要になる
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

SDK 方式にすると:

- 各モックが1つの決まった形だけを返せばよい
- テストのセットアップに条件分岐が不要になる
- あるテストがどのエンドポイントを使っているか一目で分かる
- エンドポイントごとに型安全性が得られる
