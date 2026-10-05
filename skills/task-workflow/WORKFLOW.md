# タスク運用（develop/task/ ＋ 台帳 ＋ `tw` コマンド）の正典

**置き場は2方式ある。** 既定は `develop/task/` の1件1ファイルと git の外の台帳（以下の節の大半）。
設定ファイルの「## タスク運用」に `- タスクの置き場: beads` の行があるプロジェクトだけ、錠・本文・
履歴を Beads（`bd`）に置く（末尾の「Beads 方式」。サブコマンドと出力の先頭語は同じで、違うところは
その節にまとめる）。

`/next-task`・`/plan-tasks`・`/list-tasks`・`/retrospect`・`/setup-tasks` が従うルール。
**手順は `tw` コマンドが持ち、自己テスト（`scripts/selftest_task.py`）で守る。** スキルの本文は
「どのサブコマンドをいつ打つか」と「人が判断する点」だけで、プロジェクト側で手順を上書きする
仕組みは無い。設計の経緯と採らなかった案は claude-skills の `docs/task-workflow-redesign.md`。

## 目次

| 節 | 中身 |
| --- | --- |
| ## ファイル配置と設定ファイル（AGENTS.md → CLAUDE.md の順） | 置き場（`develop/task/`・`develop/direction.md`・`develop/draft/`・`docs/history/`・台帳）と、設定ファイルの探し方・3行と `- ブランチ:` の語彙、主ブランチの決め方 |
| ## タスクファイル | front matter の文法、本文の節、読み取りの見本（両方の読み手のテストに写す表） |
| ## status と着手の印 | 遷移、依存の解決、取り残しの判定 |
| ## summary（一行要約） | 一行に収める理由 |
| ## difficulty とモデルの切り替え | 基準表、委譲の規則と、一致していても委譲する根拠の実測 |
| ## loopable（`/loop` に載せてよいか） | `Y`/`N` の基準、`hold` との違い |
| ## 1サイクル | claim → やること → 作業 → 受け入れ → 振り返り → done → コミット → ship |
| ## 送り出し | `ship` の送り方、検証コマンドを打つ時点、作業ブランチの後始末 |
| ## 結果の書き方と知見の置き場 | `## 結果` に書くこと、`progress.md` をなくした後の置き場 |
| ## コミットメッセージ | タスクIDの付け方 |
| ## 指示メモ（`develop/direction.md`） | ユーザーの節とドラフトのファイル、承認ゲート、入口2つ、ドラフトの書式、指示の履歴 |
| ## `tw` コマンドの参照 | サブコマンドと出力、終了コードの表 |
| ## 旧形式からの移行 | `LEGACY` が出たときの案内 |
| ## Beads 方式（`- タスクの置き場: beads`） | 錠と履歴を Beads（`bd`）に置く方式。ID の決まり方、設定の行、今の運用との対応、サイクルで変わるところ、トラッカー（GitHub・Jira）、GitHub との双方向、切り替え、バックアップ |

## ファイル配置と設定ファイル（AGENTS.md → CLAUDE.md の順）

置き場は**規約で固定**する（設定で変えられない）。

| 場所 | 役割 |
| --- | --- |
| `develop/task/T-xxx.md` | タスク1件1ファイル（正典。`done`・`dropped` も同じ場所に残し、**振り返りが済んだものが10件溜まったら `tw prune` でまとめて消す**（移す先は無い。本文は git の履歴から読む）） |
| `develop/direction.md` | まだタスクになっていないユーザーの指示（`## ユーザーから` の節。下の「指示メモ」）。**新形式の目印**も兼ねる |
| `develop/draft/<YYYY-MM-DD>-<要約>.md` | まだタスクになっていないエージェントのドラフト（1件1ファイル。下の「指示メモ」） |
| `docs/history/direction.md` | 指示の履歴（タスク化した指示を日付見出しの下に移す） |
| `docs/history/retrospect.md` | 横断の振り返りの記録（1回ごとに先頭へ `## YYYY-MM-DD（開始日〜終了日）` の見出しを足す。`retrospect` の SKILL.md「週ごとに振り返る」）。`tw status` が見出しの日付から `retrospect_due` を決める |
| `docs/history/tasks.md`・`docs/history/progress.md` | 旧形式の時代の履歴。**読むだけで書き足さない** |
| 台帳 `$(git rev-parse --path-format=absolute --git-common-dir)/task-workflow/` | 着手の印（`claim/T-xxx/owner`）・採番の錠（`lock/`）・最後の番号（`last-id`）・登録時に `## やること` を書いたときの主ブランチの SHA（`plan-base/T-xxx`。`ship` で消える）・着手から送り出しまでの出来事（`flow/<YYYY-MM>.jsonl`。1行1出来事で、時刻（UTC）・出来事・タスクID・`difficulty` と、`verify`・`ship` の結果の先頭語と `verify` の所要秒、`done` の `dropped` と振り返りが「兆候なし」か。会話・コマンド・パスは入れない。消えない）。コミットしない。全作業ツリーで1つ |
| 作業ツリー固有の git dir `$(git rev-parse --path-format=absolute --git-dir)/task-open-claims/T-xxx` | `claim` から `done`・`release`・`ship` までの控え（中身は空）。`tw commit-guard`・`tw handback-guard` が読む。コミットしない。作業ツリーごと |
| 作業ツリー固有の git dir の `task-verify-stamp`・`task-pause-stamp`・`task-step-stamp` | `tw verify` が通った中身の鍵と、`tw pause`・`tw step` を打った時点の中身の鍵（どれも `HEAD` の SHA・作業ツリーの木の SHA・検証コマンドの3行。`task-step-stamp` は続けてタスクIDと段の番号の2行）。コミットしない。作業ツリーごと |

**プロジェクトごとに変わる値は3行だけで、置き場は「## タスク運用」節を持つ設定ファイル**。
設定ファイルは `AGENTS.md` → `CLAUDE.md` の順で探し、**節を持つ最初のファイルを設定とする**
（`layout.find_config_file` に1箇所化。`task.py` の `read_branch_setting`・`ship.py` の
`read_verify_command`・`init.py` の `check_claude_md`・`maintenance-docs` の `check_docs.py` の
検査5がすべてここを読む）。**両方のファイルに節があれば `INVALID`（終了コード3）**——どちらに
従うか機械が決められないため、黙って片方を選ばない。どちらにも節が無ければ、これまでと同じ既定
（`- ブランチ:` は `既定`、検証コマンドは打たない）に落ちる。以下、見つかった設定ファイルの
中身は次の形（ファイル名がどちらでも同じ）:

```markdown
## タスク運用

- 検証コマンド: `pnpm check`（変更後は必ずこれを通す。受け入れ判定に使う）
- 整形コマンド: `pnpm format`
- ブランチ: 既定

タスクは `develop/task/` に1件1ファイル、指示は `develop/direction.md` に溜め、
`/plan-tasks` でタスク化して `/next-task` で進める。
```

- **行の頭は変えない**（スキルは `sed -n '/^## タスク運用/,/^## /p'` で、`tw` は行頭で読む）。
  走らせるコマンドが無ければ `なし` と書き、**行を消さない**（「検討して不要」と「未検討」を
  区別するため）。検証コマンドは最初の `` `…` `` を `sh -c` で打つ
- `- 送る前の検証コマンド:` は**任意行**（無いのが既定。無くても `MISSING_LINE` にしない。書くなら
  `- 検証コマンド:` の次に置く）。あれば `tw ship` が、付け替えと検証のあと・主ブランチへ入れる直前に、
  最初の `` `…` `` を `sh -c` で**毎回**打つ。`tw verify` の控え（`VERIFIED_SAME`）や借りの有無では
  省かず、落ちれば `VERIFY_FAILED`（終了コード8）で送らない。全件の E2E のように重い検証を、
  送る直前の1回だけに回したいときに使う。`tw verify`・`tw verify-check` は読まない。`なし` なら行が無いのと同じ
- `- 規則の発火の集計:` も**任意行**。直近30日の hook ごとの拒否の回数を出すコマンドを最初の `` `…` `` に書く。
  読むのは `tw` ではなく横断の振り返り（`retrospect` の SKILL.md「週ごとに振り返る」）で、無ければその観点を飛ばす
- `- ブランチ:` は**値の先頭語だけ**を `tw` が読む（後ろは人向けの説明で自由）:

| 先頭語 | 意味 |
| --- | --- |
| `既定` ／ `作業ブランチを切る` | `claim` が主ブランチから `feature/T-xxx` を切って移り、`ship` が送ったあと枝から降りて消す（下の「送り出し」） |
| `切らない` | いまの枝のまま。主ブランチの上ならそのまま積み、作業ツリーの枝なら `ship` で送る |
| それ以外 | `INVALID`（終了コード3）。どの手順に従うか機械が決められない |

merge commit を作る運用は選べない。**主ブランチへの ff マージ（`ship` に限らず、タスクの成果として
よそのリポジトリの主ブランチを進める場合も含む）は、人に確認を挟まず自動でやってよい**
（2026-09-16 にユーザーが指示）。push はどのプロジェクトでもスキルからは行わない（この自動化にも
push は含まない）。

**主ブランチの名前は `main` に固定しない**（`master`・`trunk` のリポジトリでも動く）。`tw` は
この順で決める（`ledger.base_branch`。1回の実行で1度だけ問い合わせて覚える）:

1. 設定ファイル（`AGENTS.md` → `CLAUDE.md` の順）「## タスク運用」の `- 主ブランチ:` 行
   （値は `` `master` `` のように囲む）——**任意行**で、
   保護ブランチや複数リモートの逃げ道。**3行と違って無いのが既定で、無くても `MISSING_LINE` に
   しない。** 囲まなければ最初の語を採り、括弧・句読点の前で切る
2. `git symbolic-ref --short refs/remotes/origin/HEAD` の枝名。**見るのは `origin` だけ**
   （`upstream` などの別名しか無ければ順3へ落ちる。fork 元を主ブランチの出どころにしないため。
   そういうリポジトリは順1の行で名指しする）
3. `main`・`master`・`trunk` のうち実在するもの（この順）
4. どれも無ければ `INVALID`（終了コード3）。**黙って `main` を作らない**

以下この文書で「主ブランチ」と書くのはこの枝で、claude-skills 自身では `main`。

## タスクファイル

YAML に見えるが **YAML ではない**。書くのは `tw` コマンドだけで、人が手で直すのは `status` の
1語くらい（`hold` ↔ `todo`）。

