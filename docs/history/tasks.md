# 完了タスクのアーカイブ

## T-001

**タスク**: /next-task が direction.md の中身で止まるのをやめ、READY が0件のときだけ止める

**difficulty**: sonnet / **loopable**: Y / **dependencies**: なし / **passes**: True

**evidence**:

skills/next-task/SKILL.md の手順1・手順2・完了報告のフォーマットと、skills/task-workflow/WORKFLOW.md「指示メモ」節を変更。
grep 'タスクを実行せず|実行せず終了' が2ファイルとも0件。setup-tasks は READY 0件時の報告と整合するため変更なし。
./check.sh 通過（selftest 全項目 ok、19スキル不整合なし）。

## 背景

`skills/next-task/SKILL.md` の手順1の末尾に、`develop/direction.md` を
`grep -v '^#' | grep -v '^\s*$'` で見て、中身があればタスクを実行せず終了する記述がある。
`/loop` 側はこれを「続行不要」の合図として扱う。根拠は `skills/task-workflow/WORKFLOW.md` の
「指示メモ（`develop/direction.md`）」節にある「セッション開始時に中身があれば、他の作業より
先にタスク化する」。

この挙動は非対称に損をしている。止めて得るのは「新しい指示で覆るかもしれないタスク1件を
無駄に実行せずに済む」ことだけなのに、失うのは「READY な todo が全部止まる」こと。しかも
`/next-task` は `direction.md` を自動タスク化しない（分解は方針決めを含むので代行しない設計）
ため、止めた先で誰も何もしない。ユーザーが戻るまで進まない点は、止めても止めなくても同じ。

## 解くべき論点

- 正典（WORKFLOW.md「指示メモ」節）の「他の作業より先にタスク化する」という文言を、
  `/plan-tasks` を先に呼ぶ動機は残したまま、`/next-task` を止めない形にどう書き換えるか
- `skills/setup-tasks/SKILL.md` の `PENDING:` の扱い（「`/plan-tasks` が先だと報告する」）が
  この方針と矛盾しないか。setup 直後は todo が0件なので実質矛盾しない見込みだが、文言を確認する

## やること

1. `skills/next-task/SKILL.md` の手順1から、`direction.md` に中身があれば終了する記述を外す。
   代わりに「中身があれば行数を数えて完了報告に添える」に変える
2. 同 SKILL.md の手順2（選ぶ）に、`READY` が0件でかつ `direction.md` に中身があるときは
   「進めるものが無く、未タスク化の指示がある → `/plan-tasks` が先」と報告して終了する、を足す
3. 同 SKILL.md の「完了報告のフォーマット」に「未タスク化の指示の有無（あれば行数）」を1行足す
4. `skills/task-workflow/WORKFLOW.md` の「指示メモ（`develop/direction.md`）」節を、
   上の挙動に合わせて書き換える
5. `skills/setup-tasks/SKILL.md` の `PENDING:` 行を確認し、矛盾していれば直す。
   矛盾していなければ触らない
6. 検証コマンド `./check.sh` を通す

## 完了条件

- `skills/next-task/SKILL.md` に「`direction.md` に中身があればタスクを実行せず終了する」旨の
  記述が1つも残っていない（`grep -n 'direction' skills/next-task/SKILL.md` で確かめられる）
- 同 SKILL.md に、`READY` が0件のときに `/plan-tasks` を促して終了する記述がある
- 同 SKILL.md の「完了報告のフォーマット」に、未タスク化の指示を報告する行がある
- `skills/task-workflow/WORKFLOW.md` の「指示メモ」節が新しい挙動と一致している
- `./check.sh` が通る

## 注意

- `/plan-tasks` 側の挙動（`direction.md` を読んでタスク化する）は変えない
- タスク化した時点で `develop/direction.md` を空にし `docs/history/direction.md` へ移す運用も変えない

## T-002

**タスク**: docs/ の置き場を固定し、docs/README.md を索引にする規約を各スキルに書く

**difficulty**: opus / **loopable**: N / **dependencies**: なし / **passes**: True

**evidence**:

提案書を docs/architecture-proposal.md、採用後の正典を docs/architecture.md に分け、調査メモを docs/research/<topic>.md に固定。3スキルに索引への追記指示を書いた。
scripts/check_repo.py に check_docs_index を追加（対象は DOCS_WRITING_SKILLS にハードコード）。research から該当記述を消すと ./check.sh が終了コード1、戻して0 を実測。
./check.sh 通過（19スキル不整合なし）。変更5ファイル。

## 背景

`docs/` に何をどこへ置くかの決め方が4通り混在している。

- `docs/history/*` は規約で固定（`skills/task-workflow/scripts/taskfiles.py` の `HISTORY_DIR`）
- `CONTEXT.md` はルート、`docs/adr/NNNN-slug.md` は固定（`skills/domain-modeling/SKILL.md` と
  `ADR-FORMAT.md`）。どちらも遅延作成
- アーキテクチャ提案は「リポジトリの慣習に従う」（`skills/architecture-proposal/SKILL.md` の
  「### 6. 提案書を置く」。`docs/architecture-proposal.md` を例示するが固定していない）
- 調査メモは「慣例があればそこ、無ければ適切と思われる場所」（`skills/research/SKILL.md` の3項目め）

後ろ2つがその場のモデルの判断なので、同じプロジェクトでも呼ぶたびに置き場が変わりうる。
さらに `docs/` に何が居るかの索引がどこにも無く、次のセッションは `ls docs/` で発見するしかない。

## 決まっていること（2026-09-16 にユーザーが選択済み。蒸し返さない）

**1. 提案書と正典は別ファイルにする。**

| ファイル | 中身 | 書く人 |
| --- | --- | --- |
| `docs/architecture-proposal.md` | 提案書（複数案の比較・移行の段階つき） | `architecture-proposal` スキル |
| `docs/architecture.md` | 採用後の正典 | **人が採否を決めてから反映する** |

`architecture-proposal` は `docs/architecture.md` を**書かない**。同スキルの
「提案と同時に適用する（ユーザーの採否の機会を奪う）」をやりがちな失敗として挙げている原則を
保つため。指示メモには「提案書を `docs/architecture.md` に固定」と書かれていたが、
それだと2回目の提案で正典を上書きすることになるので、この形に変えることでユーザーの合意を得た。

**2. 索引の検査は各スキル側だけ行う。** `scripts/check_repo.py` が検査できるのは
このスキルリポジトリ自身であって、スキルを使う側のプロジェクトの `docs/` は見られない。
そこで「`docs/` に書くスキルが、索引に1行足す指示を持っているか」だけを検査する。

## 解くべき論点

- `docs/README.md`（索引）の1行の形。パスと一行説明が要るのは確かだが、
  `README.md` の「由来」一覧のような検査しやすい形にするか、緩い箇条書きにするか
- `check_repo.py` にどう検査を足すか。既存の `check_cross_references` などと同じ粒度で、
  **対象スキルの一覧をハードコードするか、`docs/` を書く旨の記述から拾うか**。
  前者は足し忘れを検出できないが単純、後者は誤検知しやすい。どちらかを選んで理由を残す

