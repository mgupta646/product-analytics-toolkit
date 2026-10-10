"""Event-log analytics: funnels and cohort retention.

An event is a dict with at least: user_id, event, ts (datetime). Extra keys
(variant, platform, …) can be used to segment.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


def load_csv(path: str | Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["ts"] = datetime.fromisoformat(r["ts"])
        if r.get("revenue") not in (None, ""):
            r["revenue"] = float(r["revenue"])
    return rows


@dataclass
class FunnelStep:
    step: str
    users: int
    conv_from_prev: float
    conv_from_start: float
    drop_off: int


def funnel(events: list[dict], steps: list[str], segment: str | None = None) -> dict[str, list[FunnelStep]]:
    """Ordered funnel: a user counts at step k only if they did steps 1..k in order.

    Returns {segment_value: [FunnelStep, …]} ('all' when not segmented).
    """
    by_user: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_user[e["user_id"]].append(e)
    reached: dict[str, list[int]] = defaultdict(lambda: [0] * len(steps))
    for user, evs in by_user.items():
        evs.sort(key=lambda e: e["ts"])
        key = evs[0].get(segment, "unknown") if segment else "all"
        k, last_ts = 0, None
        for e in evs:
            if k < len(steps) and e["event"] == steps[k] and (last_ts is None or e["ts"] >= last_ts):
                reached[key][k] += 1
                last_ts, k = e["ts"], k + 1
    out = {}
    for key, counts in sorted(reached.items()):
        rows = []
        for i, (name, n) in enumerate(zip(steps, counts)):
            prev = counts[i - 1] if i else n
            rows.append(FunnelStep(name, n, n / prev if prev else 0.0, n / counts[0] if counts[0] else 0.0, (prev - n) if i else 0))
        out[key] = rows
    return out


def retention(events: list[dict], period_days: int = 7, periods: int = 6, activity: str | None = None,
              min_cohort: int = 50) -> list[tuple[str, int, list[float]]]:
    """Cohort retention: cohort = period of first event; retained in period k if active k periods later.

    Returns [(cohort_label, cohort_size, [share active in period 0..periods-1])].
    """
    first: dict[str, datetime] = {}
    active: dict[str, set[int]] = defaultdict(set)
    for e in sorted(events, key=lambda e: e["ts"]):
        first.setdefault(e["user_id"], e["ts"])
    start = min(first.values())
    start = datetime(start.year, start.month, start.day)
    for e in events:
        if activity and e["event"] != activity:
            continue
        cohort_idx = (first[e["user_id"]] - start).days // period_days
        idx = (e["ts"] - start).days // period_days - cohort_idx
        active[e["user_id"]].add(idx)
    cohorts: dict[int, list[str]] = defaultdict(list)
    for u, ts in first.items():
        cohorts[(ts - start).days // period_days].append(u)
    out = []
    for c in sorted(cohorts):
        users = cohorts[c]
        if len(users) < min_cohort:  # tiny tail cohorts are noise
            continue
        label = (start + timedelta(days=c * period_days)).strftime("%b %d")
        shares = []
        for k in range(periods):
            shares.append(sum(1 for u in users if k in active[u]) / len(users))
        out.append((label, len(users), shares))
    return out