```
file         = "---\n" id-line summary-line status-line difficulty-line loopable-line deps-line "---\n" body
id-line      = "id: " ID "\n"
summary-line = "summary: " TEXT "\n"
status-line  = "status: " ("todo" | "hold" | "done" | "dropped") "\n"
difficulty-line = "difficulty: " ("haiku" | "sonnet" | "opus") "\n"
loopable-line   = "loopable: " ("Y" | "N") "\n"
deps-line    = "dependencies: [" [ID *(", " ID)] "]\n"
ID           = "T-" 3*DIGIT
TEXT         = 1文字以上、改行を含まない。前後の空白は落とす。中身はそのまま（引用・エスケープ無し）
```

- **6行・この順・この綴り。** 欠け・重複・順の違い・知らないキー・CRLF はそのファイルを
  `INVALID` にする（ほかのファイルは読み続ける）。ファイル名の語幹と `id` は一致させる
- ID は `T-` + **3桁以上**（`T-1000` も来る）。並びは数字の大きさで比べる
- 着手中はファイルに書かない（台帳の印が表す）。着手しない判断で閉じたものは `dropped`

**本文の枠**（7つの見出しを**この順に全部**置く。書くことの無い欄は見出しだけ置いて、中身を空か
「なし」にする。見出しより前に文を置かない）:

| 節 | いつ・誰が書くか | 空・「なし」 |
| --- | --- | --- |
| `## 目的・背景` | 登録時（`/plan-tasks`）。何のためか、コードのどこがどうなっているか。待ち時間・実行時間を縮めるタスクは小見出し `### 実測の内訳`（段ごとの時間と測り方）を置く | 不可 |
| `## 決まっていること（蒸し返さない）` | 登録時（聞いて決まったこと・承認の範囲。検討の経緯は書かない） | 可 |
| `## 解くべき論点` | 登録時（`opus` には必ず） | 可 |
| `## やること` | **登録時**（`/plan-tasks`）に、そのときの主ブランチで調べて書く（下の「登録時に書く `## やること`」）。`### 1. …` の形で実行の順に番号を振った段で書き、完了条件の各行をどの段で満たすかが分かるようにする（段は委譲の単位で、委譲先は1段ずつ返す）。着手時に `tw plan-check` が `PLAN_STALE`（名指したファイルが変わった）・`PLAN_NOT_FIRST missing`・`unrecorded`・`steps` を返したら、委譲先が実装の前に調べ直して書き直す（`tw edit T-xxx --section 'やること' --body-file -` で節の中身だけを渡す。作業より先だったかを `tw plan-check` が見る） | 不可（`--hold` で登録するものだけ可。todo に戻したあと着手時に書く） |
| `## 完了条件` | 登録時。検証可能な言葉で | 不可 |
| `## 注意` | 登録時・着手時・作業中の知見 | 可 |
| `## 参考情報` | 登録時・作業中（関係する文書・Issue・過去のタスク・URL） | 可 |

`## 結果` は枠の外で、`tw done` が最後に足す（done/dropped で必須）。`tw new`・`tw adopt` は
枠と違う本文（見出しの欠け・順・枠の外の見出し）、空か「なし」の `## 目的・背景`・`## 完了条件`、
空か「なし」の `## やること`（`--hold` を除く）、下の形に沿わない計画、`## 結果` を拒む。
`tw edit` も枠を検査する（`## やること` は書いてよい。ファイル方式が受けるのは `--body-file`（と `--section`）と、依存を直す `--add-deps`・`--remove-deps` だけ）。

**段の形**: `## やること` の `### ` 見出しは、段 `### <n>. <名前>`（`n` は `### 1.` から1つずつ増える）と
`### 名指すファイル`・`### 作業先` だけで、段は1つ以上置く（名指すファイル・作業先は段に数えない）。
`tw new`・`tw adopt` と、`## やること` を変えて中身を入れる `tw edit`（`--section 'やること'` も本文ごとも）は、
この形に沿わない計画を理由つきで終了コード2で拒み、何も書かない。`## やること` を変えない `tw edit` は
段を見ない。入口を通らずに入った段の読めない計画は、`tw plan-check` が `PLAN_NOT_FIRST\tT-xxx\tsteps` で
書き直しへ回す。
いまの `## 目的・背景`・`## 完了条件` と違う本文は `--change-frame` なしでは `FRAME_CHANGED` で拒む
（別のタスクの下書きを渡す事故を防ぐ。この2節を変えるのは `tw show` から作り直した本文のときだけ）。`tw migrate` で移した
ファイルは本文の節の検査を受けない。

**登録時に書く `## やること`**（`tw new`・`tw adopt`）は、段のほかに小見出し
`### 名指すファイル` を1つ置き、計画が前提にするファイルを1行1つ `` - `パス` ``（後ろに説明を書いてよい）で並べる。
パスはリポジトリの根からの相対で、登録時の主ブランチの木にあるファイルかディレクトリに限る（新しく作るファイルは
置くディレクトリを名指す）。作業先が別のリポジトリなら、小見出し `### 作業先` を1つ置いてそのリポジトリの根の
絶対パスを1行 `` - `パス` `` で書く（`~` は展開して書く）。そのとき名指すファイルは作業先の根からの相対で、
検査・SHA の控え・着手時の判定は作業先のリポジトリ（の主ブランチ）で行う。
`tw new`・`tw adopt` は `HEAD` と主ブランチの分かれ目の SHA を控え、`tw claim` がその SHA から着手時の主ブランチの先端までに
名指したファイルが変わったかを判定する（`tw plan-check` の `PLAN_REGISTERED`・`PLAN_STALE`）。
変わっていれば、委譲先が実装の前に調べ直して書き直す。

**読み取りの見本**（Python の `scripts/taskfile.py` と、それを読む各プロジェクトの読み手
（例: TypeScript で front matter を読む要約関数）の**両方のテストに写す**。片方だけ直して黙って
ずれるのを防ぐ。見本の正典はこの表）:

| 入力（front matter の該当行） | 読んだ結果 |
| --- | --- |
| `summary: ` + `` `a: b` `` + ` # c [d]` | summary = `` `a: b` # c [d] ``（そのまま） |
| `summary:   前後に空白   ` | summary = `前後に空白` |
| `dependencies: []` | 依存なし |
| `dependencies: [T-001, T-1000]` | `T-001`, `T-1000` |
| `dependencies: [T-001,T-002]` | INVALID（区切りは `", "`） |
| `loopable: y` | INVALID（`Y`/`N` だけ） |
| `status: doing` | INVALID（着手中はファイルに書かない） |
| キーが5行しか無い／`owner: x` が混ざる／`summary` と `status` の順が逆 | INVALID |
| ファイル名 `T-010.md` で `id: T-011` | INVALID |
| 1行目が `---` でない | INVALID |

## status と着手の印

```
 (無) ─tw new─▶ todo ─tw claim─▶ todo＋印 ─tw done＋コミット＋tw ship─▶ done / dropped（印は消える）
                  ▲  │                  │ tw release
          人が直す │  ▼ 人が直す          ▼
                  hold                 todo
```

- `CLAIMED`（作業中）は「`todo` ＋ 台帳の印」。`hold` は人の判断待ちで、`claim` は拒む。
  `hold` ↔ `todo` はサブコマンドを持たず、人（か人がいるセッション）が1語直してコミットし `ship` で送る
  （ユーザーが直接呼んだ `/next-task` が、メインで判断を聞いてこの切り替えをすることもある）
- **見送り（やらない）と決まったら、その場で `dropped` にして閉じる。** 決定を `## 決まっていること`・
  `## 注意` に書くだけで `todo`・`hold` に残さない（残すと `/next-task` が READY として選び、委譲先が
  前提を確かめ直すだけの空振りになる）。`claim` していなければ `claim` してから `tw done --dropped`
  で閉じる
- **依存の解決**: `done`・`dropped` と、タスクファイルに無い ID（`tw prune` で消したもの・旧アーカイブ由来）は解決済み。
  `todo`・`hold` は未解決。後から変えるのは `tw edit T-xxx --add-deps T-yyy` と `--remove-deps`（本文の `## 注意` に書くだけでは台帳に入らず、BLOCKED に出ない）
- **委譲先のコミットを拒む**: 印を立ててから `done` を打つまで、その作業ツリーで `no-delegate` の委譲先が
  `git commit` などコミットを作る git のサブコマンドを打つと、hook（`tw commit-guard`）が拒む。
  メインのセッションと、別の作業ツリー・別のリポジトリへのコミットには掛からない。`general-purpose` への
  委譲と、Bash のコマンド文字列に `git` が出ないコミット（`sh -c`・スクリプト越し）には効かず、
  `done` の `COMMITS_SINCE_CLAIM` が事後に拾う
- **委譲先の返却を拒む**: 同じ間、その作業ツリーに作業（`claim` した時点の `HEAD` より後のコミットか、
  タスク自身のファイル以外の変更）があるのに、`plan-check` が `PLAN_FIRST`・`PLAN_REGISTERED` でないか
  `verify-check` が `VERIFIED_SAME`・`NOTHING` でないまま `no-delegate` の委譲先が返そうとすると、hook
  （`tw handback-guard`）が拒んで理由を委譲先へ返す。作業の無い返却（前提が誤り・`dropped`・計画だけの回・
  作業先が別のリポジトリの回）は通す。最後でない段を済ませた返却は、委譲先が `tw step T-xxx <n>` で
  いまの中身に段の印を付けてから返す（`plan-check` は通っている要がある。最後の段は印を付けられず、
  `verify-check` を求める）。目視待ち・判断が要って止める返却は、委譲先が `tw pause` で
  いまの中身に印を付けてから返す（どちらの印も、印のあとに中身が変われば効かない）。`general-purpose` への委譲には効かない
- **取り残し**（前提: 1つの作業ツリーでは同時に1セッション）:

| 状態 | 表示 | 誰が何をする |
| --- | --- | --- |
| **自分の**作業ツリーの印が `/next-task` の開始時点で残っている | `CLAIMED`（印の列が自分） | 前のセッションが落ちた。着手せず、`tw release T-xxx`（捨てる）か人が続きを見るかを預けて止まる |
| 他の作業ツリーの印で、その作業ツリーが消えている／主ブランチでもう done・dropped／`owner` が無いまま60秒 | `STALE:gone`／`STALE:shipped`／`STALE:no-owner` | `tw status` が出すだけ。片付けるのは人（`tw release T-xxx --force`） |
| それ以外 | `CLAIMED`（経過時間つき） | 触らない。長さだけで取り残しと言わない |

錠・印を時間で自動的に壊さない。取り残しは人に預ける。

## summary（一行要約）

本文を読まずに一覧を見るための一行。**登録時に必ず埋める。**

- **1行に収める。** 折り返しが要る長さ（`tw status` の `long_summary` が拾う）は、タスクが大きすぎる合図
- 本文の言い換えではなく「何をするか」を、対象を識別子で書く（`ConfigDirPath` を `ConfigRootPath` に改名）。
  理由は `## 目的・背景` の担当

## difficulty とモデルの切り替え

