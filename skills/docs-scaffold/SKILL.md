---
name: docs-scaffold
description: "docs/ に requirements・coding-standards などの文書の雛形を新しく作るスキル。「docs/ に requirements.md の雛形を作りたい」「coding-standards.md の型を揃えたい」「文書の型を毎回指示したくない」「別の場所の設計書を docs/ に取り込みたい」と言われたときに使う。architecture の提案書は architecture-proposal、用語集・ADR は domain-modeling、既にある docs/ の点検は maintenance-docs に任せる。"
---

# docs-scaffold

`docs/` の文書を新しいリポジトリで一から書くときの型を雛形にして置く。型は「`X.md` が索引と結論、`X/` が詳細」の一組で、`X.md` の冒頭に 責務／読む時／直す時 の3行と節の索引表を置く。

## 流れ

1. 対象の文書を決める
2. 外部ファイルを受ける
3. 既存の `docs/` を確かめる
4. 型で作る
5. 索引に足す

### 1. 対象の文書を決める

作れる型は `requirements`・`coding-standards` の2つ。型は `references/<文書名>.md` にある。

- `architecture` は型を持たない。`architecture-proposal` を使う
- `glossary`（用語集）・ADR は型を持たない。`domain-modeling` を使う
- 既にある `docs/` のズレを直すのは `maintenance-docs`。このスキルは書き足さない

### 2. 外部ファイルを受ける

### 3. 既存の docs/ を確かめる

作る先（`docs/<文書名>.md`）と `docs/README.md` が既にあるかを、書く前に確かめる。

### 4. 型で作る

### 5. 索引に足す

生成したら、`docs/README.md` にパスと一行説明で1行足す。
