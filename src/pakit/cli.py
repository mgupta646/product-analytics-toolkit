"""`pakit demo` · `pakit abtest` · `pakit samplesize` · `pakit srm`"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .stats import sample_size_per_arm, srm_check, two_proportion_test

ROOT = Path(__file__).resolve().parents[2]


def _counts(s: str) -> tuple[int, int]:
    x, n = s.split("/")
    return int(x), int(n)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="pakit", description="Product analytics: A/B tests, funnels, retention.")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="simulate the checkout experiment and build the dashboard")
    d.add_argument("--out", default=str(ROOT / "docs" / "index.html"))
    d.add_argument("--csv", default=str(ROOT / "data" / "events.csv"))
    a = sub.add_parser("abtest", help="two-proportion test, e.g. --control 1200/10000 --variant 1290/10000")
    a.add_argument("--control", required=True, type=_counts)
    a.add_argument("--variant", required=True, type=_counts)
    s = sub.add_parser("samplesize", help="users per arm for a minimum detectable effect")
    s.add_argument("--baseline", required=True, type=float, help="e.g. 0.12")
    s.add_argument("--mde", required=True, type=float, help="absolute, e.g. 0.01 for +1 point")
    s.add_argument("--power", type=float, default=0.8)
    r = sub.add_parser("srm", help="sample ratio mismatch check, e.g. --counts 50210 49230")
    r.add_argument("--counts", nargs=2, type=int, required=True)
    args = p.parse_args(argv)

    if args.cmd == "abtest":
        t = two_proportion_test(*args.control, *args.variant)
        print(f"control {t.control_rate:.4%} · variant {t.variant_rate:.4%} · lift {t.rel_lift:+.2%}")
        print(f"diff {t.abs_diff:+.4%} (95% CI {t.ci_low:+.4%} to {t.ci_high:+.4%}) · z = {t.z:.3f} · p = {t.p_value:.5f} · "
              f"{'SIGNIFICANT' if t.significant else 'not significant'}")
    elif args.cmd == "samplesize":
        n = sample_size_per_arm(args.baseline, args.mde, power=args.power)
        print(f"{n:,} users per arm ({2 * n:,} total) to detect {args.baseline:.2%} → {args.baseline + args.mde:.2%}")
    elif args.cmd == "srm":
        c = srm_check(*args.counts)
        print(f"chi2 = {c.chi2:.2f} · p = {c.p_value:.6f} · {'SAMPLE RATIO MISMATCH: investigate before reading results' if c.mismatch else 'split looks fine'}")
    else:
        from .dashboard import render
        from .events import funnel, retention
        from .experiment import analyse
        from .simulate import STEPS, generate, write_csv
        events = generate()
        write_csv(events, args.csv)
        res = analyse(events)
        html = render(res, funnel(events, STEPS, segment="variant"), retention(events))
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(html, encoding="utf-8")
        c = res.conversion
        print(f"{len(events):,} events · conversion {c.control_rate:.2%} → {c.variant_rate:.2%} ({c.rel_lift:+.1%}, p = {c.p_value:.4f})")
        for sgm in res.segments:
            print(f"  {sgm.segment:8} {sgm.conversion.rel_lift:+.1%}  p = {sgm.conversion.p_value:.4f}")
        print(f"verdict: {res.verdict}\ndashboard → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
