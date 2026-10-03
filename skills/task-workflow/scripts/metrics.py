"""`tw metrics`: 台帳の `flow/` の記録（`ledger.record_event`）から、期間ごとの流れの数を出す。

出力は TSV で、行頭が数の名前、2列目が今の期間、3列目が前の同じ長さの期間。
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import ledger

DAYS_DEFAULT = 7
VERIFY_FAILED_RESULTS = ("FORMAT_FAILED", "VERIFY_NOT_PASSED")
HIGHER_IS_WORSE = (
    "lead_median_seconds",
    "lead_max_seconds",
    "verify_per_task",
    "verify_failed",
    "ship_verify_failed",
    "reclaim",
)
LOWER_IS_WORSE = ("shipped", "reflection_none_ratio")


@dataclass(frozen=True, eq=False)
class Event:
    at: datetime
    kind: str
    task: str
    fields: dict


def _parse_row(line: str) -> Event | None:
    try:
        row = json.loads(line)
        at = datetime.fromisoformat(row["t"])
        if at.tzinfo is None:
            return None
        return Event(at, str(row["event"]), str(row["task"]), row)
    except (ValueError, KeyError, TypeError):
        return None


def read_events(root: str) -> tuple[list[Event], int]:
    """`(出来事を時刻順に, 読み飛ばした壊れた行の数)`。"""
    d = ledger.flow_dir(root)
    if not os.path.isdir(d):
        return [], 0
    events: list[Event] = []
    skipped = 0
    for name in sorted(os.listdir(d)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(d, name), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip() == "":
                    continue
                event = _parse_row(line)
                if event is None:
                    skipped += 1
                else:
                    events.append(event)
    return sorted(events, key=lambda e: e.at), skipped


def _number(value: str) -> float | None:
    """`12`・`2.0`・`50% (1/2)` の先頭の数。`-` は `None`。"""
    head = value.split("%")[0].strip()
    try:
        return float(head)
    except ValueError:
        return None


def _lead_seconds(events: list[Event], shipped: Event) -> float | None:
    claims = [e for e in events if e.kind == "claim" and e.task == shipped.task and e.at <= shipped.at]
    return (shipped.at - claims[-1].at).total_seconds() if claims else None


def _column(events: list[Event], start: datetime, end: datetime) -> dict[str, str]:
    inside = [e for e in events if start <= e.at < end]
    shipped = [e for e in inside if e.kind == "ship" and e.fields.get("result") == "SHIPPED"]
    leads = [s for s in (_lead_seconds(events, e) for e in shipped) if s is not None]
    verifies = [e for e in inside if e.kind == "verify"]
    verify_tasks = {e.task for e in verifies}
    reclaims = [
        e
        for e in inside
        if e.kind == "claim"
        and any(r.kind == "release" and r.task == e.task for r in events[: events.index(e)])
    ]
    dones = [e for e in inside if e.kind == "done" and not e.fields.get("dropped")]
    clean = [e for e in dones if e.fields.get("reflection") == "none"]
    return {
        "shipped": str(len(shipped)),
        "lead_median_seconds": str(round(statistics.median(leads))) if leads else "-",
        "lead_max_seconds": str(round(max(leads))) if leads else "-",
        "verify_per_task": f"{len(verifies) / len(verify_tasks):.1f}" if verifies else "-",
        "verify_failed": str(sum(1 for e in verifies if e.fields.get("result") in VERIFY_FAILED_RESULTS)),
        "ship_verify_failed": str(sum(1 for e in inside if e.kind == "ship" and e.fields.get("result") == "VERIFY_FAILED")),
        "reclaim": str(len(reclaims)),
        "reflection_none_ratio": f"{round(100 * len(clean) / len(dones))}% ({len(clean)}/{len(dones)})" if dones else "-",
    }


def columns(events: list[Event], days: int) -> tuple[dict[str, str], dict[str, str]]:
    """`(直近 days 日の数, その前の同じ長さの期間の数)`。"""
    now = datetime.now(timezone.utc)
    span = timedelta(days=days)
    return _column(events, now - span, now + timedelta(seconds=1)), _column(events, now - 2 * span, now - span)


def worse(name: str, current: str, previous: str) -> bool:
    """前の期間より悪くなったか。どちらかが `-` なら比べない。"""
    now, before = _number(current), _number(previous)
    if now is None or before is None:
        return False
    if name in LOWER_IS_WORSE:
        return now < before
    return name in HIGHER_IS_WORSE and now > before


def cmd_metrics(toplevel: str, days: int) -> None:
    if days < 1:
        print("usage: --days は1以上", file=sys.stderr)
        raise SystemExit(2)
    events, skipped = read_events(ledger.ledger_root(cwd=toplevel))
    if not events:
        print("EMPTY")
        if skipped:
            print(f"SKIPPED\t{skipped}")
        return
    current, previous = columns(events, days)
    print(f"PERIOD\t{days}d\tcurrent\tprevious")
    for name, value in current.items():
        print(f"{name}\t{value}\t{previous[name]}")
    if skipped:
        print(f"SKIPPED\t{skipped}")
