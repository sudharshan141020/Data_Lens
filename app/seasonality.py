"""
Seasonality Decomposition.

Separates a monthly trend line (see executor_v2._compute_trend, which
always aggregates to "YYYY-MM" periods) into three components: a smoothed
Trend, a repeating Seasonal pattern tied to calendar month, and whatever's
left over as Residual. Classical additive decomposition -- centered
moving-average trend, seasonal indices from calendar-month averages of the
detrended series -- computed with pandas/numpy only, no statsmodels,
consistent with the "no external ML/stats library" pattern already set by
correlation_center.py's from-scratch VIF check.

This is a different question from forecasting.py's linear trend: that one
asks "where is this heading"; this one asks "does this repeat every year,
and if so, what's the underlying trend once you strip that repetition
out". Both can run on the same trend data -- forecast_trend still owns the
projected-forward line, this module never appends points, only annotates
the existing ones.

Significance, not just a strength threshold: with few years of history,
random noise can produce a high "seasonal strength" purely because each
calendar month's index is fit from only 1-2 observations -- that's
overfitting, not a real pattern (verified empirically while building this:
2.5 years of pure noise produced a strength of 0.72, which would have been
a false positive). So a one-way ANOVA F-test on the detrended series,
grouped by calendar month, gates whether a pattern is reported at all --
same spirit as correlation_center.py gating correlations on a p-value
rather than trusting r alone on a small sample.
"""
from typing import Optional
import numpy as np
import pandas as pd

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a listed dependency
    _HAS_SCIPY = False

PERIOD = 12                      # monthly data, yearly seasonality
MIN_POINTS_FOR_SEASONALITY = 36  # 3 full cycles -- see module docstring on why 24 wasn't enough
SIGNIFICANCE_ALPHA = 0.05

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December",
}


def _month_of(label: str) -> Optional[int]:
    """Trend labels are 'YYYY-MM' strings."""
    try:
        return int(label.split("-")[1])
    except (ValueError, AttributeError, IndexError):
        return None


def _centered_moving_average(y: np.ndarray, period: int) -> np.ndarray:
    """Textbook 2xP centered moving average for an even period: a trailing
    P-length average, then a 2-term average of that to re-center it exactly
    on each point (a plain P-length rolling mean is off-center by half a
    period when P is even). NaN at both ends where the window doesn't fit --
    that's expected and handled by the caller, not a bug."""
    s = pd.Series(y)
    ma = s.rolling(window=period, center=True).mean()
    centered = ma.rolling(window=2, center=True).mean()
    # pandas centers a 2-window as (i-1, i) by default rather than (i, i+1) --
    # shift back one so it lines up with the same index the period-MA used.
    return centered.shift(-1).to_numpy()


def _anova_p_value(groups: list) -> Optional[float]:
    """One-way ANOVA p-value testing whether calendar-month means differ
    more than within-month noise would explain. None if it can't be
    computed (e.g. scipy unavailable) -- callers treat that as
    "can't confirm, don't report" rather than guessing."""
    if not _HAS_SCIPY:
        return None
    try:
        _f_stat, p = _scipy_stats.f_oneway(*groups)
        return float(p)
    except (ValueError, ZeroDivisionError):
        return None


