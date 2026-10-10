"""Static HTML dashboard (Chart.js from a CDN for the funnel; everything else is inline SVG/HTML)."""
from __future__ import annotations

import json
from html import escape

from .events import FunnelStep
from .experiment import ExperimentResult
from .stats import sample_size_per_arm

CSS = """
:root{--ink:#172033;--mute:#64708a;--line:#e3e7ef;--bg:#f5f7fb;--a:#94a3b8;--b:#7c3aed;--ok:#15803d;--bad:#b91c1c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1120px;margin:0 auto;padding:32px 20px 60px}h1{margin:0;font-size:30px}h2{margin:32px 0 12px;font-size:20px}
.sub{color:var(--mute);margin:6px 0 20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 18px}.card small{color:var(--mute);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.4px}
.card b{display:block;font-size:26px;margin:4px 0}.up{color:var(--ok)}.down{color:var(--bad)}.verdict{border-left:6px solid var(--ok);background:#effbf2;padding:14px 18px;border-radius:10px;font-weight:600}
.verdict.warn{border-color:#d97706;background:#fff8eb}.two{display:grid;grid-template-columns:1.2fr 1fr;gap:14px;margin-top:14px}@media(max-width:860px){.two{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}th{background:#f0f3f9}
.heat td{text-align:center;font-variant-numeric:tabular-nums}.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700}
.pill.ok{background:#dcfce7;color:var(--ok)}.pill.no{background:#f1f5f9;color:var(--mute)}footer{margin-top:40px;color:var(--mute);font-size:13.5px}
"""


def _pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def _p(p: float) -> str:
    return "p < 0.0001" if p < 0.0001 else f"p = {p:.4f}"


def _forest(rows: list[tuple[str, float, float, float, bool]]) -> str:
    """Forest plot of absolute differences with CIs: [(label, diff, lo, hi, significant)]"""
    lo = min(r[2] for r in rows + [("", 0, 0, 0, False)])
    hi = max(r[3] for r in rows + [("", 0, 0, 0, False)])
    pad = (hi - lo) * 0.15 or 0.01
    lo, hi = lo - pad, hi + pad
    W, row_h, left = 560, 44, 150
    x = lambda v: left + (v - lo) / (hi - lo) * (W - left - 20)  # noqa: E731
    H = row_h * len(rows) + 40
    svg = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Lift with 95% confidence intervals">',
           f'<line x1="{x(0)}" y1="10" x2="{x(0)}" y2="{H - 26}" stroke="#94a3b8" stroke-dasharray="4 4"/>',
           f'<text x="{x(0)}" y="{H - 8}" font-size="12" text-anchor="middle" fill="#64708a">no change</text>']
    for i, (label, d, l, h, sig) in enumerate(rows):
        y = 30 + i * row_h
        col = "#15803d" if sig and d > 0 else "#b91c1c" if sig else "#64708a"
        svg += [f'<text x="0" y="{y + 4}" font-size="14" fill="#172033">{escape(label)}</text>',
                f'<line x1="{x(l)}" y1="{y}" x2="{x(h)}" y2="{y}" stroke="{col}" stroke-width="3" stroke-linecap="round"/>',
                f'<circle cx="{x(d)}" cy="{y}" r="6" fill="{col}"/>',
                f'<text x="{x(h) + 8}" y="{y + 4}" font-size="12.5" fill="{col}">{d * 100:+.2f} pts</text>']
    return "".join(svg) + "</svg>"


