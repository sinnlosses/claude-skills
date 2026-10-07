# 委譲先がシェルでファイルを書き換えるのを機械で止める（振り返り: T-050）

- 観点: 黄 機械の検査
- 根拠: `agents/no-delegate.md` の25行目「ファイルの作成・書き換えは `Edit`・`Write` で行い、シェル（python・sed・heredoc のリダイレクト）で書かない」に反したと、委譲先が friction log に自分で書いた回が4タスク続いた（T-045 の `sed -i` と python の置換、T-046 の BSD の sed、T-048 の python のヒアドキュメント、T-050 の python のヒアドキュメントで red）。文書の規則だけでは止まっていない
- 出し先: `agents/no-delegate.md` の PreToolUse の hook（`tw commit-guard` と同じ並び）に、着手の印が立った作業ツリーで Bash の `sed -i`・`python3 - <<`・`> <パス>` のような書き換えを拒む検査を足すか、規則が要らないなら25行目を消すかを決めるタスク