**判断の重さ**を3段階で表すラベル。以下の対応表に従い、委譲先サブエージェントのモデルが決まる。

| 値 | 基準 | 例 |
| --- | --- | --- |
| `haiku` | 機械的な作業。判断がほぼ不要で正解が1つに定まる | 型定義を1ファイルに抜き出す |
| `sonnet` | 通常の実装。設計判断は局所的で、既存の方針・前例に沿えば決まる | 責務ごとのファイル分割 |
| `opus` | 方針・設計そのものの判断が要る。原則の衝突・トレードオフ・並行性やエラー方針 | 並列化の設計 |

**difficulty → 委譲先モデルの対応表**（ラインナップが変わったら**この表だけ**を直す。3段の語彙・
台帳・各スキルの本文は触らない）:

| difficulty | Agent ツールに渡す `model` | いまその名前が指すモデル（2026-09-27 時点） |
| --- | --- | --- |
| `haiku` | `haiku` | Claude Haiku 4.5（`claude-haiku-4-5`） |
| `sonnet` | `sonnet` | Claude Sonnet 5（`claude-sonnet-5`） |
| `opus` | `opus` | Claude Opus 5（`claude-opus-5`） |

渡すのは**世代を含まない短い名前**（`haiku`／`sonnet`／`opus`）で、世代が上がっても指す先が
入れ替わるだけなので、ふだんは右端の列だけが古くなる。`fable` のように3段に割り当てていない
モデルもあるので、**3段の語彙＝実在のモデル名だと読まない**（右端の列が対応の正典）。
右端の列（いまその名前が指すモデル）を直すときは、`/claude-api` で現行のモデルIDを確かめてから書く。記憶で書かない。

- 迷ったら1段上。作業量では上げない。着手して判断が重いと分かったら上げてから再開する
- **メインセッションのモデルは判断材料にしない**（セッションは自分のモデルを途中で変えられないので、
  切り替えの手段は委譲だけ）。**一致していても委譲する**——理由はモデルではなく文脈の隔離
- **委譲しないのは `loopable: N` に当たるとき**（ユーザーへの確認が要る・会話の文脈に依存する）だけ。
  そのときだけメインが実行し、実行モデルは `difficulty` と一致しない
- 本文を prompt に貼らない。ID とファイルのパス（`develop/task/T-xxx.md`）を渡して向こうに読ませる
- 完了報告をそのまま信用せず、受け入れはメイン側で検証コマンドの結果で決める（目視の完了条件は、メインが画像を開いて見比べて決める）

委譲の実測（3プロジェクトの委譲269件）: メインに残るのは prompt 約3,000文字＋スタブ 1,122文字＋
完了報告 2,938文字（中央値）で**約7,000文字**。同じ作業をメインで行うと CLAUDE.md（ある
プロジェクトで7,681文字）・規約・対象ソース・テスト出力が全部メインに入り、`/loop` ではサイクルごとに
積み上がる。本文を貼っていた244件は、読ませた24件より prompt が中央値で1,006文字長かった。
`haiku` を例外にしないのは、実績で269件中13件（5%）しかなく、「これは例外か」の判断が毎回1つ増えるため。

## loopable（`/loop` に載せてよいか）

そのタスクを**ユーザーのいないところで進めてよいか**。`difficulty` とは独立。基準は
「**登録時にユーザーへ聞いても解けなかったもの**」だけを `N` にする:

| `N` にしたくなる理由 | 事前に聞けば解けるか |
| --- | --- |
| 複数案のどれを採るかが未定 | 解ける（決めて `## 決まっていること` に焼く） |
| 会話中の文脈に依存する | 解ける（文脈を本文に書き出す） |
| 元に戻せない／外部へ反映する | 解ける（承認の範囲を本文に書く） |
| 対話的な検証が要る | **解けない** → `N` |

迷ったら聞く。聞けない状況（無人のセッション）のときだけ `N`。`/loop` の `/next-task` は `N` を
選ばず、ユーザーが直接呼んだときは選んでよい。

**`hold` との違い**: `N` は「人がいれば誰でも進められる」、`hold` は「人が決めるまで誰も進められない」
（決まっていない判断そのものが待っている）。`hold` は `/loop` の `/next-task` が選ばない。ユーザーが
直接呼んだときは選んでよいが、判断は**委譲せずメインで** `AskUserQuestion` で聞き、答えを
`## 決まっていること（蒸し返さない）` に焼いて `todo` に戻してから `claim` する（サブエージェントは
ユーザーに聞けないので、委譲すると決める人がすり替わる。手順は `next-task/hold.md`）。

## 1サイクル

`/next-task` の1回。各段で打つものと、止まる出力は `skills/next-task/SKILL.md`。

1. `tw status` で見渡す → `READY` を1件選ぶ（`retrospect_due` の行があれば、選ぶ前に横断の振り返りを1回行って送る。
   `next-task/weekly-retrospect.md`）
2. `tw claim T-xxx`（主ブランチへ追い付き、印を立て、必要なら作業ブランチを切る）→ `tw plan-check T-xxx`
3. 確かめる: `PLAN_REGISTERED`（登録時に書いた `## やること` が名指すファイルが変わっていない）なら、メインが
   `## やること` が `## 完了条件` の各行を覆うかを読んで確かめ、覆っていれば計画どおりに委譲する。
   `PLAN_STALE`（変わった）・`PLAN_NOT_FIRST missing`・`unrecorded`・`steps`、または覆っていなければ、書き直しから委譲する
   （委譲先が**いまの主ブランチで調べ直して `## やること` を書き直し、作業せずに返す**。`tw edit T-xxx --section 'やること' --body-file -`
   が作業より先に書いたかを印に残し、作業の後の初回の記入は拒む）。設計を利用者とすでに決め、正典・コードを
   読んでいるときはメインが書いてもよい。条件・渡す言葉は `next-task/rewrite-plan.md`
4. 委譲（段ごと。`next-task/SKILL.md` 手順5・5b）: 最初の委譲で段1を渡し、委譲先は段を1つ済ませるたびに返す。最後でない段は `tw step T-xxx <n>` を打ってから、最後の段は `tw verify` を通してから返す。メインは同じ委譲先を `SendMessage` で再開して次の段を渡す（`difficulty` を上げるときだけ上のモデルで起こし直す）。前提が崩れていれば作業せず、`tw done --dropped` にする理由を報告させる。計画どおりに委譲するときは、条件を満たせば文書の担当（`sonnet` 固定、同時に1匹まで）を並べて起こす（条件・渡す言葉は `next-task/parallel-docs.md`）。返りではメインが `tw plan-check T-xxx`（`PLAN_REGISTERED` か `PLAN_FIRST` か）と `## やること` の中身を見る（`next-task/SKILL.md` 手順5b）。`develop/task/` 以外の `develop/` は触らない。検証コマンドは `tw verify` で打つ（打つ前に主ブランチを未コミットの中身ごと取り込み、衝突したら打たずに `CONFLICT`。通ると作業ツリーの中身の鍵を控える。`## やること` が空のまま作業があれば打たない）。描画を変えるタスクでは、組み立てた直後に画を撮ってメインの目視を受けてから、E2E の期待値の撮り直しと `tw verify` に進む（`next-task/visual-review.md`）
5. 受け入れ: 完了条件に目視があれば委譲先の画像を最低1枚（いちばん狭い幅）開いて見比べる → 差分を読む → 整形コマンド → `tw verify-check`（作業先が別のリポジトリなら、委譲先が残したそのリポジトリの作業ツリーで打つ。`next-task/other-repo.md`。`VERIFIED_SAME` なら検証を省く。ほかは `tw verify`。主ブランチが進んでいれば `NOT_VERIFIED base` で、`tw verify` が取り込んでから打つ）
5a. 振り返り（`/loop` からも。`retrospect` の SKILL.md「1件だけ振り返る」）: 兆候に当たったときと、
   変更量の観点（コード・文書）で減らせる形が見つかったときだけ `develop/draft/` にドラフトのファイルを足す
6. `tw done T-xxx --result-file -`（`status` と `## 結果` を書いて stage。印はまだ消さない）
7. 作業とタスクファイル（積んだならドラフトのファイルも）を**1コミット**（`T-xxx: <件名>`。
   触ったファイルを個別に `git add`）
7a. `tw prune`（振り返り済みの `done`・`dropped` が10件以上溜まっていれば `git rm` して stage。
   届かなければ `NOTHING` で何もしない）。`PRUNED` なら**別の1コミット**
   （件名 `振り返り済みのタスクファイルを消す（N件）`。複数タスクをまとめて消す1コミットなので
   タスクIDを置かない）。いま完了にしたタスクは印があるので次の回で消える
8. `tw ship`（主ブランチへ送り、印を消す。7a のコミットも一緒に送る）

## 送り出し

`tw ship` はタスクに紐付かない（登録・振り返り・`hold` の切り替えのコミットも同じ `ship` で送る）。

- 主ブランチより遅れていれば `git rebase <主ブランチ>`（付け替えるのは自分の `<主ブランチ>..HEAD` だけ）。衝突したら
  `rebase --abort` して `CONFLICT`
- 送るのは `git -C <本体> merge --ff-only <コミット>`（本体 = 主ブランチを出している作業ツリー）か、
  本体が無ければ比較付きの `git update-ref`。先を越されたら rebase からやり直し、3回で `RACE`
- **merge commit は作らない**。本体が汚れていれば `MAIN_DIRTY` で送らない
- 並行する作業ツリーが同じタスクファイルを `tw prune` で消していても、両側の削除は衝突しない
  （中身がすべて主ブランチにあるコミットは rebase が落とす）。消したファイルを相手が書き換えていたときだけ `CONFLICT`
- 主ブランチを出している作業ツリーで起こしたときは送る段が無く、印を消して `SHIPPED <主ブランチ>` を返す

`tw verify` が検証の前に主ブランチを取り込むので、`ship` が付け替えるのは、受け入れから送るまでの間に
主ブランチが進んだときだけ。

| 検証コマンドを打つ時点 | 誰が | なぜ |
| --- | --- | --- |
| 受け入れ（`tw done` の前） | スキル | 作業の合否そのもの。主ブランチを取り込んだあとの中身で打つ。整形コマンドもここ。委譲先が `tw verify` で控えた中身と同じなら省く（`tw verify-check`。控えは cwd の作業ツリーごとなので、別のリポジトリが作業先ならそのリポジトリの作業ツリーで打つ） |
| `ship` の中で rebase が実際に付け替えたとき | `tw` | 両側の変更が初めて同じ木に乗る |
| 主ブランチへ入れる直前（`- 送る前の検証コマンド:` の行があるときだけ） | `tw` | 控えや付け替えの有無に関わらず毎回。`SHIPPED` の行に `preship=ran` が付く |
| 主ブランチへ送ったあと | 打たない | fast-forward なので、主ブランチの木は直前に検証した木と同じ |

