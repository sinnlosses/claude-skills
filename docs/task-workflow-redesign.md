# タスク運用の作り直し（設計書）

`task-workflow` と、それを使う `next-task`・`plan-tasks`・`list-tasks`・`retrospect`・
`setup-tasks` を「1件1ファイル＋git の外の台帳＋`task` コマンド」の形に作り直すための設計書。
**このファイルは設計だけを持ち、いまのスキルとスクリプトの振る舞いは変えない**（実装は
tsukumo の T-521〜T-524、切り替えは T-526）。承認済みの方針の出典は tsukumo の
`docs/history/direction.md` 2026-09-24「タスク運用の作り直し」。

## 目次

| 節 | 中身 |
| --- | --- |
| 1. 何を解くか | 課題と、変わる/変わらないものの線引き |
| 2. 論点と結論 | 解くべき論点それぞれへの結論（1論点1行の表） |
| 3. タスクファイル | 置き場・front matter の文法・本文の節・例・読み手（Python と tsukumo の TypeScript） |
| 4. 状態と台帳 | status の遷移、着手の印、錠、最後の番号、取り残しの判定、`main` の作業ツリーで起こしたとき |
| 5. `task` コマンド | 置き場と呼び方、出力と終了コードの共通規約、サブコマンドごとの仕様 |
| 6. 送り出しとブランチ設定 | `- ブランチ:` の語彙、`ship` の送り方、検証コマンドを打つ時点 |
| 7. 登録の上限と `## 積み残し` | 並列数の取り方、上限を超えたとき、積み残しからの繰り上げ |
| 8. 知見の置き場（`progress.md` をなくす） | 何をどこへ書くか |
| 9. スキルと WORKFLOW.md の新しい章立て | 各ファイルの節の並びと、消えるもの |
| 10. 移行 | `task migrate` の変換規則、`progress.md` の扱い、プロジェクトごとの手順、切り替えの順序 |
| 11. 採らなかった案 | 退けた案と理由 |
| 12. 実装タスクへの割り付け | T-521〜T-525 のどれがこの設計のどこを作るか |

## 1. 何を解くか

tsukumo では6本の作業ツリーが `main` の上の `develop/tasks.json` と `develop/progress.md` を
ロック・データベース・作業ログとして共有していて、1週間（09-17〜24）で `main` のマージ以外の
コミット938件のうち694件が `tasks.json` を触り、取り込みのマージが209件、アーカイブが92件
あった。採番の事故（T-225 の重複）、`progress.md` の「未解決」「注意」が減らないこと、運用規則が
1週間に37回書き換わったことも同じ根から出ている。

線引き:

- **git に残すのは変わりにくいもの**（タスクの仕様と結果）だけ。1件1ファイルにするので、別々の
  タスクを触る作業ツリー同士はファイル単位でぶつからない
- **変わりやすいもの**（着手の印・最後の番号・錠）は、全作業ツリーが共有する `.git` の中の
  台帳に置く。コミットしないので `main` を動かさない
- **手順は `task` コマンドが持ち、自己テストで守る。** スキルの本文は「どのサブコマンドを
  いつ打つか」と「人が判断する点」だけにする。プロジェクト側で手順を上書きする二層
  （tsukumo の `CLAUDE.md`「## タスク運用」と `docs/workflow.md`）はやめる
- 変えないもの: `difficulty`・`loopable`・`summary` の意味、サブエージェントへの委譲の規則、
  `develop/direction.md` の `## ユーザーから`／`## エージェントのドラフト` と承認ゲート、
  コミットの件名にタスクIDを置くこと、push をスキルからしないこと

## 2. 論点と結論

| 論点 | 結論（詳細の節） |
| --- | --- |
| front matter の書式と読み方 | YAML ではない専用の6行の文法（`key: value`、キーの順は固定、`dependencies` だけが `[...]` の並び、引用もエスケープも無い）。Python は標準ライブラリで、tsukumo は TypeScript で同じ文法を各自実装し、この設計書の読み取りの見本（3.4）を両方のテストに写す。YAML ライブラリには通さない（3.2） |
| 台帳の置き場と中身 | `$(git rev-parse --path-format=absolute --git-common-dir)/task-workflow/` に `claim/T-xxx/owner`（着手の印）・`lock/`（採番の錠）・`last-id`（最後に払い出した番号）の3つ（4.2） |
| 取り残しの判定 | 自分の作業ツリーの印が残っていれば取り残し（1作業ツリー＝同時に1セッションの前提）。他の作業ツリーの印は、その作業ツリーが消えている・`main` でもう done/dropped になっている・`owner` が書かれないまま60秒経った、のどれかで `STALE` と表示するだけで、消すのは人（4.3） |
| `main` を出している作業ツリーで起こしたとき | 着手の印と採番は同じ。完了のコミットがそのまま `main` に乗るので `ship` は送る段を飛ばして印を消すだけ（4.4） |
| `task` のサブコマンドの引数・出力・終了コード | 5章の表。出力は常に stdout で1行目の先頭語が種類、終了コードは 0/1/2/3/4/5/6/7/8/9 の10種で分岐できる形（5.2） |
| スキルからの呼び方 | `python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py <サブコマンド>`。PATH には入れない（5.1） |
| `ship` と `- ブランチ:` 設定の関係 | 値の先頭語を語彙として読む。`既定`／`作業ブランチを切る` は `feature/T-xxx` を `claim` が切り `ship` が消す、`切らない` はいまの枝のまま。どちらも送り方は同じ（`main` より遅れていれば `git rebase main` → `--ff-only` 相当で送る）で、merge commit は作らない（6.1・6.2） |
| 検証コマンドをいつ打つか | 受け入れ（done の前）でスキルが1回。`ship` は付け替え（rebase）が実際に起きた回だけ `task` 自身が打つ（6.3） |
| `hold` を `/next-task` がどう扱うか | 選ばない。`claim` も拒む。`hold` に依存する `todo` は `BLOCKED`。残りが `hold` だけなら「人の判断待ち」と ID を出して止まる（4.1・9.2） |
| `hold` を `/list-tasks` にどう出すか | 未完了の表に `判断待ち` の行として出す（`todo` → 作業中 → 判断待ちの順）。オススメには出さず、件数と ID を1行添える（9.4） |
| 「並列数」をどこから取るか | `git worktree list` のうち `main` を出していない作業ツリーの数（最低1）。設定は持たない。上限は `task new` が数えて拒む（7.1） |
| `retrospect` の `progress.md` と `evidence` の置き換え | 材料はタスクファイルの本文と `## 結果`、それに登録時から完了時までのタスクファイルの差分（着手時に書き足した `## やること` を含む）。旧タスクは `docs/history/tasks.md`・`docs/history/progress.md` を従来どおり読む。ID の正規表現は `T-\d{3,}` に広げる（9.5） |
| `migrate` で `progress.md` をどう扱うか | 「完了したこと」の小節は全部 `docs/history/progress.md` へ機械的に移す。「未解決」「注意」は動かさず `develop/progress.md` に残し、件数を出す。振り分けは各プロジェクトの人の判断で、終わったら人が消す。新しいスキルは `progress.md` を読まない（10.2） |

