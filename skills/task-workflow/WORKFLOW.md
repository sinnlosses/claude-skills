# タスク運用（develop/task/ ＋ 台帳 ＋ `task` コマンド）の正典

**置き場は2方式ある。** 既定は `develop/task/` の1件1ファイルと git の外の台帳（以下の節の大半）。
設定ファイルの「## タスク運用」に `- タスクの置き場: beads` の行があるプロジェクトだけ、錠・本文・
履歴を Beads（`bd`）に置く（末尾の「Beads 方式」。サブコマンドと出力の先頭語は同じで、違うところは
その節にまとめる）。

`/next-task`・`/plan-tasks`・`/list-tasks`・`/retrospect`・`/setup-tasks` が従うルール。
**手順は `task` コマンドが持ち、自己テスト（`scripts/selftest_task.py`）で守る。** スキルの本文は
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
| ## `task` コマンドの参照 | サブコマンドと出力、終了コードの表 |
| ## 旧形式からの移行 | `LEGACY` が出たときの案内 |
| ## Beads 方式（`- タスクの置き場: beads`） | 錠と履歴を Beads（`bd`）に置く方式。設定の行、今の運用との対応、サイクルで変わるところ、トラッカー（GitHub・Jira）、バックアップ |

## ファイル配置と設定ファイル（AGENTS.md → CLAUDE.md の順）

置き場は**規約で固定**する（設定で変えられない）。

| 場所 | 役割 |
| --- | --- |
| `develop/task/T-xxx.md` | タスク1件1ファイル（正典。`done`・`dropped` も同じ場所に残し、**振り返りが済んだものが10件溜まったら `task prune` でまとめて消す**（移す先は無い。本文は git の履歴から読む）） |
| `develop/direction.md` | まだタスクになっていないユーザーの指示（`## ユーザーから` の節。下の「指示メモ」）。**新形式の目印**も兼ねる |
| `develop/draft/<YYYY-MM-DD>-<要約>.md` | まだタスクになっていないエージェントのドラフト（1件1ファイル。下の「指示メモ」） |
| `develop/retrospective.md` | 手で呼ぶ `/retrospect`（まとめての振り返り）がどこまで振り返ったかの記録。1件ごとの振り返りは書かない（印は `## 結果` の `- 振り返り:` の行） |
| `docs/history/direction.md` | 指示の履歴（タスク化した指示を日付見出しの下に移す） |
| `docs/history/tasks.md`・`docs/history/progress.md` | 旧形式の時代の履歴。**読むだけで書き足さない** |
| 台帳 `$(git rev-parse --path-format=absolute --git-common-dir)/task-workflow/` | 着手の印（`claim/T-xxx/owner`）・採番の錠（`lock/`）・最後の番号（`last-id`）。コミットしない。全作業ツリーで1つ |

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

- **行の頭は変えない**（スキルは `sed -n '/^## タスク運用/,/^## /p'` で、`task` は行頭で読む）。
  走らせるコマンドが無ければ `なし` と書き、**行を消さない**（「検討して不要」と「未検討」を
  区別するため）。検証コマンドは最初の `` `…` `` を `sh -c` で打つ
- `- ブランチ:` は**値の先頭語だけ**を `task` が読む（後ろは人向けの説明で自由）:

| 先頭語 | 意味 |
| --- | --- |
| `既定` ／ `作業ブランチを切る` | `claim` が主ブランチから `feature/T-xxx` を切って移り、`ship` が送ったあと枝から降りて消す（下の「送り出し」） |
| `切らない` | いまの枝のまま。主ブランチの上ならそのまま積み、作業ツリーの枝なら `ship` で送る |
| それ以外 | `INVALID`（終了コード3）。どの手順に従うか機械が決められない |

merge commit を作る運用は選べない。**主ブランチへの ff マージ（`ship` に限らず、タスクの成果として
よそのリポジトリの主ブランチを進める場合も含む）は、人に確認を挟まず自動でやってよい**
（2026-09-16 にユーザーが指示）。push はどのプロジェクトでもスキルからは行わない（この自動化にも
push は含まない）。

**主ブランチの名前は `main` に固定しない**（`master`・`trunk` のリポジトリでも動く）。`task` は
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

YAML に見えるが **YAML ではない**。書くのは `task` コマンドだけで、人が手で直すのは `status` の
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

