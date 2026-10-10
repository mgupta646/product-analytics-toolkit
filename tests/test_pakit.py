"""Reference values in this file were computed independently with SciPy (scipy.stats)."""
import math
import random
from datetime import datetime, timedelta

import pytest

from pakit import analyse, funnel, mean_test, retention, sample_size_per_arm, srm_check, two_proportion_test, wilson
from pakit.cli import main
from pakit.simulate import STEPS, generate
from pakit.stats import norm_cdf, norm_ppf


# ---------------------------------------------------------------- distributions
@pytest.mark.parametrize("p, expected", [(0.975, 1.959963984540054), (0.001, -3.090232306167813), (0.5, 0.0)])
def test_norm_ppf_matches_scipy(p, expected):
    assert norm_ppf(p) == pytest.approx(expected, abs=1e-9)


def test_norm_cdf_matches_scipy():
    assert norm_cdf(1.96) == pytest.approx(0.9750021048517795, abs=1e-12)


# ---------------------------------------------------------------- tests
def test_two_proportion_matches_scipy():
    t = two_proportion_test(1200, 10000, 1290, 10000)
    assert t.z == pytest.approx(1.927590426492286, abs=1e-9)
    assert t.p_value == pytest.approx(0.05390609060200967, abs=1e-9)
    assert not t.significant and t.ci_low < 0 < t.ci_high      # CI agrees with the test
    assert t.rel_lift == pytest.approx(0.075)


def test_welch_mean_test_close_to_scipy_t_test():
    r = random.Random(1)
    a = [r.gauss(10, 2) for _ in range(500)]
    b = [r.gauss(10.4, 2) for _ in range(500)]
    assert mean_test(a, b).p_value == pytest.approx(0.5971130603299871, abs=0.002)  # z vs t at df≈998


def test_wilson_interval():
    lo, hi = wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-4) and hi == pytest.approx(0.5962, abs=1e-4)
    assert wilson(0, 0) == (0.0, 0.0)


def test_srm_matches_scipy_chi2():
    c = srm_check(50210, 49230)
    assert c.chi2 == pytest.approx(9.658085277554305, abs=1e-9)
    assert c.p_value == pytest.approx(0.0018852000826349664, abs=1e-12)
    assert not c.mismatch                      # 0.0019 > 0.001 alarm threshold
    assert srm_check(52000, 48000).mismatch


def test_sample_size_achieves_target_power():
    base, mde = 0.12, 0.01
    n = sample_size_per_arm(base, mde)
    p1, p2 = base, base + mde
    se = math.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / n)
    power = 1 - norm_cdf(norm_ppf(0.975) * math.sqrt(2 * ((p1 + p2) / 2) * (1 - (p1 + p2) / 2) / n) / se - mde / se)
    assert power == pytest.approx(0.80, abs=0.01)
    with pytest.raises(ValueError):
        sample_size_per_arm(0.99, 0.05)


# ---------------------------------------------------------------- funnels & retention
def ev(u, e, minutes, **kw):
    return {"user_id": u, "event": e, "ts": datetime(2026, 1, 1) + timedelta(minutes=minutes), **kw}


def test_funnel_requires_order():
    events = [ev("a", "visit", 0), ev("a", "cart", 1), ev("a", "buy", 2),
              ev("b", "visit", 0), ev("b", "buy", 1),                    # skipped cart
              ev("c", "cart", 0), ev("c", "visit", 1)]                   # cart before visit
    f = funnel(events, ["visit", "cart", "buy"])["all"]
    assert [s.users for s in f] == [3, 1, 1]
    assert f[1].conv_from_prev == pytest.approx(1 / 3) and f[1].drop_off == 2


def test_funnel_segments():
    events = [ev("a", "visit", 0, v="A"), ev("b", "visit", 0, v="B"), ev("b", "buy", 1, v="B")]
    f = funnel(events, ["visit", "buy"], segment="v")
    assert f["A"][1].users == 0 and f["B"][1].users == 1


def test_retention_counts_return_weeks():
    events = [ev("a", "visit", 0), ev("a", "visit", 60 * 24 * 8), ev("b", "visit", 0)]
    (label, size, shares), = retention(events, periods=3, min_cohort=1)
    assert size == 2 and shares == [1.0, 0.5, 0.0]


# ---------------------------------------------------------------- end to end
@pytest.fixture(scope="module")
def sim():
    return generate(n_users=80000)


def test_simulated_experiment_finds_the_mobile_effect(sim):
    res = analyse(sim)
    assert not res.srm.mismatch
    assert res.conversion.significant and res.conversion.abs_diff > 0
    seg = {s.segment: s.conversion for s in res.segments}
    assert seg["mobile"].significant and not seg["desktop"].significant
    assert res.verdict.startswith("Ship it")


def test_srm_blocks_the_verdict(sim):
    # drop a third of variant-B users: classic broken-assignment bug
    skewed = [e for e in sim if not (e["variant"] == "B" and int(e["user_id"][1:]) % 3 == 0)]
    res = analyse(skewed)
    assert res.srm.mismatch and res.verdict.startswith("Do not ship")


def test_upper_funnel_unaffected(sim):
    f = funnel(sim, STEPS, segment="variant")
    a, b = f["A"], f["B"]
    assert abs(a[2].conv_from_start - b[2].conv_from_start) < 0.01   # add_to_cart: same in both arms


def test_cli(tmp_path, capsys):
    assert main(["abtest", "--control", "1200/10000", "--variant", "1290/10000"]) == 0
    assert "not significant" in capsys.readouterr().out
    assert main(["samplesize", "--baseline", "0.12", "--mde", "0.01"]) == 0
    assert main(["srm", "--counts", "52000", "48000"]) == 0
    assert "MISMATCH" in capsys.readouterr().out
