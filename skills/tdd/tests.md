# 良いテストと悪いテスト

## 良いテスト

**結合テストスタイル**: 内部部品のモックではなく、実際のインターフェースを通してテストする。

```typescript
// GOOD: 観測可能な振る舞いをテストしている
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

特徴:

- ユーザー/呼び出し元が気にする振る舞いをテストしている
- 公開APIのみを使用している
- 内部のリファクタを乗り越えて生き残る
- 「どうやって」ではなく「何を」を記述している
- 1テストにつき論理的なアサーションは1つ

## 悪いテスト

**実装詳細テスト**: 内部構造と結合してしまっている。

```typescript
// BAD: 実装の詳細をテストしている
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

危険信号:

- 内部の協力オブジェクトをモックしている
- プライベートメソッドをテストしている
- 呼び出し回数や順序をアサーションしている
- 振る舞いが変わっていないのにリファクタするとテストが壊れる
- テスト名が「何を」ではなく「どうやって」を記述している
- インターフェースではなく外部の手段を通じて検証している

```typescript
// BAD: インターフェースを迂回して検証している
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: インターフェースを通して検証している
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

**同語反復テスト**: 期待値が実装をそのまま言い換えているだけなので、構造上必ず成功してしまう。

```typescript
// BAD: 期待値がコードの計算方法をそのまま再計算している
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// GOOD: 期待値が独立した既知のリテラル値になっている
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```