## やること

1. `skills/architecture-proposal/SKILL.md` の「### 6. 提案書を置く」を書き換える。
   提案書は `docs/architecture-proposal.md` に固定し、「リポジトリの慣習に従う」をやめる。
   「ユーザーが場所を指定したらそれに従う」「既存の設計書（正典）を直接書き換えない」は残す。
   採用後の正典が `docs/architecture.md` であること（提案書とは別ファイルで、反映は人の作業）も
   1行で書く
2. `skills/research/SKILL.md` の3項目めを `docs/research/<topic>.md` に固定する
3. 「`docs/` に何かを書いたら `docs/README.md` に1行足す」という運用を、
   `skills/architecture-proposal/SKILL.md`・`skills/research/SKILL.md`・
   `skills/domain-modeling/SKILL.md` の3つに書く。`docs/README.md` が無ければそのとき作る
   （遅延作成。空の `docs/` を先回りして掘らせない）
4. `scripts/check_repo.py` に、上の3スキルが索引に足す指示を持っているかの検査を足す。
   論点2で選んだ方式と理由を、関数の docstring かコメントに1行残す
5. `check.sh` の出力の説明が `README.md`「## 検証」節にあるので、検査を足したらそこも直す
6. 検証コマンド `./check.sh` を通す

## 完了条件

- `skills/architecture-proposal/SKILL.md` と `skills/research/SKILL.md` に、
  「リポジトリの慣習に従う」「適切と思われる場所」という趣旨の記述が残っていない
- `skills/architecture-proposal/SKILL.md` に `docs/architecture-proposal.md` が提案書の置き場、
  `docs/architecture.md` が採用後の正典（反映は人の作業）と書かれている
- `skills/research/SKILL.md` に `docs/research/<topic>.md` が書かれている
- 上の2つと `skills/domain-modeling/SKILL.md` の計3スキルに、`docs/README.md` へ1行足す指示がある
- `scripts/check_repo.py` にその検査があり、3スキルのどれか1つから該当の記述を消すと
  `./check.sh` が落ちる（**実際に一時的に消して落ちることを確かめる。確かめたら戻す**）
- `README.md`「## 検証」節の説明が、足した検査を含んでいる
- `./check.sh` が通る

## 注意

- `docs/history/` の置き場（`taskfiles.py` の `HISTORY_DIR`）は変えない
- `CONTEXT.md` がルートにある点も変えない（`domain-modeling` の既存の決定）
- **遅延作成の原則を崩さない。** 空の `docs/` や `docs/README.md` を先回りして作る指示にしない
- `README.md` の「docs/ の育て方」の案内は **T-003 が書く**。このタスクでは書かない
  （T-003 がこのタスクに依存している）
- `skills/architecture-proposal/evals/evals.json` は `docs/architecture.md` を
  「既にある設計書」の例として使っている。上の決定と整合するので**触らない**

## T-003

**タスク**: README.md に docs/ を育てる順番（遅延作成→提案→用語集→ADR）の案内を足す

**difficulty**: sonnet / **loopable**: Y / **dependencies**: T-002 / **passes**: True

**evidence**:

README.md に「## docs/ の育て方」節を追加（梯子4段 + 置き場の表5行）。表のパスは skills/*/SKILL.md の記述と grep で突き合わせて一致を確認。./check.sh が通る（selftest 全項目 ok、check_repo.py は 19スキル 不整合なし）。

## 背景

「プロジェクトで `architecture.md` のような共通ドキュメントが欲しい」と思ったときに、
どのスキルを呼べばいいのかが `README.md` から引けない。`README.md` の
「## プロジェクト側に要るもの」節はタスク運用のファイルだけを扱っていて、`docs/` の育て方に
触れていない。置き場そのものは T-002 で各スキルに固定されるので、ここで足すのは
**人が読む案内**（どの順で何を作るか）。

## やること

1. `README.md` の「## プロジェクト側に要るもの」節の隣に、`docs/` の育て方を書く。中身は
   「新規プロジェクトでは何も作らない（遅延作成）→ 構造で迷ったら `architecture-proposal` →
   用語がブレ始めたら `CONTEXT.md`（`domain-modeling`）→ 覆すのが高くつく決定をしたら
   ADR（`domain-modeling`）→ 調べ物は `research`」という梯子と、T-002 で固定した置き場の表
2. 参照は**スキル名で書く**（`~/.claude/skills/...` の絶対パスを埋めない。
   README「翻訳の方針」の慣習で、`check_repo.py` の相互参照チェックもこの形を前提にしている）
3. 検証コマンド `./check.sh` を通す

## 完了条件

- `README.md` に `docs/` の育て方の節があり、梯子（順番）と置き場の表の両方が入っている
- 表のパスが T-002 で各スキルに書いたものと一致している
- `./check.sh` が通る

## 注意

- 「## 由来」の一覧は索引として `scripts/check_repo.py` が検査している。節を足すときに壊さない

## T-004

**タスク**: develop/ と docs/history/ の役割を正典化し、会話も入口にして履歴を改名する

**difficulty**: sonnet / **loopable**: Y / **dependencies**: T-001 / **passes**: True

**evidence**:

WORKFLOW.md に「develop/<名前> が生きている状態、docs/history/<名前> がその履歴」の1文と6行の表、指示メモ節に入口2つの判定表と docs/history/direction.md の小節（台帳は3点に限定）を追加。plan-tasks/SKILL.md 手順1を3分岐に（/loop 下では会話入口を使わない旨つき）。改名は grep -rn 'tasks-archive|progress-archive' skills/ scripts/ が0件、./check.sh 通過（selftest が新名で archive 経路を通過、check_repo.py 19スキル不整合なし）。

## 背景

タスク運用のファイルの役割が、定義と名前の両方でズレている。2026-09-16 の相談で規約を決めた
ので、それをスキル側に反映する。

今ズレているところ:

- `docs/history/direction.md` の定義が「`develop/direction.md` というファイルの履歴」なのか
  「ユーザーからの指示の履歴」なのか決まっていない。前者だと、会話で受けた指示のうち
  **タスクにしなかったもの**を記録する場所が無くなる（実例: 2026-09-16 の
  「`develop/` を `docs/` に寄せるか → 寄せない」。タスクが無いので `tasks.json` に置き場が無い）
- `skills/task-workflow/WORKFLOW.md:293` が「ユーザーからの指示は、チャットではなく
  `develop/direction.md` に書く」と会話入力を明文で禁じ、`skills/plan-tasks/SKILL.md:29` は
  `develop/direction.md` が空なら何もせず終了する。このため会話で決まった指示も、いったん
  `develop/direction.md` に書いて自分で読み返す往復が要る。書いた本人が読み返すので、この
  往復は情報を1つも足していない
- 履歴の名前が `tasks-archive.md` / `progress-archive.md` / `direction.md` と不揃いで、
  `direction.md` だけ `-archive` が付かない

決めた規約は次の1文と表。

> `develop/<名前>` が生きている状態、`docs/history/<名前>` がその履歴。