`ship` は `tw verify` の控えを読まない（付け替えで中身が変わるので、付け替えた回は控えがあっても検証する）。
送る前の検証コマンドの行があれば、これとは別に毎回打つ（落ちたときの借りの扱いも `VERIFY_FAILED` と同じ）。

`VERIFY_FAILED` で終わったあとは、枝は付け替え済みのまま検証の借りが残る（作業ツリー固有の印。
`git worktree` を消すと一緒に消える）。次に打った `ship` は、その回で付け替えが起きなくても
検証コマンドを打ち直す。通れば借りは消え、以後は今までどおり付け替えた回だけ検証する。

**作業ブランチの後始末**（`- ブランチ:` が `既定`／`作業ブランチを切る` で、いまの枝が `feature/T-xxx`
のとき）: 送ったあと、**`claim` した時点の枝**（印に記録）→ 主ブランチの順に移り、`feature/T-xxx` を
消す。別の作業ツリー（本体）が主ブランチを出していると主ブランチには移れないので、作業ツリー固有の枝へ
戻して主ブランチまで追い付かせる。どちらにも移れなければ主ブランチの位置で detached HEAD にする
（次の `claim` は主ブランチから切るので困らない）。**どこに降りたかは `SHIPPED` 行末の `branch=`**
（`branch=wt1-branch`／`branch=<主ブランチ>`／`branch=detached`）に出る。`kept=feature/T-xxx` が付いたら
枝を消せなかった合図で、完了報告に書いて人に預ける（消すかどうかは人が決める）。

## 結果の書き方と知見の置き場

`## 結果` は `tw done --result-file` に渡す**3行程度**。宣言ではなく後から検証できる形で書く:

- 検証コマンドの通過件数（増減が分かる形。`1204 pass / 0 fail（+9）`）
- 生成物・検証ログへの具体的な参照、よそのリポジトリのコミットハッシュ
- 1件ごとの振り返りの印（`/next-task` を通したタスク）: `- 振り返り: 兆候なし` か
  `- 振り返り: <当たった兆候・観点>（ドラフト N件）`。**行頭の `- 振り返り:` は機械が読む**（`tw prune` が
  この行の有無で「1件ごとに振り返り済み（`reviewed`）」と判定する）ので形を変えない
- **自分の完了のコミットのハッシュは書けない**（`## 結果` がそのコミットに入り、rebase で変わる）。
  そのタスクのコミットは `git log --grep=T-xxx` で引く

書かないこと: 設計の物語、撤回した案、手順の詳細、変更したファイルの列挙。

**知見は done の前に、正典かタスクへ置く。** `develop/progress.md` は無い:

| 中身 | 置き場 |
| --- | --- |
| 何を・なぜ・どう検証したか | そのタスクの `## 結果` |
| 判断待ち | `hold` のタスク（人の判断待ち）か `todo` のタスク（直すもの） |
| 長く効く前提 | プロジェクトの正典の docs の該当節（「既知の制約」など） |
| 一時的な注意 | 関係するタスクの `## 注意`、または行き先のタスクが無ければドラフト（`develop/draft/` の1件1ファイル） |

## コミットメッセージ

- タスクのコミットは**件名の先頭にタスクID**（`T-110: コミットメッセージにタスクIDを振る`）。
  1タスク＝1コミットは「作業とタスクファイルを1コミット」で守られる。分けられない場合だけ
  `T-105, T-108: 〜`
- **IDを持たない作業には付けない**（登録・振り返り・`hold` の切り替え・移行・typo修正）
- 過去のコミットは書き換えない。末尾の署名は、利用者の `CLAUDE.md`（グローバル・プロジェクト）に定めがあればそれに従い（署名を省く定めなら付けない）、無ければセッションの attribution の指示に従う

## 指示メモ（`develop/direction.md`）

まだタスクになっていない指示の置き場で、書き手と扱いで2つに分ける:

| 置き場 | 書き手 | タスク化してよい条件 |
| --- | --- | --- |
| `develop/direction.md` の `## ユーザーから` | ユーザー（ファイル入口） | いつでも（`/loop` の `/next-task` からも） |
| `develop/draft/` のファイル（エージェントのドラフト） | エージェント（作業中の「これも直したい」、`/next-task` の1件ごとの振り返り。後者は `/loop` からも、兆候か変更量の観点に当たったときだけ積む） | **対話セッションでユーザーの承認を得たものだけ**。`/loop` からはタスク化しない |

- **ドラフトは1件1ファイル。積むのはファイルを足すこと、タスクにしたら消すのはファイルを
  `git rm` すること。** 1つのファイルの末尾に積むと、並行する作業ツリーの「末尾を消す」と
  「末尾に積む」が同じ塊になり、付け替えや merge で消した項目が戻る（`merge=union` なら黙って、
  そうでなければ衝突として）。ファイルが分かれていれば、消す側と積む側が同じ行を取り合わない
- ファイル名は `<YYYY-MM-DD>-<英小文字・数字・ハイフンの要約>.md`（例
  `2026-09-27-stabilize-ship-race-selftest.md`）。日付は積んだ日。同名のファイルがあれば要約を
  変える（既存のファイルを書き換えない）。ASCII に限るのは、ファイル名の正規化（macOS）と
  シェルの引用に左右されないため
- 書式（front matter は置かない。機械が読むのはファイルの数だけ）:

  ```markdown
  # <何を変えるか（1行）>（<出どころ: 振り返り: T-302, T-318 ／ 作業中: T-410 など>）

  - 根拠: <材料のどこにどう出ていたか。数で言えるものは数で>
  - 出し先: <どのファイルのどの節に足すか / タスクにするなら何をするタスクか>
  ```

  振り返りから積むドラフトは、`根拠` の前に `- 札: <色> <札>` と `- 根: <キー>` の2行を持つ（語彙と色は `retrospect`
  スキルの SKILL.md の節「札と1行の書式」、根は同じ SKILL.md の「ドラフトに積む」）

- `develop/direction.md` にドラフトの節は置かない（見出しの行の括弧に置き場だけを書く）。
  `init.py` は、ドラフトを積んでいたころの節（`## エージェントのドラフト`）に行が残っていれば
  `旧ドラフト節 N行` と数えて PENDING にする。見つけたら1件ずつ上の形のファイルへ移し、節を消す
- **会話入口**: チャットでの明示の指示（「これタスクにして」「それでいいよ」）も拾う。検討中の発言・
  思いつきは拾わない。迷ったら拾わない。`/loop` から回っているときは使わない
- 節見出しの無い古い `develop/direction.md` は、全体を `## ユーザーから` とみなす
- **登録する数に上限は置かない**（`READY` が何件あっても `tw new` は拒まない）。登録から着手まで
  間が空いたタスクは主ブランチとずれうるので、登録時に書いた `## やること` が名指したファイルが
  変わったかを着手時に `tw` が判定し、変わっていれば委譲先が実装の前に書き直す
- **タスク化した項目は置き場から取り除き（`## ユーザーから` は行を消し、ドラフトはファイルを
  `git rm` する）、`docs/history/direction.md` の先頭に日付見出し（`## YYYY-MM-DD`）で移す。**
  書くのは3つだけ: ユーザーの生の言い回し（ドラフト由来ならファイルの中身に
  `（エージェントのドラフト / 承認: 「…」）` を1行添える）、項目 → タスクIDの対応表、
  タスクにしなかった項目の理由。噛み砕いた説明は書かない（本文の `## 目的・背景` と二重になる）。
  移した記述は後から書き換えない

## `tw` コマンドの参照

`tw <サブコマンド>` で打つ。`tw` は `install.sh` が PATH 上（既定は `~/.local/bin`）に張る
`scripts/task.py` へのシンボリックリンクで、ロジックを持たない。PATH に無ければ `./install.sh` を
打ち直す（`task-workflow` を対象に含める）。どのディレクトリから打ってもリポジトリの根で動く。
出力は常に stdout の TSV で、1行目の先頭語が種類。

