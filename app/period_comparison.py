"""
Period-over-Period Comparison.

Compares the most recent complete monthly period against the one before
it -- not just "this month's total minus last month's total", but a
proper two-sample test (Welch's t-test, unequal variance assumed) on the
underlying row-level values from each period. A raw percent change can
look dramatic on a handful of large orders and mean nothing; the t-test
answers the more honest question: given the spread of individual values
in each period, is this difference bigger than you'd expect from chance?

Deliberately NOT gated on significance the way seasonality.py's pattern
detection is -- that gate exists there because testing 12 calendar
months at once is multiple comparisons, where noise can easily produce
one "significant-looking" month by chance. This is a single planned
comparison (last period vs. the one before), so it follows
correlation_center.py's precedent instead: always report the number and
its p-value, and let the reader see both the effect size and how much to
trust it, rather than hiding a real-but-uncertain change.

Uses the exact same "YYYY-MM" monthly grouping as executor_v2._compute_trend
so the periods being compared always match what the trend chart already
shows.
"""
from typing import Optional
import numpy as np
import pandas as pd

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a listed dependency
    _HAS_SCIPY = False

MIN_ROWS_PER_PERIOD = 5
SIGNIFICANCE_ALPHA = 0.05


def _welch_t_test(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if not _HAS_SCIPY:
        return None
    try:
        _t_stat, p = _scipy_stats.ttest_ind(a, b, equal_var=False)
        return float(p)
    except (ValueError, ZeroDivisionError):
        return None


def compare_periods(df: pd.DataFrame, date_column: str, metric_column: str, aggregation: str = "sum") -> dict:
    """df is the full (unfiltered) working dataframe -- this groups it by
    calendar month itself, the same way executor_v2._compute_trend does,
    so it isn't dependent on a trend chart having already been built."""
    tmp = df.dropna(subset=[date_column, metric_column]).copy()
    if tmp.empty:
        return {"available": False, "note": "No rows with both a date and this measure to compare."}

    tmp["_month"] = tmp[date_column].dt.to_period("M").astype(str)
    months = sorted(tmp["_month"].unique())
    if len(months) < 2:
        return {"available": False, "note": "Needs at least two calendar months of data to compare periods."}

    label_a, label_b = months[-1], months[-2]  # most recent complete month vs. the one before
    values_a = tmp.loc[tmp["_month"] == label_a, metric_column].to_numpy(dtype=float)
    values_b = tmp.loc[tmp["_month"] == label_b, metric_column].to_numpy(dtype=float)

    if len(values_a) < MIN_ROWS_PER_PERIOD or len(values_b) < MIN_ROWS_PER_PERIOD:
        return {
            "available": False,
            "note": f"Needs at least {MIN_ROWS_PER_PERIOD} records in each period for a reliable comparison -- "
                    f"{label_b} has {len(values_b)}, {label_a} has {len(values_a)}.",
        }

    stat_a = float(values_a.mean()) if aggregation == "avg" else float(values_a.sum())
    stat_b = float(values_b.mean()) if aggregation == "avg" else float(values_b.sum())
    pct_change = round(100 * (stat_a - stat_b) / stat_b, 1) if stat_b else None

    p_value = _welch_t_test(values_a, values_b)
    significant = p_value is not None and p_value < SIGNIFICANCE_ALPHA

    direction = "up" if stat_a >= stat_b else "down"
    agg_word = "averaged" if aggregation == "avg" else "totaled"
    if p_value is None:
        confidence_note = "(couldn't test significance in this environment)"
    elif significant:
        confidence_note = f"(statistically significant, p={p_value:.3f})"
    else:
        confidence_note = f"(not statistically significant given the sample size, p={p_value:.2f}) -- could just be normal variation"

    pct_text = f"{abs(pct_change)}%" if pct_change is not None else "n/a"
    summary = f"{label_a} {agg_word} {stat_a:,.2f}, {direction} {pct_text} from {label_b} {confidence_note}."

    return {
        "available": True,
        "note": None,
        "metric": metric_column,
        "aggregation": aggregation,
        "period_a": {"label": label_a, "value": round(stat_a, 2), "n": int(len(values_a))},
        "period_b": {"label": label_b, "value": round(stat_b, 2), "n": int(len(values_b))},
        "pct_change": pct_change,
        "p_value": round(p_value, 4) if p_value is not None else None,
        "significant": significant,
        "summary": summary,
    }
