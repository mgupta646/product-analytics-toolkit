"""Synthetic e-commerce event log for a checkout-redesign A/B test.

Scenario: variant B simplifies checkout (fewer form fields, saved payment).
It should mostly help the checkout_start → purchase step, and help mobile
more than desktop. Everything is seeded and synthetic.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

STEPS = ["visit", "view_product", "add_to_cart", "checkout_start", "purchase"]
BASE = {"desktop": [1.0, 0.62, 0.30, 0.62, 0.66], "mobile": [1.0, 0.55, 0.24, 0.55, 0.52]}
LIFT_B = {"desktop": 1.03, "mobile": 1.15}  # multiplier on checkout_start -> purchase


def generate(n_users: int = 80000, seed: int = 11, start: datetime = datetime(2026, 5, 4)) -> list[dict]:
    rng = random.Random(seed)
    events = []
    for i in range(n_users):
        uid = f"u{i:06d}"
        platform = "mobile" if rng.random() < 0.58 else "desktop"
        variant = "B" if rng.random() < 0.5 else "A"
        t = start + timedelta(days=rng.randrange(42), minutes=rng.randrange(24 * 60))
        probs = list(BASE[platform])
        if variant == "B":
            probs[4] = min(0.95, probs[4] * LIFT_B[platform])
        for step, p in zip(STEPS, probs):
            if rng.random() > p:
                break
            t += timedelta(seconds=rng.randint(20, 600))
            row = {"user_id": uid, "event": step, "ts": t, "variant": variant, "platform": platform, "revenue": ""}
            if step == "purchase":
                row["revenue"] = round(rng.lognormvariate(3.9, 0.45), 2)
            events.append(row)
        # return visits drive retention: purchasers come back more often
        bought = events and events[-1]["user_id"] == uid and events[-1]["event"] == "purchase"
        for week in range(1, 6):
            if rng.random() < (0.32 if bought else 0.12) * (0.82 ** (week - 1)):
                events.append({"user_id": uid, "event": "visit", "ts": t + timedelta(days=7 * week + rng.randint(-2, 2)),
                               "variant": variant, "platform": platform, "revenue": ""})
    return events


def write_csv(events: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["user_id", "event", "ts", "variant", "platform", "revenue"])
        w.writeheader()
        for e in events:
            w.writerow({**e, "ts": e["ts"].isoformat(sep=" ")})