| サブコマンド | すること | 主な出力 |
| --- | --- | --- |
| `status [--all] [--check]` | 一覧（done/dropped は件数だけ。`--all` で行も）。`--check` は検証コマンド向けの厳しい判定（`todo`・`hold` は本文の7節の枠も検査する） | 行 `id/status/difficulty/loopable/dependencies/着手可否/印/summary`、`---` の後に `counts`・`ready`・`todo_loopable`・`stale`・`invalid`・（横断の振り返りの時期なら）`retrospect_due`・（残っていれば）`legacy_progress`。`retrospect_due\t<最後の記録の日付>\t<経過日数>d` は `docs/history/retrospect.md` の見出しの日付（主ブランチの版と作業ツリーの版の遅いほう）から7日以上経ったときに出る。記録が無いあいだは台帳の `flow/` の最も古い出来事から7日以上で `retrospect_due\t-\t<経過日数>d`（`flow/` が無ければ出ない） |
| `new --summary … --difficulty … --loopable Y\|N [--deps T-001,…] [--hold] --body-file <path\|->` | 錠の中で採番してファイルを作る（コミットしない）。`## やること` の中身が要る（空にできるのは `--hold` だけ。段の形に沿わない・`### 名指すファイル` が無い・形が違う・パスが木に無い・`### 作業先` が絶対パス1行でないか git のリポジトリの根でなければ、何も作らずに終了コード2）。中身があれば、計画のリポジトリ（`### 作業先` があればそこ）の `HEAD` と主ブランチの分かれ目の SHA を控える（ファイル方式は台帳の `plan-base/T-xxx`、Beads 方式は metadata `task_plan_base`） | `CREATED`・`LOCKED` |
| `claim T-xxx` | clean・未送りなしを確かめ、主ブランチへ追い付き、印を立て（作業ツリー固有の git dir に `task-open-claims/T-xxx` の控えも置く）、設定なら枝を切る。登録時の計画の控えがあれば、名指したファイルが控えから主ブランチの先端までに変わったかを判定し、比べた先端を印に控え（台帳の印の `plan-tip`、metadata `task_plan_tip`）、変わっていなければ印に `registered` を残す（出力は変えない） | `CLAIMED`・`TAKEN`・`NOT_READY`・`DIRTY`・`UNSHIPPED` |
| `release T-xxx [--force]` | 印と `task-open-claims/T-xxx` の控えを消すだけ（ファイルは戻さない）。`--force` は人が取り残しを片付けるときで、控えは印の持ち主の作業ツリーのものを消す（その作業ツリーが消えていれば何もしない） | `RELEASED`・`NOT_CLAIMED`・`NOT_OWNER` |
| `done T-xxx [--dropped] --result-file <path\|->` | `status` と `## 結果` を書いて stage（コミットしない・印は残す）。`task-open-claims/T-xxx` の控えは消すので、このあとのコミットを `commit-guard` は拒まない。本文が枠（`## 結果` を除く7節）と違えば書かずに `INVALID`（終了コード3）。`claim` した時点の `HEAD` より後に、主ブランチに無いコミットがあれば `DONE` に続けて知らせる（`commit-guard` をすり抜けたコミットの事後の知らせ。控えの無い古い印では出さない） | `DONE`（`COMMITS_SINCE_CLAIM` が続くことがある）・`NOT_OWNER`・`INVALID` |
| `ship` | rebase → （付け替えたら）検証 → （送る前の検証コマンドの行があれば）それを毎回 → ff-only で送る → 印と `task-open-claims/T-xxx` の控えを消す → 作業ブランチから降りる | `SHIPPED`・`NOTHING`・`MAIN_DIRTY`・`CONFLICT`・`VERIFY_FAILED`・`RACE` |
| `prune [--dry-run] [--min N]` | `HEAD` で `done`・`dropped`・印なし、かつ振り返り済み（`## 結果` に `- 振り返り:` の行がある＝`reviewed`）のタスクファイルを `git rm` して stage（コミットしない）。対象が `--min`（既定10）件に届かなければ何もしない。`--dry-run` は一覧だけ（汚れていても打てる） | 対象ごとに `PRUNE\tT-xxx\treviewed`、最後に `PRUNED\t<N>`／`PLAN\t<N>`（`--dry-run`）。対象が無いか `--min` 件に届かなければ `NOTHING`。`DIRTY` |
| `migrate [--dry-run]` | 旧形式を変換する（下の「旧形式からの移行」） | `WRITE`・`MOVE`・`LEFTOVER`・`REMOVE`・`PLAN`/`MIGRATED` |
| `show T-xxx` | タスク1件をタスクファイルの形で出す（読むだけ。ファイル方式は作業ツリーの版、無ければ主ブランチの版） | 本文。無ければ `NOT_READY` |
| `edit T-xxx [--section <節名>] [--after-work] [--change-frame] [--add-deps T-001,…] [--remove-deps T-001,…] [--body-file <path\|->]` | `--add-deps`・`--remove-deps`（両方式。`--body-file` が無くてもよく、その場合は本文に触れない）は台帳の依存を直す。削除してから追加し、すでにある依存の追加は通る。自分自身・台帳に無い ID・循環になる辺・形の違う ID・依存にない ID の削除・追加と削除に同じ ID は、何も書かずに終了コード2。以下は本文について。本文を丸ごと書き換える。`--section` を付けると、その節の中身だけを渡した中身に置き換え、ほかの節は1バイトも変えない（節名は `やること`・`## やること` のどちらでも受ける。枠に無い見出し・渡した中身に行頭の `## ` の行があれば、書き込まずに終了コード2。置き換えた全文に下の検査が効く）（ファイル方式は作業ツリーのタスクファイルで、`todo`・`hold` だけ。`--summary` などの属性の引数は Beads 方式だけ）。渡した本文の `## 目的・背景`・`## 完了条件` がいまの本文と違えば、書き込まずに `FRAME_CHANGED\tT-xxx\t<違う節>` で止まる（終了コード4。行末の空白と空行の数の差は違いに数えない。いまの本文に節が無い旧形式は比べない）。変えてよいときだけ `--change-frame`（両方式）を付けて打ち直す。ほかの節だけの書き換えは今までどおり通る。`claim` の後に、着手の印の持ち主が `## やること` に初めて中身を入れたとき、その時点で作業が始まっていたか（`claim` した時点の `HEAD` より後のコミットか、タスク自身のファイルと渡した本文のファイル以外の変更があるか）を1回だけ印に残す（ファイル方式は台帳の印の `plan`、Beads 方式は metadata `task_plan`。値は `first`／`after-work`）。`after-work` になるときは書き込まずに `WORK_BEFORE_PLAN\tT-xxx\t<次の一手>` で止まる（終了コード4）。`--after-work`（両方式）を付けると書き込んで `after-work` を残し、`EDITED` の次に `PLAN_AFTER_WORK\tT-xxx\t作業の後に書いた` の行を足す（作業が始まっていなければ `--after-work` は何も変えず `first`）。front matter 付きの本文は拒む（終了コード2。除いて渡す） | `EDITED`・`NOT_READY`・`WORK_BEFORE_PLAN`・`FRAME_CHANGED` |
| `plan-check T-xxx` | 自分の着手の印について、`## やること` を作業より先に `tw edit` で書いたかを出す（読むだけ） | `PLAN_FIRST\tT-xxx`、そうでなければ `PLAN_NOT_FIRST\tT-xxx\t<理由>`（`missing`＝空か「なし」／`after-work`＝作業が始まってから書いた／`unrecorded`＝`tw edit` が印を残さなかった。`claim` の前に書いた・着手の印の持ち主でない作業ツリーから書いた・`tw edit` を通さずに書いた／`steps`＝中身はあるが段の形（「タスクファイル」の「段の形」）に沿わない。印によらずこれを先に出す）。登録時に書いた計画（`new`・`adopt`）は、名指したファイルが変わっていなければ `PLAN_REGISTERED\tT-xxx\t<控えた SHA>`（`PLAN_FIRST` と同じに扱ってよい）、変わっていて書き直していなければ `PLAN_STALE\tT-xxx\t<変わったファイル,…>`（書き直すと `PLAN_FIRST`）。比べる先は `claim` が控えた着手時の主ブランチの先端なので、受け入れで打っても変わらない。どれも終了コード0。`NOT_OWNER` |
| `verify` | 主ブランチを取り込んでから検証コマンドを打つ。取り込むのは、主ブランチが `HEAD` より先へ進んでいて `HEAD` がその祖先のとき（`claim` のあとに自分のコミットがあれば取り込まず、`ship` が付け替える）で、未コミットの中身を一時のコミットにして `git merge-tree` で主ブランチと合わせ、衝突が無ければ作業ツリーに当てて `HEAD` を主ブランチへ進める（作業は未コミットのまま残る。`git add` 済みの区別は消える）。衝突すれば何も書き換えず、検証コマンドを打たずに控えを消して `CONFLICT` で止まる。取り込みのあと・検証の前に、節に整形コマンドがあれば打つ（`なし` なら打たない。整形で変わった中身を鍵に取るので、続く `verify-check` は `VERIFIED_SAME` になる。整形が落ちたら検証コマンドを打たずに控えを消して `FORMAT_FAILED` で止まる）。打つ前後で作業ツリーの中身の鍵（`HEAD` の SHA・一時の index に `git add -A` して `write-tree` した木の SHA・検証コマンドの文字列。本物の index は変えない）を取り、通って前後で同じなら作業ツリー固有の git dir の `task-verify-stamp` に控える。落ちたら控えを消す。全出力は同じ場所の `task-verify.log`。この作業ツリーが着手の印を持つタスク（`done`・`dropped` にしたものを除く）の `## やること` が空か「なし」のまま作業が始まっていれば（`edit` と同じ判定）、検証コマンドを打たずに控えを消して `PLAN_MISSING` で止まる | 取り込んだときは先頭に `FOLDED\t<前の HEAD>..<主ブランチ>` の1行。`CONFLICT\t<ファイル,…>`（終了コード7）。`VERIFIED\t<木の SHA>\t<ログのパス>`（控えた）／`VERIFIED_UNSTAMPED\t<ログのパス>`（通ったが検証のあいだに中身が変わったので控えない）／`VERIFY_NOT_PASSED\t<ログのパス>`（終了コード10）／`FORMAT_FAILED\t<ログのパス>`（整形コマンドが落ちた。終了コード10）。どれも出力の末尾40行が続き、そのあとに同じ判定行をもう一度出す（取り込んだときは `FOLDED` の行も判定行の前にもう一度出す）。出力を `tail` で切るときは、最後の行（取り込んだときは最後の2行）だけで判定と `FOLDED` の有無が取れる。`PLAN_MISSING\tT-xxx\t<次の一手>`（終了コード10。該当するタスクごとに1行）。検証コマンドが無ければ `NOTHING` |
| `verify-check` | いまの中身の鍵を `verify` の控えと照らす（読むだけ） | `VERIFIED_SAME\t<木の SHA>`（検証を省いてよい）、そうでなければ `NOT_VERIFIED\t<理由>`（`none`＝控えが無い／`base`＝主ブランチが進んでいて `verify` が取り込める／`head`／`content`／`command`）。どちらも終了コード0。検証コマンドが無ければ `NOTHING` |
| `metrics [--days N]` | 台帳の `flow/` の記録（`claim`・`release`・`verify`・`pause`・`step`・`ship`・`done` のたびに両方式で `tw` が1行足す。書けなくても元のサブコマンドの出力と終了コードは変わらず、標準エラーに1行出るだけ）から、直近 N 日（既定 7）と、その前の同じ長さの期間の数を並べる（読むだけ）。`verify` は着手の印を持つタスクごと、`ship` は送れたタスクごと（`VERIFY_FAILED`・`CONFLICT`・`RACE` は印を持つタスクごと）に1行 | 1行目 `PERIOD\t<N>d\tcurrent\tprevious`、続けて `shipped`（送り出した件数）・`lead_median_seconds`・`lead_max_seconds`（着手から送り出しまで）・`verify_per_task`（1件あたりの `verify` の回数の平均）・`verify_failed`（`FORMAT_FAILED`・`VERIFY_NOT_PASSED` の件数）・`ship_verify_failed`（`ship` の `VERIFY_FAILED`）・`reclaim`（`release` のあとの `claim`）・`reflection_none_ratio`（`done` のうち振り返りが兆候なしの割合。`dropped` は除く）の各行が `<名前>\t<今>\t<前>`（無ければ `-`）。壊れた行は読み飛ばし `SKIPPED\t<件数>`。記録が無ければ `EMPTY` |
| `config-doctor` | このリポジトリが今の読み取りに合っているかを点検する（**読むだけ。`--fix` は無い**）。主ブランチが何で決まったか・設定ファイルがどちらか・「## タスク運用」の3行・旧形式の残り、の4検査を必ず1行ずつ出す | `base_branch`・`config_file`・`claude_md_lines`・`legacy` の4行。各行の2語目が `OK`／`MISSING`／`MISSING_LINE`／`BAD_BRANCH`／`NO_SECTION`／`FOUND`／`INVALID` |
| `commit-guard` | Claude Code の PreToolUse hook（`agents/no-delegate.md` の frontmatter）から呼ばれる。stdin の hook の入力を読み、Bash のコマンドのうちコミットを作る git のサブコマンド（`commit`・`merge`・`pull`・`cherry-pick`・`revert`・`am`・`rebase`）の実効の作業先（入力の `cwd`・`cd <dir>`・`git -C <dir>`）に `task-open-claims/` の控えがあれば拒む。両方式で同じ（`bd` を呼ばない） | 拒むときだけ PreToolUse の deny の JSON 1行（理由は「コミットせず…報告で返す」）。通すときは何も出さない |
| `pause` | いまの中身の鍵（`verify` と同じ取り方）を作業ツリー固有の git dir の `task-pause-stamp` に控え、`flow/` に `pause` を1行足す。`handback-guard` は、この控えがいまの中身と同じなら計画・検証が欠けていても返却を通す（目視待ち・判断が要って止める・計画を作業の後に書いた回の委譲先が、返す直前に打つ） | `PAUSED\t<木の SHA>` |
| `step T-xxx <n>` | 自分の着手の印のタスクの `## やること` の段 `n` を済ませた印として、いまの中身の鍵（`verify` と同じ取り方）とタスクID・段の番号を作業ツリー固有の git dir の `task-step-stamp` に控え、`flow/` に `step` を1行足す。`handback-guard` は、この控えがそのタスク・いまの中身と同じで、段がいまの計画の最後より前なら、`plan-check` が通っている限り検証が欠けていても返却を通す（最後でない段を済ませた委譲先が、返す直前に打つ）。段の読めない計画・1〜段の数の外の番号は終了コード2。最後の段は控えずに `LAST_STEP`（終了コード4。`tw verify` を通して返す） | `STEPPED\tT-xxx\t<n>/<段の数>\t<木の SHA>`・`LAST_STEP\tT-xxx\t<n>/<段の数>\t<次の一手>`・`NOT_OWNER` |
| `handback-guard` | Claude Code の hook（`agents/no-delegate.md` の frontmatter の `Stop`（委譲先では `SubagentStop` として効く）と、`SubagentHandback` の `PreToolUse`）から呼ばれる。入力の `cwd` の作業ツリーに `task-open-claims/` の控えがあり、控えのタスクのどれかに作業（`claim` した時点の `HEAD` より後のコミットか、タスク自身のファイル以外の変更）があって、`plan-check` が `PLAN_FIRST`・`PLAN_REGISTERED` でないか、`verify-check` が `VERIFIED_SAME`・`NOTHING` でなく `step` の控えも効かず、`pause` の控えもいまの中身と違えば拒む。Beads 方式では `bd` を呼ぶ | 拒むときだけ JSON 1行（`SubagentStop` は `{"decision":"block","reason":…}`、`PreToolUse` は deny。理由は欠けた `plan-check`・`verify-check` の行と次の一手）。通すとき・ほかのイベントやツールには何も出さない |

