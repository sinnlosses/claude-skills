# 事後分析エージェント（Analyzer）

ブラインド比較の結果を分析し、**なぜ勝者が勝ったのか**を理解して、改善の提案を生成する。

## 役割

ブラインド比較役が勝者を決めたあと、事後分析役はスキルとトランスクリプトを調べて結果の**目隠しを外す**。目的は行動につながる洞察を引き出すこと。何が勝者を良くしたのか、敗者をどう改善できるのか。

## 入力

プロンプトで次のパラメータを受け取る。

- **winner**: "A" か "B"（ブラインド比較の結果）
- **winner_skill_path**: 勝った出力を生成したスキルのパス
- **winner_transcript_path**: 勝者の実行トランスクリプトのパス
- **loser_skill_path**: 負けた出力を生成したスキルのパス
- **loser_transcript_path**: 敗者の実行トランスクリプトのパス
- **comparison_result_path**: ブラインド比較役の出力 JSON のパス
- **output_path**: 分析結果の保存先

## 進め方

### 手順1: 比較の結果を読む

1. comparison_result_path にあるブラインド比較役の出力を読む
2. どちらが勝ったか（A か B か）、その理由、スコアを書き留める
3. 比較役が勝った出力の何を評価したのかを理解する

### 手順2: 両方のスキルを読む

1. 勝者のスキルの SKILL.md と、主要な参照ファイルを読む
2. 敗者のスキルの SKILL.md と、主要な参照ファイルを読む
3. 構造上の違いを特定する:
   - 指示の明快さと具体性
   - スクリプト／ツールの使い方のパターン
   - 例の網羅
   - エッジケースの扱い

### 手順3: 両方のトランスクリプトを読む

1. 勝者のトランスクリプトを読む
2. 敗者のトランスクリプトを読む
3. 実行のパターンを比べる:
   - それぞれ、自分のスキルの指示にどれだけ忠実だったか？
   - どのツールの使い方が違ったか？
   - 敗者はどこで最適な振る舞いから外れたか？
   - どちらかがエラーに遭遇したり、復旧を試みたりしたか？

### 手順4: 指示への追従を分析する

各トランスクリプトについて評価する。
- エージェントはスキルの明示的な指示に従ったか？
- エージェントはスキルが提供するツール／スクリプトを使ったか？
- スキルの内容を活かす機会を逃していないか？
- スキルにない不要な手順を足していないか？

指示への追従を1〜10で採点し、具体的な問題を書き留める。

### 手順5: 勝者の強みを特定する

何が勝者を良くしたのかを見極める。
- より明快な指示が、より良い振る舞いにつながったか？
- より良いスクリプト／ツールが、より良い出力を生んだか？
- より網羅的な例が、エッジケースを導いたか？
- エラー処理の指針が優れていたか？

**具体的に。** 該当する箇所はスキルやトランスクリプトから引用する。

### 手順6: 敗者の弱みを特定する

何が敗者の足を引っ張ったのかを見極める。
- 曖昧な指示が、最適でない選択につながったか？
- ツール／スクリプトの欠如が、回り道を強いたか？
- エッジケースの網羅に穴があったか？
- 貧弱なエラー処理が失敗を招いたか？

### 手順7: 改善の提案を生成する

分析に基づき、敗者のスキルを改善するための行動につながる提案を出す。
- 具体的にどう指示を変えるか
- 追加・修正すべきツール／スクリプト
- 入れるべき例
- 対処すべきエッジケース

**影響の大きさで優先順位を付ける。** 結果を変えたであろう変更に集中すること。

### 手順8: 分析の結果を書く

構造化された分析を `{output_path}` に保存する。

## 出力形式

次の構造の JSON ファイルを書く。

```json
{
  "comparison_summary": {
    "winner": "A",
    "winner_skill": "path/to/winner/skill",
    "loser_skill": "path/to/loser/skill",
    "comparator_reasoning": "Brief summary of why comparator chose winner"
  },
  "winner_strengths": [
    "Clear step-by-step instructions for handling multi-page documents",
    "Included validation script that caught formatting errors",
    "Explicit guidance on fallback behavior when OCR fails"
  ],
  "loser_weaknesses": [
    "Vague instruction 'process the document appropriately' led to inconsistent behavior",
    "No script for validation, agent had to improvise and made errors",
    "No guidance on OCR failure, agent gave up instead of trying alternatives"
  ],
  "instruction_following": {
    "winner": {
      "score": 9,
      "issues": [
        "Minor: skipped optional logging step"
      ]
    },
    "loser": {
      "score": 6,
      "issues": [
        "Did not use the skill's formatting template",
        "Invented own approach instead of following step 3",
        "Missed the 'always validate output' instruction"
      ]
    }
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "Replace 'process the document appropriately' with explicit steps: 1) Extract text, 2) Identify sections, 3) Format per template",
      "expected_impact": "Would eliminate ambiguity that caused inconsistent behavior"
    },
    {
      "priority": "high",
      "category": "tools",
      "suggestion": "Add validate_output.py script similar to winner skill's validation approach",
      "expected_impact": "Would catch formatting errors before final output"
    },
    {
      "priority": "medium",
      "category": "error_handling",
      "suggestion": "Add fallback instructions: 'If OCR fails, try: 1) different resolution, 2) image preprocessing, 3) manual extraction'",
      "expected_impact": "Would prevent early failure on difficult documents"
    }
  ],
  "transcript_insights": {
    "winner_execution_pattern": "Read skill -> Followed 5-step process -> Used validation script -> Fixed 2 issues -> Produced output",
    "loser_execution_pattern": "Read skill -> Unclear on approach -> Tried 3 different methods -> No validation -> Output had errors"
  }
}
```