**本文の節**（並びは固定。無い節は飛ばす）:

| 節 | いつ・誰が書くか | 必須か |
| --- | --- | --- |
| `## 目的` | 登録時（`/plan-tasks`） | 必須 |
| `## 完了条件` | 登録時 | 必須。検証可能な言葉で |
| `## 背景` | 登録時 | 必須 |
| `## 決まっていること（蒸し返さない）` | 登録時（聞いて決まったこと・承認の範囲。検討の経緯は書かない） | 任意 |
| `## 解くべき論点` | 登録時（`opus` には必ず） | 任意 |
| `## やること` | **着手直後**に、いまの主ブランチで調べ直して書き足す | 着手時に必須 |
| `## 注意` | 登録時・着手時・作業中の知見 | 任意 |
| `## 結果` | `task done` | done/dropped で必須 |

`task new` は `## 目的`・`## 完了条件`・`## 背景` の欠けた本文と、`## やること`・`## 結果` を含む本文を
拒む（登録時に書いた手順は着手までに古くなる）。`task migrate` で移したファイルは本文の節の検査を
受けない。

**読み取りの見本**（Python の `scripts/taskfile.py` と、それを読む各プロジェクトの読み手
（tsukumo の `src/shared/task-summary.ts` など）の**両方のテストに写す**。片方だけ直して黙って
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
 (無) ─task new─▶ todo ─task claim─▶ todo＋印 ─task done＋コミット＋task ship─▶ done / dropped（印は消える）
                  ▲  │                  │ task release
          人が直す │  ▼ 人が直す          ▼
                  hold                 todo
```

- `CLAIMED`（作業中）は「`todo` ＋ 台帳の印」。`hold` は人の判断待ちで、`claim` は拒む。
  `hold` ↔ `todo` はサブコマンドを持たず、人（か人がいるセッション）が1語直してコミットし `ship` で送る
  （ユーザーが直接呼んだ `/next-task` が、メインで判断を聞いてこの切り替えをすることもある）
- **依存の解決**: `done`・`dropped` と、タスクファイルに無い ID（`task prune` で消したもの・旧アーカイブ由来）は解決済み。
  `todo`・`hold` は未解決
- **取り残し**（前提: 1つの作業ツリーでは同時に1セッション）:

| 状態 | 表示 | 誰が何をする |
| --- | --- | --- |
| **自分の**作業ツリーの印が `/next-task` の開始時点で残っている | `CLAIMED`（印の列が自分） | 前のセッションが落ちた。着手せず、`task release T-xxx`（捨てる）か人が続きを見るかを預けて止まる |
| 他の作業ツリーの印で、その作業ツリーが消えている／主ブランチでもう done・dropped／`owner` が無いまま60秒 | `STALE:gone`／`STALE:shipped`／`STALE:no-owner` | `task status` が出すだけ。片付けるのは人（`task release T-xxx --force`） |
| それ以外 | `CLAIMED`（経過時間つき） | 触らない。長さだけで取り残しと言わない |

錠・印を時間で自動的に壊さない。取り残しは人に預ける。

## summary（一行要約）

本文を読まずに一覧を見るための一行。**登録時に必ず埋める。**

- **1行に収める。** 折り返しが要る長さ（`task status` の `long_summary` が拾う）は、タスクが大きすぎる合図
- 本文の言い換えではなく「何をするか」を、対象を識別子で書く（`ConfigDirPath` を `ConfigRootPath` に改名）。
  理由は `## 背景` の担当

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

- 迷ったら1段上。作業量では上げない。着手して判断が重いと分かったら上げてから再開する
- **メインセッションのモデルは判断材料にしない**（セッションは自分のモデルを途中で変えられないので、
  切り替えの手段は委譲だけ）。**一致していても委譲する**——理由はモデルではなく文脈の隔離
- **委譲しないのは `loopable: N` に当たるとき**（ユーザーへの確認が要る・会話の文脈に依存する）だけ。
  そのときだけメインが実行し、実行モデルは `difficulty` と一致しない
- 本文を prompt に貼らない。ID とファイルのパス（`develop/task/T-xxx.md`）を渡して向こうに読ませる
- 完了報告をそのまま信用せず、受け入れはメイン側で検証コマンドの結果で決める

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
ユーザーに聞けないので、委譲すると決める人がすり替わる。手順は `next-task/SKILL.md` の手順3a）。