## 3. タスクファイル

### 3.1 置き場

- `develop/task/T-xxx.md`。1件1ファイルで、ファイル名の語幹と front matter の `id` は一致する
- `done`・`dropped` も同じ場所に残す。**タスクのアーカイブの段は無くなる**
  （`archive.py` とアーカイブの基準は消える。`docs/history/tasks.md` はこれまでの履歴として
  残し、書き足さない）
- ID は `T-` + **3桁以上**の数字（`T-001` … `T-999`, `T-1000` …）。tsukumo は2週間で T-530 に
  達しているので、4桁は近いうちに来る。並びは数字の大きさで比べる（文字列で比べない）

### 3.2 front matter の文法

YAML に見えるが **YAML ではない**。専用の文法を読み手ごとに実装する（YAML にしない理由は
11章）。書くのは `task` コマンドだけで、人が手で直すのは `status` の1語くらいなので、
読み手は厳しく読んでよい。

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

- **6行・この順・この綴り**。欠け・重複・順の違い・知らないキー・CRLF は、そのファイルを
  `INVALID` にする（ほかのファイルは読み続ける）
- `summary` は**書いたとおりの文字列**。`` ` `` で始まっても、`: ` や `#` や `[` を含んでも
  そのまま（ここを YAML にすると、`` ` `` 始まりの要約が構文エラーになる。この利用者の
  要約は識別子から書き始めることが多い）
- `dependencies` は空なら `[]`。区切りは `", "`（カンマと空白1つ）で固定
- `passes` と `evidence` は無くなる。着手しない判断で閉じたものは `status: dropped`
  （旧 `done` + `passes: false`）、証拠は本文の `## 結果`
- 着手中（旧 `doing`）は**ファイルに書かない**。台帳の印が表す（4.1）

### 3.3 本文の節

節の並びは固定（無い節は飛ばす）。

| 節 | いつ・誰が書くか | 必須か |
| --- | --- | --- |
| `## 目的` | 登録時（`/plan-tasks`） | 必須 |
| `## 完了条件` | 登録時 | 必須。検証可能な言葉で |
| `## 背景` | 登録時 | 必須 |
| `## 決まっていること（蒸し返さない）` | 登録時（聞いて決まったこと・承認の範囲） | 任意 |
| `## 解くべき論点` | 登録時（`opus` には必ず） | 任意 |
| `## やること` | **着手直後**に、いまの `main` で調べ直して書き足す | 着手時に必須 |
| `## 注意` | 登録時・着手時・作業中の知見 | 任意 |
| `## 結果` | `task done` | done/dropped で必須 |

- `task new` は `## 目的`・`## 完了条件`・`## 背景` が無い本文と、`## やること`・`## 結果` を
  含む本文を拒む（登録時に書いた「やること」は、着手までに行番号や前提が古くなるため）
- `## 結果` は旧 `evidence` の役（3行程度。コミットハッシュ以外の検証可能な証拠）。**自分の
  完了のコミットのハッシュは書けない**（`## 結果` がそのコミットに入り、しかも rebase で
  変わる）。そのタスクのコミットは `git log --grep=T-xxx` で引く。よそのリポジトリの
  ハッシュ（tsukumo のタスクが claude-skills に入れたコミットなど）は書いてよい

### 3.4 例と読み取りの見本

```markdown
---
id: T-531
summary: `readTaskSummaries` を develop/task/ の front matter から読む
status: todo
difficulty: sonnet
loopable: Y
dependencies: [T-521, T-525]
---

## 目的

サイドバーのタスク板が、新しい形のタスクファイルと台帳の着手の印から一覧を出す。

## 完了条件

- 一時リポジトリの3通り（新形式・旧形式・どちらも無い）がテストで通る
- `bun run check` が通る

## 背景

いまは `main` の `develop/tasks.json` を `git show` で読んでいる（`src/server/adapter/task-summary.ts`）。

## 注意

- `test/architecture.test.ts` の `node:child_process` の境界を守る
```

完了したあとは `status: done` になり、末尾に `## やること`（着手時）の後ろへ `## 結果` が付く:

```markdown
## 結果

- `bun run check`: 1204 pass / 0 fail（+9）
- 3通りの一時リポジトリのテストを `test/server/adapter/task-summary.test.ts` に追加
```

読み手（Python の `taskfile.py` と tsukumo の `src/shared/task-summary.ts`）は、次の見本を
**両方のテストに写す**（片方だけ直して黙ってずれるのを防ぐ。見本の正典は T-524 で
`skills/task-workflow/WORKFLOW.md`「タスクファイル」へ移した。下は設計時の写し）:

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

tsukumo のタスク板での扱い（T-525）: INVALID のファイルはその1件だけ読み飛ばす（いまの
「要素単位の安全側」と同じ）。一覧は ID の数字順。

## 4. 状態と台帳

### 4.1 status の遷移

```
          task new                task claim            task done ＋ commit ＋ task ship
 (無) ──────────────▶ todo ─────────────────▶ todo＋印 ────────────────────────────▶ done（印は消える）
                       │  ▲                     │  task release                     ─▶ dropped（done --dropped）
             人が決める │  │ 人が決める           ▼
                       ▼  │                   todo
                       hold
```

- **ファイルの status は4つ**（todo / hold / done / dropped）。着手中は「todo ＋ 台帳の印」で、
  `task status` とタスク板が `CLAIMED`（作業中）と表示する
- `hold` は人の判断待ち。`task claim` は拒む。`hold` ↔ `todo` の切り替えはサブコマンドを
  持たず、人（か人がいるセッションのエージェント）が front matter の1語を直してコミットし、
  `task ship` で送る
- 依存の解決: `done` と `dropped` は解決済み。`hold` と `todo` は未解決。**タスクファイルにも
  `docs/history/tasks.md` にも無い ID は解決済み**（旧アーカイブ由来。いまの規則と同じ）

### 4.2 台帳