| 生きている状態          | 履歴                         | 中身                                             |
| ----------------------- | ---------------------------- | ------------------------------------------------ |
| `develop/direction.md`  | `docs/history/direction.md`  | ユーザーからの指示（入口がファイルでも会話でも） |
| `develop/tasks.json`    | `docs/history/tasks.md`      | タスク                                           |
| `develop/progress.md`   | `docs/history/progress.md`   | 進捗                                             |

## 決まっていること（2026-09-16 にユーザーが選択済み。蒸し返さない）

**会話から指示を拾う判定は「明示の指示のときだけ」。**

| 拾う | 拾わない |
| --- | --- |
| 「これタスクにして」「登録していいよ」「この方針で進めて」 | 「うーん、この辺気になるなぁ」「いつか直したい」 |
| 提案に対する「それでいいよ」 | `/loop` から回っているときの会話履歴全般 |

検討中の発言・思いつき・雑談は拾わない。**`/loop` から回されているときは会話入力の経路を
そもそも使わない**（無人で回っている最中に会話の断片がタスクになるのを防ぐ）。

**`docs/history/direction.md` に書くのは、ユーザーの生の言い回し・項目 → タスクIDの対応表・
タスクにしなかった理由の3つだけ。** 噛み砕いた説明は `tasks.json` の `## 背景` が持つので
写さない（現在このファイルの 2026-09-16 分にはモデルが噛み砕いた50行が入っていて、
`tasks.json` と二重になっている。この形を繰り返さない）。

## やること

1. `skills/task-workflow/WORKFLOW.md` の「ファイル配置と CLAUDE.md」の表を、上の6行
   （生きている状態3 + 履歴3）と「`develop/<名前>` が生きている状態、`docs/history/<名前>` が
   その履歴」の1文に置き換える
2. 同 `WORKFLOW.md:293` の「チャットではなく」を、入口2つの書き方に変える。判定は論点1の
   保守的な条件を明記する
3. 同「指示メモ」節に `docs/history/direction.md` の定義（入口を問わない指示の履歴）と、
   何を書くか（論点2）を書く
4. `skills/plan-tasks/SKILL.md:29` の「空なら終了」を3分岐に変える:
   受信箱に中身がある → 従来通り／受信箱が空で会話に指示がある → 直接 `tasks.json` に登録し
   台帳に追記／どちらも無い → 従来通り「未対応の指示は無い」で終了
5. 改名する。`tasks-archive.md` → `tasks.md`、`progress-archive.md` → `progress.md`。
   直す場所は `skills/task-workflow/scripts/archive.py`（4箇所）・
   `skills/task-workflow/scripts/selftest.py`（2箇所）・`WORKFLOW.md`（6箇所）・
   `skills/list-tasks/SKILL.md`（2箇所）。`grep -rn 'tasks-archive\|progress-archive' skills/`
   で拾い切れる
6. 検証コマンド `./check.sh` を通す

## 完了条件

- `grep -rn 'tasks-archive\|progress-archive' skills/ scripts/` が0件
- `skills/task-workflow/WORKFLOW.md` に「`develop/<名前>` が生きている状態、
  `docs/history/<名前>` がその履歴」の1文と、6行の表がある
- `skills/plan-tasks/SKILL.md` に、受信箱が空でも会話から登録する分岐がある。かつ
  「`/loop` から回っているときは会話入力を使わない」旨が書いてある
- `skills/task-workflow/WORKFLOW.md` の「指示メモ」節に、台帳に書くものが
  「生の言い回し・対応表・タスクにしなかった理由」と限定されている
- `./check.sh` が通る（`selftest.py` が新しい名前でアーカイブの経路を通せている）

## 注意

- **利用側プロジェクトの移行は T-005 が担当する。このタスクでは他のリポジトリを触らない**
- **`archive.py` に旧名から新名への自動改名コードを足さない。** 対象は4リポジトリで全部
  把握できており、移行コードはスキル側に残ると「いつ消せるか」を誰も判断できなくなる。
  移行は T-005 で手作業の `git mv` を行う
- `docs/history/` の置き場そのもの（`taskfiles.py` の `HISTORY_DIR`）は変えない
- 判定の文面は「## 決まっていること」の表を満たすこと。緩く書くと `/loop` が会話の断片を
  タスク化しうるので、ここだけは保守的に倒す

## T-005

**タスク**: 利用側3プロジェクトを移行する（履歴の改名と workflow.json の廃止反映）

**difficulty**: sonnet / **loopable**: Y / **dependencies**: T-004 / **passes**: True

**evidence**:

3リポジトリとも改名2件・CLAUDE.md の3行・develop/workflow.json 削除・CLAUDE.md の workflow.json 参照0件を完了。コミットは Git-Bulk-Maestro a02cac4 / helm-yadokari abcf502+4e230fc / tsukumo 76400f3（いずれも作業ブランチ上、push なし、main へは未マージ）。検証コマンドは自分で再実行して通過: pnpm check 90/90（GBM）・557/557（helm-yadokari）・bun run check 545 pass（tsukumo）。

## 背景

このリポジトリのスキルを使っているプロジェクトが3つあり、**2件の未移行が溜まっている**。
片方（改名）は T-004 が作るもので、もう片方（`workflow.json` の廃止）は
commit `f7aead0` の時点から反映されていない。

### 1. 履歴ファイルの改名（T-004 が作る移行）

T-004 で `docs/history/tasks-archive.md` → `tasks.md`、`progress-archive.md` → `progress.md`
に改名する。3プロジェクトとも実ファイルがある（2026-09-16 時点の実測）:

| プロジェクト     | `tasks-archive.md` | `progress-archive.md` |
| ---------------- | ------------------ | --------------------- |
| helm-yadokari    | 1,153,941 B        | 297,166 B             |
| tsukumo          | 653,276 B          | 158,880 B             |
| Git-Bulk-Maestro | 24,608 B           | 8,324 B               |

放置すると `archive.py` が新しい名前のファイルを横に作り、**古い履歴が孤立する**
（消えはしないが以後読まれない）。

### 2. `develop/workflow.json` の廃止が反映されていない

`WORKFLOW.md` は「設定ファイル（`develop/workflow.json`）は持たない」と決め、値は
CLAUDE.md の「## タスク運用」節の `- 検証コマンド:` / `- 整形コマンド:` の2行に置くことに
なっている。しかし3プロジェクトとも:

| プロジェクト     | `develop/workflow.json` | CLAUDE.md の2行 | 「## タスク運用」節 |
| ---------------- | ----------------------- | --------------- | ------------------- |
| Git-Bulk-Maestro | 残っている（pnpm）      | 無い            | あるが `workflow.json` を正典として指したまま |
| helm-yadokari    | 残っている（pnpm）      | 無い            | 節そのものが無い    |
| tsukumo          | 残っている（bun）       | 無い            | 節そのものが無い    |

今は `/next-task` の「節が無ければ CLAUDE.md の他の節から検証コマンドを探す」フォールバックが
効いていて事故ってはいない（3つとも別の節に書いてある）。ただし規約の形ではない。
特に `tsukumo/CLAUDE.md:81-82` は「各スキルが言うチェックコマンド（`develop/workflow.json` の
`checkCommand`）は `bun run check` のこと」と、**廃止済みのファイルを指す橋渡し文**が生きている。

