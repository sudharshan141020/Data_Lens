"""
Regression tests for app.forecasting -- both the original plain-linear
path and the new seasonality-aware path (deseasonalize, fit the trend,
reapply the calendar-month offset to each projected point).
"""
import numpy as np

from app.forecasting import forecast_trend
from app.seasonality import decompose_trend


def _labels_from(year: int, month: int, n: int):
    labels = []
    for _ in range(n):
        labels.append(f"{year}-{month:02d}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return labels


# ------------------------------------------------------------- plain linear

def test_plain_linear_forecast_continues_clear_trend():
    labels = _labels_from(2022, 1, 12)
    values = [100 + 10 * i for i in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    result = forecast_trend(trend_data)

    assert result["forecast_points"]
    assert result["forecast_points"][0]["label"] == "2023-01"
    # Next point should continue the +10/month line closely (12th point,
    # index 12, on a line starting at 100 with slope 10).
    assert abs(result["forecast_points"][0]["value"] - 220) < 1e-6


def test_declines_below_min_points():
    trend_data = [{"label": f"2024-{m:02d}", "value": 100 + m} for m in range(1, 5)]
    result = forecast_trend(trend_data)
    assert result["forecast_points"] == []
    assert result["note"] is None


def test_declines_on_weak_fit():
    rng = np.random.default_rng(7)
    labels = _labels_from(2022, 1, 12)
    values = [float(rng.normal(100, 20)) for _ in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    result = forecast_trend(trend_data)
    assert result["forecast_points"] == []
    assert "R" in result["note"]  # R\u00b2 quoted back in the explanation


# ------------------------------------------------------- seasonality-aware

def test_seasonal_forecast_matches_known_injected_pattern():
    """36 months of a clean upward trend plus a known seasonal pattern.
    A plain linear fit would try to draw a straight line through the
    seasonal wobble; the seasonality-aware forecast should instead land
    close to trend + that calendar month's true offset."""
    rng = np.random.default_rng(3)
    true_seasonal = {1: -20, 2: -30, 3: -10, 4: 0, 5: 5, 6: 10,
                      7: 15, 8: 10, 9: 5, 10: 0, 11: 10, 12: 40}
    labels = _labels_from(2021, 1, 36)
    trend_data = []
    for i, label in enumerate(labels):
        month = int(label.split("-")[1])
        value = 100 + i * 2 + true_seasonal[month] + float(rng.normal(0, 2))
        trend_data.append({"label": label, "value": value})

    seasonality = decompose_trend(trend_data)
    assert seasonality["available"]

    result = forecast_trend(trend_data, seasonal_by_month=seasonality["seasonal_by_month"])
    assert result["forecast_points"]
    assert "seasonally-adjusted" in result["note"]

    # 2024-01 is index 36 on the same trend line (100 + i*2), true seasonal
    # offset for January is -20.
    jan_point = result["forecast_points"][0]
    assert jan_point["label"] == "2024-01"
    expected = 100 + 36 * 2 + true_seasonal[1]
    assert abs(jan_point["value"] - expected) < 6  # small tolerance for fit noise


def test_seasonal_forecast_falls_back_without_offsets():
    """No seasonal_by_month passed -> identical to the plain path."""
    labels = _labels_from(2022, 1, 12)
    values = [100 + 10 * i for i in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    plain = forecast_trend(trend_data)
    seasonal_but_empty = forecast_trend(trend_data, seasonal_by_month=None)
    assert plain == seasonal_but_empty


def test_seasonal_offsets_missing_a_month_falls_back_to_plain():
    """A malformed/partial offsets dict shouldn't half-apply -- it should
    fall back to the plain linear fit rather than mixing adjusted and
    unadjusted points."""
    labels = _labels_from(2022, 1, 12)
    values = [100 + 10 * i for i in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    incomplete_offsets = {1: 5.0, 2: -5.0}  # only 2 of 12 months covered
    result = forecast_trend(trend_data, seasonal_by_month=incomplete_offsets)
    plain = forecast_trend(trend_data)
    assert result == plain