置き場は `L = $(git rev-parse --path-format=absolute --git-common-dir)/task-workflow/`。
作業ツリーをいくつ切っても1つのクローンで1つ。コミットされず、`git gc` も触らない。

```
L/
├── claim/
│   └── T-521/            ← mkdir が不可分なので、これ自体が取り合いの錠
│       └── owner         ← worktree=<絶対パス> / branch=<枝> / claimed_at=<UTC ISO 8601>
├── lock/                 ← 採番（task new）と migrate の間だけある錠。中に owner（pid・時刻）
└── last-id               ← 最後に払い出した番号（例: "530\n"）
```

- `owner` は `key=value` の3行。**取り合いの判定は `mkdir claim/T-xxx` の成否だけで決め**、
  `owner` はその直後に一時ファイル → `rename` で書く。読み手は `owner` がまだ無い印を
  「書き込み中」として扱う（4.3 の `STALE:no-owner`）
- `lock/` の取り方: `mkdir` を100ms おきに最大10秒試す。取れなければ `LOCKED`（終了コード4）。
  中の `owner` が60秒より古ければ、`LOCKED` の行に `rmdir` のコマンドを添える（**自動では
  壊さない**。取り残しは人に預ける決まり）
- `last-id` は、別の作業ツリーでまだコミットしていない `task new` の番号を覚えておくためにある
  （他の作業ツリーのファイルは読まない。自分の足元だけを触る）
- クローンが別（別のマシン・別の場所に clone）だと台帳も別になり、採番がぶつかりうる。
  対象ユーザーが1人・1クローンなので受け入れ、ぶつかったら `task status --check` が落とす（5.3）

### 4.3 取り残しの判定

前提: **1つの作業ツリーでは同時に1つのセッションしか動かない**（orca の作業ツリー1本 =
1セッション。単独の作業ツリーのプロジェクトも同じ）。

| 状態 | 判定 | 誰が何をする |
| --- | --- | --- |
| 自分の作業ツリーの印がある | `/next-task` の開始時点でそれがあれば、前のセッションが途中で落ちた取り残し | `/next-task` は着手せず、ID と `task release T-xxx`（捨てる）／続きを人が見る、の2択を添えて止まる |
| 他の作業ツリーの印で、その作業ツリーが `git worktree list` に無い | `STALE:gone` | `task status` が表示するだけ。人が `task release T-xxx --force` |
| 他の印で、`main` ではもう `done`／`dropped` | `STALE:shipped`（`ship` が送ったあと印を消す前に落ちた） | 同上 |
| `owner` が無いまま60秒 | `STALE:no-owner` | 同上 |
| それ以外 | 作業中（`CLAIMED`）。経過時間を出す | 触らない。長さだけでは取り残しと言わない |

プロセスの pid では判定しない（`task` は一瞬で終わる子プロセスで、セッション本体の pid は
印に書けない）。

### 4.4 `main` を出している作業ツリーで起こしたとき

- `claim`・`new` は同じ（台帳は共有）
- 完了のコミットはそのまま `main` に乗る。`ship` は「送る段なし」として、自分の印のうち
  `HEAD` で done/dropped になったものを消して `SHIPPED` を返す
- この作業ツリーが作業中で汚れているあいだ、他の作業ツリーの `ship` は `MAIN_DIRTY`
  （終了コード4）で止まる。**本体が汚れているときは送らない**いまの決まりのまま

## 5. `task` コマンド

### 5.1 置き場と呼び方

- `skills/task-workflow/scripts/task.py`（入口）。中身は概念ごとのモジュールに分ける:
  `taskfile.py`（front matter の読み書き）、`ledger.py`（台帳・錠・印）、`ship.py`
  （送り出し）、`legacy.py`（旧形式の読み取りと `migrate`）
- **Python 3.9 の標準ライブラリだけ**（macOS の `/usr/bin/python3` が 3.9.6。`tomllib`・
  `match` は使わない）。`git` を `subprocess` で呼ぶ
- スキルからは `python3 ${CLAUDE_SKILL_DIR}/../task-workflow/scripts/task.py <サブコマンド> …`。
  以下 `task` と略す。PATH には入れない（グローバルなツールの導入になるため）。変数に入れて
  呼ばない（zsh で単語に分かれず空振りし、`;` で続けた後続だけが走る事故が2回あった）。
  人が手で打ちたければ各自 alias を張る
- どのディレクトリから打っても `git rev-parse --show-toplevel` を根として動く
- 自己テストは `skills/task-workflow/scripts/selftest_task.py`。一時ディレクトリに git
  リポジトリと作業ツリー2本を作って通す。`check.sh` に1行足す（T-521）

### 5.2 出力と終了コードの共通規約

- 結果は**常に stdout**。1行目の先頭語が種類（`CREATED`・`CLAIMED`・`TAKEN`…）で、TSV。
  stderr は使い方の誤り（argparse）だけ
- 形式の判定を全サブコマンドの最初に行う（`migrate` を除く）:
  - `develop/tasks.json` がある → `LEGACY`（`develop/task/` にファイルもあれば `INVALID`
    「移行が途中」）
  - `develop/tasks.json` が無く `develop/direction.md` がある → 新形式（`develop/task/` は
    空・無しでもよい。空ディレクトリは git に載らないので、目印を `direction.md` にする）
  - どちらも無い → `MISSING`

| 終了コード | 種類（先頭語） | 意味 | スキルがすること |
| --- | --- | --- | --- |
| 0 | 各成功語 | 成功 | 次へ |
| 1 | （traceback） | 環境の故障（未捕捉の例外。Python の既定） | エラー出力を報告して止まる。手で代用しない |
| 2 | （stderr） | 渡した引数・本文の誤り | 直して打ち直す |
| 3 | `INVALID` | データの不備（タスクファイルが読めない、移行途中、`- ブランチ:` が読めない、`--check` の重複） | 理由をそのまま報告して止まる。直しに行かない |
| 4 | `TAKEN`・`NOT_READY`・`CAP`・`DIRTY`・`MAIN_DIRTY`・`UNSHIPPED`・`LOCKED`・`NOT_OWNER` | いまの状態では進めない | 先頭語ごと（各サブコマンドの表）。多くは別のタスクを選ぶか止まる |
| 5 | `LEGACY` | 旧形式（`develop/tasks.json`） | 移行の案内（行に `task migrate --dry-run` のコマンドが付く）を出して止まる |
| 6 | `MISSING` | タスク運用を始めていない | `/setup-tasks` を案内して止まる |
| 7 | `CONFLICT` | rebase が衝突した（`rebase --abort` 済み） | 衝突したファイルを添えて人に預ける |
| 8 | `VERIFY_FAILED` | 付け替えのあとの検証コマンドが落ちた（送っていない） | 出力の末尾を添えて人に預ける |
| 9 | `RACE` | `--ff-only` が3回続けて落ちた | 人に預ける |