def decompose_trend(trend_data: list, period: int = PERIOD) -> dict:
    """trend_data is [{"label": "2023-01", "value": 123.0}, ...], already
    sorted chronologically -- the same shape forecast_trend consumes.
    Returns {"available": False, "note": ...} when there isn't enough
    history or the apparent pattern isn't statistically significant,
    otherwise the full decomposition plus a plain-English summary of the
    strongest seasonal peak/trough."""
    n = len(trend_data)
    if n < MIN_POINTS_FOR_SEASONALITY:
        years = n / period
        return {
            "available": False,
            "note": f"Needs at least 3 years of monthly history to check for a repeating yearly pattern "
                    f"with confidence -- this dataset has about {years:.1f}.",
        }

    months = [_month_of(p["label"]) for p in trend_data]
    if any(m is None for m in months):
        return {"available": False, "note": "Couldn't read calendar months from the trend data."}

    y = np.array([p["value"] for p in trend_data], dtype=float)
    trend = _centered_moving_average(y, period)
    detrended = y - trend  # NaN wherever trend is NaN (the edges)

    month_arr = np.array(months)
    groups = [detrended[(month_arr == m) & ~np.isnan(detrended)] for m in range(1, period + 1)]
    if any(len(g) < 2 for g in groups):
        return {"available": False, "note": "Not enough complete yearly cycles yet for every calendar month to be tested reliably."}

    p_value = _anova_p_value(groups)
    if p_value is None:
        return {"available": False, "note": "Couldn't test whether an apparent pattern is statistically significant in this environment."}
    if p_value >= SIGNIFICANCE_ALPHA:
        return {
            "available": False,
            "note": f"No statistically significant yearly pattern detected (p={p_value:.2f}) -- "
                    f"month-to-month swings look more like trend and noise than a genuine seasonal cycle.",
        }

    # Seasonal index per calendar month: mean detrended value for that month
    # across every year it appears, then normalized so the 12 indices sum to
    # ~0 -- the additive-decomposition convention (a "seasonal effect" that
    # didn't net out to zero would really just be part of the trend).
    raw_seasonal_by_month = {m: float(np.mean(g)) for m, g in zip(range(1, period + 1), groups)}
    overall_of_raw = float(np.mean(list(raw_seasonal_by_month.values())))
    seasonal_by_month = {m: v - overall_of_raw for m, v in raw_seasonal_by_month.items()}
    seasonal = np.array([seasonal_by_month[m] for m in months])
    residual = y - trend - seasonal  # still NaN at the edges, same positions as trend

    valid = ~np.isnan(trend)
    resid_valid = residual[valid]
    trend_valid = trend[valid]
    seasonal_valid = seasonal[valid]

    def _strength(remainder, other):
        var_r = np.var(remainder)
        var_combined = np.var(remainder + other)
        if var_combined <= 0:
            return 0.0
        return float(max(0.0, min(1.0, 1 - var_r / var_combined)))

    seasonal_strength = _strength(resid_valid, seasonal_valid)
    trend_strength = _strength(resid_valid, trend_valid)

    overall_mean = float(y.mean())
    peak_month_num = max(seasonal_by_month, key=seasonal_by_month.get)
    trough_month_num = min(seasonal_by_month, key=seasonal_by_month.get)
    peak_val = seasonal_by_month[peak_month_num]
    trough_val = seasonal_by_month[trough_month_num]
    peak_pct = round(100 * peak_val / overall_mean, 1) if overall_mean else None
    trough_pct = round(100 * trough_val / overall_mean, 1) if overall_mean else None

    summary = (
        f"{MONTH_NAMES[peak_month_num]} tends to run "
        f"{f'{abs(peak_pct)}% above' if peak_pct is not None else 'above'} the yearly average; "
        f"{MONTH_NAMES[trough_month_num]} tends to run "
        f"{f'{abs(trough_pct)}% below' if trough_pct is not None else 'below'} it "
        f"(p={p_value:.3f})."
    )

    points = []
    for i, p in enumerate(trend_data):
        points.append({
            "label": p["label"],
            "value": round(float(y[i]), 2),
            "trend": round(float(trend[i]), 2) if not np.isnan(trend[i]) else None,
            "seasonal": round(float(seasonal[i]), 2),
            "residual": round(float(residual[i]), 2) if not np.isnan(residual[i]) else None,
        })

    return {
        "available": True,
        "note": None,
        "period_months": period,
        "years_covered": round(n / period, 1),
        "p_value": round(p_value, 4),
        "seasonal_strength": round(seasonal_strength, 2),
        "trend_strength": round(trend_strength, 2),
        "peak_month": {"name": MONTH_NAMES[peak_month_num], "pct": peak_pct},
        "trough_month": {"name": MONTH_NAMES[trough_month_num], "pct": trough_pct},
        "summary": summary,
        "points": points,
    }
