"""Experiment statistics with no dependencies (standard library only).

Everything here is a closed-form, textbook method so results can be checked by hand:
  * two-proportion z-test (pooled SE for the test, unpooled SE for the CI)
  * Wilson score interval for a single rate
  * Welch's z-approximation for a difference in means (large samples)
  * sample size per arm for a target minimum detectable effect
  * sample-ratio-mismatch (SRM) check: chi-square goodness of fit
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9 after one Newton step)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p > hi:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    # one Newton refinement
    e = norm_cdf(x) - p
    return x - e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)


def wilson(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = norm_ppf(1 - (1 - confidence) / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


@dataclass
class ProportionTest:
    control_rate: float
    variant_rate: float
    abs_diff: float
    rel_lift: float
    ci_low: float           # CI on the absolute difference
    ci_high: float
    z: float
    p_value: float
    significant: bool


def two_proportion_test(x_c: int, n_c: int, x_v: int, n_v: int, alpha: float = 0.05) -> ProportionTest:
    if min(n_c, n_v) <= 0:
        raise ValueError("both groups need at least one observation")
    p_c, p_v = x_c / n_c, x_v / n_v
    pooled = (x_c + x_v) / (n_c + n_v)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_c + 1 / n_v))
    z = (p_v - p_c) / se_pooled if se_pooled else 0.0
    p = 2 * (1 - norm_cdf(abs(z)))
    se = math.sqrt(p_c * (1 - p_c) / n_c + p_v * (1 - p_v) / n_v)
    zc = norm_ppf(1 - alpha / 2)
    diff = p_v - p_c
    return ProportionTest(p_c, p_v, diff, diff / p_c if p_c else float("inf"), diff - zc * se, diff + zc * se, z, p, p < alpha)


@dataclass
class MeanTest:
    control_mean: float
    variant_mean: float
    abs_diff: float
    rel_lift: float
    ci_low: float
    ci_high: float
    z: float
    p_value: float
    significant: bool


def _mean_var(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    return m, sum((x - m) ** 2 for x in xs) / (n - 1)


def mean_test(control: list[float], variant: list[float], alpha: float = 0.05) -> MeanTest:
    """Welch-style z test, appropriate for the large samples typical of product experiments."""
    if min(len(control), len(variant)) < 2:
        raise ValueError("need at least two observations per group")
    (m_c, v_c), (m_v, v_v) = _mean_var(control), _mean_var(variant)
    se = math.sqrt(v_c / len(control) + v_v / len(variant))
    diff = m_v - m_c
    z = diff / se if se else 0.0
    p = 2 * (1 - norm_cdf(abs(z)))
    zc = norm_ppf(1 - alpha / 2)
    return MeanTest(m_c, m_v, diff, diff / m_c if m_c else float("inf"), diff - zc * se, diff + zc * se, z, p, p < alpha)


def sample_size_per_arm(baseline: float, mde_abs: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Users per arm to detect an absolute change of `mde_abs` from `baseline` (two-sided)."""
    if not 0 < baseline < 1 or mde_abs <= 0 or baseline + mde_abs >= 1:
        raise ValueError("need 0 < baseline < baseline + mde < 1")
    p1, p2 = baseline, baseline + mde_abs
    za, zb = norm_ppf(1 - alpha / 2), norm_ppf(power)
    pbar = (p1 + p2) / 2
    n = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / mde_abs ** 2
    return math.ceil(n)


@dataclass
class SRMCheck:
    observed: tuple[int, int]
    expected_share: float
    chi2: float
    p_value: float
    mismatch: bool


def srm_check(n_c: int, n_v: int, expected_share: float = 0.5, threshold: float = 0.001) -> SRMCheck:
    """If assignment isn't the split you designed, don't trust the result. p < 0.001 is the usual alarm."""
    total = n_c + n_v
    e_c, e_v = total * expected_share, total * (1 - expected_share)
    chi2 = (n_c - e_c) ** 2 / e_c + (n_v - e_v) ** 2 / e_v
    p = math.erfc(math.sqrt(chi2 / 2))  # chi-square survival function, 1 degree of freedom
    return SRMCheck((n_c, n_v), expected_share, chi2, p, p < threshold)
