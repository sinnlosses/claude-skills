#!/usr/bin/env python3
"""`task.py` の Beads 方式（`- タスクの置き場: beads`）の自己テスト。

使い方: python3 selftest_beads.py

一時ディレクトリに git リポジトリと作業ツリー2本を作り、`bd init --stealth` で `.beads` を置いて、
`task.py` を実際に子プロセスで（取り合いは同時に）起こして確かめる。本物の `bd` を使う
（無ければ飛ばして 0 で終わる。ファイル方式は `selftest_task.py` が見る）。

GitHub・Jira には繋がない。GitHub は、本物の `bd` の `bd github push`・`pull` を `GITHUB_API_URL` で
偽の HTTP サーバ（`FakeGitHub`。REST の Issue と Project の GraphQL）へ向ける。`gh` は PATH の先頭に置いた
偽のコマンドが呼ばれ方を記録して `api` を同じサーバへ転送し、`bd jira sync` は偽の `bd` が受ける
（`bd` のそれ以外のサブコマンドは本物へ渡す）。
`HOME`・`XDG_CONFIG_HOME`・`XDG_DATA_HOME` を一時ディレクトリへ向けて、利用者の家を汚さない
（`bd init` は利用者の `~/.config/bd/config.yaml` を読み書きし、並行に打つと使用状況の送信の設定まで
書き戻すことがあった。一時の家には送信を止めた設定を置く）。
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import re
import tempfile
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import beads  # noqa: E402
import layout  # noqa: E402
import ledger  # noqa: E402
import taskfile  # noqa: E402

# 利用者の値のままだと、一時リポジトリの台帳がその置き場に積もる。
os.environ.pop(ledger.STATE_DIR_ENV, None)

TASK_PY = os.path.join(HERE, "task.py")
INIT_PY = os.path.join(HERE, "init.py")
MATERIAL_PY = os.path.join(HERE, "..", "..", "retrospect", "scripts", "material.py")
BODY = ("## 目的・背景\nx\n\n## 決まっていること（蒸し返さない）\n\n## 解くべき論点\nなし\n\n## やること\n\n"
        "## 完了条件\n- 通る\n\n## 注意\nz\n\n## 参考情報\n")
# 登録の既定の本文。`make_repo` が主ブランチに置く `shared.txt` を名指す。
PLANNED_BODY = BODY.replace("## やること\n", "## やること\n### 1. 書く\nx\n\n### 名指すファイル\n- `shared.txt`\n")

failures: list[str] = []
BASE_ENV = os.environ.copy()
# テストは CPU 数の半分まで並行に走らせる。出力と環境変数はテストごとに持つ。
_local = threading.local()
# prefix ごとに `bd init --stealth` した `.beads` と、そのとき書かれた `.git/info/exclude`。`main()` が作る。
_beads_templates: dict[str, tuple[str, str]] = {}


def env() -> dict[str, str]:
    return getattr(_local, "env", BASE_ENV)


def say(line: str) -> None:
    _local.lines.append(line)


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        say(f"  ok   {label}")
    else:
        say(f"  FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def write(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗: {r.stderr}")
    return r


def run_task(cwd: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, TASK_PY, *args], cwd=cwd, capture_output=True, text=True, input=stdin, env=env()
    )


def start_task(cwd: str, *args: str, stdin: str | None = None) -> subprocess.Popen:
    p = subprocess.Popen(
        [sys.executable, TASK_PY, *args],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env(),
    )
    return p


def bd(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bd", *args], cwd=cwd, capture_output=True, text=True, env=env())


def rows(out: str) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for line in out.split("---")[0].splitlines():
        cols = line.split("\t")
        if len(cols) == 8:
            table[cols[0]] = cols
    return table


def tail_line(out: str, key: str) -> str:
    return next((l for l in out.splitlines() if l.startswith(key + "\t")), "")


def make_repo(tmp: str, branch: str = "切らない", extra: str = "", verify: str | None = None,
              prefix: str | None = beads.PREFIX_LOCAL) -> tuple[str, str, str]:
    """`(本体, 作業ツリー1, 作業ツリー2)`。`.beads` は `prefix` の作り置きを写してから `init.py` を打つ。
    `prefix` が `None` なら `init.py` が `bd init` で作る。"""
    main_path = os.path.join(tmp, "base")
    os.makedirs(main_path)
    git(main_path, "init", "-q", "-b", "main")
    git(main_path, "config", "user.email", "test@example.com")
    git(main_path, "config", "user.name", "test")
    git(main_path, "config", "beads.role", "maintainer")
    config = "# x\n\n## タスク運用\n\n"
    config += f"- 検証コマンド: {verify}\n" if verify else "- 検証コマンド: なし\n"
    config += f"- 整形コマンド: なし\n- ブランチ: {branch}\n- タスクの置き場: beads\n{extra}"
    write(os.path.join(main_path, "CLAUDE.md"), config)
    write(os.path.join(main_path, "shared.txt"), "line1\n")
    if prefix is not None:
        template, exclude = _beads_templates[prefix]
        shutil.copytree(template, os.path.join(main_path, ".beads"))
        write(os.path.join(main_path, ".git", "info", "exclude"), exclude)
    r = subprocess.run([sys.executable, INIT_PY, "develop"], cwd=main_path, capture_output=True, text=True, env=env())
    if r.returncode != 0:
        raise RuntimeError(f"init.py 失敗: {r.stdout}{r.stderr}")
    git(main_path, "add", "-A")
    git(main_path, "commit", "-q", "-m", "init")
    wt1 = os.path.join(tmp, "wt1")
    wt2 = os.path.join(tmp, "wt2")
    git(main_path, "worktree", "add", "-q", "-b", "wt1", wt1, "main")
    git(main_path, "worktree", "add", "-q", "-b", "wt2", wt2, "main")
    return main_path, wt1, wt2


def new(cwd: str, summary: str, *extra: str, body: str = PLANNED_BODY) -> str:
    r = run_task(cwd, "new", "--summary", summary, "--difficulty", "sonnet", "--loopable", "Y", *extra,
                 "--body-file", "-", stdin=body)
    if r.returncode != 0:
        raise RuntimeError(f"task new 失敗: {r.stdout}{r.stderr}")
    return r.stdout.split("\t")[1]


def new_unplanned(cwd: str, summary: str, body: str = BODY) -> str:
    """`## やること` の空な todo（`--hold` で登録して戻す）。"""
    task_id = new(cwd, summary, "--hold", body=body)
    r = run_task(cwd, "edit", task_id, "--status", "todo")
    if r.returncode != 0:
        raise RuntimeError(f"task edit --status todo 失敗: {r.stdout}{r.stderr}")
    return task_id


def work_and_done(wt: str, task_id: str, *, dropped: bool = False, name: str = "") -> None:
    write(os.path.join(wt, name or f"{task_id}.txt"), f"{task_id}\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", f"{task_id}: 作業")
    extra = ("--dropped",) if dropped else ()
    r = run_task(wt, "done", task_id, *extra, "--result-file", "-", stdin="- 検証: なし\n- 振り返り: 兆候なし\n")
    if r.returncode != 0:
        raise RuntimeError(f"task done 失敗: {r.stdout}{r.stderr}")


# --- テスト -------------------------------------------------------------------


def test_setup_and_config_doctor() -> None:
    say("init.py・config-doctor・MISSING・設定の読み違い")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp, prefix=None)
        check("init.py が .beads を作る", os.path.isdir(os.path.join(main_path, ".beads")))
        check("stealth で .beads は git に見えない", git(main_path, "status", "--porcelain").stdout.strip() == "")
        r = run_task(wt1, "config-doctor")
        check("config-doctor が store・beads・tracker の行を足す", r.returncode == 0
              and tail_line(r.stdout, "store").startswith("store\tOK\tbeads")
              and tail_line(r.stdout, "beads").startswith("beads\tOK")
              and tail_line(r.stdout, "tracker") == "tracker\tOK\tなし", r.stdout)
        r = run_task(wt1, "status")
        check("まっさらな status は集計だけ（triage 行つき）", r.returncode == 0 and r.stdout.startswith("---\n")
              and "triage\t0\t-" in r.stdout, r.stdout)
        r = run_task(wt1, "prune")
        check("prune は NOTHING", r.returncode == 0 and r.stdout.startswith("NOTHING"), r.stdout)

        shutil.rmtree(os.path.join(main_path, ".beads"))
        r = run_task(wt1, "status")
        check(".beads が無ければ MISSING（終了コード6）", r.returncode == 6 and r.stdout.startswith("MISSING"), r.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp, extra="- トラッカー: gitlab\n")
        r = run_task(wt1, "status")
        check("読めないトラッカーは INVALID（終了コード3）", r.returncode == 3 and r.stdout.startswith("INVALID"), r.stdout)
        write(os.path.join(wt1, "CLAUDE.md"), "# x\n\n## タスク運用\n\n- ブランチ: 切らない\n- タスクの置き場: どこか\n")
        r = run_task(wt1, "status")
        check("読めない置き場は INVALID（終了コード3）", r.returncode == 3 and r.stdout.startswith("INVALID"), r.stdout)


def test_file_mode_untouched_by_beads_dir() -> None:
    say("設定行が無ければ .beads があってもファイル方式のまま")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp)
        write(os.path.join(main_path, "CLAUDE.md"), "# x\n\n## タスク運用\n\n- ブランチ: 切らない\n")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "ファイル方式へ")
        r = run_task(main_path, "new", "--summary", "f", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=PLANNED_BODY)
        check("new がタスクファイルを作る", r.returncode == 0 and "develop/task/T-001.md" in r.stdout
              and os.path.exists(os.path.join(main_path, "develop", "task", "T-001.md")), r.stdout)
        r = run_task(main_path, "config-doctor")
        check("config-doctor は4行のまま", len(r.stdout.strip().splitlines()) == 4, r.stdout)
        r = run_task(main_path, "edit", "T-001", "--summary", "x")
        check("edit はファイル方式では --body-file だけ（ほかは終了コード2）", r.returncode == 2, r.stdout + r.stderr)
        r = run_task(main_path, "show", "T-001")
        check("show はファイル方式でもタスクファイルを出す", r.returncode == 0 and r.stdout.startswith("---\nid: T-001"), r.stdout)
        r = bd(main_path, "list", "--json", "--all")
        check("Beads には何も作らない", json.loads(r.stdout or "[]") == [], r.stdout)


def test_new_status_and_numbering() -> None:
    say("new・status・採番・本文の分け方")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        write(os.path.join(main_path, "docs", "history", "tasks.md"), "# 完了タスクのアーカイブ\n\n## T-040 古い\n")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "履歴")
        a = new(wt1, "最初")
        check("番号は docs/history/tasks.md の最大の次", a == "T-041", a)
        b = new(wt1, "次", "--deps", a)
        h = new(wt1, "待ち", "--hold")
        r = run_task(wt1, "new", "--summary", "x", "--difficulty", "haiku", "--loopable", "Y", "--deps", "T-999",
                     "--body-file", "-", stdin=PLANNED_BODY)
        check("Beads に無い依存は終了コード2", r.returncode == 2, r.stdout + r.stderr)
        r = run_task(wt1, "new", "--summary", "x", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=BODY)
        check("空の ## やること は終了コード2", r.returncode == 2 and "--hold" in r.stderr, r.stdout + r.stderr)
        r = run_task(wt1, "new", "--summary", "x", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=BODY.replace("## やること\n", "## やること\n### 1. 書く\n"))
        check("名指すファイルの無い ## やること は終了コード2", r.returncode == 2, r.stdout + r.stderr)
        r = run_task(wt1, "new", "--summary", "x", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=PLANNED_BODY.replace("### 1. 書く", "### 2. 書く"))
        check("段が `### 1.` から始まらない ## やること は終了コード2と理由", r.returncode == 2
              and "### 1." in r.stderr, r.stdout + r.stderr)
        h_empty = new(wt1, "空の待ち", "--hold", body=BODY)
        check("--hold なら空の ## やること を受ける", h_empty.startswith("T-"), h_empty)

        r = run_task(wt2, "status")
        t = rows(r.stdout)
        check("status の行（READY・BLOCKED・HOLD）", t.get(a, [])[5:6] == ["READY"]
              and t.get(b, [])[5:6] == [f"BLOCKED:{a}"] and t.get(h, [])[1] == "hold" and t[h][5] == "HOLD", r.stdout)
        check("counts・ready", "counts\ttodo=2\thold=2\tdone=0\tdropped=0\tclaimed=0" in r.stdout
              and "ready\t1" in r.stdout, r.stdout)
        issue = beads.show(main_path, beads.to_bd_id(a))
        check("完了条件は acceptance_criteria、ほかは description", issue is not None
              and issue.raw.get("acceptance_criteria") == "- 通る"
              and "## 完了条件" not in issue.raw.get("description", "")
              and set(issue.labels) == {"difficulty:sonnet", "loopable:Y"}, str(issue and issue.raw))

        procs = [start_task(w, "new", "--summary", f"並行{i}", "--difficulty", "haiku", "--loopable", "Y",
                            "--body-file", "-") for i, w in enumerate((wt1, wt2, main_path))]
        outs = [p.communicate(PLANNED_BODY)[0] for p in procs]
        ids = [o.split("\t")[1] for o in outs if o.startswith("CREATED")]
        check("3つ同時の new で番号が重ならない", len(ids) == 3 and len(set(ids)) == 3, repr(outs))
        r = bd(main_path, "kv", "get", beads.LAST_ID_KEY)
        check("最後の番号を bd kv に残す", r.stdout.strip().isdigit() and int(r.stdout.strip()) >= 45, r.stdout)

        check("hold は組み込みの deferred で書く", beads.show(main_path, beads.to_bd_id(h)).status == "deferred")
        bd(main_path, "config", "set", "status.custom", "pending:frozen")
        bd(main_path, "create", "--id", "t-100", "--title", "切り替え前の待ち", "-l", "difficulty:haiku,loopable:Y",
           "-s", "pending", "--silent")
        r = run_task(wt1, "status")
        check("切り替え前の pending も hold と読む", rows(r.stdout).get("T-100", [""] * 8)[1] == "hold", r.stdout)
        r = run_task(wt1, "edit", "T-100", "--status", "todo")
        check("pending から todo へ戻せる", r.returncode == 0 and beads.show(main_path, "t-100").status == "open",
              r.stdout + r.stderr)


def test_claim_race_owner_and_release() -> None:
    say("claim の取り合い・NOT_OWNER・release")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        a = new(main_path, "取り合い")
        h = new(main_path, "待ち", "--hold")
        procs = [start_task(w, "claim", a) for w in (wt1, wt2)]
        outs = [(p.communicate()[0], p.returncode) for p in procs]
        claimed = [o for o, c in outs if o.startswith("CLAIMED") and c == 0]
        taken = [o for o, c in outs if o.startswith("TAKEN") and c == 4]
        check("同時の claim は1つだけ CLAIMED、残りは TAKEN", len(claimed) == 1 and len(taken) == 1, repr(outs))
        winner = wt1 if "CLAIMED" in outs[0][0] else wt2
        loser = wt2 if winner == wt1 else wt1
        check("CLAIMED の3列目は beads:t-xxx", claimed[0].split("\t")[2] == f"beads:{beads.to_bd_id(a)}", claimed[0])
        issue = beads.show(main_path, beads.to_bd_id(a))
        check("負けた側は印の持ち主も戻り先の枝も書き換えない", issue is not None
              and issue.assignee == os.path.basename(winner)
              and (issue.raw.get("metadata") or {}).get(beads.CLAIM_BRANCH_KEY) == os.path.basename(winner),
              str(issue and issue.raw))

        r = run_task(loser, "done", a, "--result-file", "-", stdin="x\n")
        check("他人の印の done は NOT_OWNER（終了コード4）", r.returncode == 4 and r.stdout.startswith("NOT_OWNER"), r.stdout)
        r = run_task(loser, "release", a)
        check("他人の印の release は NOT_OWNER", r.returncode == 4 and r.stdout.startswith("NOT_OWNER"), r.stdout)
        r = run_task(winner, "status")
        marker = rows(r.stdout).get(a, [""] * 8)[6]
        check("印の列は作業ツリー名と経過", marker.startswith(os.path.basename(winner) + " "), r.stdout)
        r = run_task(winner, "claim", h)
        check("hold は claim できない（NOT_READY）", r.returncode == 4 and r.stdout.startswith("NOT_READY"), r.stdout)
        r = run_task(loser, "release", a, "--force")
        check("--force の release は RELEASED", r.returncode == 0 and r.stdout.startswith("RELEASED"), r.stdout)
        r = run_task(loser, "release", a)
        check("印の無い release は NOT_CLAIMED（終了コード0）", r.returncode == 0 and r.stdout.startswith("NOT_CLAIMED"), r.stdout)
        r = run_task(loser, "claim", a)
        check("解放されたら取り直せる", r.returncode == 0 and r.stdout.startswith("CLAIMED"), r.stdout)
        write(os.path.join(loser, "dirty.txt"), "x\n")
        r = run_task(loser, "claim", h)
        check("汚れた作業ツリーでは DIRTY", r.returncode == 4 and r.stdout.startswith("DIRTY"), r.stdout)


def test_done_commits_since_claim() -> None:
    say("done: claim 後のコミットを COMMITS_SINCE_CLAIM で知らせる（控えの無い印は出さない）")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        a = new(main_path, "コミットを知らせる")
        b = new(main_path, "控えの無い印")

        run_task(wt1, "claim", a)
        write(os.path.join(wt1, "illicit.txt"), "x\n")
        git(wt1, "add", "-A")
        git(wt1, "commit", "-q", "-m", f"{a}: 作業")
        sha = git(wt1, "rev-parse", "--short", "HEAD").stdout.strip()
        r = run_task(wt1, "done", a, "--result-file", "-", stdin="- 検証: なし\n- 振り返り: 兆候なし\n")
        lines = r.stdout.splitlines()
        check(
            "claim 後のコミットは COMMITS_SINCE_CLAIM で続けて知らせる",
            r.returncode == 0
            and lines == [f"DONE\t{a}\tbeads:{beads.to_bd_id(a)}\tship で閉じる", f"COMMITS_SINCE_CLAIM\t{a}\t{sha}"],
            r.stdout,
        )

        run_task(wt2, "claim", b)
        bd_id_b = beads.to_bd_id(b)
        bd(wt2, "update", bd_id_b, "--unset-metadata", beads.CLAIM_HEAD_KEY)
        write(os.path.join(wt2, "illicit2.txt"), "x\n")
        git(wt2, "add", "-A")
        git(wt2, "commit", "-q", "-m", f"{b}: 作業")
        r2 = run_task(wt2, "done", b, "--result-file", "-", stdin="- 検証: なし\n- 振り返り: 兆候なし\n")
        check(
            "控え（task_claim_head）の無い印はコミットがあっても落ちず、知らせない",
            r2.returncode == 0 and r2.stdout.strip() == f"DONE\t{b}\tbeads:{bd_id_b}\tship で閉じる",
            r2.stdout,
        )


def guard_denies(tmp: str, where: str, command: str = "git commit -m x") -> bool:
    """`tw commit-guard` を git の外（`tmp`）から打ち、拒んだか。"""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": where})
    r = run_task(tmp, "commit-guard", stdin=payload)
    if r.returncode != 0:
        raise RuntimeError(f"commit-guard が {r.returncode} で終わった: {r.stderr}")
    return '"deny"' in r.stdout


def test_commit_guard() -> None:
    say("commit-guard: 印が立って done 前の作業ツリーのコミットを拒む")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        a = new(main_path, "拒む")
        b = new(main_path, "release で外す")
        c = new(main_path, "人が外す")

        run_task(wt1, "claim", a)
        check("claim で控えが立つ（作業ツリーごと）",
              ledger.open_claims(cwd=wt1) == [a] and ledger.open_claims(cwd=wt2) == [], str(ledger.open_claims(cwd=wt1)))
        check("印の作業ツリーの git commit は拒む", guard_denies(tmp, wt1))
        check("印の無い作業ツリーの git commit は通す", not guard_denies(tmp, wt2))
        check("別の作業ツリーへの git -C は通す", not guard_denies(tmp, wt1, f"git -C {wt2} commit -m x"))
        write(os.path.join(wt1, "work.txt"), "x\n")
        git(wt1, "add", "work.txt")
        git(wt1, "commit", "-q", "-m", "メインの手直し")
        check("hook を通らないメインのコミットは印があっても通る",
              git(wt1, "log", "-1", "--format=%s").stdout.strip() == "メインの手直し")
        r = run_task(wt1, "done", a, "--result-file", "-", stdin="- 検証: なし\n- 振り返り: 兆候なし\n")
        check("done で控えが消え、そのあとの git commit は通る",
              r.returncode == 0 and ledger.open_claims(cwd=wt1) == [] and not guard_denies(tmp, wt1), r.stdout)
        r = run_task(wt1, "ship")
        check("ship のあとも控えは無い", r.returncode == 0 and ledger.open_claims(cwd=wt1) == [], r.stdout + r.stderr)

        run_task(wt2, "claim", b)
        check("release の前は拒む", guard_denies(tmp, wt2))
        run_task(wt2, "release", b)
        check("release のあとは通る", not guard_denies(tmp, wt2))

        run_task(wt2, "claim", c)
        r = run_task(wt1, "release", c, "--force")
        check("人が --force で外すと持ち主の作業ツリーの控えも消える",
              r.returncode == 0 and ledger.open_claims(cwd=wt2) == [] and not guard_denies(tmp, wt2), r.stdout)


def handback_reason(tmp: str, where: str) -> str | None:
    """`tw handback-guard` に SubagentStop を渡し、block の理由。通したら `None`。"""
    payload = json.dumps({"hook_event_name": "SubagentStop", "cwd": where})
    r = run_task(tmp, "handback-guard", stdin=payload)
    if r.returncode != 0:
        raise RuntimeError(f"handback-guard が {r.returncode} で終わった: {r.stderr}")
    return json.loads(r.stdout)["reason"] if r.stdout else None


def test_handback_guard() -> None:
    say("handback-guard・pause: 作業があるのに計画か検証が欠けた返却を拒む")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp, verify="`echo verified`")
        a = new_unplanned(main_path, "先に計画")
        b = new_unplanned(main_path, "計画なしで作業")

        check("着手の印が無い委譲は通す", handback_reason(tmp, wt1) is None)
        run_task(wt1, "claim", a)
        check("印があっても作業が無ければ通す", handback_reason(tmp, wt1) is None)
        run_task(wt1, "edit", a, "--section", "やること", "--body-file", "-", stdin="### 1. 書く\n")
        check("計画だけの回は通す", handback_reason(tmp, wt1) is None)
        write(os.path.join(wt1, "work.txt"), "x\n")
        reason = handback_reason(tmp, wt1) or ""
        check("計画があっても検証が無ければ block（NOT_VERIFIED）",
              "NOT_VERIFIED\tnone" in reason and "PLAN_NOT_FIRST" not in reason, reason)
        r = run_task(wt1, "verify")
        check("PLAN_FIRST と tw verify がそろえば通す", r.returncode == 0 and handback_reason(tmp, wt1) is None,
              r.stdout + r.stderr)

        run_task(wt2, "claim", b)
        write(os.path.join(wt2, "work.txt"), "x\n")
        reason = handback_reason(tmp, wt2) or ""
        check("計画も検証も無ければ両方の行で block", f"PLAN_NOT_FIRST\t{b}\tmissing" in reason
              and "NOT_VERIFIED\tnone" in reason, reason)
        r = run_task(wt2, "pause")
        check("tw pause を打てば通す", r.stdout.startswith("PAUSED\t") and handback_reason(tmp, wt2) is None,
              r.stdout + r.stderr)


def test_handback_guard_step() -> None:
    say("step・handback-guard: 途中の段の返却は tw step で通し、最後の段は検証を求める")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, verify="`echo verified`")
        a = new_unplanned(main_path, "段ごと")
        run_task(wt1, "claim", a)
        run_task(wt1, "edit", a, "--section", "やること", "--body-file", "-", stdin="### 1. 書く\n\n### 2. 試す\n")
        write(os.path.join(wt1, "work.txt"), "x\n")
        r = run_task(wt1, "step", a, "1")
        check("途中の段は STEPPED（n/N）を出し、返却を通す", r.returncode == 0
              and r.stdout.startswith(f"STEPPED\t{a}\t1/2\t") and handback_reason(tmp, wt1) is None, r.stdout + r.stderr)
        write(os.path.join(wt1, "work.txt"), "y\n")
        r = run_task(wt1, "step", a, "2")
        check("最後の段は LAST_STEP（終了コード4）で、返却は検証が無ければ block", r.returncode == 4
              and r.stdout.startswith(f"LAST_STEP\t{a}\t2/2\t") and "NOT_VERIFIED" in (handback_reason(tmp, wt1) or ""),
              r.stdout + r.stderr)


def test_plan_check() -> None:
    say("edit・plan-check: ## やること を作業より先に書いたかを知らせる")
    planned = BODY.replace("## やること\n", "## やること\n### 1. 書く\n")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        a = new_unplanned(main_path, "先に書く")
        b = new_unplanned(main_path, "後から書く")
        c = new_unplanned(main_path, "着手前に直す")

        def metadata(task_id: str) -> dict:
            issue = beads.show(main_path, beads.to_bd_id(task_id))
            raw = issue.raw.get("metadata") if issue is not None else None
            return raw if isinstance(raw, dict) else {}

        run_task(wt1, "claim", a)
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=planned)
        check("作業より先の edit は metadata に first を残し、claim の控えを消さない", r.returncode == 0
              and metadata(a).get(beads.PLAN_KEY) == "first" and metadata(a).get(beads.CLAIM_HEAD_KEY),
              r.stdout + r.stderr + str(metadata(a)))
        write(os.path.join(wt1, "work.txt"), "x\n")
        run_task(wt1, "edit", a, "--body-file", "-", stdin=planned.replace("1. 書く", "1. 書き直す"))
        r = run_task(wt1, "plan-check", a)
        check("作業より先に書けば PLAN_FIRST（後の書き直しで変わらない）", r.returncode == 0
              and r.stdout.strip() == f"PLAN_FIRST\t{a}", r.stdout + r.stderr)

        run_task(wt2, "claim", b)
        write(os.path.join(wt2, "work.txt"), "x\n")
        r = run_task(wt2, "plan-check", b)
        check("書かずに作業へ進むと PLAN_NOT_FIRST missing", r.returncode == 0
              and r.stdout.strip() == f"PLAN_NOT_FIRST\t{b}\tmissing", r.stdout + r.stderr)
        r = run_task(wt2, "edit", b, "--body-file", "-", stdin=planned)
        check("作業のあとの初回の記入は WORK_BEFORE_PLAN で拒み、書き込まない（終了コード4）", r.returncode == 4
              and r.stdout.startswith(f"WORK_BEFORE_PLAN\t{b}\t") and "--after-work" in r.stdout
              and beads.PLAN_KEY not in metadata(b), r.stdout + r.stderr + str(metadata(b)))
        r = run_task(wt2, "edit", b, "--after-work", "--body-file", "-", stdin=planned)
        check("--after-work なら書き込み、EDITED に続けて PLAN_AFTER_WORK を出す", r.returncode == 0
              and r.stdout.splitlines()[:2] == [f"EDITED\t{b}", f"PLAN_AFTER_WORK\t{b}\t作業の後に書いた"],
              r.stdout + r.stderr)
        r = run_task(wt2, "plan-check", b)
        check("作業のあとで書くと PLAN_NOT_FIRST after-work", r.returncode == 0
              and r.stdout.strip() == f"PLAN_NOT_FIRST\t{b}\tafter-work", r.stdout + r.stderr)
        r = run_task(wt1, "plan-check", b)
        check("自分の印が無ければ NOT_OWNER（終了コード4）", r.returncode == 4
              and r.stdout.strip() == f"NOT_OWNER\t{b}", r.stdout)

        r = run_task(main_path, "edit", c, "--body-file", "-", stdin=planned)
        check("着手の印の持ち主でない edit は記録しない", r.returncode == 0 and beads.PLAN_KEY not in metadata(c),
              r.stdout + r.stderr + str(metadata(c)))


def test_edit_frame_guard() -> None:
    say("edit: ## 目的・背景・## 完了条件 がいまの本文と違う本文は --change-frame なしで拒む")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, _wt1, _wt2 = make_repo(tmp)
        a = new(main_path, "守る本文")
        other = BODY.replace("## 目的・背景\nx", "## 目的・背景\n別のタスクの目的")

        def current() -> str:
            issue = beads.show(main_path, beads.to_bd_id(a))
            return json.dumps(issue.raw if issue is not None else {}, sort_keys=True, default=str)

        before = current()
        r = run_task(main_path, "edit", a, "--body-file", "-", stdin=other)
        check("別のタスクの本文は FRAME_CHANGED（終了コード4）で拒み、書き込まない", r.returncode == 4
              and r.stdout.startswith(f"FRAME_CHANGED\t{a}\t") and "--change-frame" in r.stdout
              and "## 目的・背景" in r.stdout and current() == before, r.stdout + r.stderr)
        r = run_task(main_path, "edit", a, "--body-file", "-", stdin=BODY.replace("- 通る", "- 通らない"))
        check("## 完了条件 だけ違っても拒む", r.returncode == 4 and r.stdout.startswith("FRAME_CHANGED\t")
              and "## 完了条件" in r.stdout and current() == before, r.stdout + r.stderr)
        r = run_task(main_path, "edit", a, "--change-frame", "--body-file", "-", stdin=other)
        issue = beads.show(main_path, beads.to_bd_id(a))
        check("--change-frame を付ければ書き込む", r.returncode == 0 and r.stdout.startswith(f"EDITED\t{a}")
              and issue is not None and "別のタスクの目的" in str(issue.raw.get("description")), r.stdout + r.stderr)
        planned = other.replace("## やること\n", "## やること\n### 1. 書く\n")
        r = run_task(main_path, "edit", a, "--body-file", "-", stdin=planned)
        check("## やること だけの書き換えは通る", r.returncode == 0 and r.stdout.startswith("EDITED\t"),
              r.stdout + r.stderr)
        r = run_task(main_path, "edit", a, "--body-file", "-", stdin=planned.replace("別のタスクの目的", "別のタスクの目的  ") + "\n\n")
        check("行末の空白と末尾の改行だけの差は通る", r.returncode == 0 and r.stdout.startswith("EDITED\t"),
              r.stdout + r.stderr)
        r = run_task(main_path, "edit", a, "--status", "hold")
        check("--status だけの edit は本文を比べない", r.returncode == 0 and r.stdout.startswith("EDITED\t"),
              r.stdout + r.stderr)


def test_edit_section() -> None:
    say("edit --section: 指した節の中身だけを置き換える")
    mentions = BODY.replace("## 目的・背景\nx", "## 目的・背景\n文中の `## やること` は境目でない\nx")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp)
        a = new_unplanned(main_path, "節だけ", body=mentions)
        b = new_unplanned(main_path, "作業のあとに書く", body=mentions)

        def text(task_id: str) -> str:
            issue = beads.show(main_path, beads.to_bd_id(task_id))
            raw = issue.raw if issue is not None else {}
            return beads.compose_body(
                str(raw.get("description") or ""), str(raw.get("acceptance_criteria") or ""), str(raw.get("notes") or ""), None
            )

        def metadata(task_id: str) -> dict:
            issue = beads.show(main_path, beads.to_bd_id(task_id))
            raw = issue.raw.get("metadata") if issue is not None else None
            return raw if isinstance(raw, dict) else {}

        run_task(wt1, "claim", a)
        run_task(wt1, "claim", b)
        before = text(a)
        r = run_task(wt1, "edit", a, "--section", "やること", "--body-file", "-", stdin="- x\n")
        check("段の無い ## やること は終了コード2と理由で拒み、書き込まない", r.returncode == 2
              and "### 1." in r.stderr and text(a) == before, r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--section", "やること", "--body-file", "-", stdin="### 1. 書く\n\n- x\n")
        want = before.replace("## やること\n\n## 完了条件", "## やること\n\n### 1. 書く\n\n- x\n\n## 完了条件")
        check("節だけが置き換わり、ほかの節は1バイトも変わらない（文中の `## やること` は境目に数えない）",
              r.returncode == 0 and r.stdout.startswith(f"EDITED\t{a}") and text(a) == want and want != before,
              r.stdout + r.stderr + text(a))
        check("作業より先の記入は metadata に first を残す", metadata(a).get(beads.PLAN_KEY) == "first", str(metadata(a)))
        mid = text(a)
        for name in ("ほげ", "結果"):
            r = run_task(wt1, "edit", a, "--section", name, "--body-file", "-", stdin="x\n")
            check(f"枠に無い見出し {name} は書き込まずに拒む（終了コード2）",
                  r.returncode == 2 and "usage:" in r.stderr and text(a) == mid, r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--section", "やること", "--body-file", "-", stdin="a\n## 完了条件\nb\n")
        check("中身に `## ` で始まる行があれば書き込まずに拒む（終了コード2）",
              r.returncode == 2 and "usage:" in r.stderr and text(a) == mid, r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--section", "完了条件", "--body-file", "-", stdin="別の条件\n")
        check("枠の節を変えれば FRAME_CHANGED（終了コード4）で拒む", r.returncode == 4
              and r.stdout.startswith(f"FRAME_CHANGED\t{a}\t") and text(a) == mid, r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--section", "完了条件", "--change-frame", "--body-file", "-", stdin="別の条件\n")
        check("--change-frame を付ければ書き込む", r.returncode == 0 and "別の条件" in text(a), r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--section", "やること")
        check("--section だけで --body-file が無ければ拒む（終了コード2）", r.returncode == 2, r.stdout + r.stderr)

        write(os.path.join(wt1, "work.txt"), "x\n")
        r = run_task(wt1, "edit", b, "--section", "やること", "--body-file", "-", stdin="### 1. z\n")
        check("作業のあとの初回の記入は WORK_BEFORE_PLAN（終了コード4）で拒み、書き込まない", r.returncode == 4
              and r.stdout.startswith(f"WORK_BEFORE_PLAN\t{b}\t") and "### 1. z" not in text(b)
              and beads.PLAN_KEY not in metadata(b), r.stdout + r.stderr)
        r = run_task(wt1, "edit", b, "--section", "やること", "--after-work", "--body-file", "-", stdin="### 1. z\n")
        check("--after-work なら書き込み、metadata に after-work を残す", r.returncode == 0
              and r.stdout.splitlines()[:2] == [f"EDITED\t{b}", f"PLAN_AFTER_WORK\t{b}\t作業の後に書いた"]
              and metadata(b).get(beads.PLAN_KEY) == "after-work", r.stdout + r.stderr + str(metadata(b)))

        r = run_task(wt1, "edit", a, "--section", "注意", "--body-file", "-", stdin="- 申し送り\n")
        check("作業のあとでも ## やること を変えない --section 注意 は拒まず、記録も変えない", r.returncode == 0
              and r.stdout.strip() == f"EDITED\t{a}" and "- 申し送り" in text(a)
              and metadata(a).get(beads.PLAN_KEY) == "first", r.stdout + r.stderr + str(metadata(a)))
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=text(a).replace("- 申し送り", "- 別の申し送り"))
        check("本文ごと渡しても ## やること が同じなら同じ", r.returncode == 0 and r.stdout.strip() == f"EDITED\t{a}"
              and "- 別の申し送り" in text(a) and metadata(a).get(beads.PLAN_KEY) == "first", r.stdout + r.stderr)


def test_edit_deps() -> None:
    say("edit --add-deps・--remove-deps: Beads の依存を後から変える")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp)
        check("Beads は一時ディレクトリの中にあり、環境変数で本物へ向いていない",
              os.path.realpath(main_path).startswith(os.path.realpath(tmp)) and not {"BEADS_DIR", "BEADS_DB"} & set(env()),
              main_path)
        a, b, c, d = (new(main_path, "x") for _ in range(4))

        def deps(task_id: str) -> list[str]:
            issue = beads.show(main_path, beads.to_bd_id(task_id))
            return sorted(beads.to_task_id(x) for x in issue.dependencies) if issue is not None else []

        def all_deps() -> dict[str, list[str]]:
            return {beads.to_task_id(i.bd_id): sorted(beads.to_task_id(x) for x in i.dependencies)
                    for i in beads.list_issues(main_path)}

        def ready(task_id: str) -> str:
            return rows(run_task(wt1, "status").stdout).get(task_id, [""] * 8)[5]

        r = run_task(wt1, "edit", b, "--add-deps", a)
        check("--add-deps で bd の依存が入り、status が BLOCKED になる", r.returncode == 0
              and r.stdout.startswith(f"EDITED\t{b}") and deps(b) == [a] and ready(b) == f"BLOCKED:{a}",
              r.stdout + r.stderr)
        r = run_task(wt1, "edit", b, "--add-deps", a)
        check("すでにある依存の追加は通る", r.returncode == 0 and deps(b) == [a], r.stdout + r.stderr)
        r = run_task(wt1, "edit", c, "--add-deps", f"{a},{b}")
        check("2件を一度に足せる", r.returncode == 0 and deps(c) == sorted([a, b]), r.stdout + r.stderr)
        r = run_task(wt1, "edit", b, "--remove-deps", a)
        check("--remove-deps で外れ、READY に戻る", r.returncode == 0 and deps(b) == [] and ready(b) == "READY",
              r.stdout + r.stderr)
        run_task(wt1, "edit", d, "--add-deps", c)

        snapshot = all_deps()
        check("一覧から読んだ依存は show と同じ", snapshot == {t: deps(t) for t in (a, b, c, d)}
              and snapshot[d] == [c], repr(snapshot))
        for label, args in (
            ("自分自身", (a, "--add-deps", a)),
            ("Beads に無い ID", (a, "--add-deps", "T-999")),
            ("形の違う ID", (a, "--add-deps", "xyz")),
            ("依存にない ID の削除", (a, "--remove-deps", b)),
            ("追加と削除に同じ ID", (a, "--add-deps", b, "--remove-deps", b)),
            ("直接の循環（C は B に依存済み）", (b, "--add-deps", c)),
            ("間接の循環（D→C→A に A→D）", (a, "--add-deps", d)),
            ("追加の一部が循環", (a, "--add-deps", f"{b},{d}")),
        ):
            r = run_task(wt1, "edit", *args)
            check(f"{label}は終了コード2で拒み、何も書かない", r.returncode == 2 and "usage:" in r.stderr
                  and all_deps() == snapshot, r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--add-deps", d)
        check("循環の文言に道が出る", f"{a}→{d}→{c}→{a}" in r.stderr, r.stderr)

        r = run_task(wt1, "edit", a)
        check("直すものが無ければ終了コード2", r.returncode == 2, r.stdout + r.stderr)
        r = run_task(wt1, "edit", b, "--add-deps", a, "--summary", "改題")
        check("ほかの引数と一緒に渡せば両方が反映される", r.returncode == 0 and deps(b) == [a]
              and "改題" in run_task(wt1, "show", b).stdout, r.stdout + r.stderr)

        bd(main_path, "create", "--id", "proj-8", "--title", "キーの課題", "--force", "--silent")
        r = run_task(wt1, "edit", "PROJ-8", "--add-deps", a)
        check("キーの課題への edit も依存を足せる（ID の形は new と同じ）", r.returncode == 0 and deps("PROJ-8") == [a],
              r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--add-deps", "PROJ-8")
        check("キーの課題を通る循環も拒む", r.returncode == 2 and "循環" in r.stderr, r.stdout + r.stderr)


def test_plan_check_unrecorded() -> None:
    say("plan-check: edit が印を残さない書き方は PLAN_NOT_FIRST unrecorded")
    planned = BODY.replace("## やること\n", "## やること\n### 1. 書く\n")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        d = new_unplanned(main_path, "claim の前に書く")
        e = new_unplanned(main_path, "持ち主でない作業ツリーから書く")

        def metadata(task_id: str) -> dict:
            issue = beads.show(main_path, beads.to_bd_id(task_id))
            raw = issue.raw.get("metadata") if issue is not None else None
            return raw if isinstance(raw, dict) else {}

        run_task(wt1, "edit", d, "--body-file", "-", stdin=planned)
        run_task(wt1, "claim", d)
        r = run_task(wt1, "plan-check", d)
        check("claim の前に書くと印が無く PLAN_NOT_FIRST unrecorded", r.returncode == 0
              and r.stdout.strip() == f"PLAN_NOT_FIRST\t{d}\tunrecorded" and beads.PLAN_KEY not in metadata(d),
              r.stdout + r.stderr + str(metadata(d)))

        run_task(wt2, "claim", e)
        run_task(wt1, "edit", e, "--body-file", "-", stdin=planned)
        r = run_task(wt2, "plan-check", e)
        check("持ち主でない作業ツリーから書くと PLAN_NOT_FIRST unrecorded", r.returncode == 0
              and r.stdout.strip() == f"PLAN_NOT_FIRST\t{e}\tunrecorded" and beads.PLAN_KEY not in metadata(e),
              r.stdout + r.stderr + str(metadata(e)))


def plan_body(*paths: str, work_repo: str | None = None) -> str:
    listed = "".join(f"- `{p}`\n" for p in paths)
    repo = f"### 作業先\n- `{work_repo}`\n\n" if work_repo else ""
    return BODY.replace("## やること\n", f"## やること\n### 1. 書く\nx\n\n{repo}### 名指すファイル\n{listed}\n")


def test_registered_plan() -> None:
    say("new・claim・plan-check: 登録時の計画が名指すファイルが着手時までに変わったかを知らせる")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        write(os.path.join(main_path, "src", "a.txt"), "a\n")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "src を足す")
        head = git(main_path, "rev-parse", "main").stdout.strip()
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        git(work, "init", "-q", "-b", "main")
        git(work, "config", "user.email", "test@example.com")
        git(work, "config", "user.name", "test")
        write(os.path.join(work, "lib", "y.txt"), "y\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "init")
        work_head = git(work, "rev-parse", "main").stdout.strip()

        def metadata(task_id: str) -> dict:
            issue = beads.show(main_path, beads.to_bd_id(task_id))
            raw = issue.raw.get("metadata") if issue is not None else None
            return raw if isinstance(raw, dict) else {}

        r = run_task(main_path, "new", "--summary", "無いファイル", "--difficulty", "sonnet", "--loopable", "Y",
                     "--body-file", "-", stdin=plan_body("nothing.txt"))
        check("木に無いパスを名指すと終了コード2", r.returncode == 2 and "nothing.txt" in r.stderr, r.stdout + r.stderr)
        same = new(main_path, "変わらない", body=plan_body("shared.txt"))
        changed = new(main_path, "変わる", body=plan_body("src/"))
        unplanned = new_unplanned(main_path, "書かない")
        remote = new(main_path, "作業先で変わる", body=plan_body("lib/y.txt", work_repo=work))
        shown = run_task(main_path, "show", same).stdout
        check("計画つきの登録は SHA を metadata に控え、## やること を notes に入れる",
              metadata(same).get(beads.PLAN_BASE_KEY) == head and "### 名指すファイル" in shown
              and beads.PLAN_BASE_KEY not in metadata(unplanned), shown + str(metadata(same)))
        check("作業先のある登録は作業先の主ブランチの SHA を控える",
              metadata(remote).get(beads.PLAN_BASE_KEY) == work_head, str(metadata(remote)))
        write(os.path.join(main_path, "src", "new.txt"), "n\n")
        git(main_path, "add", "-A")
        git(main_path, "commit", "-q", "-m", "主ブランチが進む")
        tip = git(main_path, "rev-parse", "main").stdout.strip()
        write(os.path.join(work, "lib", "y.txt"), "y2\n")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "作業先が進む")
        work_tip = git(work, "rev-parse", "main").stdout.strip()

        run_task(wt1, "claim", same)
        r = run_task(wt1, "plan-check", same)
        check("名指したファイルが変わっていなければ PLAN_REGISTERED", r.returncode == 0
              and r.stdout.strip() == f"PLAN_REGISTERED\t{same}\t{head}"
              and metadata(same).get(beads.PLAN_TIP_KEY) == tip, r.stdout + r.stderr + str(metadata(same)))

        run_task(wt2, "claim", changed)
        r = run_task(wt2, "plan-check", changed)
        check("名指したファイルが変わっていれば PLAN_STALE と変わったファイル", r.returncode == 0
              and r.stdout.strip() == f"PLAN_STALE\t{changed}\tsrc/new.txt", r.stdout + r.stderr)
        r = run_task(wt2, "edit", changed, "--body-file", "-", stdin=plan_body("src/", "shared.txt"))
        r2 = run_task(wt2, "plan-check", changed)
        check("PLAN_STALE のあとに書き直すと PLAN_FIRST", r.returncode == 0
              and r2.stdout.strip() == f"PLAN_FIRST\t{changed}", r.stdout + r.stderr + r2.stdout)

        run_task(wt1, "release", same)
        git(wt1, "merge", "-q", "--ff-only", "main")
        run_task(wt1, "claim", unplanned)
        r = run_task(wt1, "plan-check", unplanned)
        check("--hold で登録して todo に戻したものは PLAN_NOT_FIRST missing", r.returncode == 0
              and r.stdout.strip() == f"PLAN_NOT_FIRST\t{unplanned}\tmissing", r.stdout + r.stderr)
        run_task(wt1, "release", unplanned)

        run_task(wt1, "claim", remote)
        r = run_task(wt1, "plan-check", remote)
        check("作業先で名指したファイルが変わっていれば PLAN_STALE で、作業先の先端を控える", r.returncode == 0
              and r.stdout.strip() == f"PLAN_STALE\t{remote}\tlib/y.txt"
              and metadata(remote).get(beads.PLAN_TIP_KEY) == work_tip, r.stdout + r.stderr + str(metadata(remote)))


def test_verify_stamp() -> None:
    say("verify・verify-check: Beads 方式でも同じ形で控えて照らす")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, verify="`echo 3 pass`")
        r = run_task(wt1, "verify")
        check("通れば VERIFIED", r.returncode == 0 and r.stdout.startswith("VERIFIED\t"), r.stdout + r.stderr)
        tree = r.stdout.split("\t")[1] if r.stdout.startswith("VERIFIED\t") else "?"
        r = run_task(wt1, "verify-check")
        check("同じ中身なら VERIFIED_SAME", r.stdout.strip() == f"VERIFIED_SAME\t{tree}", r.stdout + r.stderr)
        write(os.path.join(wt1, "shared.txt"), "line1\nline2\n")
        r = run_task(wt1, "verify-check")
        check("変えれば NOT_VERIFIED content", r.stdout.strip() == "NOT_VERIFIED\tcontent", r.stdout + r.stderr)
        write(os.path.join(main_path, "other.txt"), "main\n")
        git(main_path, "add", "other.txt")
        git(main_path, "commit", "-q", "-m", "mainだけの変更")
        r = run_task(wt1, "verify-check")
        check("main が進めば NOT_VERIFIED base", r.stdout.strip() == "NOT_VERIFIED\tbase", r.stdout + r.stderr)
        r = run_task(wt1, "verify")
        check("main を取り込んでから打つ", r.returncode == 0 and r.stdout.startswith("FOLDED\t")
              and "\nVERIFIED\t" in r.stdout and os.path.exists(os.path.join(wt1, "other.txt")), r.stdout + r.stderr)


def test_verify_refuses_unplanned_work() -> None:
    say("verify: 着手中のタスクの ## やること が空のまま作業が始まっていたら検証を打たない")
    planned = BODY.replace("## やること\n", "## やること\n### 1. 書く\n")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp, verify="`echo verified`")
        a = new_unplanned(main_path, "関門")
        b = new_unplanned(main_path, "done の後")
        run_task(wt1, "claim", a)
        r = run_task(wt1, "verify")
        check("作業が始まっていなければ空でも打つ", r.returncode == 0 and r.stdout.startswith("VERIFIED\t"),
              r.stdout + r.stderr)
        write(os.path.join(wt1, "work.txt"), "x\n")
        r = run_task(wt1, "verify")
        r2 = run_task(wt1, "verify-check")
        check("空のまま作業があれば PLAN_MISSING（終了コード10）で、検証コマンドを打たず控えを消す", r.returncode == 10
              and r.stdout.startswith(f"PLAN_MISSING\t{a}\t") and "verified" not in r.stdout
              and r2.stdout.strip() == "NOT_VERIFIED\tnone", r.stdout + r2.stdout + r.stderr)
        run_task(wt1, "edit", a, "--after-work", "--body-file", "-", stdin=planned)
        r = run_task(wt1, "verify")
        check("書けば打つ", r.returncode == 0 and r.stdout.startswith("VERIFIED\t"), r.stdout + r.stderr)

        run_task(wt2, "claim", b)
        work_and_done(wt2, b)
        r = run_task(wt2, "verify")
        check("done の後は空でも打つ", r.returncode == 0 and r.stdout.startswith("VERIFIED\t"), r.stdout + r.stderr)


def test_cycle_done_ship_and_dropped() -> None:
    say("1サイクル（claim → edit → done → ship）と見送り")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp, branch="既定")
        a = new_unplanned(main_path, "前段")
        b = new(main_path, "後段", "--deps", a)
        c = new(main_path, "見送る")
        d = new(main_path, "見送りに依存", "--deps", c)

        r = run_task(wt1, "claim", a)
        check("既定の枝の設定なら feature/T-xxx を切る", r.stdout.strip().endswith(f"branch=feature/{a}"), r.stdout)
        shown = run_task(wt1, "show", a).stdout
        body = shown.split("---\n", 2)[2].replace("## やること\n", "## やること\n\n### 1. 書く\n")
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=body)
        check("edit が本文を受ける", r.returncode == 0 and r.stdout.startswith("EDITED"), r.stdout + r.stderr)
        issue = beads.show(main_path, beads.to_bd_id(a))
        check("## やること は notes へ", issue is not None and issue.raw.get("notes") == "### 1. 書く", str(issue and issue.raw))
        shown = run_task(wt1, "show", a).stdout
        heads = [l for l in shown.split("\n") if l.startswith("## ")]
        check("show は枠の7節をこの順に出す", heads == list(taskfile.SECTION_HEADINGS), shown)
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=body.replace("## 参考情報\n", ""))
        check("edit は枠の欠けた本文を拒む（終了コード2）", r.returncode == 2, r.stdout + r.stderr)
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=body + "\n## 結果\n\nx\n")
        check("edit は ## 結果 を拒む（終了コード2）", r.returncode == 2, r.stdout + r.stderr)

        work_and_done(wt1, a)
        r = run_task(wt2, "status")
        check("done のあとも ship までは印が残り、後段は BLOCKED", rows(r.stdout).get(b, [""] * 8)[5] == f"BLOCKED:{a}"
              and rows(r.stdout).get(a, [""] * 8)[5] == "CLAIMED", r.stdout)
        r = run_task(wt1, "ship")
        first = r.stdout.splitlines()[0] if r.stdout else ""
        check("ship は SHIPPED で閉じた ID を released に出す", r.returncode == 0 and first.startswith("SHIPPED")
              and f"released={a}" in first, r.stdout + r.stderr)
        check("claim した枝（wt1）へ戻って feature 枝を消す", "branch=wt1" in first
              and git(wt1, "branch", "--list", f"feature/{a}").stdout.strip() == "", first)
        check("ship のあとにバックアップを取る", any(l.startswith("BACKUP\tOK") for l in r.stdout.splitlines()), r.stdout)
        r = run_task(wt2, "status", "--all")
        t = rows(r.stdout)
        check("閉じたものは done、後段は READY", t.get(a, [""] * 8)[1] == "done" and t.get(b, [""] * 8)[5] == "READY", r.stdout)
        shown = run_task(wt2, "show", a).stdout
        check("show の末尾に ## 結果（comment から）", shown.rstrip().endswith("- 振り返り: 兆候なし")
              and "status: done" in shown, shown)

        r = run_task(wt2, "claim", c)
        work_and_done(wt2, c, dropped=True)
        r = run_task(wt2, "ship")
        r = run_task(wt1, "status", "--all")
        t = rows(r.stdout)
        check("dropped は closed ＋ label cancelled で、依存を解決する", t.get(c, [""] * 8)[1] == "dropped"
              and t.get(d, [""] * 8)[5] == "READY", r.stdout)
        issue = beads.show(main_path, beads.to_bd_id(c))
        check("閉じたあと ship: の印は残らない", issue is not None and issue.status == "closed"
              and "cancelled" in issue.labels and not any(l.startswith("ship:") for l in issue.labels),
              str(issue and issue.labels))

        # retrospect の材料（Beads の comment と版）
        mat = subprocess.run([sys.executable, MATERIAL_PY, ".", a], cwd=main_path, capture_output=True, text=True, env=env())
        check("material.py は Beads の本文と版の差を出す", f"出典\tBeads {beads.to_bd_id(a)}" in mat.stdout
              and "+### 1. 書く" in mat.stdout, mat.stdout + mat.stderr)


def test_flow_records_and_metrics() -> None:
    say("flow・metrics: Beads 方式でも同じ記録が台帳に残り、書けなくても元の結果は変わらない")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp, verify="`echo ok`")
        a = new(main_path, "流れ")
        run_task(wt1, "claim", a)
        run_task(wt1, "release", a)
        run_task(wt1, "claim", a)
        r = run_task(wt1, "verify")
        check("verify は VERIFIED", r.returncode == 0 and r.stdout.startswith("VERIFIED\t"), r.stdout + r.stderr)
        work_and_done(wt1, a)
        r = run_task(wt1, "ship")
        check("ship は SHIPPED", r.returncode == 0 and r.stdout.startswith("SHIPPED"), r.stdout + r.stderr)

        d = ledger.flow_dir(ledger.ledger_root(cwd=wt1))
        recs: list[dict] = []
        for name in sorted(os.listdir(d)):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                recs += [json.loads(line) for line in f if line.strip()]
        steps = [(e["event"], e["task"], e.get("result")) for e in recs]
        check(
            "claim・release・claim・verify・done・ship が1行ずつ残る",
            steps
            == [
                ("claim", a, None),
                ("release", a, None),
                ("claim", a, None),
                ("verify", a, "VERIFIED"),
                ("done", a, None),
                ("ship", a, "SHIPPED"),
            ],
            repr(steps),
        )
        check("difficulty と done の振り返りが入る", {e["difficulty"] for e in recs} == {"sonnet"}
              and next(e for e in recs if e["event"] == "done")["reflection"] == "none", repr(recs))
        r = run_task(wt1, "metrics")
        table = {l.split("\t")[0]: l.split("\t")[1:] for l in r.stdout.splitlines()}
        say("  --- tw metrics の出力 ---")
        for line in r.stdout.splitlines():
            say(f"  | {line}")
        check("metrics が数を出す", r.returncode == 0 and table.get("shipped") == ["1", "0"]
              and table.get("verify_per_task") == ["1.0", "-"] and table.get("reclaim") == ["1", "0"]
              and table.get("reflection_none_ratio") == ["100% (1/1)", "-"], r.stdout + r.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _wt2 = make_repo(tmp)
        a = new(main_path, "書けない")
        write(ledger.flow_dir(ledger.ledger_root(cwd=wt1)), "ファイルがディレクトリの場所を塞ぐ\n")
        r = run_task(wt1, "claim", a)
        check("記録を書けなくても claim の出力と終了コードは変わらず、標準エラーに1行だけ出る",
              r.returncode == 0 and r.stdout.startswith(f"CLAIMED\t{a}\t") and r.stderr.strip().startswith("flow:")
              and len(r.stderr.strip().splitlines()) == 1, r.stdout + r.stderr)
        r = run_task(wt1, "metrics")
        check("記録が無ければ EMPTY", r.returncode == 0 and r.stdout.strip() == "EMPTY", r.stdout + r.stderr)


def test_stale_markers() -> None:
    say("取り残しの判定（gone・shipped・no-owner）")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        a = new(main_path, "消える作業ツリー")
        b = new(main_path, "送ったのに閉じていない")
        c = new(main_path, "持ち主なし")
        run_task(wt2, "claim", a)
        git(main_path, "worktree", "remove", "--force", wt2)
        run_task(wt1, "claim", b)
        work_and_done(wt1, b)
        git(main_path, "merge", "--ff-only", "-q", "wt1")
        bd(main_path, "update", beads.to_bd_id(c), "--status", "in_progress")
        r = run_task(main_path, "status")
        stale = tail_line(r.stdout, "stale")
        check("STALE:gone・STALE:shipped・STALE:no-owner", f"{a}:STALE:gone(wt2)" in stale
              and f"{b}:STALE:shipped(wt1)" in stale and f"{c}:STALE:no-owner" in stale, r.stdout)


def test_retrospect_due() -> None:
    say("status: 横断の振り返りの時期に retrospect_due の行を出す")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp)
        r = run_task(wt1, "status")
        check("記録も flow/ も無い初回は出さない", r.returncode == 0 and tail_line(r.stdout, "retrospect_due") == "",
              r.stdout + r.stderr)

        at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")
        write(os.path.join(ledger.flow_dir(ledger.ledger_root(cwd=wt1)), "2000-01.jsonl"),
              json.dumps({"t": at, "event": "claim", "task": "T-001", "difficulty": "haiku"}) + "\n")
        r = run_task(wt1, "status")
        check("記録が無く flow/ の最古が8日前なら -\\t8d で出る", tail_line(r.stdout, "retrospect_due") == "retrospect_due\t-\t8d",
              r.stdout)

        write(os.path.join(wt1, "docs", "history", "retrospect.md"),
              f"# 横断の振り返りの記録\n\n## {datetime.now().date().isoformat()}（x〜y）\n")
        r = run_task(wt1, "status")
        check("今日の記録を書くと出なくなる", tail_line(r.stdout, "retrospect_due") == "", r.stdout)
        git(wt1, "add", "-A")
        git(wt1, "commit", "-q", "-m", "記録")
        git(main_path, "merge", "--ff-only", "-q", "wt1")
        r = run_task(wt2, "status")
        check("主ブランチへ入れれば、ほかの作業ツリーでも出ない", tail_line(r.stdout, "retrospect_due") == "", r.stdout)


def test_triage_and_adopt() -> None:
    say("振り分け前の課題（トラッカーから来たもの）と adopt")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp)
        # `bd` に採番させると数字だけの hash（`t-456`）になりうるので、数字でない ID を決めて作る。
        raw = bd(main_path, "create", "--id", "t-x1a", "--title", "外から来た", "-d", "本文", "--silent").stdout.strip()
        r = run_task(wt1, "status")
        check("labels の無い課題は triage に出て READY にならない", f"triage\t1\t{raw}" in r.stdout
              and "ready\t0" in r.stdout and rows(r.stdout).get(raw, [""] * 8)[5] == "TRIAGE", r.stdout)
        r = run_task(wt1, "claim", raw)
        check("振り分け前は claim できない（NOT_READY TRIAGE）", r.returncode == 4 and "TRIAGE" in r.stdout, r.stdout)
        before = bd(main_path, "show", raw, "--json").stdout
        r = run_task(wt1, "adopt", raw, "--difficulty", "haiku", "--loopable", "N", "--body-file", "-", stdin=BODY)
        check("空の ## やること の adopt は終了コード2で、課題を変えない", r.returncode == 2
              and bd(main_path, "show", raw, "--json").stdout == before, r.stdout + r.stderr)
        r = run_task(wt1, "adopt", raw, "--difficulty", "haiku", "--loopable", "N", "--body-file", "-",
                     stdin=PLANNED_BODY.replace("### 1. 書く", "### 書く"))
        check("段の無い ## やること の adopt は終了コード2と理由で、課題を変えない", r.returncode == 2
              and "### 1." in r.stderr and bd(main_path, "show", raw, "--json").stdout == before, r.stdout + r.stderr)
        r = run_task(wt1, "adopt", raw, "--difficulty", "haiku", "--loopable", "N", "--body-file", "-", stdin=PLANNED_BODY)
        check("adopt が番号を振る", r.returncode == 0 and r.stdout.startswith(f"ADOPTED\t{raw}\tT-001"), r.stdout + r.stderr)
        adopted = beads.show(main_path, beads.to_bd_id("T-001"))
        metadata = adopted.raw.get("metadata") if adopted is not None else None
        check("adopt は ## やること を notes に入れ、主ブランチの SHA を控える", adopted is not None
              and "### 名指すファイル" in str(adopted.raw.get("notes"))
              and isinstance(metadata, dict)
              and metadata.get(beads.PLAN_BASE_KEY) == git(main_path, "rev-parse", "main").stdout.strip(),
              str(adopted and adopted.raw))
        r = run_task(wt1, "status")
        check("adopt したものは READY", rows(r.stdout).get("T-001", [""] * 8)[5] == "READY" and "triage\t0" in r.stdout, r.stdout)


class FakeGitHub:
    """偽の GitHub。REST の Issue（本物の `bd github push`・`pull` が `GITHUB_API_URL` で叩く）と、
    Project の GraphQL（偽の `gh api graphql` が転送する）を、1つの HTTP サーバの中の状態で受ける。"""

    def __init__(self) -> None:
        self.issues: dict[int, dict] = {}
        self.items: dict[str, dict] = {}  # 項目 ID → {"url", "status"}
        self.option_prefix = "O-"
        self.graphql: list[str] = []  # 受けた GraphQL の問い合わせの種類（最初の語）
        self.clock_offset = 0  # 秒。GitHub 側の編集を後の時刻にする
        self.graphql_down = False  # 真のあいだ GraphQL（Project の Status 欄）だけを落とす
        self.lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401
                pass

            def _reply(self, code: int, obj) -> None:
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode() or "null") if n else None
                with fake.lock:
                    code, obj = fake.route(self.command, self.path, body)
                self._reply(code, obj)

            do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + self.clock_offset))

    def issue_json(self, i: dict) -> dict:
        n = i["number"]
        return {
            "id": 1000 + n, "node_id": f"I_{n}", "number": n, "title": i["title"], "body": i["body"],
            "state": i["state"], "labels": [{"name": l} for l in i["labels"]], "assignees": [], "assignee": None,
            "created_at": i["created_at"], "updated_at": i["updated_at"], "closed_at": None,
            "html_url": f"https://github.com/o/r/issues/{n}", "url": f"{self.url}/repos/o/r/issues/{n}",
            "user": {"login": "someone"},
        }

    def edit(self, number: int, **fields) -> None:
        """人が GitHub で Issue を直した（題・本文・state・labels）。"""
        with self.lock:
            self.issues[number].update(fields)
            self.issues[number]["updated_at"] = self.now()

    def open_issue(self, title: str, labels: list[str]) -> int:
        with self.lock:
            return self._create({"title": title, "body": "外で立てた", "labels": labels})["number"]

    def _create(self, body: dict) -> dict:
        n = len(self.issues) + 1
        issue = {"number": n, "title": body.get("title", ""), "body": body.get("body") or "", "state": "open",
                 "labels": list(body.get("labels") or []), "created_at": self.now(), "updated_at": self.now()}
        self.issues[n] = issue
        return issue

    def status_of(self, number: int) -> str | None:
        url = f"https://github.com/o/r/issues/{number}"
        return next((i["status"] for i in self.items.values() if i["url"] == url), None)

    def route(self, method: str, path: str, body):
        u = urlparse(path)
        m = re.fullmatch(r"/repos/o/r/issues/(\d+)", u.path)
        if u.path == "/graphql":
            return 200, self.answer_graphql(body["query"], body.get("variables") or {})
        if method == "POST" and u.path == "/repos/o/r/issues":
            return 201, self.issue_json(self._create(body))
        if m and method == "PATCH":
            issue = self.issues[int(m.group(1))]
            for k in ("title", "body", "state", "labels"):
                if k in body:
                    issue[k] = body[k]
            issue["updated_at"] = self.now()
            return 200, self.issue_json(issue)
        if m and method == "GET":
            issue = self.issues.get(int(m.group(1)))
            return (200, self.issue_json(issue)) if issue else (404, {"message": "Not Found"})
        if u.path == "/repos/o/r/issues" and method == "GET":
            q = parse_qs(u.query)
            state, since = (q.get("state") or ["open"])[0], (q.get("since") or [""])[0]
            found = [i for i in self.issues.values() if (state == "all" or i["state"] == state)
                     and (not since or i["updated_at"] >= since)]
            return 200, [self.issue_json(i) for i in found]
        return 404, {"message": f"fake: {method} {u.path}"}

    def answer_graphql(self, query: str, v: dict) -> dict:
        if self.graphql_down:
            return {"errors": [{"message": "fake: GraphQL を落とす"}]}
        names = ["Pending", "Todo", "In progress", "Done", "Cancel"]
        if "repositoryOwner" in query:
            self.graphql.append("project")
            options = [{"id": self.option_prefix + n, "name": n} for n in names]
            return {"data": {"repositoryOwner": {"projectV2": {"id": "PID", "field": {"id": "FID", "options": options}}}}}
        if "projectItems" in query:
            self.graphql.append("issue")
            url = f"https://github.com/{v['owner']}/{v['repo']}/issues/{v['number']}"
            nodes = [{"id": k, "project": {"id": "PID"}} for k, i in self.items.items() if i["url"] == url]
            return {"data": {"repository": {"issue": {"id": f"I_{v['number']}", "projectItems": {"nodes": nodes}}}}}
        if "addProjectV2ItemById" in query:
            self.graphql.append("add")
            n = v["content"].split("_", 1)[1]
            item_id = f"PVTI_{n}"
            self.items[item_id] = {"url": f"https://github.com/o/r/issues/{n}", "status": None}
            return {"data": {"addProjectV2ItemById": {"item": {"id": item_id}}}}
        if "updateProjectV2ItemFieldValue" in query:
            self.graphql.append("set")
            option, item = v["option"], self.items.get(v["item"])
            if item is None or not option.startswith(self.option_prefix):
                return {"errors": [{"message": "Could not resolve to a node"}]}
            item["status"] = option[len(self.option_prefix):]
            return {"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": v["item"]}}}}
        if "items(first" in query:
            self.graphql.append("items")
            nodes = [{"id": k, "content": {"url": i["url"]},
                      "fieldValueByName": {"name": i["status"]} if i["status"] else None} for k, i in self.items.items()]
            return {"data": {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}
        return {"errors": [{"message": "fake: 知らない問い合わせ"}]}


def _fake_bin(tmp: str) -> str:
    """偽の `bd`（jira の sync だけ受けて `<FAKE_BD_LOG>.jira` の課題を作り、残りは本物へ）と、
    偽の `gh`（呼ばれ方を記録し、`api` は偽の GitHub へ転送）。

    偽の `bd` は、`<FAKE_BD_LOG>.before-pull`（`{"cwd", "argv"}` の JSON）があれば `github pull` の前に
    1回だけそれを打ち、`<FAKE_BD_LOG>.fail-update` があるあいだは assignee か metadata を書く `update` を、
    `<FAKE_BD_LOG>.fail-push` があるあいだは `github push` を落とす。"""
    bin_dir = os.path.join(tmp, "bin")
    real_bd = shutil.which("bd") or "bd"
    write(os.path.join(bin_dir, "bd"), f"""#!{sys.executable}