## 1サイクル

`/next-task` の1回。各段で打つものと、止まる出力は `skills/next-task/SKILL.md`。

1. `task status` で見渡す → `READY` を1件選ぶ
2. `task claim T-xxx`（主ブランチへ追い付き、印を立て、必要なら作業ブランチを切る）
3. 委譲先が**いまの主ブランチで調べ直して `## やること` を書き足す**。前提が崩れていれば作業せず、
   `task done --dropped` にする理由を報告する
4. 作業する（`develop/task/` 以外の `develop/` は触らない）
5. 受け入れ: 差分を読む → 整形コマンド → 検証コマンド
5a. 振り返り（`/loop` からも。`retrospect` の SKILL.md「1件だけ振り返る」）: 兆候に当たったときだけ
   `develop/draft/` にドラフトのファイルを足す
6. `task done T-xxx --result-file -`（`status` と `## 結果` を書いて stage。印はまだ消さない）
7. 作業とタスクファイル（積んだならドラフトのファイルも）を**1コミット**（`T-xxx: <件名>`。
   触ったファイルを個別に `git add`）
7a. `task prune`（振り返り済みの `done`・`dropped` が10件以上溜まっていれば `git rm` して stage。
   届かなければ `NOTHING` で何もしない）。`PRUNED` なら**別の1コミット**
   （件名 `振り返り済みのタスクファイルを消す（N件）`。タスクIDを置かない——`scan.py` が件名のIDで
   割り付けるので、置くとそのタスクの材料に削除が混ざる）。いま完了にしたタスクは印があるので次の回で消える
8. `task ship`（主ブランチへ送り、印を消す。7a のコミットも一緒に送る）

## 送り出し

`task ship` はタスクに紐付かない（登録・振り返り・`hold` の切り替えのコミットも同じ `ship` で送る）。

- 主ブランチより遅れていれば `git rebase <主ブランチ>`（付け替えるのは自分の `<主ブランチ>..HEAD` だけ）。衝突したら
  `rebase --abort` して `CONFLICT`
- 送るのは `git -C <本体> merge --ff-only <コミット>`（本体 = 主ブランチを出している作業ツリー）か、
  本体が無ければ比較付きの `git update-ref`。先を越されたら rebase からやり直し、3回で `RACE`
- **merge commit は作らない**。本体が汚れていれば `MAIN_DIRTY` で送らない
- 並行する作業ツリーが同じタスクファイルを `task prune` で消していても、両側の削除は衝突しない
  （中身がすべて主ブランチにあるコミットは rebase が落とす）。消したファイルを相手が書き換えていたときだけ `CONFLICT`
- 主ブランチを出している作業ツリーで起こしたときは送る段が無く、印を消して `SHIPPED <主ブランチ>` を返す

| 検証コマンドを打つ時点 | 誰が | なぜ |
| --- | --- | --- |
| 受け入れ（`task done` の前） | スキル | 作業の合否そのもの。整形コマンドもここ |
| `ship` の中で rebase が実際に付け替えたとき | `task` | 両側の変更が初めて同じ木に乗る |
| 主ブランチへ送ったあと | 打たない | fast-forward なので、主ブランチの木は直前に検証した木と同じ |

**作業ブランチの後始末**（`- ブランチ:` が `既定`／`作業ブランチを切る` で、いまの枝が `feature/T-xxx`
のとき）: 送ったあと、**`claim` した時点の枝**（印に記録）→ 主ブランチの順に移り、`feature/T-xxx` を
消す。別の作業ツリー（本体）が主ブランチを出していると主ブランチには移れないので、作業ツリー固有の枝へ
戻して主ブランチまで追い付かせる。どちらにも移れなければ主ブランチの位置で detached HEAD にする
（次の `claim` は主ブランチから切るので困らない）。**どこに降りたかは `SHIPPED` 行末の `branch=`**
（`branch=wt1-branch`／`branch=<主ブランチ>`／`branch=detached`）に出る。`kept=feature/T-xxx` が付いたら
枝を消せなかった合図で、完了報告に書いて人に預ける（消すかどうかは人が決める）。

## 結果の書き方と知見の置き場

`## 結果` は `task done --result-file` に渡す**3行程度**。宣言ではなく後から検証できる形で書く:

- 検証コマンドの通過件数（増減が分かる形。`1204 pass / 0 fail（+9）`）
- 生成物・検証ログへの具体的な参照、よそのリポジトリのコミットハッシュ
- 1件ごとの振り返りの印（`/next-task` を通したタスク）: `- 振り返り: 兆候なし` か
  `- 振り返り: <当たった兆候>（ドラフト N件）`。**行頭の `- 振り返り:` は機械が読む**（`retrospect` の
  `scan.py` が「1件ごとに振り返り済み」と判定する）ので形を変えない
- **自分の完了のコミットのハッシュは書けない**（`## 結果` がそのコミットに入り、rebase で変わる）。
  そのタスクのコミットは `git log --grep=T-xxx` で引く

書かないこと: 設計の物語、撤回した案、手順の詳細、変更したファイルの列挙。

**知見は done の前に、正典かタスクへ置く。** `develop/progress.md` は無い:

| 中身 | 置き場 |
| --- | --- |
| 何を・なぜ・どう検証したか | そのタスクの `## 結果` |
| 判断待ち | `hold` のタスク（人の判断待ち）か `todo` のタスク（直すもの） |
| 長く効く前提 | プロジェクトの正典の docs の該当節（「既知の制約」など） |
| 一時的な注意 | 関係するタスクの `## 注意` |

## コミットメッセージ

- タスクのコミットは**件名の先頭にタスクID**（`T-110: コミットメッセージにタスクIDを振る`）。
  1タスク＝1コミットは「作業とタスクファイルを1コミット」で守られる。分けられない場合だけ
  `T-105, T-108: 〜`
- **IDを持たない作業には付けない**（登録・振り返り・`hold` の切り替え・移行・typo修正）
- 過去のコミットは書き換えない。末尾の attribution はセッションの指示に従う

## 指示メモ（`develop/direction.md`）

まだタスクになっていない指示の置き場で、書き手と扱いで2つに分ける:

| 置き場 | 書き手 | タスク化してよい条件 |
| --- | --- | --- |
| `develop/direction.md` の `## ユーザーから` | ユーザー（ファイル入口） | いつでも（`/loop` の `/next-task` からも） |
| `develop/draft/` のファイル（エージェントのドラフト） | エージェント（作業中の「これも直したい」、`/retrospect`、`/next-task` の1件ごとの振り返り。最後のものは `/loop` からも、兆候に当たったときだけ積む） | **対話セッションでユーザーの承認を得たものだけ**。`/loop` からはタスク化しない |

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

- `develop/direction.md` にドラフトの節は置かない（見出しの行の括弧に置き場だけを書く）。
  `init.py` は、ドラフトを積んでいたころの節（`## エージェントのドラフト`）に行が残っていれば
  `旧ドラフト節 N行` と数えて PENDING にする。見つけたら1件ずつ上の形のファイルへ移し、節を消す
- **会話入口**: チャットでの明示の指示（「これタスクにして」「それでいいよ」）も拾う。検討中の発言・
  思いつきは拾わない。迷ったら拾わない。`/loop` から回っているときは使わない
- 節見出しの無い古い `develop/direction.md` は、全体を `## ユーザーから` とみなす
- **登録する数に上限は置かない**（`READY` が何件あっても `task new` は拒まない）。登録から着手まで
  間が空いたタスクは `## 背景` が主ブランチとずれうるので、着手直後の `## やること` を書くときに
  いまの主ブランチと突き合わせる
- **タスク化した項目は置き場から取り除き（`## ユーザーから` は行を消し、ドラフトはファイルを
  `git rm` する）、`docs/history/direction.md` の先頭に日付見出し（`## YYYY-MM-DD`）で移す。**
  書くのは3つだけ: ユーザーの生の言い回し（ドラフト由来ならファイルの中身に
  `（エージェントのドラフト / 承認: 「…」）` を1行添える）、項目 → タスクIDの対応表、
  タスクにしなかった項目の理由。噛み砕いた説明は書かない（本文の `## 背景` と二重になる）。
  移した記述は後から書き換えない

## `task` コマンドの参照

スキルからは `python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py <サブコマンド>`
（以下 `task`。PATH には入れない。**変数に入れず、毎回そのまま打つ**——`T="python3 …"; $T …` は
zsh で単語に分かれず空振りし、`;` で続けた後続のコマンドだけが走る）。どのディレクトリから
打ってもリポジトリの根で動く。出力は常に stdout の TSV で、1行目の先頭語が種類。