### 5.3 `task status`

```
task status [--all] [--check]
```

読む: `main` の `develop/task/`（`git ls-tree` ＋ `git cat-file --batch`）、自分の作業ツリーにしか
無いタスクファイル（まだ送っていない `new`。`local` と印を付ける）、台帳、`docs/history/tasks.md`
の見出し、`develop/direction.md` の `## 積み残し`。**`main` と作業ツリーの両方にある ID は
`main` を正とする**（作業ツリーの写しは、送るまで・追い付くまで古いことがある）。**本文は出さない。**

```
T-520	todo	opus	N	-	CLAIMED	tsukumo-2 12m	タスク運用の設計書を書く
T-521	todo	opus	Y	-	READY	-	task コマンドの new・status・claim・release と台帳を作る
T-522	todo	sonnet	Y	T-521	BLOCKED:T-521	-	task コマンドの done と ship を作る
T-600	hold	sonnet	Y	-	HOLD	-	雑談の要約の上限を決める
T-601	todo	haiku	Y	-	READY	local	（まだ送っていない登録）
---
counts	todo=3	hold=1	done=412	dropped=9	claimed=1
ready	2/12	(並列数 6)
todo_loopable	N=1
long_summary	0	-
stale	1	T-499:STALE:gone(/…/tsukumo-7)
backlog	3	(develop/direction.md の ## 積み残し)
invalid	0	-
legacy_progress	develop/progress.md	未解決 14 / 注意 72	（移行の残り。振り分けたら消す）
```

- 列: `id / status / difficulty / loopable / dependencies / 着手可否 / 印 / summary`。
  着手可否は `READY`・`BLOCKED:<ID,…>`・`HOLD`・`CLAIMED`・`-`（done/dropped）
- 行の並び: ID の数字順。**done/dropped の行は既定では出さない**（件数だけ）。`--all` で出す
- `legacy_progress` 行は `develop/progress.md` が残っているときだけ出る（止める理由にはしない）
- `--check`: 検証コマンドから呼ぶための厳しい判定。INVALID のファイル、ファイル名と `id` の
  不一致、**タスクファイルと `docs/history/tasks.md` の両方にある ID** があれば終了コード3。
  `docs/history/tasks.md` の中だけの重複（tsukumo の T-225）は履歴で直せないので見ない
  （例外の一覧を持たずに済む）
- 終了コード: 0（`--check` 以外は INVALID があっても一覧として成立するので0）/ 3 / 5 / 6

### 5.4 `task new`

```
task new --summary <一行> --difficulty haiku|sonnet|opus --loopable Y|N
         [--deps T-001,T-002] [--hold] --body-file <path | ->
```

1. 本文を検査する（3.3。欠けや禁止の節は終了コード2）
2. 錠を取る → 番号 = max(`main` の `develop/task/`, 作業ツリーの `develop/task/`,
   `docs/history/tasks.md` の `## T-<数>`（作業ツリーと `main` の両方）, `last-id`) + 1
   → ファイルを排他作成（`O_EXCL`）→ `last-id` を書く → 錠を外す
3. 上限（7章）を超えるなら**錠の中で**拒む（`--hold` のとき・依存で `BLOCKED` になるときは数えない）

| 出力 | 終了コード |
| --- | --- |
| `CREATED\tT-531\tdevelop/task/T-531.md` | 0 |
| `CAP\t12/12\t(並列数 6)\t残りは develop/direction.md の ## 積み残し へ` | 4 |
| `LOCKED\t…` | 4 |

コミットはしない（`/plan-tasks` が登録ぶんと `docs/history/direction.md` をまとめて1コミットにする）。

### 5.5 `task claim`

```
task claim <T-xxx>
```

1. 作業ツリーが clean でなければ `DIRTY`
2. `main` に入っていない自分のコミットがあれば `UNSHIPPED`（前のタスクを送ってから次へ）
3. `main` より遅れていれば追い付く（自分のコミットが無いので fast-forward になる）
4. `main` の上でそのタスクが `todo` で依存が解決済みでなければ `NOT_READY`（`hold` もここ）
5. `mkdir L/claim/T-xxx`。既にあれば `TAKEN`
6. ブランチ設定が `既定` なら `feature/T-xxx` を `main` から切って移る（6.1。いまの枝が
   `main` でなくても、手順2で未送りのコミットが無いと分かっているので `main` から切ってよい）

| 出力 | 終了コード |
| --- | --- |
| `CLAIMED\tT-521\tdevelop/task/T-521.md\tbranch=feature/T-521` | 0 |
| `TAKEN\tT-521\t<作業ツリー>\t<経過>` | 4 |
| `NOT_READY\tT-521\t<status か BLOCKED:…>` | 4 |
| `DIRTY` / `UNSHIPPED\t<件数>` / `INVALID\t- ブランチ: が読めない` | 4 / 4 / 3 |

このあと本文を読むのは `develop/task/T-xxx.md` を1つ開くだけでよい（全件の本文を読まずに
済むのはファイルが分かれたこと自体が担う。本文を出すサブコマンドは作らない）。

### 5.6 `task release`

```
task release <T-xxx> [--force]
```

印を消すだけ（ファイルの編集は戻さない。戻すなら `git restore`）。自分の作業ツリーの印でなければ
`NOT_OWNER`（4）で、`--force` は人が取り残しを片付けるときに使う（スキルは付けない）。
`RELEASED\tT-xxx` / 印が無ければ `NOT_CLAIMED\tT-xxx`（0。何度打っても同じ結果）。

### 5.7 `task done`

```
task done <T-xxx> [--dropped] --result-file <path | ->
```

1. 自分の作業ツリーの印でなければ `NOT_OWNER`（4）
2. front matter の `status` を `done`（`--dropped` なら `dropped`）にし、`## 結果` を書く
   （あれば置き換える。空の結果は終了コード2）
3. `git add develop/task/T-xxx.md`

`DONE\tT-xxx\tdevelop/task/T-xxx.md\tstaged`（0）。**コミットはしない**。作業の差分と一緒に
1コミットにするのは呼ぶ側（`T-xxx: <件名>`）。**印もまだ消さない**——消すのは `ship` が
`main` へ送り終えたとき。ここで消すと、送るまでのあいだ `main` の上では `todo` のままで印も
無い時間ができ、別の作業ツリーが同じタスクを取れてしまう。