各プロジェクトの実際の値（移行時はこれを CLAUDE.md の2行に書く。`git log` ではなく現物で確認すること）:

| プロジェクト     | 検証コマンド    | 整形コマンド     |
| ---------------- | --------------- | ---------------- |
| Git-Bulk-Maestro | `pnpm check`    | `pnpm format`    |
| helm-yadokari    | `pnpm check`    | `pnpm format`    |
| tsukumo          | `bun run check` | `bun run format` |

## 決まっていること（2026-09-16 にユーザーが承認済み。蒸し返さない）

**承認の範囲**: 下に挙げた3つのリポジトリに対して、このタスクの「## やること」に書かれた
変更（履歴ファイルの `git mv`、CLAUDE.md の「## タスク運用」節の用意、`develop/workflow.json`
の削除、`workflow.json` を指す記述の除去）を、**各リポジトリの作業ブランチにコミットしてよい**。
ユーザーの事前承認はこの範囲に限る。**push はしない。** 他の変更を混ぜない。

**`docs/workflow.md`（Git-Bulk-Maestro）の扱い**: `## このプロジェクトの値(develop/workflow.json)`
節（12〜19行目あたり。`checkCommand` / `formatCommand` の表を含む）を**削除する**。値は
CLAUDE.md の2行が持つ。残りの節（コミットメッセージ・ブランチ運用・現在の状態・
要件定義の記録の行き先）は**そのまま残す**。`WORKFLOW.md` の同名の規定と食い違っていた場合も
**直さずに** evidence に1行書いて報告する（他リポジトリの運用方針を変えるのはこのタスクの
範囲外）。

## やること

対象は次の3リポジトリ。**それぞれのリポジトリで作業ブランチを切り、そのリポジトリの流儀で
コミットする**（このリポジトリにはコミットしない）。

- `/Users/sinnlos/ghq/github.com/sinnlosses/Git-Bulk-Maestro`
- `/Users/sinnlos/ghq/github.com/sinnlosses/helm-yadokari`
- `/Users/sinnlos/ghq/github.com/sinnlosses/tsukumo`

各プロジェクトで:

1. `git mv docs/history/tasks-archive.md docs/history/tasks.md` と
   `git mv docs/history/progress-archive.md docs/history/progress.md`。**中身は触らない**
2. CLAUDE.md に「## タスク運用」節を用意し、`- 検証コマンド:` / `- 整形コマンド:` /
   `- ブランチ:` の行を書く（形は `WORKFLOW.md` の「ファイル配置と CLAUDE.md」。
   行の頭は変えない）。既にある節は中身を新しい形に差し替える
3. 書いた検証コマンドが**実際に通ることを確かめてから** `develop/workflow.json` を削除する
4. `workflow.json` を指している記述を CLAUDE.md から消す（tsukumo の 81-82 行のような橋渡し文、
   Git-Bulk-Maestro の「## タスク運用」節のリンク）。`grep -rn 'workflow.json' CLAUDE.md docs/`
   で拾う
5. `docs/workflow.md` のような、タスク運用の値を別に持っているファイルがあれば、正典が
   二重にならないか確認する（Git-Bulk-Maestro が該当。中身次第で残す／消すを判断し、理由を
   evidence に書く）

あわせて `helm-yadokari` の `docs/history/test-inventory.md`（23,446 B）を確認する。
`docs/history/` は「`develop/` の履歴」の置き場なので規約上ここに居てはいけない。
移し先が決まらなければ**動かさず**、見つけた事実だけ evidence に書いて閉じる。

## 完了条件

- 3プロジェクトとも `docs/history/tasks.md` と `docs/history/progress.md` が存在し、
  `tasks-archive.md` / `progress-archive.md` が存在しない
- 3プロジェクトとも `develop/workflow.json` が存在せず、CLAUDE.md の「## タスク運用」節に
  `- 検証コマンド:` と `- 整形コマンド:` の2行がある
- 3プロジェクトとも `grep -rn 'workflow.json' CLAUDE.md` が0件
- 各プロジェクトで検証コマンドを実行して通ったことを確認した
- evidence に3リポジトリのコミットハッシュを書いた

## 注意

- **他のリポジトリを変更するタスク。** 承認の範囲は「## 決まっていること」に書いた通りで、
  そこから外れる変更（push、他の修正の混入）はしない
- **T-004 が終わってから着手する。** 先に改名すると、スキル側がまだ旧名を見ている
- 各リポジトリの未コミットの変更を巻き込まない。2026-09-16 時点では
  tsukumo の `develop/direction.md` に未コミットの変更が1件あった
- push はしない


## 進捗（2026-09-16 時点。着手時はここから読む）

**Git-Bulk-Maestro は完了済み。** ブランチ `chore/docs-history-rename-workflow-cleanup`、
コミット `a02cac4`（push していない）。改名2件・CLAUDE.md の3行・`develop/workflow.json` の削除・
`docs/workflow.md` の「このプロジェクトの値」節の削除まで済み、`pnpm check` は 90/90 で通る。
`grep -rn 'workflow.json' CLAUDE.md docs/` も0件。**このリポジトリは再度触らない。**

発見（直していない。このタスクの範囲外）: `docs/workflow.md` の「## ブランチ運用」節は
「main に直接コミットする、作業ブランチを切らない」と書いてあり、CLAUDE.md に入れた
`- ブランチ: 作業ブランチを切る` と食い違う。他リポジトリの運用方針の変更は範囲外なので残した。

**残りは helm-yadokari と tsukumo の2つ。** どちらも 2026-09-16 時点で**別のセッションが
作業中**で着手できなかった:

- tsukumo: 未コミット33件（`character-edit` 系の作りかけ）。`docs/history/progress-archive.md`
  自体も変更済みなので、改名をコミットすると他人の作業を巻き込む
- helm-yadokari: 着手直前はクリーンだったが、作業中に別セッションが JSDoc の一括修正を始めた
  （`src/**/*.ts` 33件 + `docs/coding-standards.md`）。着手を取り消し、ブランチも削除して
  main に戻してある。**残骸は無い**

再開するときは、対象リポジトリの `git status` がクリーンであることを確かめてから入る。

helm-yadokari で分かっていること（再開時に使う）:
- `develop/workflow.json` の現物は `pnpm check` / `pnpm format`
- CLAUDE.md に `## タスク運用` 節が無い。`workflow.json` への参照は `## 進捗管理とHandoff`
  （161行目付近）と `## 導入済みスキル`（129行目付近）の2箇所
- helm-yadokari にも `docs/workflow.md` があり、`## このプロジェクトの値（develop/workflow.json）`
  の表を持つ。承認の範囲は Git-Bulk-Maestro の `docs/workflow.md` だけなので、ここは
  別途ユーザーに確認する
- `docs/history/test-inventory.md` は**動かさない**で決着。T-119 が `develop/` から意図して
  移したもので、`docs/coding-standards.md`（455行目・471行目付近）が現役の正典として参照して
  いる。このタスクでの対応は不要