| サブコマンド | すること | 主な出力 |
| --- | --- | --- |
| `status [--all] [--check]` | 一覧（done/dropped は件数だけ。`--all` で行も）。`--check` は検証コマンド向けの厳しい判定 | 行 `id/status/difficulty/loopable/dependencies/着手可否/印/summary`、`---` の後に `counts`・`ready`・`todo_loopable`・`stale`・`invalid`・（残っていれば）`legacy_progress` |
| `new --summary … --difficulty … --loopable Y\|N [--deps T-001,…] [--hold] --body-file <path\|->` | 錠の中で採番してファイルを作る（コミットしない） | `CREATED`・`LOCKED` |
| `claim T-xxx` | clean・未送りなしを確かめ、主ブランチへ追い付き、印を立て、設定なら枝を切る | `CLAIMED`・`TAKEN`・`NOT_READY`・`DIRTY`・`UNSHIPPED` |
| `release T-xxx [--force]` | 印を消すだけ（ファイルは戻さない）。`--force` は人が取り残しを片付けるとき | `RELEASED`・`NOT_CLAIMED`・`NOT_OWNER` |
| `done T-xxx [--dropped] --result-file <path\|->` | `status` と `## 結果` を書いて stage（コミットしない・印は残す） | `DONE`・`NOT_OWNER` |
| `ship` | rebase → （付け替えたら）検証 → ff-only で送る → 印を消す → 作業ブランチから降りる | `SHIPPED`・`NOTHING`・`MAIN_DIRTY`・`CONFLICT`・`VERIFY_FAILED`・`RACE` |
| `prune [--dry-run] [--min N]` | `HEAD` で `done`・`dropped`・印なし、かつ振り返り済み（`## 結果` に `- 振り返り:` の行がある＝`reviewed`／`develop/retrospective.md` の基準点の版で既に `done`・`dropped`＝`retrospect`）のタスクファイルを `git rm` して stage（コミットしない）。対象が `--min`（既定10）件に届かなければ何もしない。`--dry-run` は一覧だけ（汚れていても打てる） | 対象ごとに `PRUNE\tT-xxx\t<reviewed\|retrospect>`、最後に `PRUNED\t<N>`／`PLAN\t<N>`（`--dry-run`）。対象が無いか `--min` 件に届かなければ `NOTHING`。`DIRTY`・`INVALID`（基準点のハッシュが無い） |
| `migrate [--dry-run]` | 旧形式を変換する（下の「旧形式からの移行」） | `WRITE`・`MOVE`・`LEFTOVER`・`REMOVE`・`PLAN`/`MIGRATED` |
| `show T-xxx` | タスク1件をタスクファイルの形で出す（読むだけ。ファイル方式は作業ツリーの版、無ければ主ブランチの版） | 本文。無ければ `NOT_READY` |
| `config-doctor` | このリポジトリが今の読み取りに合っているかを点検する（**読むだけ。`--fix` は無い**）。主ブランチが何で決まったか・設定ファイルがどちらか・「## タスク運用」の3行・旧形式の残り、の4検査を必ず1行ずつ出す | `base_branch`・`config_file`・`claude_md_lines`・`legacy` の4行。各行の2語目が `OK`／`MISSING`／`MISSING_LINE`／`BAD_BRANCH`／`NO_SECTION`／`FOUND`／`INVALID` |

| 終了コード | 先頭語 | 意味 | スキルがすること |
| --- | --- | --- | --- |
| 0 | 各成功語 | 成功 | 次へ |
| 1 | （traceback） | 環境の故障 | エラー出力を報告して止まる。**手で代用しない** |
| 2 | （stderr） | 渡した引数・本文の誤り | 直して打ち直す |
| 3 | `INVALID` | データの不備（読めないタスクファイル、移行途中、`- ブランチ:` が読めない、主ブランチが決まらない、`--check` の重複、`develop/retrospective.md` の基準点がリポジトリに無い） | 理由をそのまま報告して止まる。**直しに行かない** |
| 4 | `TAKEN`・`NOT_READY`・`DIRTY`・`MAIN_DIRTY`・`UNSHIPPED`・`LOCKED`・`NOT_OWNER` | いまの状態では進めない | 各スキルの表のとおり（別の1件を選ぶか止まる） |
| 5 | `LEGACY` | 旧形式 | 下の「旧形式からの移行」を案内して止まる |
| 6 | `MISSING` | タスク運用を始めていない | `/setup-tasks` を案内して止まる |
| 7 | `CONFLICT` | rebase が衝突した（`--abort` 済み） | 衝突したファイルを添えて人に預ける |
| 8 | `VERIFY_FAILED` | 付け替えのあとの検証が落ちた（送っていない） | 出力の末尾を添えて人に預ける |
| 9 | `RACE` | `--ff-only` が3回続けて落ちた | 人に預ける |