| 終了コード | 先頭語 | 意味 | スキルがすること |
| --- | --- | --- | --- |
| 0 | 各成功語（`plan-check` の `PLAN_NOT_FIRST`・`PLAN_STALE`・`verify-check` の `NOT_VERIFIED` を含む） | 成功（`PLAN_NOT_FIRST`・`PLAN_STALE`・`NOT_VERIFIED` は止める合図ではなく、着手・受け入れで扱う知らせ） | 次へ |
| 1 | （traceback） | 環境の故障 | エラー出力を報告して止まる。**手で代用しない** |
| 2 | （stderr） | 渡した引数・本文の誤り | 直して打ち直す |
| 3 | `INVALID` | データの不備（読めないタスクファイル、移行途中、`- ブランチ:` が読めない、主ブランチが決まらない、`--check` の重複） | 理由をそのまま報告して止まる。**直しに行かない** |
| 4 | `TAKEN`・`NOT_READY`・`DIRTY`・`MAIN_DIRTY`・`UNSHIPPED`・`LOCKED`・`NOT_OWNER`・`WORK_BEFORE_PLAN`・`FRAME_CHANGED`・`LAST_STEP` | いまの状態では進めない | 各スキルの表のとおり（別の1件を選ぶか止まる） |
| 5 | `LEGACY` | 旧形式 | 下の「旧形式からの移行」を案内して止まる |
| 6 | `MISSING` | タスク運用を始めていない | `/setup-tasks` を案内して止まる |
| 7 | `CONFLICT` | `ship` の rebase が衝突した（`--abort` 済み）か、`verify` の主ブランチの取り込みが衝突した（何も書き換えていない） | 衝突したファイルを添えて人に預ける。`verify` の衝突を解いたあとは `tw verify` を打ち直す |
| 8 | `VERIFY_FAILED` | 付け替えのあとの検証が落ちた（送っていない）。行は `VERIFY_FAILED\t<コマンド>\t<ログのパス>` で、続けて出力の末尾40行。ログは stdout と stderr を出た順に残した全文 | ログを読み、落ちた箇所を添えて人に預ける |
| 9 | `RACE` | `--ff-only` が3回続けて落ちた | 人に預ける |
| 10 | `VERIFY_NOT_PASSED`・`FORMAT_FAILED`・`PLAN_MISSING` | `verify` の検証コマンドが落ちた／整形コマンドが落ちた（検証は打っていない）／`## やること` が空のまま作業があるので打たなかった（どちらも控えは消えた） | `VERIFY_NOT_PASSED`・`FORMAT_FAILED` は出力の末尾（全体はログ）を読んで直し、`PLAN_MISSING` は `## やること` を書いて `tw edit T-xxx --after-work` で渡し、打ち直す |

**サブコマンドを足すときは、この参照表と終了コード表も同じコミットで直す**（参照表の追随が落ちると、読み手と実装が食い違う）。

`/loop` は 1・3〜9 のどれで止まっても「続行不要」の合図として扱う。

**`config-doctor` だけは終了コード1の意味が違う**（「直すものがある」。環境の故障ではない）。4検査の最悪値を返し、`INVALID` があれば3、直すものがあれば1、全部OKで0。点検のコマンドなので、1で止まっても報告するだけでよい。

**`commit-guard`・`handback-guard` は Claude Code の hook の取り決めに従う**: 出力は TSV でなく JSON で、終了コードはいつも0。
読めない入力も何も出さずに通す。タスク運用を始めていないリポジトリ・git の外でも打てる。


## 旧形式からの移行

`develop/tasks.json` があって `develop/task/` が無いプロジェクトでは、`tw` のどのサブコマンドも
`LEGACY\ttask migrate --dry-run`（終了コード5）で止まり、`init.py` も何も作らずに `LEGACY` を返す。
**スキルはここで止まって移行を案内する。自分で移さない**（全作業ツリーの手を止める必要があり、
判断が要る）。案内する手順（プロジェクトごとに人が行う）:

1. そのプロジェクトの全作業ツリーの手を止め、主ブランチに `doing` が無いこと、各作業ツリーに
   主ブランチへ入っていないコミットと未コミットの変更が無いことを確かめる
2. 主ブランチを出している作業ツリーで `tw migrate --dry-run` → 件数と `LEFTOVER` を見る
3. `tw migrate` → 差分を見て1コミット（件名「タスクを1件1ファイルへ移す」。IDなし）
4. CLAUDE.md「## タスク運用」の `- ブランチ:` を語彙に合わせ、`develop/tasks.json`・
   `develop/progress.md` を名指ししている説明を直す
5. `tw status` の一覧が移行前と ID・status・依存で一致することを確かめる
6. ほかの作業ツリーは、再開するときに `git rebase <主ブランチ>`（自分のコミットが無いので追い付くだけ）
7. `develop/progress.md` に残った「未解決」「注意」（と前置き文）を上の「知見の置き場」の表で
   振り分けて消す。残っているあいだは `tw status` の `legacy_progress` 行が知らせる（止めはしない）

変換の規則: `status: done` ＋ `passes: true` → `done`、`passes: false` → `dropped`、`doing` が
残っていれば `NOT_READY` で全体を止める。`evidence` は `## 結果` になる。「完了したこと」の小節は
全部 `docs/history/progress.md` へ移る。`docs/history/tasks.md` は動かさない。
`develop/tasks.json` と `develop/task/` の両方があれば移行が途中で、`INVALID`（終了コード3）になる。


## Beads 方式（`- タスクの置き場: beads`）

錠（着手の印・採番）と本文・履歴を Beads（`bd` 1.3.0 で確かめた）に置き、`tw` は Beads と
トラッカーと git をつなぐ薄い包みになる。**ファイル方式と併存し、設定の行が無いプロジェクトは
ファイル方式のまま**（`.beads` があっても見ない）。サブコマンド・出力の先頭語・終了コードは
ファイル方式と同じで、スキルは下の「サイクルで変わるところ」だけを読み替える。

**ID はトラッカーで決まる。** トラッカーが `github` なら **GitHub の Issue 番号がタスクID**で、`tw` の
入出力とコミットの件名は `GH-<番号>`（ゼロ埋めしない）、Beads の中は `gh-<番号>`。`なし`・`jira` なら
`tw` が採番し、外は `T-<n>`（3桁以上）、Beads の中は `t-<n>`。ただし `jira` で取り込んだ課題は
**Jira のキーがタスクID**（外は `PROJ-123`、Beads の中は `proj-123`。下の「トラッカー」）。どちらの方式かは Beads の `issue_prefix`
（`gh` か `t`）で決め、`tw` は両方の形を読む（切り替えの途中は `t-<n>` と `gh-<n>` が混ざる）。
加えて **Jira のキー**（`PROJ-123`。プロジェクトキーは2文字以上・英大文字始まり `[A-Z][A-Z0-9_]+-\d+`、
Beads の中は `proj-123`）も同じ ID として読む。読む形はトラッカーで切り替えず常に3つを受け、`T-<n>`・
`GH-<n>` を先に当てるので Jira のキーとは取り違えない。`status` の並びは `T-<n>` → `GH-<n>` → Jira のキー
（キー名・番号の順）→ 仮の ID。`tw` が採番する番号（`last-id` の候補）に Jira のキーは数えない。
ファイル方式・過去の `T-xxx`（git の履歴と `docs/history/`）は動かさない。

**設定の行**（「## タスク運用」節の任意行。どれも無いのが既定）:

| 行 | 値 | 無いとき |
| --- | --- | --- |
| `- タスクの置き場:` | `develop/task`（ファイル方式）・`beads` | ファイル方式。ほかの値は `INVALID`（終了コード3） |
| `- トラッカー:` | `なし`・`github`・`jira` | `なし`。ほかの値は `INVALID` |
| `- GitHub Project:` | `` `<owner>/<番号>` ``（Status 欄を書く Project） | `github` なら `INVALID` |
| `- バックアップ:` | `` `<パス>` ``（git の外） | `${XDG_DATA_HOME:-~/.local/share}/task-workflow/<本体の作業ツリーの名前>` |

