#!/usr/bin/env python3
"""`task.py` の Beads 方式（`- タスクの置き場: beads`）の自己テスト。

使い方: python3 selftest_beads.py

一時ディレクトリに git リポジトリと作業ツリー2本を作り、`bd init --stealth` で `.beads` を置いて、
`task.py` を実際に子プロセスで（取り合いは同時に）起こして確かめる。本物の `bd` を使う
（無ければ飛ばして 0 で終わる。ファイル方式は `selftest_task.py` が見る）。

GitHub・Jira には繋がない。`bd github sync`・`bd jira sync` と `gh` は、PATH の先頭に置いた
偽のコマンドが受けて呼ばれ方を記録する（`bd` のそれ以外のサブコマンドは本物へ渡す）。
`HOME`・`XDG_CONFIG_HOME`・`XDG_DATA_HOME` を一時ディレクトリへ向けて、利用者の家を汚さない
（`bd init` は利用者の `~/.config/bd/config.yaml` を読み書きし、並行に打つと使用状況の送信の設定まで
書き戻すことがあった。一時の家には送信を止めた設定を置く）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import beads  # noqa: E402
import taskfile  # noqa: E402

TASK_PY = os.path.join(HERE, "task.py")
INIT_PY = os.path.join(HERE, "init.py")
SCAN_PY = os.path.join(HERE, "..", "..", "retrospect", "scripts", "scan.py")
MATERIAL_PY = os.path.join(HERE, "..", "..", "retrospect", "scripts", "material.py")
BODY = ("## 目的・背景\nx\n\n## 決まっていること（蒸し返さない）\n\n## 解くべき論点\nなし\n\n## やること\n\n"
        "## 完了条件\n- 通る\n\n## 注意\nz\n\n## 参考情報\n")

failures: list[str] = []
BASE_ENV = os.environ.copy()
# テストは並行に走らせる（1件ごとに `bd init` が数秒かかる）。出力と環境変数はテストごとに持つ。
_local = threading.local()


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


def make_repo(tmp: str, branch: str = "切らない", extra: str = "", verify: str | None = None) -> tuple[str, str, str]:
    """`(本体, 作業ツリー1, 作業ツリー2)`。`init.py` で `.beads` を用意する。"""
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


def new(cwd: str, summary: str, *extra: str, body: str = BODY) -> str:
    r = run_task(cwd, "new", "--summary", summary, "--difficulty", "sonnet", "--loopable", "Y", *extra,
                 "--body-file", "-", stdin=body)
    if r.returncode != 0:
        raise RuntimeError(f"task new 失敗: {r.stdout}{r.stderr}")
    return r.stdout.split("\t")[1]


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
        main_path, wt1, _ = make_repo(tmp)
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
                     "--body-file", "-", stdin=BODY)
        check("new がタスクファイルを作る", r.returncode == 0 and "develop/task/T-001.md" in r.stdout
              and os.path.exists(os.path.join(main_path, "develop", "task", "T-001.md")), r.stdout)
        r = run_task(main_path, "config-doctor")
        check("config-doctor は4行のまま", len(r.stdout.strip().splitlines()) == 4, r.stdout)
        r = run_task(main_path, "edit", "T-001", "--summary", "x")
        check("edit はファイル方式では使えない（終了コード2）", r.returncode == 2, r.stdout + r.stderr)
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
                     "--body-file", "-", stdin=BODY)
        check("Beads に無い依存は終了コード2", r.returncode == 2, r.stdout + r.stderr)
        r = run_task(wt1, "new", "--summary", "x", "--difficulty", "haiku", "--loopable", "Y",
                     "--body-file", "-", stdin=BODY.replace("## やること\n", "## やること\n1\n"))
        check("## やること を書いた本文は終了コード2", r.returncode == 2, r.stdout + r.stderr)

        r = run_task(wt2, "status")
        t = rows(r.stdout)
        check("status の行（READY・BLOCKED・HOLD）", t.get(a, [])[5:6] == ["READY"]
              and t.get(b, [])[5:6] == [f"BLOCKED:{a}"] and t.get(h, [])[1] == "hold" and t[h][5] == "HOLD", r.stdout)
        check("counts・ready", "counts\ttodo=2\thold=1\tdone=0\tdropped=0\tclaimed=0" in r.stdout
              and "ready\t1" in r.stdout, r.stdout)
        issue = beads.show(main_path, beads.to_bd_id(a))
        check("完了条件は acceptance_criteria、ほかは description", issue is not None
              and issue.raw.get("acceptance_criteria") == "- 通る"
              and "## 完了条件" not in issue.raw.get("description", "")
              and set(issue.labels) == {"difficulty:sonnet", "loopable:Y"}, str(issue and issue.raw))

        procs = [start_task(w, "new", "--summary", f"並行{i}", "--difficulty", "haiku", "--loopable", "Y",
                            "--body-file", "-") for i, w in enumerate((wt1, wt2, main_path))]
        outs = [p.communicate(BODY)[0] for p in procs]
        ids = [o.split("\t")[1] for o in outs if o.startswith("CREATED")]
        check("3つ同時の new で番号が重ならない", len(ids) == 3 and len(set(ids)) == 3, repr(outs))
        r = bd(main_path, "kv", "get", beads.LAST_ID_KEY)
        check("最後の番号を bd kv に残す", r.stdout.strip().isdigit() and int(r.stdout.strip()) >= 45, r.stdout)


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


def test_cycle_done_ship_and_dropped() -> None:
    say("1サイクル（claim → edit → done → ship）と見送り")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, wt2 = make_repo(tmp, branch="既定")
        a = new(main_path, "前段")
        b = new(main_path, "後段", "--deps", a)
        c = new(main_path, "見送る")
        d = new(main_path, "見送りに依存", "--deps", c)

        r = run_task(wt1, "claim", a)
        check("既定の枝の設定なら feature/T-xxx を切る", r.stdout.strip().endswith(f"branch=feature/{a}"), r.stdout)
        shown = run_task(wt1, "show", a).stdout
        body = shown.split("---\n", 2)[2].replace("## やること\n", "## やること\n\n1. 書く\n")
        r = run_task(wt1, "edit", a, "--body-file", "-", stdin=body)
        check("edit が本文を受ける", r.returncode == 0 and r.stdout.startswith("EDITED"), r.stdout + r.stderr)
        issue = beads.show(main_path, beads.to_bd_id(a))
        check("## やること は notes へ", issue is not None and issue.raw.get("notes") == "1. 書く", str(issue and issue.raw))
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
        scan = subprocess.run([sys.executable, SCAN_PY, ".", "--since", git(main_path, "rev-list", "--max-parents=0", "HEAD").stdout.strip()],
                              cwd=main_path, capture_output=True, text=True, env=env())
        check("scan.py は Beads の ## 結果 で振り返り済みを判定する", f"reviewed\t{a},{c}" in scan.stdout
              or f"reviewed\t{c},{a}" in scan.stdout, scan.stdout + scan.stderr)
        mat = subprocess.run([sys.executable, MATERIAL_PY, ".", a], cwd=main_path, capture_output=True, text=True, env=env())
        check("material.py は Beads の本文と版の差を出す", f"出典\tBeads {beads.to_bd_id(a)}" in mat.stdout
              and "+1. 書く" in mat.stdout, mat.stdout + mat.stderr)


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


def test_triage_and_adopt() -> None:
    say("振り分け前の課題（トラッカーから来たもの）と adopt")
    with tempfile.TemporaryDirectory() as tmp:
        main_path, wt1, _ = make_repo(tmp)
        raw = bd(main_path, "create", "--title", "外から来た", "-d", "本文", "--silent").stdout.strip()
        r = run_task(wt1, "status")
        check("labels の無い課題は triage に出て READY にならない", f"triage\t1\t{raw}" in r.stdout
              and "ready\t0" in r.stdout and rows(r.stdout).get(raw, [""] * 8)[5] == "TRIAGE", r.stdout)
        r = run_task(wt1, "claim", raw)
        check("振り分け前は claim できない（NOT_READY TRIAGE）", r.returncode == 4 and "TRIAGE" in r.stdout, r.stdout)
        r = run_task(wt1, "adopt", raw, "--difficulty", "haiku", "--loopable", "N", "--body-file", "-", stdin=BODY)
        check("adopt が番号を振る", r.returncode == 0 and r.stdout.startswith(f"ADOPTED\t{raw}\tT-001"), r.stdout + r.stderr)
        r = run_task(wt1, "status")
        check("adopt したものは READY", rows(r.stdout).get("T-001", [""] * 8)[5] == "READY" and "triage\t0" in r.stdout, r.stdout)


def _fake_bin(tmp: str) -> str:
    """偽の `bd`（github/jira の sync だけ受け、残りは本物へ）と偽の `gh` を置いたディレクトリ。"""
    bin_dir = os.path.join(tmp, "bin")
    real_bd = shutil.which("bd") or "bd"
    write(os.path.join(bin_dir, "bd"), f"""#!{sys.executable}