### 2回目の着手（同日）も中断。helm-yadokari は競合しやすい

着手前の `git status --short` は空だったが、**作業の途中で別セッションが再開**した
（`src/main.ts` に JSDoc の整形が入った）。自分の変更（ブランチ・改名2件・CLAUDE.md・
`git rm develop/workflow.json`）は全て元に戻し、ブランチも削除済み。**残骸は無い**
（`main` が `79b7356`、`develop/workflow.json` と旧名の履歴2ファイルが存在することを確認済み）。

2回目で新たに分かったこと:

- **`pnpm check` は通る**（557/557）。改名と CLAUDE.md の追記を載せたブランチ上で実測した
- `CLAUDE.md` の `- ブランチ:` に書く値は `切らない。直接 main にコミットする`。
  helm-yadokari の既存の `## Git運用` 節がその運用を定めているため、正典の既定ではなく
  そちらを上書きの形で書く
- `docs/workflow.md` の「## このプロジェクトの値（develop/workflow.json）」の表は
  `develop/workflow.json` の現物（`pnpm check` / `pnpm format`）と一致していて、新たな
  食い違いは無い。承認の範囲外なので**触らない**

**3回目の着手では、着手前だけでなくコミットの直前にもう一度 `git status --short` を見る。**
汚れていたら自分の変更を戻して閉じる（2回とも、この形で中断している）。

## T-006

**タスク**: loopable の N を「聞いても解けなかったもの」に定義し直し、登録時に聞く手順を足す

**difficulty**: sonnet / **loopable**: Y / **dependencies**: T-004 / **passes**: True

**evidence**:

WORKFLOW.md「loopable」節を「登録時にユーザーへ聞いても解けなかったもの」の定義に変え、4行の表で「対話的な検証が必要」だけを解けない側に置いた。「tasks.json のフィールド」節に `## 決まっていること（蒸し返さない）` の書くこと/書かないことを追加。plan-tasks/SKILL.md 手順4に N を付ける前に聞く手順、節一覧に `## 決まっていること`、完了報告を「聞いても解けなかった理由」に具体化。grep で旧文言「迷ったら N」は0件、./check.sh 通過。

## 背景

`loopable` を `"N"` にする理由が、正典では3つ並んでいるだけで**性質の違う2種類が混ざっている**
（`skills/task-workflow/WORKFLOW.md` の「loopable（`/loop` に載せてよいか）」節）。

| `N` になる理由 | 正体 | 事前に聞けば解けるか |
| --- | --- | --- |
| 複数案のどれを採るかが未定 | 判断が未了 | 解ける（登録時に決めて本文に焼く） |
| 会話中の文脈に依存する | 本文が不完全 | 解ける（文脈を本文に書き出す） |
| 元に戻せない／外部へ反映する | 実行の性質 | 解ける（承認の範囲を本文に書く） |
| 対話的な検証が必要 | 受け入れに人が要る | **解けない** |

上3つは「登録時にユーザーへ聞けば消える `N`」なのに、今の正典は「**迷ったら `N`**」としか
書いていないので、聞けば `Y` にできるものまで `N` で登録されてしまう。`/loop` に載らない
タスクが増え、ユーザーが1件ずつ呼ぶことになる。

実例が2件ある。T-002 は `N` で登録したが、着手時に2つ質問して本文に焼き込んだだけで普通に
委譲できた（登録時に聞いていれば `Y` だった）。T-004・T-005 も同じ経緯で、登録後にユーザーへ
確認して `Y` に直している。

## 決まっていること（2026-09-16 にユーザーが選択済み。蒸し返さない）

- **「元に戻せない／外部へ反映する」タスクは、承認の範囲を本文に書けば `Y` にしてよい。**
  対象と行為を限定して書く（例: 「この3リポジトリにこの変更をコミットしてよい。push はしない」）。
  push をスキルから行わない既存の規約は変えないので、実質の上限はローカルのコミットまで
- **「対話的な検証が必要」だけは事前承認で `Y` にできない。** 実行ではなく受け入れの問題で、
  通ったかどうかを人が見ないと判定できないため
- 事前承認を残す置き場は、タスク本文の **`## 決まっていること（蒸し返さない）`** 節。
  T-002・T-004・T-005 で先に使っており、サブエージェントが迷わず走ることを確認済み

## やること

1. `skills/task-workflow/WORKFLOW.md` の「loopable」節を書き換える:
   - `N` の基準を「**登録時にユーザーへ聞いても解けなかったもの**」と定義し直す
   - 上の背景の4行の表（`N` の理由・正体・事前に聞けば解けるか）を入れる
   - 「**迷ったら `N` を選ぶ**」を「**迷ったら聞く。聞けない状況のときだけ `N`**」に変える。
     ただし「自動進行で事故るコストはユーザーを待たせるコストより大きい」という理由付けは残す
     （聞けないときに `N` へ倒す根拠は変わらないため）
2. `skills/task-workflow/WORKFLOW.md` の「tasks.json のフィールド」節（またはタスク本文の
   書式を述べている箇所）に、`## 決まっていること（蒸し返さない）` 節を足す。何を書くか
   （ユーザーが選んだ結果と、承認の範囲）と、**何を書かないか**（検討の経緯。それは `## 背景`）
   を1行ずつ
3. `skills/plan-tasks/SKILL.md` の手順4（書く）に、**`N` を付ける前にその判断をユーザーへ聞く**
   手順を足す。聞いた結果は `## 決まっていること` 節に焼き込み、`Y` で登録する。
   同スキルの本文は現在タスク本文を5節（背景／解くべき論点／やること／完了条件／注意）と
   定めているので、`## 決まっていること` を含む形に直す
4. `skills/plan-tasks/SKILL.md` の完了報告のフォーマットにある「`"N"` のタスクは理由も1行で
   書く」を、「**聞いても解けなかった理由**を書く」に具体化する
5. `skills/next-task/SKILL.md` 手順2の「ユーザーが直接呼んだときは `"N"` も選んでよい。着手前に
   ユーザーの判断が要る点を先に確認する」が、新しい定義と矛盾しないか確認する。矛盾して
   いなければ触らない
6. 検証コマンド `./check.sh` を通す

## 完了条件

- `skills/task-workflow/WORKFLOW.md` の「loopable」節に、`N` の理由を「事前に聞けば解けるか」で
  分けた表があり、「対話的な検証が必要」だけが解けない側に置かれている
- 同節に「迷ったら聞く。聞けない状況のときだけ `N`」の趣旨が書かれており、
  「迷ったら `N` を選ぶ」という旧来の文言が残っていない
- `skills/task-workflow/WORKFLOW.md` に `## 決まっていること` 節の説明（何を書くか・何を書かないか）がある
- `skills/plan-tasks/SKILL.md` の手順4に、`N` を付ける前にユーザーへ聞く手順がある
- `skills/plan-tasks/SKILL.md` が示すタスク本文の節の一覧に `## 決まっていること` が入っている
- `./check.sh` が通る

## 注意

- **`loopable` フィールドそのものは廃止しない。** 聞いても解けない `N`（対話的な検証）が
  残るため、`/next-task` と `/list-tasks` の `N` の扱いは変えない
