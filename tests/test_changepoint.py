"""
Regression tests for app.changepoint -- the local-regression-
discontinuity break detector, as distinct from forecasting.py (ordinary
trend) and seasonality.py (repeating calendar pattern).
"""
import numpy as np

from app.changepoint import detect_changepoint
from app.seasonality import decompose_trend


def _labels(n, start_year=2021):
    out, y, m = [], start_year, 1
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def test_no_break_in_pure_noise():
    rng = np.random.default_rng(2)
    labels = _labels(36)
    values = [100 + rng.normal(0, 10) for _ in range(36)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]
    assert detect_changepoint(trend_data)["available"] is False


def test_gradual_trend_is_not_mistaken_for_a_break():
    """A smooth, continuous climb is forecasting.py's territory, not
    this module's -- splitting late in any growing series shows SOME
    mean gap just because the back half is bigger, so this specifically
    guards against that false positive."""
    rng = np.random.default_rng(3)
    labels = _labels(36)
    values = [100 + i * 2 + rng.normal(0, 5) for i in range(36)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]
    assert detect_changepoint(trend_data)["available"] is False


def test_detects_a_clean_step_change_at_the_right_point():
    rng = np.random.default_rng(1)
    labels = _labels(36)
    values = [100 + rng.normal(0, 5) for _ in range(24)] + [150 + rng.normal(0, 5) for _ in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    result = detect_changepoint(trend_data)
    assert result["available"]
    bp = result["break_point"]
    assert bp["label"] == "2023-01"  # the 25th point -- where the step actually happens
    assert bp["direction"] == "jump"
    assert 40 <= bp["change_pct"] <= 58
    assert bp["before_count"] == 24
    assert bp["after_count"] == 12
    assert bp["p_value"] < 0.05


def test_detects_a_step_on_top_of_an_ongoing_trend():
    """The break should still be found at the right point even when
    there's a real trend running through both sides of it -- a step
    doesn't have to mean a flat series on either side."""
    rng = np.random.default_rng(5)
    labels = _labels(36)
    values = (
        [100 + i * 1.5 + rng.normal(0, 5) for i in range(24)]
        + [100 + 24 * 1.5 + 50 + (i - 24) * 1.5 + rng.normal(0, 5) for i in range(24, 36)]
    )
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    result = detect_changepoint(trend_data)
    assert result["available"]
    assert result["break_point"]["label"] == "2023-01"


def test_detects_a_drop_not_just_a_jump():
    rng = np.random.default_rng(9)
    labels = _labels(30)
    values = [200 + rng.normal(0, 5) for _ in range(18)] + [120 + rng.normal(0, 5) for _ in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    result = detect_changepoint(trend_data)
    assert result["available"]
    assert result["break_point"]["direction"] == "drop"
    assert result["break_point"]["change_pct"] < 0


def test_too_few_points_returns_unavailable():
    trend_data = [{"label": f"2022-{m:02d}", "value": 100 + m} for m in range(1, 7)]
    result = detect_changepoint(trend_data)
    assert result["available"] is False
    assert result["break_point"] is None


def test_small_shift_below_minimum_change_is_not_reported():
    """Statistically detectable but economically trivial (a 3% wobble)
    shouldn't be reported as a structural break."""
    rng = np.random.default_rng(11)
    labels = _labels(40)
    values = [100 + rng.normal(0, 0.5) for _ in range(20)] + [103 + rng.normal(0, 0.5) for _ in range(20)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]
    assert detect_changepoint(trend_data)["available"] is False


def test_seasonality_aware_path_recovers_the_true_break_date():
    """Without deseasonalizing, a big Dec-to-Jan seasonal cliff can be
    mistaken for the break; given a real seasonal_by_month, the true
    break date should be recovered instead."""
    true_seasonal = {1: -20, 2: -30, 3: -10, 4: 0, 5: 5, 6: 10, 7: 15, 8: 10, 9: 5, 10: 0, 11: 10, 12: 40}
    labels = _labels(36)

    # Learn a clean seasonal_by_month from a separate, jump-free series
    # with the same seasonal pattern (mirrors how main.py gets it from
    # decompose_trend on the real historical data).
    rng = np.random.default_rng(3)
    clean_values = [100 + i * 2 + true_seasonal[int(l.split("-")[1])] + rng.normal(0, 2) for i, l in enumerate(labels)]
    clean_trend_data = [{"label": l, "value": v} for l, v in zip(labels, clean_values)]
    seasonality = decompose_trend(clean_trend_data)
    assert seasonality["available"]

    # A separate series with a real jump at index 24, plus the same seasonal pattern.
    rng2 = np.random.default_rng(7)
    jump_values = []
    for i, l in enumerate(labels):
        month = int(l.split("-")[1])
        base = 100 if i < 24 else 140
        jump_values.append(base + true_seasonal[month] + rng2.normal(0, 2))
    jump_trend_data = [{"label": l, "value": v} for l, v in zip(labels, jump_values)]

    plain_result = detect_changepoint(jump_trend_data)
    deseasonalized_result = detect_changepoint(jump_trend_data, seasonal_by_month=seasonality["seasonal_by_month"])

    assert deseasonalized_result["available"]
    assert deseasonalized_result["break_point"]["label"] == "2023-01"
    # The plain (non-deseasonalized) run either disagrees on where the break is,
    # or doesn't find one at all -- demonstrating deseasonalizing is doing real work.
    assert not plain_result["available"] or plain_result["break_point"]["label"] != "2023-01"


def test_seasonal_offsets_missing_a_month_falls_back_to_plain():
    """An incomplete offsets dict shouldn't half-apply -- falls back to
    the plain (non-deseasonalized) path, same convention as
    forecasting.py."""
    rng = np.random.default_rng(1)
    labels = _labels(36)
    values = [100 + rng.normal(0, 5) for _ in range(24)] + [150 + rng.normal(0, 5) for _ in range(12)]
    trend_data = [{"label": l, "value": v} for l, v in zip(labels, values)]

    incomplete_offsets = {1: 5.0, 2: -5.0}  # only 2 of 12 months covered
    result = detect_changepoint(trend_data, seasonal_by_month=incomplete_offsets)
    plain = detect_changepoint(trend_data)
    assert result == plain