import json, os, subprocess, sys
REAL = {real_bd!r}
args = sys.argv[1:]
core = [a for i, a in enumerate(args) if a != "--actor" and (i == 0 or args[i - 1] != "--actor")]
if core[:1] in (["github"], ["jira"]) and "sync" in core:
    with open(os.environ["FAKE_BD_LOG"], "a") as f:
        f.write(" ".join(core) + ("\\ttoken" if os.environ.get("GITHUB_TOKEN") else "") + "\\n")
    if os.environ.get("FAKE_BD_SYNC_FAIL"):
        sys.stderr.write("network down\\n")
        sys.exit(1)
    if core[0] == "github":
        out = subprocess.run([REAL, "list", "--all", "-n", "0", "--json"], capture_output=True, text=True).stdout
        for n, issue in enumerate(json.loads(out or "[]"), start=1):
            if not issue.get("external_ref"):
                num = issue["id"].split("-")[-1]
                subprocess.run([REAL, "update", issue["id"], "--external-ref",
                                "https://github.com/o/r/issues/" + num], capture_output=True)
    sys.exit(0)
os.execv(REAL, [REAL] + args)
""")
    write(os.path.join(bin_dir, "gh"), f"""#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
state_path = os.environ["FAKE_GH_STATE"]
state = json.load(open(state_path)) if os.path.exists(state_path) else {{"items": [], "calls": []}}
state["calls"].append(args)
out = None
if args[:2] == ["auth", "token"]:
    if os.environ.get("FAKE_GH_AUTH_FAIL"):
        sys.exit(1)
    print("fake-token")