- 既存タスクの `loopable` を遡って付け直さない（正典「loopable」の既存の運用と同じ）
- `develop/` 配下のファイルは触らない。このタスクはスキルのドキュメントの変更のみ

## T-007

**タスク**: /next-task が着手時に status を doing にし、遷移を誰が書くか正典に書く

**difficulty**: sonnet / **loopable**: Y / **dependencies**: なし / **passes**: True

**evidence**:

next-task/SKILL.md に手順4「doing にする」を新設し、以降の手順を1つずつ繰り下げ（旧4〜7 → 5〜8）。doing のまま残ったタスクは手順2で自動再開せずユーザーに預ける。委譲時の申し送りに「tasks.json はコミットしない」を追加。WORKFLOW.md「tasks.json のフィールド」節に todo→doing→done の書き手・タイミング・コミットしない理由を明記。./check.sh 通過。

## 背景

`status` の `doing` は、定義と読む側だけがあって**書く側がどこにも無い**。

- `skills/task-workflow/WORKFLOW.md:95` が `status` の取りうる値として `todo` / `doing` / `done`
  を定義している
- `skills/task-workflow/scripts/status.py:92` は `counts` 行に `doing=N` を出す
- `skills/list-tasks/SKILL.md:73` は `doing` を「作業中」と表示し、同 116行目は
  「`doing` のタスクがあるときは、推薦の前に1行で `T-xxx` が `doing` のまま と添える」と定めている
- しかし `skills/next-task/SKILL.md` は手順6（記録してコミット）で `todo` から直接 `done` に
  書き換えるだけで、着手時に `doing` にする手順が無い。`skills/plan-tasks/SKILL.md:99` は
  登録時に `status: "todo"` 固定

このため `/list-tasks` の「`doing` のまま」警告は、人が手で書き換えない限り発火しない。
異常終了で落ちたタスクを次のセッションが見つける経路が無い。

## 決まっていること（蒸し返さない）

- **案A を採る。** `doing` は廃止せず、`/next-task` が着手時に書くようにする

## 解くべき論点

- **`doing` を書いた時点でコミットするか。** 正典「コミットメッセージ」は 1タスク＝1コミットと
  定めており、着手時にもコミットすると1タスクが2コミットになる。コミットしない場合、
  `doing` は作業ツリー上にだけ存在し、完了時のコミットには `done` が入る（差分は生じない）。
  **異常終了の検知は作業ツリーを見る `/list-tasks` が行うので、コミットしないほうが正典と
  整合する**——この方針で進めてよいか、実装時に `WORKFLOW.md` の記述と突き合わせて確かめる
- **サブエージェントに巻き込まれないか。** `/next-task` 手順4 は委譲先に「コミットしない」と
  渡しているが、`develop/tasks.json` が `doing` で汚れた状態で委譲が始まる。委譲先が
  `git add -A` を打つ手順になっていないかを確認し、必要なら手順4の渡し方に1行足す

## やること

1. `skills/next-task/SKILL.md` の手順3（ブランチ）と手順4（実行）のあいだ、または手順3の中に、
   **選んだタスクの `status` を `"doing"` に書き換える**ステップを足す。書き換えは
   `develop/tasks.json` の当該タスク1件だけで、他のフィールドは触らない
2. 同 手順6（記録してコミット）の説明を、`doing` → `done` に直す形に更新する
3. 上の「## 解くべき論点」の1点目の結論を `skills/task-workflow/WORKFLOW.md` の
   「tasks.json のフィールド」節（`status` の行の近く）に1〜2行で書く。`todo` → `doing` →
   `done` の遷移を誰が書くかが正典から読めるようにする
4. 異常終了で `doing` が残った場合に `/next-task` が何をするかを決めて書く
   （`skills/next-task/SKILL.md` 手順2 の選び方。`doing` のタスクを拾い直すのか、
   ユーザーに預けるのか）。`/list-tasks` 側は既に警告を出すので**そちらは変えない**
5. 検証コマンド `./check.sh` を通す

## 完了条件

- `skills/next-task/SKILL.md` に、着手時に `status` を `"doing"` にするステップがある
- `skills/task-workflow/WORKFLOW.md` に、`todo` → `doing` → `done` を誰がいつ書くかが書かれている
- `skills/next-task/SKILL.md` 手順2 に、`doing` のまま残ったタスクの扱いが書かれている
- `skills/list-tasks/SKILL.md` は変更しない（`git diff --stat` に出ない）
- `./check.sh` が通る

## 注意

- **`doing` を廃止しない。** 案A で確定済み
- `develop/tasks.json` の既存タスクの `status` を書き換えない
- `scripts/check_repo.py` がスキル間の相互参照を検査している。参照はスキル名で書く

## T-008

**タスク**: ブランチを feature/T-xxx に固定し、main への ff マージと削除まで正典の既定にする

**difficulty**: sonnet / **loopable**: Y / **dependencies**: なし / **passes**: True

**evidence**:

WORKFLOW.md「ファイル配置と CLAUDE.md」の「ここでは決めない」を削除し、feature/T-<タスクID>・ff マージ・ブランチ削除を既定として明記。ff できないときは rebase→再試行、rebase がコンフリクトしたら --no-ff に落とさずユーザーに預ける。検証コマンドは rebase を挟んだときだけ再実行。next-task/SKILL.md 手順3を feature ブランチに、手順8にマージを新設（旧8は9へ）。CLAUDE.md の - ブランチ: 行は「既定」。./check.sh 通過。

## 背景

ブランチ運用が正典に無く、タスクの完了地点が「作業ブランチへのコミット」で止まっている。

- `skills/task-workflow/WORKFLOW.md:81-83` は「ブランチ運用（作業ブランチを切るか、
  デフォルトブランチに直接コミットするか）はプロジェクトの `CLAUDE.md` に従う。**ここでは
  決めない**」と明記している
- `skills/next-task/SKILL.md` 手順3 も「プロジェクトの `CLAUDE.md` のGit運用に従う」とだけ書く
- 同 手順7 は「push はしない。このスキルはコミットまでで止める」。**main へ戻す手順がどこにも
  無い**ので、作業ブランチが積み上がる（実例: 2026-09-16 のセッションは
  `tasks/docs-layout-and-loop-halt` 1本に T-001〜T-006 の6タスクを載せた）
- `WORKFLOW.md:54` の CLAUDE.md テンプレートは `- ブランチ: 作業ブランチを切る` という
  値の例を示すだけで、ブランチ名の規則もマージの有無も定めていない

## 決まっていること（蒸し返さない）

- **ブランチ名は `feature/T-<タスクID>`**（例: `feature/T-008`）。1タスク＝1ブランチ
- **タスクのゴールは main へのマージまで。** マージは **fast-forward**（マージコミットを作らない）
- **マージが済んだら `feature/T-xxx` は削除する**
- **これは正典（`WORKFLOW.md`）の既定にする。** `CLAUDE.md` の `- ブランチ:` 行で
  プロジェクトごとに上書きできる余地は残す
- **push は引き続き行わない。** 外部への反映は明示的に頼まれたときだけ