`/loop` は 1・3〜9 のどれで止まっても「続行不要」の合図として扱う。

**`config-doctor` だけは終了コード1の意味が違う**（「直すものがある」。環境の故障ではない）。4検査の最悪値を返し、`INVALID` があれば3、直すものがあれば1、全部OKで0。点検のコマンドなので、1で止まっても報告するだけでよい。


## 旧形式からの移行

`develop/tasks.json` があって `develop/task/` が無いプロジェクトでは、`task` のどのサブコマンドも
`LEGACY\ttask migrate --dry-run`（終了コード5）で止まり、`init.py` も何も作らずに `LEGACY` を返す。
**スキルはここで止まって移行を案内する。自分で移さない**（全作業ツリーの手を止める必要があり、
判断が要る）。案内する手順（プロジェクトごとに人が行う）:

1. そのプロジェクトの全作業ツリーの手を止め、主ブランチに `doing` が無いこと、各作業ツリーに
   主ブランチへ入っていないコミットと未コミットの変更が無いことを確かめる
2. 主ブランチを出している作業ツリーで `task migrate --dry-run` → 件数と `LEFTOVER` を見る
3. `task migrate` → 差分を見て1コミット（件名「タスクを1件1ファイルへ移す」。IDなし）
4. CLAUDE.md「## タスク運用」の `- ブランチ:` を語彙に合わせ、`develop/tasks.json`・
   `develop/progress.md` を名指ししている説明を直す
5. `task status` の一覧が移行前と ID・status・依存で一致することを確かめる
6. ほかの作業ツリーは、再開するときに `git rebase <主ブランチ>`（自分のコミットが無いので追い付くだけ）
7. `develop/progress.md` に残った「未解決」「注意」（と前置き文）を上の「知見の置き場」の表で
   振り分けて消す。残っているあいだは `task status` の `legacy_progress` 行が知らせる（止めはしない）

変換の規則: `status: done` ＋ `passes: true` → `done`、`passes: false` → `dropped`、`doing` が
残っていれば `NOT_READY` で全体を止める。`evidence` は `## 結果` になる。「完了したこと」の小節は
全部 `docs/history/progress.md` へ移る。`docs/history/tasks.md` は動かさない。
`develop/tasks.json` と `develop/task/` の両方があれば移行が途中で、`INVALID`（終了コード3）になる。


## Beads 方式（`- タスクの置き場: beads`）

錠（着手の印・採番）と本文・履歴を Beads（`bd` 1.3.0 で確かめた）に置き、`task` は Beads と
トラッカーと git をつなぐ薄い包みになる。**ファイル方式と併存し、設定の行が無いプロジェクトは
ファイル方式のまま**（`.beads` があっても見ない）。サブコマンド・出力の先頭語・終了コードは
ファイル方式と同じで、スキルは下の「サイクルで変わるところ」だけを読み替える。設計の経緯と
Beads の挙動の実測は tsukumo の `docs/research/github-projects.md`。

**設定の行**（「## タスク運用」節の任意行。どれも無いのが既定）:

| 行 | 値 | 無いとき |
| --- | --- | --- |
| `- タスクの置き場:` | `develop/task`（ファイル方式）・`beads` | ファイル方式。ほかの値は `INVALID`（終了コード3） |
| `- トラッカー:` | `なし`・`github`・`jira` | `なし`。ほかの値は `INVALID` |
| `- GitHub Project:` | `` `<owner>/<番号>` ``（Status 欄を書く Project） | `github` なら `INVALID` |
| `- バックアップ:` | `` `<パス>` ``（git の外） | `${XDG_DATA_HOME:-~/.local/share}/task-workflow/<本体の作業ツリーの名前>` |