**用意**: `/setup-tasks` の `init.py` が、主ブランチを出している作業ツリー（本体）で
`bd init --stealth -p gh`（トラッカーが `github`）か `-p t`（それ以外）を打つ。`hold` は組み込みの
状態 `deferred` に置く（独自の状態は GitHub との往復で `open` に戻るので使わない）。`.beads` は本体の根に1つで、
どの作業ツリーの `bd` も同じデータベースを読む。`--stealth` は `.git/info/exclude` で `.beads` を外し、
コミットも `AGENTS.md`・`CLAUDE.md` への書き足しもしない（**`--stealth` なしの `bd init` を打たない**。
両方を書き足して自動でコミットする）。ただし `--stealth` は利用者の `~/.config/bd/config.yaml` に `no-git-ops: true` を
書き足す（端末全体の設定。2026-09-27 の実測）。`bd` を同時に何本も `init` すると、この設定ファイルの
ほかの値（使用状況の送信を止めた `metrics.disabled`）まで書き戻したことがあるので、`init` は1本ずつ打つ
（自己テストは `HOME` を一時ディレクトリへ向けて利用者の設定に触れない）。`github` なら人が `gh auth login`（`project` スコープ）と
`bd config set github.repository <owner>/<repo>` を済ませる。

**今の運用との対応**（`beads.py` の docstring と同じ表。どれも落とさずに移す）:

| ファイル方式 | Beads 方式 |
| --- | --- |
| タスクID `T-123` | `github`: 外は `GH-5`、Beads の中は `gh-5`（Issue 番号）。`なし`・`jira`: 外は `T-123`、Beads の中は `t-123`（接頭辞は小文字だけ）。`jira` で取り込んだ課題は外が `PROJ-123`、中が `proj-123` |
| 採番の錠（`lock/`）と `last-id` | `github`: GitHub の採番（下の「GitHub との双方向」の登録）。`なし`・`jira`: `bd create --id t-<n>`（同じ番号は1つしか作れない。負けたら次の番号で打ち直し、20回で `LOCKED`）。最後の番号は `bd kv` の `task-workflow.last-id`。候補は Beads の番号・`bd kv`・主ブランチの `develop/task/` と `docs/history/tasks.md`・台帳の `last-id` の最大 |
| 着手の印（`mkdir claim/T-xxx`） | `bd update --claim`（actor は作業ツリーの名前）。`claim` した時点の枝は metadata `task_branch` |
| `NOT_OWNER` | `done`・`release` の前に assignee が自分かを見る（`bd close` も actor が違えば拒む） |
| `todo`・`hold` | `open`・`deferred`（`bd ready` から外れる。GitHub では label `status::deferred`）。切り替え前の独自の状態 `pending` も `hold` と読む |
| `done`・`dropped` | `bd close`（`dropped` は label `cancelled` を足す。独自の状態 `cancelled` は依存を解決しないので使わない） |
| `difficulty`・`loopable` | label `difficulty:<値>`・`loopable:<Y/N>` |
| `dependencies` | `blocks` の依存（`bd create --deps`。後から変えるのは `tw edit --add-deps`・`--remove-deps` が打つ `bd dep add`・`bd dep remove`） |
| `summary` | `title` |
| `## 完了条件` | `acceptance_criteria` |
| `## やること` | `notes` |
| `## やること` を作業より先に書いたかの記録（台帳の印の `plan`。`first`・`after-work`・`registered`） | metadata `task_plan` |
| 登録時に `## やること` を書いたときの SHA（台帳の `plan-base/T-xxx`）と、着手時に比べた主ブランチの先端（台帳の印の `plan-tip`） | metadata `task_plan_base`・`task_plan_tip` |
| `## 目的・背景`・`## 決まっていること`・`## 解くべき論点`・`## 注意`・`## 参考情報` | `description`（見出しのまま）。`tw show` は枠の7節を空でもこの順に出す |
| `## 結果`（`- 振り返り:` を含む） | `## 結果` で始まる comment（最後のものが正） |
| 登録から完了までの本文の差（`retrospect` の材料） | `bd history`（`material.py` が最初と最後の版の差を出す） |
| git に残る過去の `develop/task/` と `docs/history/` | 動かさない |
| 送り出し（`tw ship`） | そのまま（git の手順は同じ） |

**サイクルで変わるところ**（「1サイクル」の各段の読み替え）:

- **読む・書く**: タスクファイルを開く代わりに `tw show T-xxx`（タスクファイルと同じ形で出す）。
  直すのは `tw edit T-xxx --body-file <path|->`（本文を丸ごと渡す。1つの節だけなら `--section <節名>` を足して中身だけを渡す。`## 完了条件`・`## やること` は
  それぞれの欄へ分けて入れ、版は `bd history` に残る。`## 結果` は拒む。`## 目的・背景`・`## 完了条件` を
  いまと違う内容にするときは `--change-frame` を付ける）。`hold` ↔ `todo` は
  `tw edit T-xxx --status todo|hold`、`loopable`・`difficulty`・`summary` も `tw edit` の引数で直す。
  依存は `--add-deps`・`--remove-deps`（`bd dep add`・`bd dep remove`）
  （コミットも `ship` も要らない）
- **`done`**: `## 結果` を comment に入れ、label `ship:done`／`ship:dropped` を立てる（stage しない。
  印はまだ消さない）。コミットは作業のファイルだけで、差分が無ければコミットしない
- **`ship`**: 送り終えたあと（`SHIPPED`・`NOTHING` のどちらでも）、自分の印のうち `ship:*` の立った
  ものを `bd close` する（依存はここで初めて解決する。主ブランチに作業が入る前に後段を開けない）。
  閉じられなかったものは `NOT_CLOSED\tT-xxx\t<理由>` の行。続けて `TRACKER`・`BACKUP` の行が付く
- **`prune`**: 消すタスクファイルが無いので常に `NOTHING`
- **取り残し**: `STALE:gone` は assignee がどの作業ツリーの名前でもない、`STALE:shipped` は `ship:*` が
  立っていて主ブランチに着手より後の `T-xxx:`（`github` なら `GH-<n>:`）の件名のコミットがある、`STALE:no-owner` は assignee の
  無い `in_progress`。片付けるのは人（`tw release T-xxx --force` ＝ `bd unclaim --force`）。
  **`bd reclaim` を打たない**——`--claim` には5分の lease が付くが、期限が過ぎても他の actor は
  `claim` できない（実測）。期限切れの印を外すのは `bd reclaim` だけで、それは長い作業の印を壊す
- **振り分け前**（番号でない ID か、`difficulty`・`loopable` の label が無い課題。トラッカーから
  取り込んだもの）: `status` の `着手可否` が `TRIAGE` で、末尾の `triage` 行に出る。`claim` は
  `NOT_READY\tT-xxx\tTRIAGE`。人の確認つきで `tw adopt <ID> --difficulty … --loopable … --body-file …`
  （label を付け、`## 完了条件` を書き起こす。`jira` はキーの無い課題にだけ番号を振り、キーのある課題は
  キーの ID のまま（まだなら付け替える。行き先が既にあれば `TRACKER\tINVALID` の行を出して終了コード3で、
  番号も振らない）。`github` は取り込みの時点で `gh-<Issue 番号>` になっているので番号は変えない）してから着手する
- **`status` の末尾**: `invalid` の次に `triage\t<件数>\t<ID>` が必ず、`jira` なら `jira_close` 行が付く

**トラッカー**（錠と本文は Beads が持ち、トラッカーは写し。**失敗はタスクの操作を止めない**——
`new`・`claim`・`release`・`edit`・`adopt`・`done`・`ship` は `TRACKER\tFAILED\t…` の行を足して終了コードは
そのまま。打ち直しは `tw sync`。`bd github` は GitHub に届かなくても終了コード0を返すので、`tw` は
`--json` の `stats.errors` と `Warning: Failed` の行で失敗を見る）:

| 方式 | すること | しないこと |
| --- | --- | --- |
| `github` | `issue_prefix` が `gh` なら双方向（下の「GitHub との双方向」）、`t` なら Beads から送るだけ。1件だけを触る操作（`new`・`claim`・`release`・`edit`・`adopt`・`done`）はその1件だけを `bd github push <ID>` で、`ship`・`sync` は全件を `bd github sync --push-only` で送る。そのあと Project の Status 欄を `gh api graphql` で書く（`deferred` → `Pending`、`open` → `Todo`、`in_progress` → `In progress`、閉じた → `Done`、`cancelled` → `Cancel`。Project に無い Issue は足す）。`bd` は Status 欄を触らない。token は `GITHUB_TOKEN` が無ければ `gh auth token` | 引数なしの `bd github sync`・`--pull-only`（`bd` の増分の取り込みは取りこぼす）。`gh project` のコマンド（`item-list` は入れ子の上限で1回約101点かかり、どれも持ち主の照会を足す）。Status 欄を読んで合わせる（人が Project で変えた Status は、次にその課題の Beads の状態が変わるまで戻らない） |
| `jira` | `tw sync`（と各操作のあと）で `bd jira sync --pull` だけ。取り込んだ課題の ID は `issue_prefix` の hash（`t-aby`。数字だけにもなりうる）なので、`external_ref`（`https://<site>/browse/PROJ-123`）のキーと ID が違う振り分け前の課題を `bd rename` で `proj-123` にする（行き先が既にあれば付け替えず `TRACKER\tINVALID\t<ID>\t<行き先> が既にある（付け替えない）`。`bd rename` は接頭辞が `issue_prefix` と違っても通り、次の取り込みは `external_ref` で同じ課題に当てる）。ローカルで閉じた Jira の課題（`external_ref` あり）には label `jira:close` を付け、`status` の `jira_close` 行に出す。人が Jira で閉じたら `tw jira-closed T-xxx` で外す | Jira へ書く（`--push`・引数なしの `sync`）。状態は人が Jira で変える |
| `なし` | 何もしない（`tw sync` は `NOTHING`） | ― |

**Status 欄の控え**（GraphQL の枠は1時間に5000点・アカウント単位で、点数は要求の上限で数えられる）:
Project・Status 欄・選択肢の ID は `bd kv` の `task-workflow.project` に控え、控えで書いて落ちたら（欄や
選択肢を作り直したとき）1回だけ読み直す。Issue ごとの項目 ID と最後に書いた Status は
`task-workflow.project-items`（Issue の URL が鍵）に控え、Beads の状態から決まる Status が控えと同じ課題には
触らない。項目 ID が控えに無い課題は Issue の `projectItems(first: 10)` だけを引き、控えの無い課題が10件を
超えるとき（最初の1回）は Project を `items(first: 100)` の `id`・`content.url`・`fieldValueByName("Status")`
だけで一巡して控えを埋める。Issue の読み書きと取り込む番号を選ぶ一覧は REST で、GraphQL の枠を食わない。

**Jira の方式は本物の Jira で試していない**（サイトとトークンが要る）。取り込んだ課題の ID・`external_ref` の形と、
付け替えたあとの取り込みが同じ課題に当たることは、`jira.url` を手元の偽の HTTP サーバへ向けた `bd` で確かめた（2026-09-29）。`bd jira sync --pull` が
ローカルで閉じた課題をどう扱うか（開き直すか）は未確認で、試すときは人に用意を頼む。