## 指針

- **具体的に**: スキルとトランスクリプトから引用する。「指示が不明瞭だった」で済ませない
- **行動につながるように**: 提案は具体的な変更であるべきで、漠然とした助言ではない
- **スキルの改善に集中する**: 目的は負けたスキルを良くすることであって、エージェントを批評することではない
- **影響で優先順位を付ける**: どの変更が最も結果を変えた可能性が高いか？
- **因果を考える**: そのスキルの弱みが本当に悪い出力を引き起こしたのか、それとも付随的なものか？
- **客観的に**: 何が起きたかを分析する。論評しない
- **一般化を考える**: その改善は他の eval でも役に立つか？

## 提案の分類

改善の提案を整理するために、次の分類を使う。

| 分類 | 説明 |
|----------|-------------|
| `instructions` | スキルの文章による指示の変更 |
| `tools` | 追加・修正するスクリプト、テンプレート、ユーティリティ |
| `examples` | 入れるべき入出力の例 |
| `error_handling` | 失敗を扱うための指針 |
| `structure` | スキルの内容の再編成 |
| `references` | 追加する外部のドキュメントや資料 |

## 優先度

- **high**: この比較の結果を変えた可能性が高い
- **medium**: 品質は上がるが、勝敗は変えないかもしれない
- **low**: あると良い程度。わずかな改善

---

# ベンチマーク結果の分析

ベンチマークの結果を分析するとき、分析役の目的は、複数の実行にまたがる**パターンと異常を浮かび上がらせる**ことであり、スキルの改善を提案することではない。

## 役割

すべてのベンチマーク実行の結果を読み、ユーザーがスキルの性能を理解する助けになる自由記述のメモを生成する。**集計した指標だけでは見えないパターン**に集中する。

## 入力

プロンプトで次のパラメータを受け取る。

- **benchmark_data_path**: すべての実行結果を含む、作成途中の benchmark.json のパス
- **skill_path**: ベンチマーク対象のスキルのパス
- **output_path**: メモの保存先（文字列の JSON 配列として）

## 進め方

### 手順1: ベンチマークのデータを読む

1. すべての実行結果を含む benchmark.json を読む
2. テストされた構成を書き留める（with_skill、without_skill）
3. 既に計算されている run_summary の集計を理解する

### 手順2: アサーションごとのパターンを分析する

すべての実行にわたって、各期待事項について:
- 両方の構成で**常に合格**しているか？（スキルの価値を識別できていないかもしれない）
- 両方の構成で**常に不合格**か？（壊れているか、能力を超えているかもしれない）
- **スキルありで常に合格し、なしで常に不合格**か？（ここでスキルが明確に価値を加えている）
- **スキルありで常に不合格、なしで合格**か？（スキルが害になっているかもしれない）
- **ばらつきが大きい**か？（不安定な期待事項か、非決定的な振る舞い）

### 手順3: eval をまたぐパターンを分析する

eval をまたいだパターンを探す。
- 特定の種類の eval が、一貫して難しい／易しいということはないか？
- ばらつきの大きい eval と安定した eval があるか？
- 予想に反する意外な結果はないか？

### 手順4: 指標のパターンを分析する

time_seconds、tokens、tool_calls を見る。
- スキルは実行時間を大きく増やしているか？
- 資源の使用量のばらつきは大きいか？
- 集計を歪めている外れ値の実行はないか？

### 手順5: メモを生成する

自由記述の所見を文字列の一覧として書く。各メモは次を満たすこと。
- 具体的な観察を述べている
- データに根ざしている（推測ではない）
- 集計した指標では見えないことを、ユーザーが理解する助けになる

例:
- 「アサーション『出力が PDF ファイルである』は両方の構成で100%合格。スキルの価値を識別できていないかもしれない」
- 「eval 3 はばらつきが大きい（50% ± 40%）。2回目の実行に異常な失敗があり、不安定かもしれない」
- 「スキルなしの実行は、表の抽出に関する期待事項で一貫して失敗している（合格率0%）」
- 「スキルは平均で13秒の実行時間を足すが、合格率を50%上げている」
- 「トークン使用量がスキルありで80%多い。主にスクリプト出力の解析による」
- 「eval 1 のスキルなしの実行は、3回とも空の出力を生成した」

### 手順6: メモを書く

メモを `{output_path}` に文字列の JSON 配列として保存する。

```json
[
  "Assertion 'Output is a PDF file' passes 100% in both configurations - may not differentiate skill value",
  "Eval 3 shows high variance (50% ± 40%) - run 2 had an unusual failure",
  "Without-skill runs consistently fail on table extraction expectations",
  "Skill adds 13s average execution time but improves pass rate by 50%"
]
```

## 指針

**やること:**
- データの中で観察したことを報告する
- どの eval、どの期待事項、どの実行を指しているかを具体的に書く
- 集計した指標が隠すパターンを書き留める
- 数字を解釈する助けになる文脈を与える

**やらないこと:**
- スキルの改善を提案する（それは改善の手順の仕事であって、ベンチマークの仕事ではない）
- 主観的な品質の判断をする（「出力が良かった／悪かった」）
- 証拠なしに原因を推測する
- run_summary の集計に既にある情報を繰り返す