elif args[:2] == ["project", "view"]:
    out = {{"id": "PID", "number": int(args[2])}}
elif args[:2] == ["project", "field-list"]:
    names = ["Pending", "Todo", "In progress", "Done", "Cancel"]
    out = {{"fields": [{{"id": "FID", "name": "Status", "options": [{{"id": "O-" + n, "name": n}} for n in names]}}]}}
elif args[:2] == ["project", "item-list"]:
    out = {{"items": state["items"]}}
elif args[:2] == ["project", "item-add"]:
    url = args[args.index("--url") + 1]
    item = {{"id": "I-" + url.rsplit("/", 1)[-1], "content": {{"url": url}}, "status": "Pending"}}
    state["items"].append(item)
    out = item
elif args[:2] == ["project", "item-edit"]:
    item_id = args[args.index("--id") + 1]
    option = args[args.index("--single-select-option-id") + 1]
    for item in state["items"]:
        if item["id"] == item_id:
            item["status"] = option[len("O-"):]
json.dump(state, open(state_path, "w"))
if out is not None:
    print(json.dumps(out))
""")
    for name in ("bd", "gh"):
        os.chmod(os.path.join(bin_dir, name), 0o755)
    return bin_dir


def _with_fakes(tmp: str) -> dict[str, str]:
    env = dict(BASE_ENV)
    env["PATH"] = _fake_bin(tmp) + os.pathsep + env.get("PATH", "")
    env["FAKE_BD_LOG"] = os.path.join(tmp, "bd.log")
    env["FAKE_GH_STATE"] = os.path.join(tmp, "gh.json")
    env.pop("GITHUB_TOKEN", None)
    return env


def test_tracker_github() -> None:
    say("トラッカー github（偽の bd github sync と gh）")
    with tempfile.TemporaryDirectory() as tmp:
        _local.env = _with_fakes(tmp)
        try:
            main_path, wt1, _ = make_repo(tmp, extra="- トラッカー: github\n- GitHub Project: `sinnlosses/1`\n")
            a = new(main_path, "GitHub へ")
            h = new(main_path, "待ち", "--hold")
            c = new(main_path, "見送る")
            with open(env()["FAKE_BD_LOG"]) as f:
                log = f.read()
            check("new のたびに bd github sync --push-only（token は gh auth token から）",
                  "github sync --push-only\ttoken" in log and "--pull" not in log, log)
            state = json.load(open(env()["FAKE_GH_STATE"]))
            status = {i["content"]["url"].rsplit("/", 1)[-1]: i["status"] for i in state["items"]}
            num = lambda t: t.split("-")[1]  # noqa: E731
            check("Status 欄: open → Todo、pending → Pending", status.get(num(a)) == "Todo"
                  and status.get(num(h)) == "Pending", repr(status))
            run_task(wt1, "claim", a)
            state = json.load(open(env()["FAKE_GH_STATE"]))
            status = {i["content"]["url"].rsplit("/", 1)[-1]: i["status"] for i in state["items"]}
            check("claim で In progress", status.get(num(a)) == "In progress", repr(status))
            work_and_done(wt1, a)
            run_task(wt1, "ship")
            run_task(wt1, "claim", c)
            work_and_done(wt1, c, dropped=True, name="c.txt")
            r = run_task(wt1, "ship")
            state = json.load(open(env()["FAKE_GH_STATE"]))
            status = {i["content"]["url"].rsplit("/", 1)[-1]: i["status"] for i in state["items"]}
            check("閉じたら Done、見送りは Cancel", status.get(num(a)) == "Done" and status.get(num(c)) == "Cancel",
                  repr(status) + r.stdout)
            check("ship の行に TRACKER OK", any(l.startswith("TRACKER\tOK\tgithub") for l in r.stdout.splitlines()), r.stdout)

            env()["FAKE_BD_SYNC_FAIL"] = "1"
            r = run_task(main_path, "new", "--summary", "落ちても登録", "--difficulty", "haiku", "--loopable", "Y",
                         "--body-file", "-", stdin=BODY)
            check("トラッカーの失敗は new を止めない（TRACKER FAILED を足して終了コード0）", r.returncode == 0
                  and r.stdout.startswith("CREATED") and "TRACKER\tFAILED\tgithub" in r.stdout, r.stdout)
            r = run_task(main_path, "sync")
            check("task sync の失敗は終了コード10", r.returncode == 10 and "TRACKER\tFAILED" in r.stdout, r.stdout)
            env().pop("FAKE_BD_SYNC_FAIL")
            r = run_task(main_path, "sync")
            check("task sync で打ち直せる", r.returncode == 0 and r.stdout.startswith("TRACKER\tOK\tgithub"), r.stdout)
        finally:
            del _local.env


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


def main() -> None:
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
        tests = (
            test_setup_and_config_doctor,
            test_file_mode_untouched_by_beads_dir,
            test_new_status_and_numbering,
            test_claim_race_owner_and_release,
            test_cycle_done_ship_and_dropped,
            test_stale_markers,
            test_triage_and_adopt,
            test_tracker_github,
            test_tracker_jira,
            test_backup,
        )
        with ThreadPoolExecutor(max_workers=len(tests)) as pool:
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