**GitHub との双方向**（`github` のとき。`bd` 1.3.0 の実測に合わせた形）:

- **`bd` の増分の取り込みを使わない**。`bd` は前回の同期の時刻（push でも pull でも進む）より後に
  更新された Issue だけを読むので、その間の GitHub での変更と、立てた直後の Issue を取りこぼす。
  `tw sync` は GitHub の一覧（REST の `repos/<repo>/issues?state=all&since=…`）で見た最後の更新時刻を
  自分で覚え（`bd kv` の `task-workflow.github-seen`。無ければ開いている全件）、その1時間前より後に
  更新された Issue（立てた直後の Issue が一覧に遅れて出る分をさかのぼる）を番号で `bd github pull <番号>…` する
- **登録**（`tw new`）: `bd create --id gh-new-<作業ツリーの名前>-<時刻>`（仮の ID。`bd` の採番は
  数字だけの hash になりうるので使わない）→ `bd github push <仮の ID>` → `external_ref` の末尾の番号 →
  `bd rename <仮の ID> gh-<番号>`（依存・comment・履歴ごと付け替わる）→ もう一度 `bd github push`（付け替えも
  Beads の更新なので、前回の同期の時刻を進めておく）。push で落ちたら仮の ID のまま
  `TRACKER\tFAILED` を出し、`tw sync` が push と付け替えをやり直す
- **取り込み**: 取り込んだ課題の ID は `gh-<時刻>-1-<hash>` なので、`external_ref` の番号 `n` と ID が
  違う課題は `tw` が `bd rename` で `gh-<n>` にする（行き先が既にあれば付け替えず `INVALID` の行）。
  label が無ければ振り分け前（上の「サイクルで変わるところ」）
- **写る欄**: 題 ↔ `title`、本文 ↔ `description`、label ↔ label（`difficulty:*`・`loopable:*`・`ship:*`・
  `cancelled` も）、開閉 ↔ `open`／`closed`、`status::in_progress`・`status::deferred` ↔ `in_progress`・
  `deferred`。`acceptance_criteria`・`notes`・comment（`## 結果`）は Beads だけに置き、GitHub には出さない
- **錠の持ち主**: 取り込みは assignee を GitHub の担当者で上書きし（作業ツリーの名前は GitHub の
  利用者でないので空になる）、metadata を消し、label `status::in_progress` が GitHub に無ければ
  `open` に戻す。`tw` は取り込みを actor `<作業ツリーの名前>:github-pull` で打ち、その更新の書く直前の版
  （`bd history --events` の `old_value`。取り込みの最中に別の作業ツリーが着手しても、その着手が入る）
  から、消えた assignee と metadata の印（`task_*`）を `bd update` で戻す。`open` に戻った着手は、
  着手の送りが GitHub に届く前の版で上書きされたとき（課題を最後に送った時刻が着手より前）だけ
  `in_progress` に戻し、送ったあとで label が外れた・GitHub で担当者が付いたものは手放しとして戻さない。
  戻せなければ `TRACKER\tFAILED` の行を足し、ほかの行（`CLOSED` など）と送りは続ける。
  **取り込みはすべてこの包みを通す**
- **タスクの操作**（`claim`・`release`・`edit`・`adopt`・`done`）: 触る課題だけを
  取り込み → 操作 → `bd github push <ID>` の順で打つ。`ship` は取り込まずに全件を送る。
  取り込みは前回の同期の時刻を進めるので、取り込みのあとの直し（assignee・label・付け替え）は
  その場で送る（送らないと、次の取り込みがその課題を「Beads で変えたもの」として飛ばし、GitHub での変更を送り返して消す）
- **衝突**: 課題ごとの勝ち負けで、欄ごとには合わせない。取り込みは前回の同期より後に Beads で
  変えた課題を上書きしないので、**両側で変えたら Beads が勝ち**、GitHub の版は Issue の編集履歴に残る。
  `tw` はその課題を `TRACKER\tCONFLICT\tGH-<n>` の行で知らせる（人が履歴から拾い直す）。`bd` は飛ばしたことを
  教えないので、`tw` が課題ごとに最後に送った・取り込んだ時刻（`bd kv` の `task-workflow.github-synced`）を
  控え、そのあとに Beads と GitHub の両方で更新された課題を衝突とする
- **GitHub で閉じる**: 取り込むと Beads でも閉じ、依存が解ける。`ship:*` の無い課題が GitHub で
  閉じられたら見送りとして label `cancelled` を足し、`TRACKER\tCLOSED\tGH-<n>` の行を出す（着手中なら
  人に預ける）。GitHub で開き直したら `cancelled` と `ship:*` を外す
- **`tw sync` の順**: 控える → 取り込む → 付け替える・着手の印を戻す（直したものを送る）→
  push（`bd github sync --push-only`）→ 登録で落ちた仮の ID を付け替える → Status 欄を書く

**Jira の方式との違い**:

| | `github` | `jira` |
| --- | --- | --- |
| タスクID | Issue 番号（`GH-5`） | 取り込んだ課題は Jira のキー（`PROJ-123`。取り込みの直後に `external_ref` のキーへ付け替える）、ローカルで `tw new` した課題は `tw` の採番（`T-123`）で、混ざる |
| 登録 | Issue を先に作って番号を得る | Beads だけに作る（Jira に書かない） |
| 同期の向き | 双方向（取り込みは `tw` が番号で選ぶ） | 取り込みだけ（`bd jira sync --pull`） |
| 状態を変える場所 | どちらでも（GitHub で閉じたら見送り） | Beads。Jira で閉じるのは人（`jira_close`） |
| 衝突 | Beads が勝ち、`CONFLICT` の行 | 起きない（Jira に書かない） |

**切り替え**（ファイル方式から Beads 方式へ、`t-<n>` から `gh-<n>` へ）は、全作業ツリーの手を止めて
人が立ち会う。付け替えの前に `bd export` と `bd backup` を取る。`t-<n>` から `gh-<n>` へは、未完了の
課題を `external_ref` の番号へ `bd rename` し、`pending` を `deferred` に変え、旧い ID を `description` の
末尾の1行（`旧ID: T-123`）に残し、`issue_prefix` を `gh` にして `status.custom` を `bd config unset` で外す。
`task-workflow.github-seen` は消しておき、最初の `tw sync` で開いた全件を取り込む。
`issue_prefix` は `bd config set` では変えられず（`bd` 1.3.0 は拒む）、勧められる `bd rename-prefix` は閉じた
`t-<n>` まで付け替えて本文の参照も書き換えるので使わない。`bd` を動かしていないときに、
`.beads/embeddeddolt/<metadata.json の dolt_database>` で
``dolt sql -q "update config set value='gh' where `key`='issue_prefix'"`` を打ち、`dolt commit -am <件名> --author <名前>` で
残す（2026-09-28 に確かめた）。
`jira` で `T-<n>` の ID のまま取り込み済みの課題は、振り分け前（label が無い）なら次の `tw sync` で
キーの ID へ付け替わる。`adopt` 済みの `T-<n>` は `tw` が付け替えない（作業ブランチとコミットの件名が
`T-<n>` を指す）。キーへ揃えるなら、全作業ツリーの手を止めて `bd export` と `bd backup` を取ってから、未完了の
ものを `bd rename t-<n> <キーの小文字>` し、旧い ID を `description` の末尾の1行（`旧ID: T-123`）に残す。
閉じたものは付け替えない。
**置き場や ID を切り替えるコミットは、消す・付け替えるものを全部済ませた木で検証コマンドを打ってから送る。**

**バックアップ**: `.beads` は git の外なので、タスクの記録は git の履歴に残らない。`tw ship` の
最後と `tw backup` が、置き場へ `bd backup sync`（Dolt の履歴ごと。置き場が未設定なら
`bd backup init <置き場>/dolt`）と `bd export -o <置き場>/issues.jsonl` を取る（`BACKUP\tOK|FAILED\t<置き場>`）。
**置き場がリポジトリの中なら取らない**——`bd export` の JSONL には作成者のメールアドレス（`owner`）が
入るので、公開リポジトリにコミットされうる場所へ置かない。戻すのは `bd backup restore`（人が行う）。

**触らないもの**: `bd metrics`（端末全体の設定）、`bd reclaim`、`bd init` の `--stealth` なし。

**Beads 方式だけのサブコマンド**（ファイル方式で打つと終了コード2。`show` は両方式）:

| サブコマンド | すること | 主な出力 |
| --- | --- | --- |
| `show T-xxx` | タスク1件をタスクファイルの形で出す（読むだけ） | 本文。無ければ `NOT_READY` |
| `edit T-xxx [--body-file …] [--section <節名>] [--after-work] [--change-frame] [--summary …] [--difficulty …] [--loopable Y\|N] [--status todo\|hold] [--add-deps …] [--remove-deps …]` | 本文と属性と依存を直す（依存は `bd dep add`・`bd dep remove` を1辺ずつ打つ。`bd` の循環検査の前に tw が先に拒む）。`--status` は着手前（`open`・`deferred`）だけ。`## やること` の初回の記入と `--change-frame` の扱いはファイル方式と同じ | `EDITED`・`NOT_READY`・`WORK_BEFORE_PLAN`・`FRAME_CHANGED` |
| `adopt <ID> --difficulty … --loopable … [--summary …] --body-file …` | 振り分け前の課題に label と本文を付ける（`jira` はキーの無い課題に番号も）。本文の検査は `new` と同じで `## やること` の中身が要り（`--hold` は無い）、`notes` に入れて metadata `task_plan_base` を控える | `ADOPTED\t<元のID>\t<ID>` |
| `sync` | トラッカーと同期する（`github` は双方向、`jira` は取り込み、打ち直しも兼ねる） | `TRACKER\tOK\|FAILED\t…`・`NOTHING` |
| `backup` | バックアップを取る | `BACKUP\tOK\|FAILED\t<置き場>` |
| `jira-closed T-xxx…` | `jira:close` を外す | `CLEARED` |

| 終了コード | 先頭語 | 意味 | スキルがすること |
| --- | --- | --- | --- |
| 6 | `MISSING\t<.beads のパス>` | 設定は Beads 方式なのに `.beads` が無い | `/setup-tasks` を案内して止まる |
| 10 | `TRACKER\tFAILED`・`BACKUP\tFAILED`（`sync`・`backup` だけ） | トラッカー・バックアップに届かない | 行を添えて報告する（タスクの操作は済んでいる） |

`config-doctor` は `- タスクの置き場:` 行があるときだけ、4行のあとに `store`・（Beads 方式なら）
`beads`・`tracker` の行を足す（`beads\tMISSING` は終了コード1）。
