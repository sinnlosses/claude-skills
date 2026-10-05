# 作業先が別のリポジトリのとき

タスクが直す対象が自分の作業ツリーの外のリポジトリのときの、実装の依頼文の項目（手順5c）と受け入れ（手順6）。

## 実装の依頼文に足す項目（手順5c）

   - 作業先が別のリポジトリのときだけ渡す（下の手順6の「作業先が別のリポジトリのとき」）: 「作業先の
     リポジトリでは、別の作業ツリー（`git worktree add -b <枝> <パス> main`）で直してコミットし、**コミットの
     あと**にその作業ツリーを cwd にして `tw verify` を打つ（控えは cwd の作業ツリーごとで、鍵に `HEAD` の
     SHA を含むので、コミットの前に打つと受け入れで `NOT_VERIFIED head` になる）。**`main` へ入れず、
     作業ツリーと枝を消さずに残して**、作業ツリーのパスと `tw verify` の判定行（`VERIFIED`・
     `VERIFY_NOT_PASSED` など）を報告に書く。作業先に `tw` の台帳が無く `tw verify` が `MISSING` を
     返すときは、検証コマンドを自分で打って通し、打ったコマンドと終了コードを報告に書く」。
     別のリポジトリの作業ツリーには着手の控えが無いので、そこでのコミットは hook に拒まれない

## 受け入れ（手順6）

   **作業先が別のリポジトリのとき**（タスクが直す対象が自分の作業ツリーの外のリポジトリ）: 控えは
   cwd の作業ツリーごとに別なので、`git diff` と `tw verify-check` は、委譲先が残した作業先の作業ツリー
   （報告のパス）で `cd <パス> && tw verify-check` と打つ（自分の作業ツリーで打つと `NOT_VERIFIED none`
   になるだけ）。コメント行の拾い出しも同じ作業ツリーで、主ブランチから委譲先の枝までの範囲
   （`python3 ${CLAUDE_SKILL_DIR}/../comment-audit/scripts/diff_added_comment_lines.py main..<枝>`）を
   渡して打つ。レビューの判定も同じ作業ツリーで同じ範囲を渡して打ち
   （`python3 ${CLAUDE_SKILL_DIR}/scripts/review_needed.py --difficulty <difficulty> main..<枝>`）、
   レビュアーに渡す差分のコマンドも `git diff main...<枝>` にする。表は同じに読む。`VERIFIED_SAME` なら、検証コマンドを打たずに作業先の本体で
   `git merge --ff-only <枝>` して、作業ツリーと枝を消す（`git worktree remove`・`git branch -d`）。
   `NOT_VERIFIED` ならその作業ツリーで `tw verify` を打ち直してから同じ段取りへ進む。受け入れで直すなら
   その作業ツリーで直してコミットしてから打つ。`tw` が `MISSING` を返す作業先では控えが無いので、
   委譲先の報告を信用せず検証コマンドを打つ。