import json, os, subprocess, sys
REAL = {real_bd!r}
args = sys.argv[1:]
core = [a for i, a in enumerate(args) if a != "--actor" and (i == 0 or args[i - 1] != "--actor")]
before_pull = os.environ["FAKE_BD_LOG"] + ".before-pull"
if core[:2] == ["github", "pull"] and os.path.exists(before_pull):
    with open(before_pull) as f:
        hook = json.load(f)
    os.remove(before_pull)
    subprocess.run(hook["argv"], cwd=hook["cwd"], capture_output=True)
if core[:1] == ["update"] and ("--assignee" in core or "--set-metadata" in core) \\
        and os.path.exists(os.environ["FAKE_BD_LOG"] + ".fail-update"):
    sys.stderr.write("fake bd: update を落とす\\n")
    sys.exit(1)
if core[:2] == ["github", "push"] and os.path.exists(os.environ["FAKE_BD_LOG"] + ".fail-push"):
    sys.stderr.write("fake bd: github push を落とす\\n")
    sys.exit(1)
if core[:1] == ["jira"] and "sync" in core:
    with open(os.environ["FAKE_BD_LOG"], "a") as f:
        f.write(" ".join(core) + "\\n")
    if os.environ.get("FAKE_BD_SYNC_FAIL"):
        sys.exit(1)
    pending = os.environ["FAKE_BD_LOG"] + ".jira"
    if os.path.exists(pending):
        with open(pending) as f:
            for line in f.read().splitlines():
                bd_id, title, ref = line.split("\\t")
                subprocess.run([REAL, "create", "--id", bd_id, "--title", title, "--external-ref", ref, "--silent"],
                               check=True, capture_output=True)
        os.remove(pending)
    sys.exit(0)
