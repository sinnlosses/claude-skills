"""トラッカー（GitHub・Jira・なし）との橋渡し。Beads 方式でだけ使う。

正典は WORKFLOW.md「Beads 方式」の「トラッカー」。錠と本文は Beads が持ち、トラッカーは
写しを持つだけなので、**ここの失敗はタスクの操作を止めない**（呼ぶ側は `TRACKER\\tFAILED\\t…` の
行を足して先へ進み、`task sync` で打ち直す）。

- `github`: `bd github sync --push-only`（Issue と label）→ Project の Status 欄を `gh project
  item-edit` で書く（`bd` は Status 欄を触らない）。`bd` へ渡す token は `GITHUB_TOKEN` が無ければ
  `gh auth token` から取る
- `jira`: `bd jira sync --pull` だけ。Jira には書かない（`--push` と引数なしの `sync` は打たない）。
  状態の変更は人が Jira で行い、ローカルで閉じたものには label `jira:close` を付けて
  `task status` の `jira_close` 行に出す
- `なし`: 何もしない
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

import beads
import layout

# Project の Status 欄の選択肢の名前（Beads の状態 → 欄の値）。
STATUS_OPTIONS = {
    "pending": "Pending",
    "open": "Todo",
    "in_progress": "In progress",
    "done": "Done",
    "cancelled": "Cancel",
}
ISSUE_URL = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/issues/(\d+)$")
ISSUE_NUMBER = re.compile(r"^(?:gh-|#)?(\d+)$")


class TrackerSettingError(RuntimeError):
    """設定ファイルのトラッカーの行が読めない（呼ぶ側が `INVALID`・終了コード3にする）。"""


@dataclass(frozen=True)
class Tracker:
    kind: str  # "なし" | "github" | "jira"
    project_owner: str | None = None
    project_number: str | None = None


def read_tracker(toplevel: str) -> Tracker:
    value = layout.read_setting_value(toplevel, layout.TRACKER_KEY)
    kind = layout.setting_word(value) if value else "なし"
    if kind not in layout.TRACKER_VALUES:
        raise TrackerSettingError(
            f"- {layout.TRACKER_KEY}: の値 {kind!r} を機械が読めない（{' / '.join(layout.TRACKER_VALUES)}）"
        )
    if kind != "github":
        return Tracker(kind)
    project = layout.read_setting_value(toplevel, layout.GITHUB_PROJECT_KEY)
    m = re.fullmatch(r"([^/\s]+)/(\d+)", layout.setting_word(project)) if project else None
    if m is None:
        raise TrackerSettingError(
            f"- {layout.TRACKER_KEY}: github には - {layout.GITHUB_PROJECT_KEY}: `<owner>/<番号>` の行が要る"
        )
    return Tracker(kind, m.group(1), m.group(2))


def sync(toplevel: str, tracker: Tracker) -> list[str]:
    """トラッカーへ写す。出力の行（`TRACKER\\t…`）を返す。`なし` なら空。"""
    if tracker.kind == "github":
        return _sync_github(toplevel, tracker)
    if tracker.kind == "jira":
        r = _bd(toplevel, ["jira", "sync", "--pull"], os.environ.copy())
        if r.returncode != 0:
            return [f"TRACKER\tFAILED\tjira\tbd jira sync --pull: {_tail(r)}"]
        return ["TRACKER\tOK\tjira\tpulled"]
    return []


# --- GitHub ----------------------------------------------------------------------


def _sync_github(toplevel: str, tracker: Tracker) -> list[str]:
    env = os.environ.copy()
    if not env.get("GITHUB_TOKEN"):
        token = _gh(toplevel, ["auth", "token"])
        if token.returncode != 0 or not token.stdout.strip():
            return [f"TRACKER\tFAILED\tgithub\tgh auth token: {_tail(token)}"]
        env["GITHUB_TOKEN"] = token.stdout.strip()

    r = _bd(toplevel, ["github", "sync", "--push-only"], env)
    if r.returncode != 0:
        return [f"TRACKER\tFAILED\tgithub\tbd github sync --push-only: {_tail(r)}"]

    try:
        changed = _bridge_status(toplevel, tracker)
    except _GhFailed as e:
        return [f"TRACKER\tFAILED\tgithub\t{e}"]
    return [f"TRACKER\tOK\tgithub\tpushed\tstatus_changed={changed}"]


class _GhFailed(RuntimeError):
    pass


def _bridge_status(toplevel: str, tracker: Tracker) -> int:
    """Project の Status 欄を Beads の状態に揃える。書き換えた件数を返す。"""
    owner, number = tracker.project_owner or "", tracker.project_number or ""
    project = _gh_json(toplevel, ["project", "view", number, "--owner", owner, "--format", "json"])
    fields = _gh_json(toplevel, ["project", "field-list", number, "--owner", owner, "--format", "json"])
    status_field = next((f for f in fields.get("fields", []) if f.get("name") == "Status"), None)
    if status_field is None:
        raise _GhFailed("Project に Status 欄が無い")
    options = {o.get("name"): o.get("id") for o in status_field.get("options", [])}
    missing = [n for n in STATUS_OPTIONS.values() if n not in options]
    if missing:
        raise _GhFailed("Status 欄に選択肢が無い: " + ", ".join(missing))
    items = _gh_json(
        toplevel, ["project", "item-list", number, "--owner", owner, "--format", "json", "-L", "10000"]
    ).get("items", [])
    by_url = {(i.get("content") or {}).get("url"): i for i in items if isinstance(i, dict)}

    default_repo = _default_repo(toplevel)
    changed = 0
    for issue in beads.list_issues(toplevel):
        url = _issue_url(issue.external_ref, default_repo)
        if url is None:
            continue
        want = STATUS_OPTIONS.get(beads.workflow_state(issue))
        if want is None:
            continue
        item = by_url.get(url)
        if item is None:
            item = _gh_json(toplevel, ["project", "item-add", number, "--owner", owner, "--url", url, "--format", "json"])
        if item.get("status") == want:
            continue
        r = _gh(
            toplevel,
            [
                "project",
                "item-edit",
                "--id",
                str(item.get("id")),
                "--project-id",
                str(project.get("id")),
                "--field-id",
                str(status_field.get("id")),
                "--single-select-option-id",
                str(options[want]),
            ],
        )
        if r.returncode != 0:
            raise _GhFailed(f"gh project item-edit {url}: {_tail(r)}")
        changed += 1
    return changed


def _issue_url(external_ref: str | None, default_repo: str | None) -> str | None:
    if not external_ref:
        return None
    ref = external_ref.strip()
    if ISSUE_URL.match(ref):
        return ref
    m = ISSUE_NUMBER.match(ref)
    if m and default_repo:
        return f"https://github.com/{default_repo}/issues/{m.group(1)}"
    return None


def _default_repo(toplevel: str) -> str | None:
    for key in ("github.repository",):
        r = beads.run(toplevel, ["config", "get", key])
        value = r.stdout.strip()
        if r.returncode == 0 and "/" in value and " " not in value:
            return value
    owner = beads.run(toplevel, ["config", "get", "github.owner"]).stdout.strip()
    repo = beads.run(toplevel, ["config", "get", "github.repo"]).stdout.strip()
    if owner and repo and " " not in owner + repo:
        return f"{owner}/{repo}"
    return None


# --- 呼び出し ----------------------------------------------------------------------


def _bd(toplevel: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([beads.BD, *args], cwd=toplevel, capture_output=True, text=True, env=env)
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))


def _gh(toplevel: str, args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh", *args], cwd=toplevel, capture_output=True, text=True)
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))


def _gh_json(toplevel: str, args: list[str]) -> dict:
    r = _gh(toplevel, args)
    if r.returncode != 0:
        raise _GhFailed(f"gh {' '.join(args[:2])}: {_tail(r)}")
    try:
        data = json.loads(r.stdout)
    except ValueError as e:
        raise _GhFailed(f"gh {' '.join(args[:2])} の JSON が読めない: {e}") from e
    return data if isinstance(data, dict) else {}


def _tail(r: subprocess.CompletedProcess) -> str:
    text = ((r.stderr or "") + (r.stdout or "")).strip().replace("\t", " ")
    return " / ".join(text.splitlines()[-3:]) or f"終了コード {r.returncode}"
