"""
Regression tests for the bootstrap significance gating in weak_points.py
(via confidence_intervals.bootstrap_metric_significance) -- both the
"held up under resampling" path and the "downgraded because it might be
noise" path, across detectors using the plain-array bootstrap
(declining_trend) and the paired-DataFrame bootstrap (concentration_risk,
underperforming_segment, margin_risk, discount_risk, outlier_risk).
"""
import numpy as np
import pandas as pd

from app.understanding import understand_dataset
from app.weak_points import (
    declining_trend, outlier_risk, concentration_risk,
    underperforming_segment, margin_risk, discount_risk, missing_data,
)


def _dated(vals_by_year: dict):
    rows_dates, vals = [], []
    for year, vals_for_year in vals_by_year.items():
        vals.extend(vals_for_year)
        rows_dates.extend([pd.Timestamp(f"{year}-06-15")] * len(vals_for_year))
    return pd.DataFrame({"Order_Date": rows_dates, "Sales": vals})


def test_declining_trend_significant_gets_confirmation_note():
    rng = np.random.default_rng(1)
    n = 500
    df = _dated({
        year: base + rng.normal(0, 5, n)
        for year, base in zip([2021, 2022, 2023], [100, 80, 40])
    })
    profile = understand_dataset(df)
    wps = declining_trend(df, profile)
    assert wps
    wp = wps[0]
    assert wp.significant is True
    assert wp.ci_low is not None and wp.ci_high is not None
    assert wp.priority == "high"  # not downgraded
    assert "reshuffling the data" in wp.impact


def test_declining_trend_noisy_gets_downgraded():
    """Same shape of claim (a >5% decline), but small n and high variance
    -- resampling should sometimes erase the decline, so this should come
    back downgraded rather than reported at full confidence."""
    rng = np.random.default_rng(0)
    n = 6
    df = _dated({
        year: base + rng.normal(0, 45, n)
        for year, base in zip([2021, 2023], [100, 80])
    })
    profile = understand_dataset(df)
    wps = declining_trend(df, profile)
    assert wps
    wp = wps[0]
    assert wp.significant is False
    assert wp.priority == "low"  # downgraded from its pre-gate medium
    assert "caveat" in wp.impact.lower()


def test_missing_data_is_not_gated():
    """missing_data is a fact about the whole dataset, not an inferential
    claim about a sample -- it should never get a significance check."""
    df = pd.DataFrame({
        "Category": ["A"] * 100,
        "Notes": [None] * 60 + ["x"] * 40,
    })
    profile = understand_dataset(df)
    wps = missing_data(df, profile)
    for wp in wps:
        assert wp.significant is None
        assert wp.ci_low is None and wp.ci_high is None


def test_outlier_risk_significant_gets_confirmation_note():
    rng = np.random.default_rng(3)
    n = 300
    vals = rng.normal(50, 5, n)
    vals[:6] = rng.normal(2000, 50, 6)
    df = pd.DataFrame({"Sales": vals})
    profile = understand_dataset(df)
    wps = outlier_risk(df, profile)
    assert wps
    assert wps[0].significant is True
    assert wps[0].priority == "high"


def test_concentration_risk_significant_gets_confirmation_note():
    rng = np.random.default_rng(5)
    n = 200
    rows = []
    for c in ["A", "B", "C", "D"]:
        base = 500 if c == "A" else 20
        rows.extend(zip([c] * n, rng.normal(base, 5, n)))
    df = pd.DataFrame(rows, columns=["Category", "Sales"])
    profile = understand_dataset(df)
    wps = concentration_risk(df, profile)
    assert wps
    assert wps[0].significant is True


def test_underperforming_segment_significant_gets_confirmation_note():
    rng = np.random.default_rng(6)
    n = 200
    rows = []
    for g, base in zip(["X", "Y"], [80, 40]):
        rows.extend(zip([g] * n, rng.normal(base, 5, n)))
    df = pd.DataFrame(rows, columns=["Class", "Score"])
    profile = understand_dataset(df)
    wps = underperforming_segment(df, profile)
    assert wps
    assert wps[0].significant is True


def test_underperforming_segment_noisy_gets_downgraded():
    rng = np.random.default_rng(0)
    n = 6
    rows = []
    for g, base in zip(["X", "Y"], [70, 55]):
        rows.extend(zip([g] * n, rng.normal(base, 30, n)))
    df = pd.DataFrame(rows, columns=["Class", "Score"])
    profile = understand_dataset(df)
    wps = underperforming_segment(df, profile)
    assert wps
    wp = wps[0]
    assert wp.significant is False
    assert wp.priority == "low"


def test_margin_risk_significant_gets_confirmation_note():
    rng = np.random.default_rng(7)
    n = 200
    rows = []
    for c, margin_target in zip(["Furniture", "Tech"], [-0.15, 0.25]):
        rev = rng.normal(100, 10, n)
        profit = rev * margin_target + rng.normal(0, 3, n)
        rows.extend(zip([c] * n, rev, profit))
    df = pd.DataFrame(rows, columns=["Category", "Sales", "Profit"])
    profile = understand_dataset(df)
    wps = margin_risk(df, profile)
    assert wps
    losing = next(w for w in wps if "losing money" in w.problem)
    assert losing.significant is True


def test_discount_risk_significant_gets_confirmation_note():
    rng = np.random.default_rng(8)
    n = 600
    discount = rng.uniform(0, 0.8, n)
    rev = rng.normal(100, 10, n)
    profit = rev * (0.3 - discount) + rng.normal(0, 3, n)
    df = pd.DataFrame({"Sales": rev, "Profit": profit, "Discount": discount})
    profile = understand_dataset(df)
    wps = discount_risk(df, profile)
    assert wps
    assert wps[0].significant is True