### 5.8 `task ship`

```
task ship
```

6.2 の手順。出力:

| 出力 | 終了コード |
| --- | --- |
| `SHIPPED\t<旧main>..<新main>\trebased=yes|no\tverify=ran|skipped\ttries=<n>\treleased=T-xxx,…` | 0 |
| `SHIPPED\tmain\t(送る段なし)\treleased=…`（`main` の作業ツリーで起こしたとき） | 0 |
| `NOTHING\t(main に無いコミットが無い)` | 0 |
| `DIRTY` / `MAIN_DIRTY\t<本体のパス>` | 4 |
| `CONFLICT\t<ファイル>,…` | 7 |
| `VERIFY_FAILED\t<コマンド>` ＋ 出力の末尾40行 | 8 |
| `RACE\t3` | 9 |

`ship` はタスクに紐付かない（登録のコミットも振り返りのコミットも同じ `ship` で送る）。

### 5.9 `task migrate`

```
task migrate [--dry-run]
```

10章。出力は `WRITE\tdevelop/task/T-xxx.md` を件数ぶん、`MOVE\tprogress 完了したこと <n>小節
→ docs/history/progress.md`、`LEFTOVER\tdevelop/progress.md\t未解決 <n> / 注意 <m>`、
`REMOVE\tdevelop/tasks.json`、最後に `MIGRATED\t<件数>`（`--dry-run` なら `PLAN\t<件数>`
で、何も書かない）。変更は `git add`/`git rm` まで行い、コミットしない。
`doing` のタスクが残っていれば `NOT_READY\tT-xxx\tdoing`（4）で何もしない。作業ツリーが
汚れていれば `DIRTY`（4）。

## 6. 送り出しとブランチ設定

### 6.1 `- ブランチ:` の語彙

CLAUDE.md「## タスク運用」の `- ブランチ:` 行を、**値の先頭語だけ**機械が読む（後ろは人向けの
説明で自由）。

| 先頭語 | 意味 | いま使っているプロジェクト |
| --- | --- | --- |
| `既定` ／ `作業ブランチを切る` | `claim` が `main` から `feature/T-xxx` を切って移り、`ship` が送ったあと `main` に戻って枝を消す | claude-skills（`既定`）、Git-Bulk-Maestro（`作業ブランチを切る`） |
| `切らない` | いまの枝のまま。`main` の上ならそのまま `main` に積む、作業ツリーの枝なら `ship` で送る | gitlab-watari-dori・helm-yadokari（`main` の上）。tsukumo（作業ツリーの枝。いまの行は `自分で切らない。…` なので切り替え（T-526）で `切らない。…` に直す） |
| それ以外 | `INVALID`（3）。どの手順に従えばよいか機械が決められない | — |

これで旧 WORKFLOW.md の「プロジェクト側がブランチ運用を自由に上書きできる」は無くなる。
merge commit を作る運用（旧既定の `git merge`、`--no-ff` の例）は選べなくなる。

### 6.2 `ship` の手順

1. 形式の判定。作業ツリーが clean でなければ `DIRTY`
2. `main` に無い自分のコミットが無ければ `NOTHING`（印の後始末だけする）
3. いまの枝が `main` なら「送る段なし」: `HEAD` で done/dropped の自分の印を消して `SHIPPED`
4. 送り先を決める: `git worktree list --porcelain` で `refs/heads/main` を出している作業ツリー
   （本体）を探す。あれば本体が clean でなければ `MAIN_DIRTY`
5. 最大3回繰り返す:
   1. `main` が `HEAD` の祖先でなければ `git rebase main`。衝突したら `git rebase --abort`
      して `CONFLICT`。**付け替えるのは `main..HEAD`（自分の枝のまだ `main` に無いコミット）
      だけ**で、他の作業ツリーの枝には触らない
   2. この回で付け替えが起きたなら、検証コマンドを打つ（6.3）。落ちたら `VERIFY_FAILED`
      （枝は付け替え済みのまま残る。送っていない）
   3. 送る: 本体があれば `git -C <本体> merge --ff-only <枝>`。本体が無ければ（どの作業ツリーも
      `main` を出していない）`git update-ref refs/heads/main <HEAD> <見た main>`（見たときから
      `main` が動いていれば失敗する比較付きの更新）。成功したら抜ける。失敗は相手に先を
      越された合図なので1へ
6. 3回とも送れなければ `RACE`
7. 送れたら、新しい `main` で done/dropped になった自分の印を消す。ブランチ設定が `既定` なら
   `main` に移って `feature/T-xxx` を消す（`git branch -d`。送った直後なので必ず消せる）。
   **T-524 で変えた点**: 別の作業ツリーが `main` を出していると `checkout main` が通らず枝が黙って
   残るので、戻り先を「`claim` した時点の枝（印の `branch=`。`main` まで追い付かせる）→ `main` →
   `main` の位置で detached HEAD」の順にし、降りた先を `SHIPPED` 行末の `branch=`（消せなければ
   `kept=`）に出す。detached からでも送れるよう、送るのは枝の名前ではなく `HEAD` のコミットにした

**merge commit は作らない**（取り込みは rebase、送るのは fast-forward か比較付きの更新だけ）。
自己テストは `git log --merges main` が0件であることを見る（T-522）。

切り替えの前の作業ツリーの枝には、いまの運用の `git merge main` の merge commit が残っている。
切り替えは全作業ツリーが `main` に入り切った状態で行う（T-526 の手順1）ので、rebase が
それを平らにし直すことは起きない。

### 6.3 検証コマンドを打つ時点

| 時点 | 誰が | なぜ |
| --- | --- | --- |
| 受け入れ（`task done` の前） | スキル（`/next-task` の受け入れの手順） | 作業の合否そのもの。整形コマンドもここ |
| `ship` の中で rebase が実際に付け替えたとき | `task` | 両側の変更が初めて同じ木に乗る。付け替えなしなら木は受け入れ時と同じなので打たない |
| `main` へ送ったあと | 打たない | 送るのは fast-forward なので、`main` の木は直前に検証した木と同じ |

検証コマンドは CLAUDE.md「## タスク運用」の `- 検証コマンド:` 行の最初の `` `…` `` を
`sh -c` で打つ。`なし` なら打たず、出力に `verify=none` と書く。時間の上限は付けない
（テストが長いプロジェクトがある）。

## 7. 登録の上限と `## 積み残し`

**2026-09-24 に撤去した（ユーザー決定）。** `task new` は `READY` の件数で拒まなくなり、
`CAP`・`## 積み残し`・`task status` の `backlog` 行と `ready` の上限表示はなくなった。以下は
当時の設計として残す。