os.execv(REAL, [REAL] + args)
""")
    write(os.path.join(bin_dir, "gh"), f"""#!{sys.executable}
import json, os, sys, urllib.request
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
server = os.environ["GITHUB_API_URL"]
def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(server + path, data=data, method=method, headers={{"Content-Type": "application/json"}})
    try:
        return json.load(urllib.request.urlopen(req, timeout=10))
    except OSError as e:
        sys.stderr.write(f"fake gh: {{e}}\\n")
        sys.exit(1)
if args[:2] == ["auth", "token"]:
    if os.environ.get("FAKE_GH_AUTH_FAIL"):
        sys.exit(1)
    print("fake-token")
elif args[:2] == ["api", "graphql"]:
    query, variables = "", {{}}
    for flag, kv in zip(args[2::2], args[3::2]):
        k, v = kv.split("=", 1)
        if k == "query":
            query = v
        else:
            variables[k] = int(v) if flag == "-F" else v
    print(json.dumps(call("POST", "/graphql", {{"query": query, "variables": variables}})))
elif args[:1] == ["api"]:
    path = "/" + [a for a in args[1:] if not a.startswith("--")][0]
    out = call("GET", path)
    print(json.dumps([out] if "--slurp" in args else out))
else:
    sys.stderr.write("fake gh: 知らない呼び出し " + " ".join(args) + "\\n")
    sys.exit(1)