## 解くべき論点

- **fast-forward できないときどうするか。** main が進んでいると `git merge --ff-only` は失敗する。
  作業ブランチを main に rebase してから ff するのか、止めてユーザーに預けるのかを決めて書く。
  `/loop` の無人進行中に起きるので、**黙って `--no-ff` に落とさない**こと
- **`CLAUDE.md` の `- ブランチ:` 行に何を書くか。** 既定に従う場合の値の書き方と、
  上書きしたい場合の書き方の両方を、`WORKFLOW.md:48-54` のテンプレートに反映する
- **検証コマンドを通す位置。** 現在は手順5（受け入れ）で通している。マージ後にもう一度
  通すかどうかを決める（ff なら main の内容はブランチと同一になるため、重ねる必要は無いはず）

## やること

1. `skills/task-workflow/WORKFLOW.md:81-83` の「ここでは決めない」を、上の「## 決まっていること」
   を既定として持つ形に書き換える。`CLAUDE.md` で上書きできることも明記する
2. 同 `WORKFLOW.md:48-54` の CLAUDE.md テンプレートの `- ブランチ:` 行を、新しい既定に合わせる
3. `skills/next-task/SKILL.md` 手順3 を、`feature/T-<タスクID>` を切る手順に書き換える
4. 同スキルに**マージの手順**を足す（手順6のコミットの後、手順7の「push はしない」の前）。
   ff マージ → ブランチ削除まで。fast-forward できなかったときの扱いは「## 解くべき論点」で
   決めた内容を書く
5. このリポジトリの `CLAUDE.md` の「## タスク運用」節の `- ブランチ:` 行を、2で決めた書き方に直す
6. 検証コマンド `./check.sh` を通す

## 完了条件

- `skills/task-workflow/WORKFLOW.md` から「ブランチ運用は…ここでは決めない」の記述が消え、
  `feature/T-<タスクID>` と fast-forward マージとブランチ削除が既定として書かれている
- `skills/task-workflow/WORKFLOW.md` に、`CLAUDE.md` の `- ブランチ:` 行で上書きできる旨がある
- `skills/next-task/SKILL.md` に、ブランチを切る手順とマージする手順の両方があり、
  fast-forward できなかったときの扱いが書かれている
- `skills/next-task/SKILL.md` に「push はしない」が残っている
- このリポジトリの `CLAUDE.md` の `- ブランチ:` 行が新しい既定に沿っている
- `./check.sh` が通る

## 注意

- **他のリポジトリ（Git-Bulk-Maestro・helm-yadokari・tsukumo）のファイルを触らない。**
  正典を変えれば各プロジェクトは次に `/next-task` を呼んだ時点で従う。利用側の移行は T-005 の担当
- **push しない**
- `scripts/check_repo.py` がスキル間の相互参照を検査している。参照はスキル名で書く

## T-009

**タスク**: マージの既定を ff-only + rebase からふつうの git merge に変える

**difficulty**: sonnet / **loopable**: Y / **dependencies**: なし / **passes**: True

**evidence**:

WORKFLOW.md のブランチ運用と next-task/SKILL.md 手順8を、--ff-only + rebase からふつうの git merge に変更。検証コマンドの再実行は「マージコミットができた回だけ main で」に掛け替え、落ちたら reset --hard で main を戻す（未コミットの変更があれば reset せず報告）。コンフリクトは自動解消せずユーザーに預ける。grep -rn 'ff-only|rebase' skills/ が0件、./check.sh 通過。

## 背景

T-008 で入れたマージの既定が `git merge --ff-only` で、fast-forward できないときの回復手段を
`git rebase main` にしている。該当箇所は2つ:

- `skills/task-workflow/WORKFLOW.md:87-100`（既定の定義、rebase の手順、検証コマンドを通す位置）
- `skills/next-task/SKILL.md:161-174`（手順8「マージ」）

rebase を選んだことで**条件分岐が1つ増えている**。rebase はコミットを作り直す（差分の適用先が
変わる）ため、「rebase を挟んだ場合は ff の前にもう一度検証コマンドを通す」という例外規定が
要る。ユーザーは main が直線であることを求めておらず（「コミットが増えること自体に不都合は
ない」）、rebase の手間のほうを嫌っている。

ふつうの `git merge` なら、分岐していないときは ff で滑り（コミットは増えない）、分岐して
いたらマージコミットを作るだけで、rebase の経路そのものが消える。

代わりに1つ論点が入れ替わる。**マージコミットができた回は、main の木が「どちらのブランチでも
テストされていない状態」になる**（両側の変更が初めて同居する）。ff にはこの問題が無い。
よって検証コマンドの再実行は「rebase を挟んだとき」ではなく「マージコミットができたとき」に
掛け替える。

## 決まっていること（蒸し返さない）

- **既定は `--ff-only` をやめてふつうの `git merge`。** 分岐していなければ ff、分岐して
  いたらマージコミット
- **`rebase` は使わない。** 正典からもスキルからも rebase の手順を消す
- **マージコミットができた回だけ、main で検証コマンドを通す。** ff で済んだ回は通さない
- マージ後に作業ブランチを削除する既定と、**push しない**既定は変えない

## 解くべき論点

- **マージがコンフリクトしたときの扱い。** 現在は「rebase がコンフリクトしたらユーザーに
  預ける」。rebase を消すので、`git merge` がコンフリクトした場合の文面に書き換える。
  `/loop` の無人進行中に起きるので、**自動で解消しようとせず預ける**方針は変えない
  （`resolving-merge-conflicts` スキルへの言及も残す）
- **マージ後の検証コマンドが落ちたときどうするか。** ff では起こらなかった事象なので、
  今の正典に規定が無い。`git merge --abort` は使えない（コミット済みのため）ので、
  `git reset --hard` で戻すのか、落ちたことを報告して main に残したまま預けるのかを決める。
  **main を壊したまま黙って次のタスクへ進まない**こと
- **`CLAUDE.md` の `- ブランチ:` 行の上書きの例**（`WORKFLOW.md:69`）が
  「fast-forward できないときは常にユーザーに預ける」という今の既定を前提にしている。
  新しい既定に合う例に差し替える

## やること

1. `skills/task-workflow/WORKFLOW.md:87-100` のブランチ運用の既定を書き換える。
   `--ff-only` とマージが失敗したときの rebase 手順を消し、ふつうの `git merge` にする。
   検証コマンドを通す位置を「マージコミットができたとき」に掛け替える
2. 同 `WORKFLOW.md:69` の `- ブランチ:` 行の上書きの例を、新しい既定に合うものに差し替える
3. `skills/next-task/SKILL.md` 手順8を1と同じ内容に書き換える
4. 「## 解くべき論点」の2点（コンフリクト時、マージ後の検証が落ちたとき）の結論を、
   `WORKFLOW.md` と `skills/next-task/SKILL.md` の両方に書く
5. 検証コマンド `./check.sh` を通す

## 完了条件

- `grep -rn 'ff-only\|rebase' skills/` が0件
- `skills/task-workflow/WORKFLOW.md` に、ふつうの `git merge` を使う既定と、
  「マージコミットができた回だけ main で検証コマンドを通す」が書かれている