### 7.1 並列数

**並列数 = `git worktree list` のうち `refs/heads/main` を出していない作業ツリーの数（最低1）**。
上限 = 並列数 × 2 で、数えるのは `READY` の `todo` だけ（`hold`・`BLOCKED`・作業中は数えない）。

- tsukumo（本体＋6本）→ 6 → 12件（方針の「いまは12件」と同じ）
- 単独の作業ツリーのプロジェクト → 1 → 2件
- 作業ツリーを足したり消したりするとそのまま追随する。設定を持たないので古くならない

上限の検査は `task new` が錠の中で行い、超えたら `CAP`（4）で拒む。`/plan-tasks` はそれを
受けて残りを `## 積み残し` へ置く。

### 7.2 `## 積み残し`

`develop/direction.md` に3つめの節を足す（`/setup-tasks` の骨組みにも入れる）。

```markdown
## 積み残し

- <summary>（difficulty: sonnet / loopable: Y / 元の指示: docs/history/direction.md 2026-09-24「…」）
  - 目的: …
  - 完了条件: …
```

- **ID を振らない**（振ると、登録から着手までの時間を縮めるという目的が消える）
- 分解と承認は済んでいるので、**繰り上げは `/loop` の無人のセッションでもしてよい**
  （`## ユーザーから` と同じ扱い。`## エージェントのドラフト` の封じとは別）
- 繰り上げるとき（`/plan-tasks`、または `/next-task` の「READY が0件」の分岐）は、その場で
  いまの `main` に照らして背景を書き直してから `task new` する。古くなって要らなくなった項目は
  理由を添えて消す
- 未対応の指示があるかの判定は、節ごとに見る（`## 積み残し` に中身があっても「未タスク化の
  指示」には数えない）。`init.py` の `check_direction()` もこれに合わせる

## 8. 知見の置き場（`progress.md` をなくす）

**規則: 知見は done の前に、正典（各プロジェクトの docs）かタスクへ置く。**
`develop/progress.md` と `docs/history/progress.md` への書き足しはやめる。

| 旧 `progress.md` の中身 | 新しい置き場 |
| --- | --- |
| 完了したこと（何を・なぜ・どう検証したか） | そのタスクの `## 結果` |
| 未解決（判断待ち） | `hold` のタスク（人の判断待ち）か `todo` のタスク（直すもの） |
| 注意（長く効く前提） | プロジェクトの正典の docs の該当節（「既知の制約」など） |
| 注意（一時的なもの） | 関係するタスクの `## 注意` |

tsukumo の `scripts/merge-progress.ts`・`scripts/progress-done-section.ts`・それらのテスト・
`.gitattributes` の `merge=progress` は T-527 で消す。

## 9. スキルと WORKFLOW.md の新しい章立て

目標の行数は、いまの WORKFLOW.md 563行・スキル5本（next-task 226・plan-tasks 193・
list-tasks 129・retrospect 189・setup-tasks 107）に対して、WORKFLOW.md 250行・スキル5本で
合計450行ほど（T-524 が前後を evidence に書く）。

### 9.1 `task-workflow/WORKFLOW.md`

1. 目次
2. ファイル配置と CLAUDE.md（`develop/task/`・`develop/direction.md`・`docs/history/`（履歴。
   書き足さない）・台帳。CLAUDE.md の3行と `- ブランチ:` の語彙）
3. タスクファイル（front matter の文法、本文の節、読み取りの見本）
4. status と着手の印（遷移図、依存の解決、取り残し）
5. summary（一行要約）
6. difficulty とモデルの切り替え（いまの2節を縮めて残す。委譲の根拠の実測は残す）
7. loopable（いまのまま。`hold` との違いを1段落: `N` は人がいれば進められる、`hold` は人が
   決めるまで誰も進められない）
8. 1サイクル（claim → やることを書き足す → 作業 → 受け入れ → done → コミット → ship）
9. 送り出し（6章の要約。検証コマンドの時点の表）
10. 結果の書き方（旧「良いevidenceの書き方」）と、知見の置き場（8章）
11. コミットメッセージ（1タスク＝1コミットは完了のコミットで守られる。登録・振り返りは IDなし）
12. 指示メモ（`## ユーザーから`・`## エージェントのドラフト`・`## 積み残し`、登録の上限）
13. `task` コマンドの参照（サブコマンドと終了コードの表。5章の写し）
14. 旧形式からの移行（`LEGACY` が出たときの案内）

消える節: progress.md の構成、肥大化したときのアーカイブ（と小節3つ）、`dependencies` の
アーカイブの扱い、ブランチ運用の自由な上書き、マージ後の検証と `reset --hard` の巻き戻し
（merge commit ができないので要らない）。

### 9.2 `next-task/SKILL.md`

1. このプロジェクトの設定（`## タスク運用` 節の埋め込み。いまと同じガード付き）
2. 手順
   1. 見渡す: `task status`。5 → 移行の案内、6 → `/setup-tasks` の案内で止まる
   2. 取り残し: 自分の作業ツリーの印（`CLAIMED` で印の列が自分）があれば止まる（4.3）
   3. 選ぶ: `READY` から1件（`/loop` では `loopable: N` を除く）。無ければ
      `## 積み残し` の繰り上げ → `## ユーザーから` のタスク化（`/plan-tasks` の手順を
      読み込んで実行）→ 残りが `hold`／`N` だけなら ID を添えて止まる
   4. `task claim T-xxx`（`TAKEN`・`NOT_READY` なら手順1からやり直して別の1件を選ぶ。
      3回続いたら止まる）
   5. 委譲: `difficulty` のモデルのサブエージェントへ。渡すのは ID とファイルのパスと
      「まず今の `main` で調べ直して `## やること` を書き足す。前提が崩れていれば
      `task done --dropped` にする理由を報告する」「`develop/task/` 以外の develop/ を
      触らない」
   6. 受け入れ: 差分を見る → 整形コマンド → 検証コマンド
   7. `task done T-xxx --result-file -` → 作業とタスクファイルを1コミット（`git add -A` を
      使わず触ったファイルを個別に）
   8. `task ship`。4/7/8/9 は先頭語を添えて止まる（`/loop` はこれを「続行不要」と扱う）
3. 完了報告のフォーマット（done にしたID、検証の結果、`ready`・`hold`・`backlog` の件数、
   `## ユーザーから`／`## エージェントのドラフト` の行数）

### 9.3 `plan-tasks/SKILL.md`

