"""
Changepoint / Structural Break Detection.

forecasting.py and seasonality.py both assume the series moves
smoothly -- a gradual trend, a repeating calendar pattern. Neither is
built to notice a sudden, one-time jump: a price change, a policy
shift, a broken data pipeline, a new market opening. A break like that
just gets averaged into the trend line instead of called out as "this
is where something changed" -- a different failure mode than either of
those two modules catches.

The approach: scan every plausible place to split the series into a
"before" and "after", and score each split by how big a DISCONTINUITY
it would take to explain the data there -- fit a separate straight
line to each side, and compare where the left side's own line would
land right at the boundary against where the right side's own line
starts. A big, standardized gap between those two points means
something changed abruptly right there; a small gap means the series
was already headed that way on its own trend, break or no break. This
is what makes it a true break detector rather than just a trend
detector with extra steps: a single smoothly growing series has
~zero gap at every candidate split (both local lines agree with each
other at the boundary, because there's nothing of the sort), while a
sudden jump -- with or without an underlying trend running through it
-- shows a large one exactly where the jump is. An earlier version of
this that simply detrended the whole series with one global line first
looked reasonable but actually broke on a pure step change: a single
straight line fit through flat-then-flat data compromises between the
two levels, which smears the discontinuity and can shift the detected
break date away from where it actually happened. Comparing LOCAL lines
at each candidate boundary, rather than removing one GLOBAL line up
front, doesn't have that failure mode.

Whether the best split found is significant at all is judged by a
permutation test (shuffle the series, rerun the same best-split
search, repeat many times, see how often shuffled data would produce
as strong a "break" as the real one) rather than reading the best
split's statistic off a textbook t-distribution -- deliberately
searching for the strongest break out of many candidate split points
means the usual textbook p-value for a single comparison would be too
optimistic. Same "resample and see how often this could happen by
chance" idea the rest of this app already leans on
(confidence_intervals.py, weak_points.py), applied here to a
different kind of claim.

Seasonality-aware the same way forecasting.py is: given a significant
seasonal pattern from seasonality.decompose_trend(), the scan runs on
the deseasonalized series first, so a predictable December spike never
gets mistaken for a structural break. Falls back to the raw series
unchanged when no seasonal pattern is available.

Scoped to the overall trend only (the same one measure/metric
forecast_trend and decompose_trend already operate on) -- not
per-segment. A reasonable next step, not this one.
"""
from typing import Optional
import numpy as np

MIN_POINTS_FOR_CHANGEPOINT = 8
MIN_SEGMENT_SIZE = 4            # points required on each side of a candidate split -- enough to fit a stable local line
N_PERMUTATIONS = 1000
SIGNIFICANCE_ALPHA = 0.05
MIN_CHANGE_PCT = 15.0           # minimum relative shift to be worth reporting, even if "significant"
RANDOM_SEED = 42


def _month_of(label: str) -> Optional[int]:
    try:
        return int(label.split("-")[1])
    except (ValueError, AttributeError, IndexError):
        return None


def _deseasonalize(trend_data: list, y: np.ndarray, seasonal_by_month: dict) -> Optional[np.ndarray]:
    out = np.empty_like(y)
    for i, p in enumerate(trend_data):
        m = _month_of(p["label"])
        if m is None or m not in seasonal_by_month:
            return None
        out[i] = y[i] - seasonal_by_month[m]
    return out


def _best_split(values: np.ndarray, min_segment: int) -> tuple:
    """For every candidate split i, fits a separate straight line to
    values[:i] and values[i:] and scores it by the standardized gap
    between where the left line's own trend would land right at the
    boundary and where the right line's own trend starts there -- see
    module docstring for why a local discontinuity, not a global
    detrend, is what correctly separates "a break happened" from "this
    is just an ordinary trend." Returns (best_split_index, best_stat).

    Vectorized across every candidate split at once via cumulative
    sums, rather than fitting each split's two lines with a
    np.polyfit call in a Python loop -- this runs inside a ~1000-draw
    permutation test (see detect_changepoint), so the per-candidate
    approach was measured taking several seconds per call on a
    realistic-length series; this closed-form version does the same
    simple-linear-regression math (least squares has a closed form for
    one predictor) in a handful of array operations instead, over a
    thousand times faster with identical results."""
    n = len(values)
    if n < 2 * min_segment:
        return None, -1.0

    y = values
    # Running sums over y[0:i] for i = 0..n (index i holds the sum of the
    # first i points), so sum(y[:i]) is a single lookup rather than a
    # fresh pass over the array for every candidate split.
    cs_y = np.concatenate(([0.0], np.cumsum(y)))
    cs_y2 = np.concatenate(([0.0], np.cumsum(y * y)))
    # sum(j * y[j]) for j = 0..i-1, i.e. y weighted by its GLOBAL index --
    # valid as-is for the left segment (whose local x matches the global
    # index, since it starts at 0); re-based for the right segment below.
    idx = np.arange(n, dtype=float)
    cs_xy = np.concatenate(([0.0], np.cumsum(idx * y)))

    candidates = np.arange(min_segment, n - min_segment + 1)
    n1 = candidates.astype(float)
    n2 = n - n1

    # ---- left segment: local x == global x == 0..n1-1 ----
    sum_y1 = cs_y[candidates]
    sum_xy1 = cs_xy[candidates]
    sum_y2_1 = cs_y2[candidates]
    xbar1 = (n1 - 1) / 2
    ybar1 = sum_y1 / n1
    sxx1 = n1 * (n1 - 1) * (n1 + 1) / 12            # sum((x-xbar)^2) for x=0..n1-1, closed form
    sxy1 = sum_xy1 - n1 * xbar1 * ybar1
    slope1 = np.divide(sxy1, sxx1, out=np.zeros_like(sxy1), where=sxx1 > 0)
    intercept1 = ybar1 - slope1 * xbar1
    syy1 = sum_y2_1 - n1 * ybar1 ** 2
    sse1 = np.maximum(syy1 - slope1 * sxy1, 0.0)     # standard OLS SSE = Syy - slope*Sxy
    var1 = sse1 / np.maximum(n1 - 1, 1)
    left_edge = slope1 * (n1 - 1) + intercept1       # left line's own value at its last point

    # ---- right segment: local x = 0..n2-1, corresponding to global index candidates..n-1 ----
    total_y, total_y2, total_xy = cs_y[n], cs_y2[n], cs_xy[n]
    sum_y2seg = total_y - sum_y1
    sum_y2_2 = total_y2 - sum_y2_1
    # sum of (global index)*y over the right segment, then re-based to LOCAL
    # index (subtract i * sum_y) so it matches x'=0..n2-1 starting at the split.
    sum_xy_global_right = total_xy - sum_xy1
    sum_xy2 = sum_xy_global_right - candidates * sum_y2seg
    xbar2 = (n2 - 1) / 2
    ybar2 = sum_y2seg / n2
    sxx2 = n2 * (n2 - 1) * (n2 + 1) / 12
    sxy2 = sum_xy2 - n2 * xbar2 * ybar2
    slope2 = np.divide(sxy2, sxx2, out=np.zeros_like(sxy2), where=sxx2 > 0)
    intercept2 = ybar2 - slope2 * xbar2
    syy2 = sum_y2_2 - n2 * ybar2 ** 2
    sse2 = np.maximum(syy2 - slope2 * sxy2, 0.0)
    var2 = sse2 / np.maximum(n2 - 1, 1)
    right_edge = intercept2                           # right line's own value at its first point

    denom = np.sqrt(var1 / n1 + var2 / n2)
    stats = np.divide(np.abs(right_edge - left_edge), denom, out=np.zeros_like(denom), where=denom > 0)

    best_pos = int(np.argmax(stats))
    return int(candidates[best_pos]), float(stats[best_pos])