**用意**: `/setup-tasks` の `init.py` が、主ブランチを出している作業ツリー（本体）で
`bd init --stealth -p t` を打ち、独自の状態 `pending:frozen` を足す。`.beads` は本体の根に1つで、
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
| タスクID `T-123` | Beads の中は `t-123`（接頭辞は小文字だけ）。`task` の入出力とコミットの件名は `T-123` のまま |
| 採番の錠（`lock/`）と `last-id` | `bd create --id t-<n>`（同じ番号は1つしか作れない。負けたら次の番号で打ち直し、20回で `LOCKED`）。最後の番号は `bd kv` の `task-workflow.last-id`。候補は Beads の番号・`bd kv`・主ブランチの `develop/task/` と `docs/history/tasks.md`・台帳の `last-id` の最大 |
| 着手の印（`mkdir claim/T-xxx`） | `bd update --claim`（actor は作業ツリーの名前）。`claim` した時点の枝は metadata `task_branch` |
| `NOT_OWNER` | `done`・`release` の前に assignee が自分かを見る（`bd close` も actor が違えば拒む） |
| `todo`・`hold` | `open`・`pending`（`bd ready` から外れる） |
| `done`・`dropped` | `bd close`（`dropped` は label `cancelled` を足す。独自の状態 `cancelled` は依存を解決しないので使わない） |
| `difficulty`・`loopable` | label `difficulty:<値>`・`loopable:<Y/N>` |
| `dependencies` | `blocks` の依存（`bd create --deps`） |
| `summary` | `title` |
| `## 完了条件` | `acceptance_criteria` |
| `## やること` | `notes` |
| `## 目的`・`## 背景`・`## 決まっていること`・`## 解くべき論点`・`## 注意` | `description`（見出しのまま） |
| `## 結果`（`- 振り返り:` を含む） | `## 結果` で始まる comment（最後のものが正） |
| 登録から完了までの本文の差（`retrospect` の材料） | `bd history`（`material.py` が最初と最後の版の差を出す） |
| git に残る過去の `develop/task/` と `docs/history/` | 動かさない |
| 送り出し（`task ship`） | そのまま（git の手順は同じ） |

**サイクルで変わるところ**（「1サイクル」の各段の読み替え）:

- **読む・書く**: タスクファイルを開く代わりに `task show T-xxx`（タスクファイルと同じ形で出す）。
  直すのは `task edit T-xxx --body-file <path|->`（本文を丸ごと渡す。`## 完了条件`・`## やること` は
  それぞれの欄へ分けて入れ、版は `bd history` に残る。`## 結果` は拒む）。`hold` ↔ `todo` は
  `task edit T-xxx --status todo|hold`、`loopable`・`difficulty`・`summary` も `task edit` の引数で直す
  （コミットも `ship` も要らない）
- **`done`**: `## 結果` を comment に入れ、label `ship:done`／`ship:dropped` を立てる（stage しない。
  印はまだ消さない）。コミットは作業のファイルだけで、差分が無ければコミットしない
- **`ship`**: 送り終えたあと（`SHIPPED`・`NOTHING` のどちらでも）、自分の印のうち `ship:*` の立った
  ものを `bd close` する（依存はここで初めて解決する。主ブランチに作業が入る前に後段を開けない）。
  閉じられなかったものは `NOT_CLOSED\tT-xxx\t<理由>` の行。続けて `TRACKER`・`BACKUP` の行が付く
- **`prune`**: 消すタスクファイルが無いので常に `NOTHING`
- **取り残し**: `STALE:gone` は assignee がどの作業ツリーの名前でもない、`STALE:shipped` は `ship:*` が
  立っていて主ブランチに着手より後の `T-xxx:` の件名のコミットがある、`STALE:no-owner` は assignee の
  無い `in_progress`。片付けるのは人（`task release T-xxx --force` ＝ `bd unclaim --force`）。
  **`bd reclaim` を打たない**——`--claim` には5分の lease が付くが、期限が過ぎても他の actor は
  `claim` できない（実測）。期限切れの印を外すのは `bd reclaim` だけで、それは長い作業の印を壊す
- **振り分け前**（番号でない ID か、`difficulty`・`loopable` の label が無い課題。トラッカーから
  取り込んだもの）: `status` の `着手可否` が `TRIAGE` で、末尾の `triage` 行に出る。`claim` は
  `NOT_READY\tT-xxx\tTRIAGE`。人の確認つきで `task adopt <ID> --difficulty … --loopable … --body-file …`
  （番号を振り、`## 完了条件` を書き起こす）してから着手する