- `skills/task-workflow/WORKFLOW.md` と `skills/next-task/SKILL.md` の両方に、
  マージがコンフリクトしたときユーザーに預ける旨と、マージ後の検証コマンドが落ちたときの
  扱いが書かれている
- `skills/next-task/SKILL.md` に「push はしない」が残っている
- `./check.sh` が通る

## 注意

- **他のリポジトリを触らない。** 正典を変えれば各プロジェクトは次に `/next-task` を
  呼んだ時点で従う
- マージ後にブランチを削除する既定と、`feature/T-<タスクID>` というブランチ名は変えない
- `scripts/check_repo.py` がスキル間の相互参照を検査している。参照はスキル名で書く

## T-010

**タスク**: direction.md を著者で2節に分け、エージェントのドラフトに承認ゲートを置く

**difficulty**: sonnet / **loopable**: Y / **dependencies**: なし / **passes**: True

**evidence**:

WORKFLOW.md・plan-tasks・next-task・setup-tasks・init.py・selftest.py と develop/direction.md を `## ユーザーから`／`## エージェントのドラフト` の2節に統一。./check.sh 通過（init.py の新規テスト4件を含め自己テスト全件 ok、19スキル不整合なし）。節が無い旧形式は check_direction() が「ユーザーから1行」で PENDING を返し、SKILL.md のフォールバック grep も同じ1行を拾うことを一時ディレクトリで確認。

## 背景

`skills/task-workflow/WORKFLOW.md` は `develop/direction.md` を「ユーザーからの指示
（まだタスクになっていない）」と定義している（「ファイル配置と CLAUDE.md」の表と
「指示メモ（`develop/direction.md`）」節）。書き手はユーザーだけで、エージェントが作業中に
見つけた「これも直したい」を置く場所が無い。いまエージェントがこのファイルに対してするのは
`/setup-tasks` で雛形を作ることと、`/plan-tasks` でタスク化した後に見出しだけに空にすること
の2つで、中身を足す役は持っていない。

指示の入口は2つ（ファイル入口＝direction.md に書く／会話入口＝チャットで明示の指示）で、
会話入口は `/loop` から呼ばれたときは塞いである（無人進行中に会話の断片がタスク化するのを
防ぐため。正典「指示メモ」と `skills/plan-tasks/SKILL.md` 手順1）。ファイル入口にはこの封じが
無いので、direction.md をエージェントも書ける置き場に広げると、`/loop` 中にエージェントが
書いたドラフトをエージェント自身がタスク化して実装できてしまう。

あわせて2つズレる。`docs/history/direction.md` に書くのは正典上「ユーザーの生の言い回し」
だけなので、エージェントのドラフトをそのまま移すと台帳が出典を偽る。また
`skills/next-task/SKILL.md` 手順1・2は「見出し行以外に中身があるか」で未タスク化の指示を
判定し、`READY` が0件のとき「`/plan-tasks` が先」と報告するので、ドラフトが溜まっている
だけで催促が出る。

判定の実装は3箇所: `skills/next-task/SKILL.md` 手順1 と `skills/plan-tasks/SKILL.md` 手順1 の
`grep -v '^#' develop/direction.md | grep -v '^\s*$'`、および
`skills/task-workflow/scripts/init.py` の `check_direction()`（見出し以外の行数を数える）。
雛形は同ファイルの `DIRECTION` 定数で、いまは `# 未対応の指示メモ` の1行。

## 決まっていること（蒸し返さない）

- `develop/direction.md` は「まだタスクになっていないドラフト」の置き場とし、ユーザーと
  エージェントの両方が書ける。決まったタスクの正典は従来どおり `develop/tasks.json`
- 節を2つ置いて著者で分ける: `## ユーザーから` と `## エージェントのドラフト`
- 節見出しは `#` で始まるため、既存の `grep -v '^#'` 判定がそのまま動く形にする
  （行頭マーカー方式は採らない）
- `## エージェントのドラフト` は、対話セッションでユーザーの承認を得たものだけタスク化する。
  未承認のものは節に残してよい（まだ `tasks.json` に無いので正典は二重にならない）
- `/plan-tasks` が `/loop` から呼ばれているときは `## エージェントのドラフト` を一切
  触らない（会話入口を塞ぐのと同じ理由）
- `docs/history/direction.md` には、ドラフト由来のものだけ出典を1行添える
  （例: `（エージェントのドラフト / 承認: 「…」）`）。ユーザー由来の書き方は変えない
- `/next-task` が「`/plan-tasks` が先」と報告するのは `## ユーザーから` に中身があるときだけ。
  行数の報告は節ごとに分ける
- 既存の「タスク化済みを `develop/direction.md` に残さない」原則は維持する
- 呼び名はリポジトリ既存の語彙（ユーザー／エージェント）に合わせ、出力スタイル由来の
  呼び名は使わない

## 解くべき論点

- 節が無い `develop/direction.md`（この変更より前に作られたもの、利用側プロジェクトの
  既存ファイル）をどう扱うか。「節が無ければ全体を `## ユーザーから` とみなす」で足りるか、
  判定側に明記が要るか

## やること

1. `skills/task-workflow/WORKFLOW.md` の「指示メモ（`develop/direction.md`）」節と
   「ファイル配置と CLAUDE.md」の表を書き換える（定義・2節・承認ゲート・`/loop` の封じ・
   履歴の出典注記）。冒頭の目次表の該当行も合わせる
2. `skills/plan-tasks/SKILL.md` の手順1の分岐と手順6を節ごとの扱いに直し、
   「完了報告のフォーマット」に承認の有無を出す
3. `skills/next-task/SKILL.md` の手順1・2と「完了報告のフォーマット」を、節ごとの行数と
   `## ユーザーから` 基準の判定に直す
4. `skills/task-workflow/scripts/init.py` の `DIRECTION` 定数を2節入りの雛形にし、
   `check_direction()` を節ごとに数える形にする。`skills/setup-tasks/SKILL.md` の
   雛形の説明も合わせる
5. `skills/task-workflow/scripts/selftest.py` の `direction.md` を扱うテストを、新しい雛形と
   判定に合わせる
6. 論点で決めた「節が無いファイル」の扱いを、判定する側（init.py と2つの SKILL.md）に
   1行で書く

## 完了条件

- `./check.sh` が通る
- `develop/direction.md` を扱う6箇所（WORKFLOW.md・plan-tasks・next-task・setup-tasks・
  init.py・selftest.py）が同じ節名で揃っている
- `/loop` から `/plan-tasks` を呼んだとき `## エージェントのドラフト` を触らないことが、
  `skills/plan-tasks/SKILL.md` の手順1に書かれている
- 節が無い `direction.md` を読ませても、判定が従来どおり（全体を未タスク化の指示として
  数える）動くことを確認した結果が `evidence` にある

## 注意

- 利用側プロジェクトの `develop/direction.md` はこのリポジトリからは触らない。移行が要る
  なら別タスクにする（前例: T-005）
- このリポジトリ自身の `develop/direction.md` を2節の形に直すのはこのタスクに含めてよい
