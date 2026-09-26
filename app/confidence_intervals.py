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

Also exposes bootstrap_metric_significance, a general-purpose version of
the same idea for callers whose claim isn't a single overall KPI but a
comparison or a share (weak_points.py's detectors: "this segment
underperforms by 22%", "this share is way above expected") -- resample
the same groups the claim was built from, recompute the caller's own
metric on each draw, and report whether the resulting interval clears
the threshold that made the claim worth flagging in the first place.
"""
import math
import numpy as np
import pandas as pd

N_BOOTSTRAP = 1000
MAX_BOOTSTRAP_ROWS = 20_000
MIN_ROWS = 10
MAX_MEASURES = 6

N_BOOTSTRAP_SIGNIFICANCE = 300  # lighter than N_BOOTSTRAP -- this runs per weak point, sometimes several per dataset


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


def bootstrap_metric_significance(
    groups: dict,
    metric_fn,
    reference: float = 0.0,
    n_boot: int = N_BOOTSTRAP_SIGNIFICANCE,
    seed: int = 42,
) -> "dict | None":
    """General-purpose bootstrap significance test for a claim that isn't
    a single overall KPI -- a gap between a segment and the average, a
    share of a total, a margin, a percent change between two periods.

    groups: {name: values} -- one entry per group of ROWS the claim is
    built from (e.g. {"first_year": ..., "last_year": ...}, or
    {"segment": ...} when the claim only needs one). Pass a 1-D
    np.ndarray when metric_fn only needs a single column from that
    group's rows; pass a pandas DataFrame (or Series) when it needs more
    than one column from the SAME rows together (e.g. a revenue and a
    profit column for a margin) -- resampling a DataFrame draws whole
    rows, so columns that must stay paired don't get shuffled apart from
    each other. Each group is resampled with replacement at its own true
    size on every draw, capped at MAX_BOOTSTRAP_ROWS for speed on very
    large groups (same cap and same "point estimate is exact, only the
    interval's width is approximated on very large data" tradeoff as
    compute_kpi_confidence_intervals above).

    metric_fn(resampled: dict) -> float | None -- recomputes exactly the
    metric the caller already computed on the real data (a % change, a
    gap, a margin, a share), reading from the same-keyed dict of
    resampled groups. Return None for a draw that can't produce a valid
    number (e.g. a resample with nothing in the segment, or a zero
    denominator) -- it's excluded rather than poisoning the interval.

    reference is the boundary that made the underlying finding worth
    flagging in the first place -- 0 for "is this gap/margin/change even
    real", or the specific threshold the detector used (e.g. the -5%
    decline cutoff, or the share the detector considered "way above
    normal"). significant is True only when the bootstrap interval
    doesn't straddle that boundary, i.e. resampling essentially never
    landed back on the "not actually a problem" side.

    Returns None (not a result with significant=False) when there isn't
    enough data to trust the interval at all -- a group with under 2 rows,
    or too many draws failing to produce a usable value -- so callers can
    tell "checked, and it didn't hold up" apart from "couldn't check"."""
    rng = np.random.default_rng(seed)
    capped = {}
    for key, values in groups.items():
        n = len(values)
        if n < 2:
            return None
        if n <= MAX_BOOTSTRAP_ROWS:
            capped[key] = values
        elif isinstance(values, (pd.DataFrame, pd.Series)):
            capped[key] = values.sample(n=MAX_BOOTSTRAP_ROWS, random_state=seed)
        else:
            capped[key] = rng.choice(np.asarray(values), size=MAX_BOOTSTRAP_ROWS, replace=False)

    draws = []
    for _ in range(n_boot):
        resampled = {}
        for key, values in capped.items():
            n = len(values)
            if isinstance(values, (pd.DataFrame, pd.Series)):
                resampled[key] = values.iloc[rng.integers(0, n, size=n)]
            else:
                resampled[key] = rng.choice(np.asarray(values), size=n, replace=True)
        val = metric_fn(resampled)
        if val is None:
            continue
        val = float(val)
        if math.isnan(val) or math.isinf(val):
            continue
        draws.append(val)

    if len(draws) < n_boot * 0.5:
        return None

    ci_low, ci_high = (float(x) for x in np.percentile(draws, [2.5, 97.5]))
    return {"ci_low": ci_low, "ci_high": ci_high, "significant": not (ci_low <= reference <= ci_high)}
