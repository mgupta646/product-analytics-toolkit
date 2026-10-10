"""Analyse an A/B test from an event log: SRM first, then conversion, revenue and segments."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .stats import MeanTest, ProportionTest, SRMCheck, mean_test, srm_check, two_proportion_test


@dataclass
class SegmentResult:
    segment: str
    n_control: int
    n_variant: int
    conversion: ProportionTest


@dataclass
class ExperimentResult:
    srm: SRMCheck
    conversion: ProportionTest          # purchasers / assigned users
    checkout_completion: ProportionTest  # purchasers / users who started checkout
    revenue_per_user: MeanTest
    segments: list[SegmentResult] = field(default_factory=list)
    verdict: str = ""


def _users(events: list[dict], variant_key: str) -> dict[str, dict]:
    users: dict[str, dict] = {}
    for e in events:
        u = users.setdefault(e["user_id"], {"variant": e[variant_key], "events": set(), "revenue": 0.0, "platform": e.get("platform")})
        u["events"].add(e["event"])
        if e.get("revenue") not in (None, ""):
            u["revenue"] += float(e["revenue"])
    return users


def analyse(events: list[dict], control: str = "A", variant: str = "B", goal: str = "purchase",
            checkout: str = "checkout_start", segment: str | None = "platform", variant_key: str = "variant") -> ExperimentResult:
    users = _users(events, variant_key)
    groups: dict[str, list[dict]] = defaultdict(list)
    for u in users.values():
        groups[u["variant"]].append(u)
    c, v = groups[control], groups[variant]
    srm = srm_check(len(c), len(v))

    def conv(cs, vs, denom_event=None):
        cs2 = [u for u in cs if denom_event is None or denom_event in u["events"]]
        vs2 = [u for u in vs if denom_event is None or denom_event in u["events"]]
        return two_proportion_test(sum(goal in u["events"] for u in cs2), len(cs2), sum(goal in u["events"] for u in vs2), len(vs2))

    res = ExperimentResult(
        srm=srm,
        conversion=conv(c, v),
        checkout_completion=conv(c, v, checkout),
        revenue_per_user=mean_test([u["revenue"] for u in c], [u["revenue"] for u in v]),
    )
    if segment:
        for seg in sorted({u[segment] for u in users.values()}):
            cs, vs = [u for u in c if u[segment] == seg], [u for u in v if u[segment] == seg]
            res.segments.append(SegmentResult(seg, len(cs), len(vs), conv(cs, vs)))

    if srm.mismatch:
        res.verdict = "Do not ship yet: the traffic split doesn't match the design (sample ratio mismatch), so the comparison isn't trustworthy."
    elif res.conversion.significant and res.conversion.abs_diff > 0:
        res.verdict = (f"Ship it: conversion is up {res.conversion.rel_lift:+.1%} (95% CI {res.conversion.ci_low:+.2%} to {res.conversion.ci_high:+.2%} "
                       f"absolute), with no sample ratio mismatch.")
    elif res.conversion.significant:
        res.verdict = "Don't ship: the variant significantly lowers conversion."
    else:
        res.verdict = "Inconclusive: the difference is within noise. Keep running if the planned sample size hasn't been reached."
    return res