- **`status` の末尾**: `invalid` の次に `triage\t<件数>\t<ID>` が必ず、`jira` なら `jira_close` 行が付く

**トラッカー**（錠と本文は Beads が持ち、トラッカーは写し。**失敗はタスクの操作を止めない**——
`new`・`claim`・`release`・`edit`・`adopt`・`ship` は `TRACKER\tFAILED\t…` の行を足して終了コードは
そのまま。打ち直しは `task sync`）:

| 方式 | すること | しないこと |
| --- | --- | --- |
| `github` | `bd github sync --push-only`（Issue と label。token は `GITHUB_TOKEN` が無ければ `gh auth token`）→ Project の Status 欄を `gh project item-edit` で書く（`pending` → `Pending`、`open` → `Todo`、`in_progress` → `In progress`、閉じた → `Done`、`cancelled` → `Cancel`。Project に無い Issue は `item-add`）。`bd` は Status 欄を触らない | `--pull-only`・引数なしの `sync`（GitHub 側の変更を取り込まない） |
| `jira` | `task sync` で `bd jira sync --pull` だけ。ローカルで閉じた Jira の課題（`external_ref` あり）には label `jira:close` を付け、`status` の `jira_close` 行に出す。人が Jira で閉じたら `task jira-closed T-xxx` で外す | Jira へ書く（`--push`・引数なしの `sync`）。状態は人が Jira で変える |
| `なし` | 何もしない（`task sync` は `NOTHING`） | ― |

**Jira の方式は本物の Jira で試していない**（サイトとトークンが要る）。`bd jira sync --pull` が
ローカルで閉じた課題をどう扱うか（開き直すか）は未確認で、試すときは人に用意を頼む。

**バックアップ**: `.beads` は git の外なので、タスクの記録は git の履歴に残らない。`task ship` の
最後と `task backup` が、置き場へ `bd backup sync`（Dolt の履歴ごと。置き場が未設定なら
`bd backup init <置き場>/dolt`）と `bd export -o <置き場>/issues.jsonl` を取る（`BACKUP\tOK|FAILED\t<置き場>`）。
**置き場がリポジトリの中なら取らない**——`bd export` の JSONL には作成者のメールアドレス（`owner`）が
入るので、公開リポジトリにコミットされうる場所へ置かない。戻すのは `bd backup restore`（人が行う）。

**触らないもの**: `bd metrics`（端末全体の設定）、`bd reclaim`、`bd init` の `--stealth` なし。

**Beads 方式だけのサブコマンド**（ファイル方式で打つと終了コード2。`show` は両方式）:

| サブコマンド | すること | 主な出力 |
| --- | --- | --- |
| `show T-xxx` | タスク1件をタスクファイルの形で出す（読むだけ） | 本文。無ければ `NOT_READY` |
| `edit T-xxx [--body-file …] [--summary …] [--difficulty …] [--loopable Y\|N] [--status todo\|hold]` | 本文と属性を直す。`--status` は着手前（`open`・`pending`）だけ | `EDITED`・`NOT_READY` |
| `adopt <ID> --difficulty … --loopable … [--summary …] --body-file …` | 振り分け前の課題に番号と label と本文を付ける | `ADOPTED\t<元のID>\tT-xxx` |
| `sync` | トラッカーへ写す（打ち直し） | `TRACKER\tOK\|FAILED\t…`・`NOTHING` |
| `backup` | バックアップを取る | `BACKUP\tOK\|FAILED\t<置き場>` |
| `jira-closed T-xxx…` | `jira:close` を外す | `CLEARED` |

| 終了コード | 先頭語 | 意味 | スキルがすること |
| --- | --- | --- | --- |
| 6 | `MISSING\t<.beads のパス>` | 設定は Beads 方式なのに `.beads` が無い | `/setup-tasks` を案内して止まる |
| 10 | `TRACKER\tFAILED`・`BACKUP\tFAILED`（`sync`・`backup` だけ） | トラッカー・バックアップに届かない | 行を添えて報告する（タスクの操作は済んでいる） |

`config-doctor` は `- タスクの置き場:` 行があるときだけ、4行のあとに `store`・（Beads 方式なら）
`beads`・`tracker` の行を足す（`beads\tMISSING` は終了コード1）。
