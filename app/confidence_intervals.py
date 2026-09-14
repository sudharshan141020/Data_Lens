"""
Confidence Intervals on KPIs.

A KPI like "average order value: $177" is a single point estimate --
this adds the honest second half of that sentence: how much would that
number plausibly move if the underlying process generated a slightly
different set of orders? Answered via bootstrap resampling (resample the
actual rows with replacement, many times, recompute the statistic each
time, take the 2.5th/97.5th percentiles as a 95% interval) rather than a
textbook formula -- consistent with the "from scratch, no external stats
library beyond numpy/scipy" pattern the rest of this app follows, and it
makes no distributional assumption about the underlying data (unlike the
classic mean +/- 1.96*SE formula, which assumes something closer to
normality).

Performance: bootstrapping the full column B times is O(B x n). For
very large datasets that's needlessly expensive for a number whose whole
point is to communicate roughly how much a KPI might wobble -- same
performance-conscious sampling pattern as clustering.py and
anomaly_detection.py, with the same disclosure when it kicks in.
"""
import numpy as np
import pandas as pd

N_BOOTSTRAP = 1000
MAX_BOOTSTRAP_ROWS = 20_000
MIN_ROWS = 10
MAX_MEASURES = 6


def compute_kpi_confidence_intervals(df: pd.DataFrame, profile) -> dict:
    measures = profile.measures[:MAX_MEASURES]
    if not measures:
        return {"available": False, "note": "No numeric measures to estimate.", "intervals": []}

    rng = np.random.default_rng(42)
    intervals = []
    sampled_any = False

    for m in measures:
        full_values = df[m.column].dropna().to_numpy(dtype=float)
        n_true = len(full_values)
        if n_true < MIN_ROWS:
            continue

        # The point estimate is always the real number from the complete
        # data (cheap to compute exactly regardless of size) -- only the
        # CI's *width* comes from bootstrapping, and only that part gets
        # sampled down for speed on very large datasets.
        true_mean = float(np.mean(full_values))
        point = true_mean if m.aggregation == "avg" else true_mean * n_true

        sampled = n_true > MAX_BOOTSTRAP_ROWS
        boot_base = rng.choice(full_values, size=MAX_BOOTSTRAP_ROWS, replace=False) if sampled else full_values
        if sampled:
            sampled_any = True

        # Bootstrap the MEAN's sampling distribution (stable regardless of
        # aggregation), then scale to a sum using the TRUE row count --
        # scaling by the sampled subset's size would be wrong even though
        # that's what was actually resampled.
        base_n = len(boot_base)
        boot_means = np.empty(N_BOOTSTRAP)
        for i in range(N_BOOTSTRAP):
            boot_means[i] = rng.choice(boot_base, size=base_n, replace=True).mean()

        mean_low, mean_high = np.percentile(boot_means, [2.5, 97.5])
        if m.aggregation == "avg":
            low, high = float(mean_low), float(mean_high)
        else:
            low, high = float(mean_low * n_true), float(mean_high * n_true)

        margin = (high - low) / 2
        relative_margin_pct = round(100 * margin / abs(point), 1) if point else None

        intervals.append({
            "measure": m.column,
            "aggregation": m.aggregation,
            "point_estimate": round(point, 2),
            "ci_low": round(low, 2),
            "ci_high": round(high, 2),
            "relative_margin_pct": relative_margin_pct,
        })

    if not intervals:
        return {"available": False, "note": f"Needs at least {MIN_ROWS} non-missing values in a measure to estimate a confidence interval.", "intervals": []}

    note = "The interval width was estimated from a random sample of 20,000 rows for speed; the point estimates themselves use all rows." if sampled_any else None
    return {"available": True, "note": note, "intervals": intervals}
