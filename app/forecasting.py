"""
Trend forecasting.

Purely rule-based, consistent with the rest of the app's "no LLM calls"
design constraint: a simple linear regression fitted over the existing
monthly trend points, projected forward a few periods. This is a rough
estimate, not a predictive model -- explicitly labeled as such, and gated
behind an R^2 threshold so a flat or noisy trend doesn't get a misleading
straight-line projection tacked onto it.

Seasonality-aware: when the caller has a significant seasonal pattern
from seasonality.decompose_trend() (a calendar-month -> additive offset
map), forecast_trend deseasonalizes the series before fitting the line
and reapplies the right offset to each projected future month, instead
of fitting a straight line through the seasonal wobble. Without one --
no significant pattern, or not enough history for seasonality.py to even
test for one -- this falls back to the original plain-linear behavior
unchanged.
"""
from typing import Optional
import numpy as np

MIN_POINTS_FOR_FORECAST = 6
FORECAST_PERIODS = 3
MIN_R2_FOR_FORECAST = 0.3


def _next_month_label(label: str) -> Optional[str]:
    """Trend labels are 'YYYY-MM' strings (see executor_v2._compute_trend,
    which builds them via `.dt.to_period("M").astype(str)`)."""
    try:
        year_s, month_s = label.split("-")
        year, month = int(year_s), int(month_s)
    except (ValueError, AttributeError):
        return None
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


def _month_of(label: str) -> Optional[int]:
    """Same 'YYYY-MM' parsing as seasonality._month_of -- duplicated
    rather than imported so this module still degrades cleanly (plain
    linear forecast) if it's ever used standalone."""
    try:
        return int(label.split("-")[1])
    except (ValueError, AttributeError, IndexError):
        return None


def _deseasonalize(trend_data: list, y: np.ndarray, seasonal_by_month: dict) -> Optional[np.ndarray]:
    """Subtracts the calendar-month seasonal offset from each point.
    Returns None (caller falls back to plain linear) if any label's month
    can't be read or isn't covered by seasonal_by_month, rather than
    silently leaving some points seasonally-adjusted and others not."""
    out = np.empty_like(y)
    for i, p in enumerate(trend_data):
        m = _month_of(p["label"])
        if m is None or m not in seasonal_by_month:
            return None
        out[i] = y[i] - seasonal_by_month[m]
    return out


def forecast_trend(
    trend_data: list,
    periods_ahead: int = FORECAST_PERIODS,
    seasonal_by_month: Optional[dict] = None,
) -> dict:
    """trend_data is [{"label": "2023-01", "value": 123.0}, ...], already
    sorted chronologically. seasonal_by_month, when given, is the
    calendar-month -> additive offset map from a significant
    seasonality.decompose_trend() result on this same data -- pass it and
    the line is fit on the deseasonalized series, with each projected
    point's own calendar-month offset added back in. Returns
    {"forecast_points": [...], "note": str or None} -- forecast_points is
    empty when there isn't enough data or the linear fit is too weak to be
    worth projecting; note explains why when that happens, so the UI can
    say something useful instead of silently showing nothing."""
    n = len(trend_data)
    if n < MIN_POINTS_FOR_FORECAST:
        return {"forecast_points": [], "note": None}

    x_full = np.arange(n, dtype=float)
    y_raw_full = np.array([p["value"] for p in trend_data], dtype=float)

    seasonally_adjusted = False
    if seasonal_by_month:
        deseasonalized = _deseasonalize(trend_data, y_raw_full, seasonal_by_month)
        if deseasonalized is not None:
            y_full = deseasonalized
            seasonally_adjusted = True
        else:
            y_full = y_raw_full
    else:
        y_full = y_raw_full

    # A dataset's most recent period is often a partial one -- data
    # collection simply stopped mid-month. That makes the last point's sum
    # artificially low compared to every full period before it, which
    # would otherwise drag the fitted line down and make the forecast
    # visually "jump" up from a misleadingly low last point. Detect this
    # conservatively (last point far below both the established trend AND
    # the historical minimum -- not just a genuine recent downturn, which
    # should still be reflected) and fit on the prior points instead.
    excluded_last = False
    if n >= MIN_POINTS_FOR_FORECAST + 1:
        slope_chk, intercept_chk = np.polyfit(x_full[:-1], y_full[:-1], 1)
        predicted_last = slope_chk * x_full[-1] + intercept_chk
        if predicted_last > 0 and y_full[-1] < 0.25 * predicted_last and y_full[-1] < y_full[:-1].min():
            excluded_last = True

    if excluded_last:
        x, y, fit_labels = x_full[:-1], y_full[:-1], trend_data[:-1]
    else:
        x, y, fit_labels = x_full, y_full, trend_data

    try:
        slope, intercept = np.polyfit(x, y, 1)
    except (np.linalg.LinAlgError, ValueError):
        return {"forecast_points": [], "note": None}

    y_pred = slope * x + intercept
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    if r_squared < MIN_R2_FOR_FORECAST:
        return {
            "forecast_points": [],
            "note": f"No clear enough trend to forecast reliably (fit quality R\u00b2={r_squared:.2f}).",
        }

    true_last_index = n - 1
    label = trend_data[-1]["label"]  # always continue from the true last period's label,
    forecast_points = []              # never the (possibly earlier) last-fitted period's label,
    for i in range(1, periods_ahead + 1):  # so labels never duplicate or skip.
        label = _next_month_label(label)
        if label is None:
            break
        trend_component = slope * (true_last_index + i) + intercept
        if seasonally_adjusted:
            future_month = _month_of(label)
            offset = seasonal_by_month.get(future_month, 0.0) if future_month is not None else 0.0
            projected = trend_component + offset
        else:
            projected = trend_component
        forecast_points.append({"label": label, "value": round(float(projected), 2), "is_forecast": True})

    if not forecast_points:
        return {"forecast_points": [], "note": None}

    direction = "upward" if slope > 0 else "downward" if slope < 0 else "flat"
    if seasonally_adjusted:
        note = (
            f"Projected {len(forecast_points)} month{'s' if len(forecast_points) != 1 else ''} ahead "
            f"using a seasonally-adjusted trend ({direction} once the yearly pattern is stripped out, "
            f"R\u00b2={r_squared:.2f}) -- the underlying trend is projected forward, then each month's "
            f"typical seasonal swing is added back in. A rough estimate, not a guarantee."
        )
    else:
        note = (
            f"Projected {len(forecast_points)} month{'s' if len(forecast_points) != 1 else ''} ahead "
            f"using a linear trend ({direction}, R\u00b2={r_squared:.2f}) -- a rough estimate based on "
            f"the existing pattern, not a guarantee."
        )
    if excluded_last:
        note += " The most recent period looked incomplete, so it was excluded from the trend calculation."
    return {"forecast_points": forecast_points, "note": note}
