"""product-analytics-toolkit: A/B tests, funnels and retention with zero dependencies."""
from .events import funnel, load_csv, retention
from .experiment import analyse
from .stats import mean_test, sample_size_per_arm, srm_check, two_proportion_test, wilson

__all__ = ["analyse", "funnel", "load_csv", "mean_test", "retention", "sample_size_per_arm", "srm_check", "two_proportion_test", "wilson"]
__version__ = "0.1.0"