def detect_changepoint(trend_data: list, seasonal_by_month: Optional[dict] = None) -> dict:
    """trend_data is [{"label": "2023-01", "value": 123.0}, ...], already
    sorted chronologically -- the same shape forecast_trend and
    decompose_trend take, and should be called with the same real
    historical points only (no forecasted tail mixed in).

    Returns {"available": bool, "note": str | None, "break_point": dict | None}.
    break_point, when present, has: label (first period of the "after"
    segment), before_label/after_label (first and last period of each
    segment, for a human-readable range), before_mean, after_mean,
    change_pct, direction ("jump" | "drop"), p_value, before_count,
    after_count, summary (a plain-language sentence)."""
    n = len(trend_data)
    if n < MIN_POINTS_FOR_CHANGEPOINT:
        return {"available": False, "note": None, "break_point": None}

    y_raw = np.array([p["value"] for p in trend_data], dtype=float)

    y = y_raw
    if seasonal_by_month:
        deseasonalized = _deseasonalize(trend_data, y_raw, seasonal_by_month)
        if deseasonalized is not None:
            y = deseasonalized

    split_i, observed_stat = _best_split(y, MIN_SEGMENT_SIZE)
    if split_i is None or observed_stat <= 0:
        return {"available": False, "note": None, "break_point": None}

    rng = np.random.default_rng(RANDOM_SEED)
    exceed_count = 0
    for _ in range(N_PERMUTATIONS):
        shuffled = rng.permutation(y)
        _, perm_stat = _best_split(shuffled, MIN_SEGMENT_SIZE)
        if perm_stat >= observed_stat:
            exceed_count += 1
    p_value = (exceed_count + 1) / (N_PERMUTATIONS + 1)

    if p_value >= SIGNIFICANCE_ALPHA:
        return {"available": False, "note": None, "break_point": None}

    before_mean = float(y[:split_i].mean())
    after_mean = float(y[split_i:].mean())
    if before_mean == 0:
        return {"available": False, "note": None, "break_point": None}
    change_pct = (after_mean - before_mean) / abs(before_mean) * 100

    if abs(change_pct) < MIN_CHANGE_PCT:
        return {"available": False, "note": None, "break_point": None}

    direction = "jump" if change_pct > 0 else "drop"
    label = trend_data[split_i]["label"]
    before_label = trend_data[0]["label"]
    before_end_label = trend_data[split_i - 1]["label"]
    after_label = trend_data[-1]["label"]

    summary = (
        f"Something changed around {label} -- the average shifted from {before_mean:,.2f} "
        f"({before_label} to {before_end_label}) to {after_mean:,.2f} ({label} to {after_label}), "
        f"a {abs(change_pct):.0f}% {direction}. This looks like a one-time shift rather than a "
        f"gradual trend -- worth checking what happened around that date (a price or policy change, "
        f"a new market, a data pipeline issue) rather than reading it as part of the overall trend."
    )

    return {
        "available": True,
        "note": None,
        "break_point": {
            "label": label,
            "before_label": before_label,
            "before_end_label": before_end_label,
            "after_label": after_label,
            "before_mean": round(before_mean, 2),
            "after_mean": round(after_mean, 2),
            "change_pct": round(change_pct, 1),
            "direction": direction,
            "p_value": round(p_value, 4),
            "before_count": int(split_i),
            "after_count": int(n - split_i),
            "summary": summary,
        },
    }