def render(res: ExperimentResult, funnels: dict[str, list[FunnelStep]], retention: list, title: str = "Checkout redesign experiment") -> str:
    conv, rpu, cc = res.conversion, res.revenue_per_user, res.checkout_completion
    n_c, n_v = res.srm.observed
    mde_n = sample_size_per_arm(conv.control_rate, 0.01)
    arrow = lambda t: f'<span class="{"up" if t.abs_diff > 0 else "down"}">{t.rel_lift:+.1%}</span>'  # noqa: E731
    cards = f"""<div class="grid">
<div class="card"><small>Purchase conversion</small><b>{_pct(conv.control_rate, 2)} → {_pct(conv.variant_rate, 2)}</b>{arrow(conv)} · {_p(conv.p_value)}</div>
<div class="card"><small>Checkout completion</small><b>{_pct(cc.control_rate)} → {_pct(cc.variant_rate)}</b>{arrow(cc)} · {_p(cc.p_value)}</div>
<div class="card"><small>Revenue per user</small><b>${rpu.control_mean:.2f} → ${rpu.variant_mean:.2f}</b>{arrow(rpu)} · {_p(rpu.p_value)}</div>
<div class="card"><small>Sample ratio (SRM)</small><b>{n_c:,} / {n_v:,}</b>{'<span class="down">mismatch</span>' if res.srm.mismatch else '<span class="up">balanced</span>'} · p = {res.srm.p_value:.3f}</div></div>"""
    forest = [("All users", conv.abs_diff, conv.ci_low, conv.ci_high, conv.significant)] + \
             [(s.segment.title(), s.conversion.abs_diff, s.conversion.ci_low, s.conversion.ci_high, s.conversion.significant) for s in res.segments]
    seg_rows = "".join(
        f"<tr><td>{escape(s.segment.title())}</td><td style='white-space:nowrap'>{s.n_control:,} / {s.n_variant:,}</td><td>{_pct(s.conversion.control_rate, 2)}</td><td>{_pct(s.conversion.variant_rate, 2)}</td>"
        f"<td>{s.conversion.rel_lift:+.1%}</td><td style='white-space:nowrap'>{_p(s.conversion.p_value).replace('p = ', '')}</td><td><span class='pill {'ok' if s.conversion.significant else 'no'}'>{'significant' if s.conversion.significant else 'not significant'}</span></td></tr>"
        for s in res.segments)
    labels = [s.step.replace("_", " ") for s in next(iter(funnels.values()))]
    datasets = [{"label": f"Variant {k}", "data": [round(100 * s.conv_from_start, 2) for s in v],
                 "backgroundColor": "#94a3b8" if k == "A" else "#7c3aed", "borderRadius": 6} for k, v in funnels.items()]
    drop_rows = "".join(
        "<tr><td>" + escape(a.step.replace('_', ' ')) + "</td>" + "".join(f"<td>{_pct(f[i].conv_from_prev)}</td>" for f in funnels.values()) + "</tr>"
        for i, a in enumerate(next(iter(funnels.values()))) if i)
    heat_head = "".join(f"<th>Week {k}</th>" for k in range(len(retention[0][2])))
    heat_rows = "".join(
        f"<tr><td>{label}</td><td>{n:,}</td>" + "".join(
            f"<td style='background:rgba(124,58,237,{0.08 + 0.85 * s:.2f});color:{'#fff' if s > 0.45 else '#172033'}'>{_pct(s, 0)}</td>" for s in shares) + "</tr>"
        for label, n, shares in retention)
    verdict_cls = "verdict warn" if res.srm.mismatch or not conv.significant else "verdict"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{CSS}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script></head><body><main>
<h1>{escape(title)}</h1>
<p class="sub">Variant B simplifies checkout. {n_c + n_v:,} users, randomized 50/50, six weeks of synthetic data. Analysed with
<a href="https://github.com/mgupta646/product-analytics-toolkit">product-analytics-toolkit</a>.</p>
<div class="{verdict_cls}">{escape(res.verdict)}</div>
<h2>Results</h2>{cards}
<div class="two"><div class="card"><h2 style="margin-top:0">Lift by segment (95% CI)</h2>{_forest(forest)}
<p class="sub">The effect is concentrated on mobile, where the old checkout lost the most users. Desktop alone wouldn't justify the change.</p></div>
<div class="card"><h2 style="margin-top:0">Segments</h2><table><thead><tr><th>Platform</th><th>Users A / B</th><th>A</th><th>B</th><th>Lift</th><th>p</th><th></th></tr></thead><tbody>{seg_rows}</tbody></table>
<p class="sub">Planning note: detecting a 1-point change from a {_pct(conv.control_rate, 1)} baseline needs ~{mde_n:,} users per arm (α = 0.05, power = 80%).</p></div></div>
<h2>Funnel</h2><div class="two"><div class="card"><canvas id="funnel" height="250"></canvas></div>
<div class="card"><table><thead><tr><th>Step conversion</th>{''.join(f'<th>{escape(k)}</th>' for k in funnels)}</tr></thead><tbody>{drop_rows}</tbody></table>
<p class="sub">Only the last step should move: the redesign touched checkout, not discovery. Earlier steps matching between arms is a useful sanity check.</p></div></div>
<h2>Weekly retention by cohort</h2><div class="card" style="overflow:auto"><table class="heat"><thead><tr><th>Cohort</th><th>Users</th>{heat_head}</tr></thead><tbody>{heat_rows}</tbody></table></div>
<footer>Synthetic data generated by <code>pakit.simulate</code>. Statistics are closed-form and dependency-free; see <code>pakit/stats.py</code>.</footer>
</main>
<script>
new Chart(document.getElementById('funnel'), {{type:'bar', data:{{labels:{json.dumps(labels)}, datasets:{json.dumps(datasets)}}},
 options:{{plugins:{{title:{{display:true,text:'% of visitors reaching each step'}}}}, scales:{{y:{{beginAtZero:true,ticks:{{callback:v=>v+'%'}}}}}}}}}});
</script></body></html>"""
