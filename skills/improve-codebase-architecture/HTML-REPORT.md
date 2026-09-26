# HTML レポートの形式

アーキテクチャレビューは、OS の一時ディレクトリに置く単一の自己完結した HTML ファイルとして描画する。Tailwind と Mermaid はどちらも CDN から読み込む。Mermaid はグラフ状の図を確実に処理し、手作りの div とインライン SVG はもっと編集的な視覚化（マス図、断面図）を担う。両方を混ぜる: すべてを Mermaid に頼らないこと、そうすると見た目が一般的になってしまう。

## 雛形

```html
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <title>{{repo name}} のアーキテクチャレビュー</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      /* small custom layer for things Tailwind doesn't cover cleanly:
         dashed seam lines, hand-drawn-feeling arrow heads, etc. */
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>...</header>
      <section id="candidates" class="space-y-10">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```

## Header

リポジトリ名、日付、そして簡潔な凡例: 実線の箱＝モジュール、破線＝シーム、赤い矢印＝漏れ、太い濃色の箱＝深いモジュール。導入の段落は無し。候補にまっすぐ入る。

## Candidate card

図が重みを担う。文章は控えめで平易で、（`codebase-design` スキルの）用語集の言葉を儀礼抜きで使う。

各候補は1つの `<article>`:

- **Title**: 短く、深化の名前をつける（例: 「Order intake パイプラインを1つに集約する」）。
- **Badge row**: recommendation strength（`Strong` = emerald、`Worth exploring` = amber、`Speculative` = slate）に加えて、依存関係カテゴリのタグ（`in-process`、`local-substitutable`、`ports & adapters`、`mock`）。
- **Files**: モノスペースの一覧、`font-mono text-sm`。
- **Before / After diagram**: 中心となるもの。2列を並べる。下のパターンを参照。
- **Problem**: 一文。何が痛いか。
- **Solution**: 一文。何が変わるか。
- **Wins**: 箇条書き、各1行に収まる短さ。例: 「テストはインターフェース1つを叩く」「Pricing の漏れが止まる」「浅いラッパー4つを消す」。
- **ADR callout**（該当する場合）: amber 系の色のボックスに一行。

説明の段落は書かない。図を理解するのに段落が必要なら、図を描き直す。

## 図のパターン

候補に合うパターンを選ぶ。混ぜる。すべての図を同じ見た目にしない。バリエーションこそが要点の一部である。

### Mermaid graph（依存関係／呼び出しフローの主力）

「X が Y を呼び、Y が Z を呼び、ほら、これだけ絡んでいる」を示したいときは Mermaid の `flowchart` か `graph` を使う。突然出てきた感じにならないよう、Tailwind でスタイルしたカードで包む。classDef でスタイルし、漏れているエッジを赤に、深いモジュールを濃色にする。シーケンス図は「before: 6往復、after: 1往復」のようなケースに向く。

```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      A[OrderHandler] --> B[OrderValidator]
      B --> C[OrderRepo]
      C -.leak.-> D[PricingClient]
      classDef leak stroke:#dc2626,stroke-width:2px;
      class C,D leak
  </pre>
</div>
```

### 手作りの箱と矢印（Mermaid のレイアウトが思い通りにならないとき）

モジュールを枠線とラベル付きの `<div>` として表す。矢印はインライン SVG の `<line>` か `<path>` を、relative なコンテナの上に absolute で配置する。「after」の図を、内部が灰色になった1つの太枠の深いモジュールのように見せたいときはこちらを使う。Mermaid ではその太さで描けない。

### Cross-section（層状の浅さに向く）

水平のバンド（`h-12 border-l-4`）を積み重ね、呼び出しが通過する層を示す。Before: 何もしていない薄い層が6つ。After: 統合された責務がラベルされた太いバンドが1つ。

### Mass diagram（「インターフェースが実装と同じくらい広い」場合に向く）

モジュールごとに2つの矩形: 1つはインターフェースの表面積、もう1つは実装。Before: インターフェースの矩形が実装の矩形とほぼ同じ高さ（浅い）。After: インターフェースの矩形は短く、実装の矩形は高い（深い）。

### Call-graph collapse

Before: 関数呼び出しの木を、入れ子の箱として描く。After: 同じ木を1つの箱に集約し、いまは内部呼び出しとなったものを、その中にフェードした状態で示す。

## スタイルの指針

- エディトリアルに寄せる、コーポレートダッシュボード風にしない。余白をたっぷり取る。見出しにはセリフ体も選択肢（`font-serif` は stone/slate とよく合う）。
- 色は控えめに: アクセント1色（emerald か indigo）に加え、漏れには赤、警告には amber。
- 図の高さは約320pxに保ち、before/after がスクロールなしで並んで収まるようにする。
- 図の中のモジュールラベルには `text-xs uppercase tracking-wider` を使い、UI ではなく図式として読めるようにする。
- スクリプトは Tailwind の CDN と Mermaid の ESM インポートのみ。レポートはそれ以外は静的: アプリコードは無く、Mermaid 自身の描画以外のインタラクティブ性も無い。

## Top recommendation セクション

1つの大きめのカード。候補名、理由を一文、そのカードへのアンカーリンク。それだけ。

## トーン

平易な**日本語**で簡潔に、しかしアーキテクチャの名詞と動詞は `codebase-design` スキルの用語集からそのまま持ってくる。簡潔さは言葉が流れる言い訳にはならない。カードのラベル（`Files`・`Problem`・`Solution`・`Wins`）とバッジの値（`Strong` など）は色や構造との対応が付いているので英語のまま置く。

**必ず使う:** モジュール、インターフェース、実装、深さ、深い、浅い、シーム、アダプター、レバレッジ、局所性。

**決して置き換えない:** ユニット・コンポーネント・サービス（モジュールの代わりに）、API・シグネチャ（インターフェースの代わりに）、境界（シームの代わりに）、レイヤー・ラッパー（モジュールを意味しているときに、その代わりに）。

**この文体に合う言い回し:**

- 「Order intake モジュールは浅い: インターフェースが実装とほぼ同じ複雑さ」
- 「Pricing がシームを越えて漏れている」
- 「深化: インターフェース1つ、テストする場所1つ」
- 「アダプターが2つあるからシームは正当: 本番は HTTP、テストはインメモリ」

**Wins の箇条書き**は用語集の言葉で得られるものを名指す: 「局所性: バグが1つのモジュールに集まる」「レバレッジ: インターフェース1つで呼び出し箇所 N 個」「インターフェースが縮み、実装がラッパーを吸収する」。「保守しやすくなる」「コードがきれいになる」とは書かない。それらの言葉は用語集に無く、使う資格が無いからである。

ヘッジ（前置き）も、前置きの言い訳も、「〜という点は注目に値する」のような言い回しも書かない。一文が箇条書きにできるなら、箇条書きにする。箇条書きが削れるなら、削る。`codebase-design` の語彙集に無い言葉を使うなら、まず既にある言葉に手を伸ばす。