1. このプロジェクトの設定
2. 手順: 読む（direction.md の3節と `task status`。本文を読むのは重なりそうな1件だけ）→
   確かめる → 分解する → 書く（`## 目的`・`## 完了条件`・`## 背景`、必要なら
   `## 決まっていること（蒸し返さない）`・`## 解くべき論点`・`## 注意`。`## やること` は
   書かない）→ `task new` を1件ずつ（`CAP` が出たら残りを `## 積み残し` へ）→
   `docs/history/direction.md` へ移す → 1コミット → `task ship`
3. 完了報告のフォーマット（項目 → タスクID／積み残しの対応表は必ず出す）

消えるもの: 登録直後のアーカイブ判定、`progress.md` の「未解決」「注意」を読む・書く指示。

### 9.4 `list-tasks/SKILL.md`

- `task status` の出力から表を1つ。行の順は `READY` の todo → `BLOCKED` の todo → 作業中
  （`CLAIMED`。印の列の作業ツリー名を `作業中（tsukumo-3）` と出す）→ 判断待ち（`HOLD`）
- 表の下の1行: 件数（todo/作業中/判断待ち/done/dropped）、`ready` と上限、`backlog` の件数。
  `stale` が1件以上ならもう1行（ID と理由。片付けるのは人）。`legacy_progress` が出ていれば
  もう1行（移行の残り）
- オススメ: `READY` から1件（順位の付け方はいまのまま）。**`hold` は推薦しない**。`READY` が
  0件で `hold` があるなら「人の判断待ち: T-xxx」と添える

### 9.5 `retrospect/SKILL.md` と `scripts/`

- 材料2つを置き換える（`material.py`）:
  - **タスク本文と結果**: `develop/task/T-xxx.md`（`HEAD` の版）。無ければ
    `docs/history/tasks.md`（旧アーカイブ）。旧 `evidence` の代わりに `## 結果`
  - **`progress.md` の小節** → **タスクファイルの差分**: `git log -p --follow -- develop/task/T-xxx.md`
    から、登録時の本文と完了時の本文の差（着手時に書き足した `## やること`・`## 注意` の量）。
    登録の粗さと、着手までにどれだけ前提が動いたかがここに出る。旧タスクは
    `docs/history/progress.md` の小節を従来どおり探す
- 兆候の表に1行足す: 「着手時の `## やること` が登録時の `## 背景` の前提を覆している →
  登録の書き方（`plan-tasks`）／積み残しにすべきだった」
- `scan.py`・`material.py` のタスクIDの正規表現を `T-\d{3,}` にする（`T-1000` を拾う）
- 記録ファイル `develop/retrospective.md` と、出し先 `## エージェントのドラフト` は変えない。
  コミットは2ファイルを指定して行い、`task ship` で送る

### 9.6 `setup-tasks/SKILL.md` と `init.py`

- 作るのは `develop/direction.md`（`## ユーザーから`・`## エージェントのドラフト`・
  `## 積み残し`）だけ。`develop/tasks.json`・`develop/progress.md` は作らない。
  `develop/tasks.json` があれば作らずに `LEGACY` を返し、`task migrate` を案内する
- CLAUDE.md の節は3行のまま。`- ブランチ:` の雛形は `既定` にし、語彙（6.1）を添える

### 9.7 スクリプトの行き先

| いま | 切り替え後（T-524 の枝で行い、T-526 で `main` へ） |
| --- | --- |
| `status.py` | 消す（`task status`） |
| `archive.py` | 消す（アーカイブの段が無い） |
| `taskfiles.py` | 消す。`migrate` が要る旧形式の読み取り（tasks.json・progress.md の節分け）は `legacy.py` へ移す |
| `init.py` | 残して新しい骨組みに書き直す |
| `selftest.py` | アーカイブの検査を消し、`legacy.py` の検査を残す |

T-521〜T-523 は `task.py` 一式を**足すだけ**で `main` に入れてよい（どのスキルもまだ呼ばない
ので、どのプロジェクトの振る舞いも変わらない）。旧スクリプトを消すのは T-524 の枝だけ。

## 10. 移行

### 10.1 `task migrate` の変換規則

| `tasks.json` | タスクファイル |
| --- | --- |
| `id`・`summary`・`difficulty`・`loopable`・`dependencies` | front matter の同名の行（`loopable` が無ければ `Y`、`summary` が無ければ `task` の先頭行、改行は空白に） |
| `status: todo` | `todo` |
| `status: done` かつ `passes: true` | `done` |
| `status: done` かつ `passes: false` | `dropped` |
| `status: doing` | 移行しない。`NOT_READY`（4）で全体を止める |
| `task` | 本文にそのまま（節を組み替えない。`## 目的` を機械で作れないので、**移行したファイルは本文の節の検査を受けない**。検査は `task new` のときだけ） |
| `evidence`（空でなければ） | 末尾に `## 結果` として足す（本文に既に `## 結果` があれば `INVALID` で止める） |
| `passes`（`true` の `todo` など、上の表に当たらない組み合わせ） | 捨てる（旧形式でも意味を持たない） |

あわせて台帳の `last-id` を、変換したタスクと `docs/history/tasks.md` の最大に合わせる。
`docs/history/tasks.md` は動かさない。

### 10.2 `progress.md` の扱い

- **「完了したこと」の小節は全部 `docs/history/progress.md` へ移す**（`archive.py` と同じ
  書式・新しい順で先頭に差し込む。機械的に移せるのはここだけ）
- **「未解決」「注意」は動かさない。** 振り分け（hold/todo のタスク・正典の docs・捨てる）は
  プロジェクトごとの人の判断なので、`develop/progress.md` にその2節だけを残し、先頭に
  「移行の残り。8章の表で振り分けたら消す」の1行を足す。件数を `LEFTOVER` 行に出す
- **「完了したこと」より前にある前置き文（`# 現在の状態` のような、どの節にも属さない文章）も
  消さずに残す。** 移す先が無い文章を機械的に捨てるとデータを失う操作になるので、「未解決」
  「注意」と同じ「人が振り分けたら消す」側に置く。残したときは `LEFTOVER` 行をもう1行足して
  知らせる
- 「未解決」「注意」が両方空、かつ前置き文も無ければ `develop/progress.md` を消す
- 新しいスキルは `progress.md` を読まない。残っているあいだは `task status` の
  `legacy_progress` 行が知らせ続ける（止めはしない）

### 10.3 プロジェクトごとの手順

1. そのプロジェクトの全作業ツリーの手を止め、`main` に `doing` が無いこと、各作業ツリーに
   `main` へ入っていないコミットと未コミットの変更が無いことを確かめる