""")
    for name in ("bd", "gh"):
        os.chmod(os.path.join(bin_dir, name), 0o755)
    return bin_dir


def _with_fakes(tmp: str, fake: FakeGitHub | None = None) -> dict[str, str]:
    env = dict(BASE_ENV)
    env["PATH"] = _fake_bin(tmp) + os.pathsep + env.get("PATH", "")
    env["FAKE_BD_LOG"] = os.path.join(tmp, "bd.log")
    env["FAKE_GH_LOG"] = os.path.join(tmp, "gh.log")
    env["GITHUB_API_URL"] = fake.url if fake else "http://127.0.0.1:9"
    env.pop("GITHUB_TOKEN", None)
    return env


def gh_calls() -> list[list[str]]:
    path = env()["FAKE_GH_LOG"]
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _github_repo(tmp: str, prefix: str) -> tuple[str, str]:
    """トラッカーが github の `(本体, 作業ツリー1)`。`prefix` が `t` なら切り替え前（送るだけ）。"""
    main_path, wt1, _ = make_repo(tmp, extra="- トラッカー: github\n- GitHub Project: `sinnlosses/1`\n", prefix=prefix)
    bd(main_path, "config", "set", "github.repository", "o/r")
    return main_path, wt1


@contextlib.contextmanager
def _github(prefix: str = beads.PREFIX_GITHUB) -> Iterator[tuple["FakeGitHub", str, str, str]]:
    """偽の GitHub へ向けた `(偽の GitHub, 一時ディレクトリ, 本体, 作業ツリー1)`。"""
    fake = FakeGitHub()
    with tempfile.TemporaryDirectory() as tmp:
        _local.env = _with_fakes(tmp, fake)
        try:
            main_path, wt1 = _github_repo(tmp, prefix)
            yield fake, tmp, main_path, wt1
        finally:
            fake.close()
            del _local.env


def _num(task_id: str) -> int:
    return int(beads.to_bd_id(task_id).split("-")[1])


def _claim_state(main_path: str, task_id: str) -> tuple[str, str | None, dict]:
    """`(Beads の status, assignee, metadata)`。"""
    issue = beads.show(main_path, beads.to_bd_id(task_id))
    raw = issue.raw.get("metadata") if issue is not None else None
    return (issue.status if issue else "", issue.assignee if issue else None, raw if isinstance(raw, dict) else {})


def test_tracker_github_push_only() -> None:
    say("トラッカー github・issue_prefix t（切り替え前: 送るだけ・Status 欄の控え）")
    with _github(beads.PREFIX_LOCAL) as (fake, _tmp, main_path, wt1):
        a = new(main_path, "GitHub へ")
        h = new(main_path, "待ち", "--hold")
        c = new(main_path, "見送る")
        check("ID は t の採番のまま", a == "T-001", a)
        check("new で Issue が立つ（1件ずつ送る。token は gh auth token から）", len(fake.issues) == 3
              and ["auth", "token"] in gh_calls(), repr(fake.issues))
        check("hold は deferred で書く", beads.show(main_path, beads.to_bd_id(h)).status == "deferred")
        check("Status 欄: open → Todo、hold → Pending", fake.status_of(_num(a)) == "Todo"
              and fake.status_of(_num(h)) == "Pending", repr(fake.items))
        check("取り込まない（GitHub の Issue を読みに行かない）",
              not any(c[:1] == ["api"] and c[1] != "graphql" for c in gh_calls()), repr(gh_calls()))
        check("Project・Status 欄の ID は1回だけ引いて控える", fake.graphql.count("project") == 1, repr(fake.graphql))

        before = len(gh_calls())
        shown = run_task(wt1, "show", a).stdout.split("---\n", 2)[2]
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=shown.replace("## 注意\n\nz", "## 注意\n\nzz"))
        calls = gh_calls()[before:]
        check("状態の変わらない edit は gh api・gh project を呼ばない", r.returncode == 0
              and "TRACKER\tOK\tgithub\tpushed=1\tstatus_changed=0" in r.stdout
              and not any(c[:1] in (["api"], ["project"]) for c in calls), r.stdout + repr(calls))
        check("edit は触った1件だけを送る", "zz" in fake.issues[_num(a)]["body"], repr(fake.issues[_num(a)]))

        before_calls, before_gql = len(gh_calls()), len(fake.graphql)
        r = run_task(wt1, "claim", a)
        calls = [c for c in gh_calls()[before_calls:] if c[:2] == ["api", "graphql"]]
        check("claim で In progress", fake.status_of(_num(a)) == "In progress", repr(fake.items))
        check("claim の GraphQL は数回（持ち主の照会・field-list・item-list なし）", 1 <= len(calls) <= 3
              and "project" not in fake.graphql[before_gql:] and "items" not in fake.graphql[before_gql:]
              and not any(c[:1] == ["project"] for c in gh_calls()), repr(fake.graphql[before_gql:]))
        work_and_done(wt1, a)
        run_task(wt1, "ship")
        run_task(wt1, "claim", c)
        work_and_done(wt1, c, dropped=True, name="c.txt")
        r = run_task(wt1, "ship")
        check("閉じたら Done、見送りは Cancel", fake.status_of(_num(a)) == "Done"
              and fake.status_of(_num(c)) == "Cancel", repr(fake.items) + r.stdout)
        check("ship の行に TRACKER OK", any(l.startswith("TRACKER\tOK\tgithub") for l in r.stdout.splitlines()), r.stdout)
        check("GitHub で閉じる", fake.issues[_num(a)]["state"] == "closed")

        before_gql = len(fake.graphql)
        r = run_task(main_path, "sync")
        check("変わりの無い sync は GraphQL を呼ばない", r.returncode == 0 and fake.graphql[before_gql:] == [],
              r.stdout + repr(fake.graphql[before_gql:]))


def test_tracker_github_push_only_recovery() -> None:
    say("トラッカー github・issue_prefix t: 古い選択肢の読み直しと、GitHub に届かないとき")
    with _github(beads.PREFIX_LOCAL) as (fake, _tmp, main_path, _wt1):
        h = new(main_path, "待ち", "--hold")
        fake.option_prefix = "O2-"  # 人が Status 欄の選択肢を作り直した
        before_gql = len(fake.graphql)
        r = run_task(main_path, "edit", h, "--status", "todo")
        check("控えた選択肢が古ければ1回だけ読み直して書く", fake.status_of(_num(h)) == "Todo"
              and fake.graphql[before_gql:].count("project") == 1 and "TRACKER\tOK" in r.stdout,
              r.stdout + repr(fake.graphql[before_gql:]))

        fake.close()
        r = run_task(main_path, "new", "--summary", "落ちても登録", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=PLANNED_BODY)
        check("トラッカーの失敗は new を止めない（TRACKER FAILED を足して終了コード0）", r.returncode == 0
              and r.stdout.startswith("CREATED") and "TRACKER\tFAILED\tgithub" in r.stdout, r.stdout)
        r = run_task(main_path, "sync")
        check("task sync の失敗は終了コード10", r.returncode == 10 and "TRACKER\tFAILED" in r.stdout, r.stdout)


def test_tracker_github_bidirectional() -> None:
    say("トラッカー github・issue_prefix gh（Issue 番号の ID・GitHub で立てた Issue の取り込みと adopt）")
    with _github() as (fake, _tmp, main_path, wt1):
        fake.open_issue("先にある PR 以外の Issue", [])
        a = new(main_path, "Issue を先に立てる")
        check("new は Issue を立てて GH-<番号> を返す", a == "GH-2" and beads.show(main_path, "gh-2") is not None, a)
        check("仮の ID は残らない", not any(i.bd_id.startswith("gh-new-") for i in beads.list_issues(main_path)))
        p = new(main_path, "登録時に計画を書く", body=plan_body("shared.txt"))
        issue = beads.show(main_path, beads.to_bd_id(p))
        raw = issue.raw if issue is not None else {}
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        check("付け替えたあとも登録時の計画（notes）と控え（metadata）が残る", p.startswith("GH-")
              and "### 名指すファイル" in str(raw.get("notes")) and bool(meta.get(beads.PLAN_BASE_KEY)), str(raw))
        b = new(main_path, "後段", "--deps", a)
        r = run_task(wt1, "status")
        check("status は GH-<n> の行と依存", rows(r.stdout).get(b, [""] * 8)[5] == f"BLOCKED:{a}", r.stdout)
        check("Status 欄も書く", fake.status_of(2) == "Todo", repr(fake.items))

        r = run_task(main_path, "sync")
        check("sync が GitHub で立てた Issue を取り込み、番号の ID へ付け替えて振り分け前にする", r.returncode == 0
              and "triage\t1\tGH-1" in run_task(main_path, "status").stdout, r.stdout)
        r = run_task(main_path, "adopt", "GH-1", "--difficulty", "haiku", "--loopable", "N", "--body-file", "-",
                     stdin=PLANNED_BODY)
        check("adopt は番号を変えない", r.stdout.startswith("ADOPTED\tGH-1\tGH-1"), r.stdout + r.stderr)


def test_tracker_github_pull_round_trip() -> None:
    say("トラッカー github: 着手中の課題へ GitHub での変更を取り込み、両側で変えたら Beads が勝つ")
    with _github() as (fake, _tmp, main_path, wt1):
        a = new(main_path, "着手してから GitHub で直される")
        n, bd_id = _num(a), beads.to_bd_id(a)
        r = run_task(wt1, "claim", a)
        check("claim", r.returncode == 0 and r.stdout.startswith("CLAIMED"), r.stdout + r.stderr)
        fake.edit(n, body="GitHub で直した本文")
        r = run_task(main_path, "sync")
        issue = beads.show(main_path, bd_id)
        check("取り込みで GitHub の本文が入り、錠の持ち主（assignee）は戻る", issue is not None
              and "GitHub で直した本文" in str(issue.raw.get("description"))
              and issue.assignee == "wt1" and issue.status == "in_progress", r.stdout + str(issue and issue.raw))

        fake.edit(n, body="GitHub で2回目に直した本文")
        r = run_task(main_path, "sync")
        issue = beads.show(main_path, bd_id)
        check("assignee を戻したあとの GitHub での変更も次の取り込みで入る（送り返して消さない）", issue is not None
              and "2回目" in str(issue.raw.get("description")) and "2回目" in fake.issues[n]["body"]
              and "CONFLICT" not in r.stdout, r.stdout + str(issue and issue.raw.get("description")))

        time.sleep(1.1)
        bd(main_path, "update", bd_id, "--title", "Beads で直した題")
        fake.clock_offset = 60
        fake.edit(n, body="GitHub でも直した")
        r = run_task(main_path, "sync")
        check("両側で変えたら CONFLICT の行を出し、Beads が勝つ", f"TRACKER\tCONFLICT\t{a}" in r.stdout
              and fake.issues[n]["title"] == "Beads で直した題", r.stdout + repr(fake.issues[n]))


def test_tracker_github_closed_and_hold() -> None:
    say("トラッカー github: GitHub で閉じた・開き直した課題と、hold の課題の取り込み")
    with _github() as (fake, _tmp, main_path, _wt1):
        c = new(main_path, "GitHub で閉じられる")
        run_task(main_path, "sync")  # 最初の取り込みは開いた Issue しか見ない
        fake.edit(_num(c), state="closed")
        r = run_task(main_path, "sync")
        t = rows(run_task(main_path, "status", "--all").stdout)
        check("ship の印の無い課題が GitHub で閉じたら見送り（cancelled）と CLOSED の行", f"TRACKER\tCLOSED\t{c}" in r.stdout
              and t.get(c, [""] * 8)[1] == "dropped", r.stdout)
        fake.edit(_num(c), state="open")
        run_task(main_path, "sync")
        issue = beads.show(main_path, beads.to_bd_id(c))
        check("開き直したら cancelled を外す", issue is not None and issue.status == "open"
              and "cancelled" not in issue.labels, str(issue and issue.labels))

        h = new(main_path, "待ち", "--hold")
        fake.edit(_num(h), body="GitHub で本文だけ直す")
        run_task(main_path, "sync")
        check("hold（deferred）は GitHub での編集を往復しても hold のまま",
              rows(run_task(main_path, "status").stdout).get(h, [""] * 8)[1] == "hold")


def test_tracker_github_provisional_id() -> None:
    say("トラッカー github: Issue を立てられなかった new は仮の ID のまま、sync が送り直して付け替える")
    with _github() as (fake, _tmp, main_path, _wt1):
        fake.close()
        r = run_task(main_path, "new", "--summary", "落ちたら仮の ID", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=PLANNED_BODY)
        provisional = r.stdout.split("\t")[1] if r.stdout.startswith("CREATED") else ""
        check("push で落ちたら仮の ID のまま CREATED と TRACKER FAILED", provisional.startswith("gh-new-")
              and "TRACKER\tFAILED" in r.stdout, r.stdout)
        fake2 = FakeGitHub()
        fake2.issues, fake2.items = fake.issues, fake.items
        env()["GITHUB_API_URL"] = fake2.url
        try:
            r = run_task(main_path, "sync")
            ids = {i.bd_id for i in beads.list_issues(main_path)}
            check("task sync が送り直して番号の ID へ付け替える", r.returncode == 0 and not any(
                i.startswith("gh-new-") for i in ids) and f"gh-{len(fake2.issues)}" in ids, r.stdout + repr(ids))
        finally:
            fake2.close()


def test_tracker_github_keeps_claim_marks() -> None:
    say("トラッカー github: 取り込みが着手中の課題を上書きしても、着手の印（assignee と metadata）を戻す")
    with _github() as (fake, tmp, main_path, wt1):
        a = new(main_path, "計画を登録して着手する", body=plan_body("shared.txt"))
        b = new(main_path, "送りが届かないまま着手する")
        c = new(main_path, "取り込みの最中に着手する")
        e = new(main_path, "GitHub で手放す")
        g = new(main_path, "Project の書き込みが落ちたあと GitHub で手放す")
        write(os.path.join(main_path, "shared.txt"), "line1\nline2\n")
        git(main_path, "commit", "-q", "-am", "主ブランチが進む")
        for t in (a, e):
            run_task(wt1, "claim", t)
        check("着手の送りは GitHub に label status::in_progress を付ける",
              "status::in_progress" in fake.issues[_num(e)]["labels"], repr(fake.issues[_num(e)]))
        env()["GITHUB_API_URL"] = "http://127.0.0.1:9"
        r = run_task(wt1, "claim", b)
        env()["GITHUB_API_URL"] = fake.url
        check("送りが届かない着手は GitHub に label が付かない", "TRACKER\tFAILED" in r.stdout
              and "status::in_progress" not in fake.issues[_num(b)]["labels"], r.stdout + repr(fake.issues[_num(b)]))
        fake.graphql_down = True
        r = run_task(wt1, "claim", g)
        fake.graphql_down = False
        check("push が通って Project の書き込みだけ落ちた着手は GitHub に label が付く", "TRACKER\tFAILED" in r.stdout
              and "status::in_progress" in fake.issues[_num(g)]["labels"], r.stdout + repr(fake.issues[_num(g)]))
        claimed = _claim_state(main_path, a)

        write(os.path.join(tmp, "bd.log.before-pull"),
              json.dumps({"cwd": wt1, "argv": [sys.executable, TASK_PY, "claim", c]}))
        fake.edit(_num(a))
        fake.edit(_num(c))
        for t in (e, g):
            fake.edit(_num(t), labels=[l for l in fake.issues[_num(t)]["labels"] if not l.startswith("status")])
        r = run_task(main_path, "sync")
        state = {t: _claim_state(main_path, t) for t in (a, b, c, e, g)}
        marks = (beads.CLAIM_BRANCH_KEY, beads.CLAIM_HEAD_KEY, beads.PLAN_BASE_KEY, beads.PLAN_TIP_KEY)
        check("取り込みが上書きしても assignee と metadata が戻る", r.returncode == 0
              and state[a][:2] == ("in_progress", "wt1")
              and all(state[a][2].get(k) == claimed[2].get(k) and claimed[2].get(k) for k in marks),
              r.stdout + r.stderr + repr(claimed) + repr(state[a]))
        check("着手の送りが届く前の GitHub の版で open に戻ったら着手を戻す", state[b][:2] == ("in_progress", "wt1"),
              r.stdout + repr(state[b]))
        check("取り込みの最中の着手も戻す", not os.path.exists(os.path.join(tmp, "bd.log.before-pull"))
              and state[c][:2] == ("in_progress", "wt1") and bool(state[c][2].get(beads.CLAIM_HEAD_KEY)),
              r.stdout + repr(state[c]))
        check("着手を送ったあと GitHub で label が外れた（手放した）課題は着手に戻さず、metadata だけ戻す",
              state[e][:2] == ("open", None) and bool(state[e][2].get(beads.CLAIM_HEAD_KEY)),
              r.stdout + repr(state[e]))
        check("push は通り Project の書き込みが落ちたあと GitHub で label を外した課題は着手に戻さない",
              state[g][:2] == ("open", None), r.stdout + repr(state[g]))


def test_tracker_github_plan_marks_after_pull() -> None:
    say("トラッカー github: 着手のあとに計画を書いた時点の判定は、取り込みのあとも残る")
    with _github() as (fake, _tmp, main_path, wt1):
        a = new(main_path, "着手のあとに計画を書き直す", body=plan_body("shared.txt"))
        b = new_unplanned(main_path, "作業のあとに計画を書く")
        write(os.path.join(main_path, "shared.txt"), "line1\nline2\n")
        git(main_path, "commit", "-q", "-am", "主ブランチが進む")
        for t in (a, b):
            run_task(wt1, "claim", t)
        r = run_task(wt1, "plan-check", a)
        check("名指したファイルが変わっていれば着手で PLAN_STALE", r.stdout.strip() == f"PLAN_STALE\t{a}\tshared.txt",
              r.stdout + r.stderr)

        r = run_task(wt1, "edit", a, "--section", "やること", "--body-file", "-",
                     stdin="### 1. 直す\nx\n\n### 名指すファイル\n- `shared.txt`\n")
        fake.edit(_num(a))
        run_task(main_path, "sync")
        r2 = run_task(wt1, "plan-check", a)
        check("PLAN_STALE で着手して作業の前に edit --section で書けば、取り込みのあとも PLAN_FIRST",
              r.returncode == 0 and r2.stdout.strip() == f"PLAN_FIRST\t{a}", r.stdout + r.stderr + r2.stdout)

        write(os.path.join(wt1, "work.txt"), "作業\n")
        r = run_task(wt1, "edit", b, "--section", "やること", "--after-work", "--body-file", "-",
                     stdin="### 1. 書く\nx\n")
        fake.edit(_num(b))
        run_task(main_path, "sync")
        r2 = run_task(wt1, "plan-check", b)
        check("作業のあとに書けば、取り込みのあとも PLAN_NOT_FIRST after-work", r.returncode == 0
              and r2.stdout.strip() == f"PLAN_NOT_FIRST\t{b}\tafter-work", r.stdout + r.stderr + r2.stdout)


def test_tracker_github_restore_failure() -> None:
    say("トラッカー github: 着手の印を戻せない取り込み")
    with _github() as (fake, tmp, main_path, wt1):
        d = new(main_path, "印を戻せない")
        f = new(main_path, "GitHub で閉じる")
        run_task(wt1, "claim", d)
        run_task(main_path, "sync")  # 最初の取り込みは開いた Issue しか見ない
        write(os.path.join(tmp, "bd.log.fail-update"), "")
        fake.edit(_num(d))
        fake.edit(_num(f), state="closed")
        r = run_task(main_path, "sync")
        os.remove(os.path.join(tmp, "bd.log.fail-update"))
        check("戻せなければ TRACKER FAILED（終了コード10）", r.returncode == 10
              and any(l.startswith("TRACKER\tFAILED\tgithub") and d in l for l in r.stdout.splitlines()),
              r.stdout + r.stderr)
        check("戻しが落ちても同じ取り込みの CLOSED の行は出る", f"TRACKER\tCLOSED\t{f}" in r.stdout, r.stdout)


def test_tracker_github_push_mark() -> None:
    say("トラッカー github: 送りの控えを取り込みの時刻と分ける")
    with _github() as (fake, tmp, main_path, wt1):
        x = new(main_path, "取り込みと同じ秒の着手の送りが落ちる")
        w = new(main_path, "ほかの課題を直して bd の前回の同期の時刻を進める")
        write(os.path.join(tmp, "bd.log.fail-push"), "")
        r = run_task(wt1, "claim", x)
        os.remove(os.path.join(tmp, "bd.log.fail-push"))
        check("取り込みは通り push だけが落ちた着手は TRACKER FAILED", r.stdout.startswith("CLAIMED")
              and "TRACKER\tFAILED" in r.stdout and "status::in_progress" not in fake.issues[_num(x)]["labels"],
              r.stdout + r.stderr)
        time.sleep(1.1)
        shown = run_task(main_path, "show", w).stdout.split("---\n", 2)[2]
        run_task(main_path, "edit", w, "--body-file", "-", stdin=shown.replace("## 注意\n\nz", "## 注意\n\nzz"))
        # 取り込みの時刻が着手と同じ秒に収まった形を決め打ちで作る。
        issue = beads.show(main_path, beads.to_bd_id(x))
        started = beads.parse_time(issue.started_at) if issue is not None else None
        synced = json.loads(bd(main_path, "kv", "get", "task-workflow.github-synced").stdout or "{}")
        if started is not None:
            synced[str(_num(x))] = started.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        bd(main_path, "kv", "set", "task-workflow.github-synced", json.dumps(synced))
        fake.edit(_num(x))
        r = run_task(main_path, "sync")
        state = _claim_state(main_path, x)[:2]
        check("取り込みと着手が同じ秒で push だけが落ちた着手は、次の取り込みで戻るか TRACKER FAILED",
              started is not None and (state == ("in_progress", "wt1") or any(
                  l.startswith("TRACKER\tFAILED") and x in l for l in r.stdout.splitlines())),
              r.stdout + repr(state))


def test_tracker_github_push_from_other_worktree() -> None:
    say("トラッカー github: 取り込みの最中に別の作業ツリーが送った着手を書き戻さない")
    with _github() as (fake, tmp, main_path, wt1):
        y = new(main_path, "別の作業ツリーで着手して送る")
        z = new(main_path, "本体で直す")
        time.sleep(1.1)
        write(os.path.join(tmp, "bd.log.before-pull"),
              json.dumps({"cwd": wt1, "argv": [sys.executable, TASK_PY, "claim", y]}))
        shown = run_task(main_path, "show", z).stdout.split("---\n", 2)[2]
        r = run_task(main_path, "edit", z, "--body-file", "-", stdin=shown.replace("## 注意\n\nz", "## 注意\n\nzz"))
        check("本体の操作の取り込みの最中に別の作業ツリーが着手して送る", r.returncode == 0
              and not os.path.exists(os.path.join(tmp, "bd.log.before-pull"))
              and "status::in_progress" in fake.issues[_num(y)]["labels"], r.stdout + r.stderr)
        fake.edit(_num(y), labels=[l for l in fake.issues[_num(y)]["labels"] if not l.startswith("status")])
        r = run_task(main_path, "sync")
        state = _claim_state(main_path, y)[:2]
        check("別の作業ツリーの送りを古い控えで書き戻さず、そのあと GitHub で手放した課題は着手に戻さない",
              state == ("open", None), r.stdout + repr(state))


def test_tracker_jira() -> None:
    say("トラッカー jira（偽の bd jira sync。--pull だけ）")
    with tempfile.TemporaryDirectory() as tmp:
        _local.env = _with_fakes(tmp)
        try:
            main_path, wt1, _ = make_repo(tmp, extra="- トラッカー: jira\n")
            a = new(main_path, "Jira から")
            bd(main_path, "update", beads.to_bd_id(a), "--external-ref", "https://x.atlassian.net/browse/P-1")
            r = run_task(main_path, "sync")
            check("task sync は bd jira sync --pull", r.returncode == 0 and r.stdout.startswith("TRACKER\tOK\tjira"), r.stdout)
            run_task(wt1, "claim", a)
            work_and_done(wt1, a)
            run_task(wt1, "ship")
            with open(env()["FAKE_BD_LOG"]) as f:
                log = f.read().splitlines()
            check("Jira へは書かない（--pull だけ）", log and all(l.startswith("jira sync --pull") for l in log), repr(log))
            r = run_task(main_path, "status")
            check("閉じた Jira 課題は jira_close に出る", tail_line(r.stdout, "jira_close") == f"jira_close\t1\t{a}", r.stdout)
            r = run_task(main_path, "jira-closed", a)
            r = run_task(main_path, "status")
            check("jira-closed で外れる", tail_line(r.stdout, "jira_close") == "jira_close\t0\t-", r.stdout)
        finally:
            del _local.env


def test_tracker_jira_rename() -> None:
    say("トラッカー jira: 取り込んだ課題を Jira のキーの ID へ付け替える")
    with tempfile.TemporaryDirectory() as tmp:
        _local.env = _with_fakes(tmp)
        try:
            main_path, wt1, _ = make_repo(tmp, extra="- トラッカー: jira\n")
            site = "https://x.atlassian.net/browse/"
            local = new(main_path, "ローカルの課題")
            adopted = new(main_path, "キーのある adopt 済みの課題")
            bd(main_path, "update", beads.to_bd_id(adopted), "--external-ref", f"{site}PROJ-11")
            bd(main_path, "create", "--id", "t-x1a", "--title", "前に取り込んだ", "--external-ref", f"{site}PROJ-7", "--silent")
            bd(main_path, "dep", "add", beads.to_bd_id(local), "t-x1a")
            bd(main_path, "comments", "add", "t-x1a", "Jira から来た")
            bd(main_path, "create", "--id", "proj-8", "--title", "先にある", "--force", "--silent")
            write(env()["FAKE_BD_LOG"] + ".jira", f"t-x1b\t行き先が既にある\t{site}PROJ-8\n"
                  f"t-456\t数字だけの hash\t{site}PROJ-9\n")
            r = run_task(main_path, "sync")
            ids = {i.bd_id for i in beads.list_issues(main_path)}
            check("tw sync の取り込みのあと、振り分け前の課題は external_ref のキーの ID になる（数字だけの hash も）",
                  r.returncode == 0 and {"proj-7", "proj-9", "t-x1b", "proj-8"} <= ids
                  and not {"t-x1a", "t-456"} & ids, r.stdout + repr(ids))
            check("行き先が既にあれば付け替えず INVALID の行",
                  "TRACKER\tINVALID\tt-x1b\tPROJ-8 が既にある（付け替えない）" in r.stdout, r.stdout)
            issue = beads.show(main_path, beads.to_bd_id(local))
            comments = beads.comments(main_path, "proj-7")
            check("依存・comment・版が付いてくる", issue is not None and issue.dependencies == ("proj-7",)
                  and [c.get("text") for c in comments] == ["Jira から来た"]
                  and beads.history(main_path, "proj-7") != [], repr(issue and issue.dependencies) + repr(comments))
            check("ローカルの T-xxx と adopt 済みの T-xxx は付け替えない",
                  {beads.to_bd_id(local), beads.to_bd_id(adopted)} <= ids, repr(ids))
            r = run_task(main_path, "status")
            check("付け替えた課題は Jira のキーで triage に出る", "PROJ-7" in tail_line(r.stdout, "triage")
                  and "PROJ-9" in tail_line(r.stdout, "triage"), r.stdout)

            r = run_task(wt1, "adopt", "PROJ-7", "--difficulty", "haiku", "--loopable", "N", "--body-file", "-",
                         stdin=PLANNED_BODY)
            check("adopt はキーの課題に番号を振らない", r.returncode == 0 and r.stdout.startswith("ADOPTED\tPROJ-7\tPROJ-7"),
                  r.stdout + r.stderr)
            bd(main_path, "create", "--id", "t-x1c", "--title", "付け替え前", "--external-ref", f"{site}PROJ-10", "--silent")
            r = run_task(wt1, "adopt", "t-x1c", "--difficulty", "haiku", "--loopable", "N", "--body-file", "-",
                         stdin=PLANNED_BODY)
            check("adopt はキーの ID へ付け替える", r.returncode == 0 and r.stdout.startswith("ADOPTED\tt-x1c\tPROJ-10"),
                  r.stdout + r.stderr)
            r = run_task(wt1, "adopt", "t-x1b", "--difficulty", "haiku", "--loopable", "N", "--body-file", "-",
                         stdin=PLANNED_BODY)
            ids = {i.bd_id for i in beads.list_issues(main_path)}
            check("行き先が既にあれば adopt は INVALID で番号も振らない（終了コード3）", r.returncode == 3
                  and "TRACKER\tINVALID\tt-x1b" in r.stdout and "t-x1b" in ids and "ADOPTED" not in r.stdout,
                  r.stdout + r.stderr + repr(ids))

            run_task(wt1, "claim", "PROJ-7")
            work_and_done(wt1, "PROJ-7")
            r = run_task(wt1, "ship")
            r = run_task(main_path, "status")
            check("閉じたキーの課題は jira_close に出る", tail_line(r.stdout, "jira_close") == "jira_close\t1\tPROJ-7", r.stdout)
            run_task(main_path, "jira-closed", "PROJ-7")
            r = run_task(main_path, "status")
            check("jira-closed PROJ-7 で外れる", tail_line(r.stdout, "jira_close") == "jira_close\t0\t-", r.stdout)
        finally:
            del _local.env


def test_backup() -> None:
    say("バックアップ（git の外の決まった場所）")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp)
        new(main_path, "残す")
        r = run_task(wt1, "backup")
        target = os.path.join(env()["XDG_DATA_HOME"], "task-workflow", "base")
        check("既定の置き場へ bd backup と bd export を取る", r.returncode == 0 and r.stdout.startswith(f"BACKUP\tOK\t{target}")
              and os.path.exists(os.path.join(target, "issues.jsonl"))
              and os.path.isdir(os.path.join(target, "dolt")), r.stdout + r.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp, extra="- バックアップ: `./keep`\n")
        r = run_task(main_path, "backup")
        check("リポジトリの中へは取らない（終了コード10）", r.returncode == 10 and "BACKUP\tFAILED" in r.stdout, r.stdout)


def _make_beads_template(home: str, prefix: str) -> None:
    repo = os.path.join(home, f"beads-template-{prefix}")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "beads.role", "maintainer")
    r = bd(repo, "init", "--stealth", "-p", prefix, "--non-interactive", "--skip-hooks", "--quiet")
    if r.returncode != 0:
        raise RuntimeError(f"bd init -p {prefix} 失敗: {r.stdout}{r.stderr}")
    with open(os.path.join(repo, ".git", "info", "exclude"), encoding="utf-8") as f:
        _beads_templates[prefix] = (os.path.join(repo, ".beads"), f.read())


def _stat(path: str) -> tuple[float, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_mtime, st.st_size


def _run_one(test) -> list[str]:
    _local.lines = []
    try:
        test()
    except Exception as e:  # noqa: BLE001  1件の故障で残りのテストを止めない
        check(f"{test.__name__} が落ちずに終わる", False, repr(e))
    return _local.lines


def test_id_forms() -> None:
    """ID の形: `T-<n>`・`GH-<n>`・Jira のキー（`PROJ-123`）を読み、前の2つを Jira のキーと取り違えない。"""
    forms = {"T-123": "t-123", "GH-5": "gh-5", "PROJ-123": "proj-123", "AB2_C-7": "ab2_c-7"}
    for shown, inner in forms.items():
        check(f"{shown} は Beads の中で {inner} と行き来する",
              beads.to_bd_id(shown) == inner and beads.to_task_id(inner) == shown and beads.is_numbered(inner))
        check(f"{shown} は --deps・retrospect の引数・ブランチ・文中の検索が受ける",
              layout.ANY_ID_PATTERN.match(shown) is not None
              and layout.FEATURE_BRANCH_PATTERN.fullmatch(f"feature/{shown}") is not None
              and (layout.ID_SEARCH_PATTERN.search(f"{shown}: 直す") or [None])[0] == shown)
    for bad in ("T-12", "P-123", "proj-123", "PROJ-", "1AB-3", "PROJ-12a"):
        check(f"{bad} は ID の形でない", layout.ANY_ID_PATTERN.match(bad) is None)
    check("T-<n>・GH-<n> は Jira の枝で読まれない（番号の意味が変わらない）",
          beads.id_number("t-123") == 123 and beads.id_number("gh-5") is None and beads.id_number("proj-123") is None
          and beads.BD_ID_PATTERN.match("t-123").group(3) is None and beads.BD_ID_PATTERN.match("gh-5").group(3) is None)
    check("仮の ID・取り込んだままの ID は番号付きでない",
          not any(beads.is_numbered(i) for i in ("gh-new-wt-1700000000", "gh-1790123-1-4dfc", "t-12")))
    ordered = sorted(["PROJ-2", "GH-new-x", "ABC-9", "GH-5", "T-123", "PROJ-1", "T-045"], key=beads.sort_key)
    check("status の並びは T → GH → Jira のキー（キー名・番号）→ 仮の ID",
          ordered == ["T-045", "T-123", "GH-5", "ABC-9", "PROJ-1", "PROJ-2", "GH-new-x"], repr(ordered))


def test_bd_time_forms() -> None:
    """`bd` の時刻は小数の桁（0〜9桁）と `Z`・時差によらず読め、時刻でないものは `None`。"""
    forms = {
        "2026-10-05T08:12:39Z": 0,
        "2026-10-05T08:12:39.7Z": 700000,
        "2026-10-05T17:12:39.78+09:00": 780000,
        "2026-10-05T08:12:39.1234Z": 123400,
        "2026-10-05T08:12:39.123456789Z": 123456,
    }
    for text, micro in forms.items():
        check(f"{text} を読む", beads.parse_time(text) == datetime(2026, 10, 5, 8, 12, 39, micro, tzinfo=timezone.utc),
              repr(beads.parse_time(text)))
    check("時刻でないものは None", beads.parse_time("昨日") is None and beads.parse_time(None) is None)


def main() -> None:
    only = sys.argv[1:]  # テストの関数名を渡すとそれだけを走らせる（手で直すとき）
    if shutil.which("bd") is None:
        print("bd が無いので Beads 方式の自己テストを飛ばす")
        return
    real_config = os.path.join(os.path.expanduser("~"), ".config", "bd", "config.yaml")
    before = _stat(real_config)
    with tempfile.TemporaryDirectory() as home:
        write(os.path.join(home, ".config", "bd", "config.yaml"),
              "metrics:\n    disabled: true\n    notice_shown: true\nno-git-ops: true\n")
        BASE_ENV["HOME"] = home
        BASE_ENV["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
        BASE_ENV["XDG_DATA_HOME"] = os.path.join(home, ".local", "share")
        BASE_ENV.pop("BEADS_ACTOR", None)
        BASE_ENV.pop("GITHUB_TOKEN", None)
        # 長いものから並列に乗せる（後ろに残ると全体がその分延びる）。
        tests = (
            test_tracker_github_keeps_claim_marks,
            test_tracker_github_plan_marks_after_pull,
            test_tracker_github_bidirectional,
            test_tracker_github_pull_round_trip,
            test_tracker_github_push_mark,
            test_tracker_github_push_from_other_worktree,
            test_tracker_github_push_only,
            test_tracker_github_closed_and_hold,
            test_tracker_github_restore_failure,
            test_tracker_github_provisional_id,
            test_tracker_github_push_only_recovery,
            test_id_forms,
            test_bd_time_forms,
            test_setup_and_config_doctor,
            test_file_mode_untouched_by_beads_dir,
            test_new_status_and_numbering,
            test_claim_race_owner_and_release,
            test_cycle_done_ship_and_dropped,
            test_done_commits_since_claim,
            test_commit_guard,
            test_handback_guard,
            test_handback_guard_step,
            test_plan_check,
            test_edit_frame_guard,
            test_edit_section,
            test_edit_deps,
            test_plan_check_unrecorded,
            test_registered_plan,
            test_verify_stamp,
            test_verify_refuses_unplanned_work,
            test_flow_records_and_metrics,
            test_stale_markers,
            test_retrospect_due,
            test_triage_and_adopt,
            test_tracker_jira,
            test_tracker_jira_rename,
            test_backup,
        )
        tests = tuple(t for t in tests if not only or t.__name__ in only)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda prefix: _make_beads_template(home, prefix), (beads.PREFIX_LOCAL, beads.PREFIX_GITHUB)))
        with ThreadPoolExecutor(max_workers=min(len(tests), max(1, (os.cpu_count() or 2) // 2))) as pool:
            outputs = list(pool.map(_run_one, tests))
    for lines in outputs:
        print("\n".join(lines))
    _local.lines = []
    check("利用者の ~/.config/bd/config.yaml に触れていない", _stat(real_config) == before, real_config)
    print("\n".join(_local.lines))
    print()
    if failures:
        print(f"FAILED {len(failures)}件: " + ", ".join(failures))
        raise SystemExit(1)
    print("すべて通った")


if __name__ == "__main__":
    main()