2. `main` を出している作業ツリーで `task migrate --dry-run` → 件数と `LEFTOVER` を見る
3. `task migrate` → 差分を見て1コミット（件名「タスクを1件1ファイルへ移す」。IDなし）
4. CLAUDE.md「## タスク運用」の `- ブランチ:` を語彙（6.1）に合わせ、`develop/tasks.json`・
   `develop/progress.md` を名指ししている説明を直す
5. `task status` の一覧が、移行前の `status.py` の一覧と ID・status（doing を除く）・依存で
   一致することを確かめる
6. ほかの作業ツリーは、再開するときに `git rebase main`（自分のコミットが無いので追い付くだけ）
7. `LEFTOVER` の2節を振り分けて `develop/progress.md` を消す（tsukumo は T-527）

### 10.4 切り替えの順序（共通スキルを使う全プロジェクト）

1. T-521〜T-523: `task.py` 一式を claude-skills の `main` へ（足すだけ。誰の振る舞いも変わらない）
2. T-524: スキル5本と WORKFLOW.md の書き直しを枝 `feature/tsukumo-T-524` に作り、`main` へは
   入れない
3. T-525: tsukumo のタスク板を新旧どちらも読めるようにする
4. T-526: tsukumo の全作業ツリーを止め、T-524 の枝を claude-skills の `main` へ入れ、
   claude-skills 自身と tsukumo を 10.3 の手順で移す
5. 入れた瞬間から、ほかのプロジェクト（Git-Bulk-Maestro・gitlab-watari-dori・helm-yadokari）で
   タスク系のスキルを呼ぶと `LEGACY` で止まり、`task migrate --dry-run` を案内する。
   移すかどうかは各プロジェクトで決める

## 11. 採らなかった案

| 案 | 退けた理由 |
| --- | --- |
| front matter を本物の YAML にしてライブラリで読む | Python の標準ライブラリに YAML が無い（PyYAML を入れるのは外部依存）。YAML 1.1 の読み手は `Y`/`N` を真偽値に変える。`` ` `` 始まりの `summary` が構文エラーになり、避けるには引用とエスケープの規則が要る。tsukumo 側にも YAML のライブラリが要る |
| TOML の front matter（`+++`） | `tomllib` は 3.11 から（手元は 3.9.6）で、書き手が無い。TypeScript 側にもライブラリが要る |
| 1件1 JSON ファイル | 本文（Markdown）を文字列に詰めることになり、人が読めず差分も読めない |
| 着手の印を `main` にコミットする（いまの tsukumo） | 1タスクで `main` へのコミットが2回、そのたびに取り込みが要る。1週間で取り込みのマージ209件の出どころ |
| 着手の印を git の参照（`refs/task-claims/*`）に置く | `update-ref` の比較付きの更新で不可分にできるが、人にもタスク板にも見えにくく、`mkdir` と比べて得るものが無い |
| 台帳を `~/.task-workflow/` や `$TMPDIR` に置く | クローン単位にならない（同じ名前の別プロジェクトが混ざる）。`$TMPDIR` は再起動で消える |
| 錠に `fcntl.flock` を使う | 取り残しが外から見えない（ディレクトリの錠なら `ls` で見えて `rmdir` で外せる）。TypeScript 側の読み手とも揃えにくい |
| 古い印・古い錠を時間で自動的に壊す | 取り残しは人に預ける決まり。長いタスクと落ちたセッションを経過時間では区別できない |
| pid で取り残しを判定する | `task` は短命の子プロセスで、セッション本体の pid を印に書けない |
| `task done` で印を消す（T-522 の本文の書き方） | 送るまでのあいだ `main` の上では `todo` で印も無くなり、別の作業ツリーが同じタスクを取れる。印は `ship` が送り終えてから消す |
| `task done` がコミットまでする | 作業のコミットと記録のコミットが分かれるか、`task` が「どのファイルが作業か」を知る必要が出る。コミットは呼ぶ側が1回で行う |
| 取り込みを `git merge main` のままにする | 取り込みのたびに merge commit ができ、送るときの `--ff-only` の前提（枝が `main` の子孫）を merge commit で満たすことになる。rebase はユーザー承認済み |
| 並列数を固定値にする／CLAUDE.md の設定にする | 作業ツリーを足し引きしたときに黙って古くなる。`git worktree list` はいつもいまの数を返す |
| 並列数を `git worktree list` の全数にする | tsukumo で7（本体を含む）になり、方針の12件と合わない。本体は `main` を出しているだけで、タスクを並べて進める場所として数えない |
| 採番を時刻やランダムにして錠をなくす | `T-` + 連番の読みやすさと、`docs/history/tasks.md` との連続が失われる |
| `- ブランチ:` を自由文のままモデルに解釈させる | `task ship` が読めない。手順をコマンドに持たせる方針と矛盾する |
| 本文を出す `task show` | ファイルが1件1つになったので、1ファイルを開けば済む |
| `task` を PATH に入れる | グローバルなツールの導入になる。スキルからは `${CLAUDE_SKILL_DIR}` で足りる |
| ID の重複の例外（T-225）を共通の検査に載せる | 共通の `--check` は「タスクファイルと履歴の間」と「ファイル名と id」だけを見る。履歴の中だけの重複は直せない過去なので見ない。tsukumo の T-519 のテストはプロジェクト側で例外を持ち続けてよい |
| 移行で「未解決」「注意」を機械的に `hold` のタスクや `## 積み残し` にする | 86項目の多くは解消済み・古い・正典へ行くべきもので、機械的に移すとタスクの一覧が汚れる。振り分けは人の判断と決まっている |
| 移行したタスクの本文を新しい節の形に組み替える | `## 目的` を機械で書けない。検査を `task new` のときだけにして、古い本文はそのまま読めるようにする |

## 12. 実装タスクへの割り付け

| タスク | この設計のどこ |
| --- | --- |
| T-521 | 3.2〜3.4（`taskfile.py`）、4.2〜4.3（`ledger.py`）、5.1〜5.6（`new`・`status`・`claim`・`release`）、7.1、`selftest_task.py` と `check.sh` の1行 |
| T-522 | 5.7〜5.8、6（`ship.py`） |
| T-523 | 5.2 の形式の判定、5.9、10.1〜10.2（`legacy.py`） |
| T-524 | 7.2、9 全体（枝のまま。`main` へは T-526） |
| T-525 | 3.4 の見本を tsukumo のテストへ写す、4.1 の依存の解決、4.2 の台帳を読む（着手中の表示）、ID の数字順 |
