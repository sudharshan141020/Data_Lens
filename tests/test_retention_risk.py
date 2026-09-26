"""
Regression tests for cohort_analysis.assess_retention_risk -- the
per-entity "overdue to return" flag, distinct from analyze_cohorts'
aggregate retention curve.
"""
import numpy as np
import pandas as pd

from app.understanding import understand_dataset
from app.cohort_analysis import assess_retention_risk


def _build(regular_customers=50, lapsed_customers=10, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    ref_date = pd.Timestamp("2024-06-01")

    for cust in range(regular_customers):
        start = ref_date - pd.Timedelta(days=int(rng.integers(300, 400)))
        d = start
        while d < ref_date:
            rows.append((f"C{cust}", d))
            d += pd.Timedelta(days=max(1, int(rng.normal(30, 4))))

    for cust in range(regular_customers, regular_customers + lapsed_customers):
        d = ref_date - pd.Timedelta(days=300)
        cutoff = ref_date - pd.Timedelta(days=120)
        while d < cutoff:
            rows.append((f"C{cust}", d))
            d += pd.Timedelta(days=max(1, int(rng.normal(30, 4))))

    return pd.DataFrame(rows, columns=["Customer_ID", "Order_Date"])


def test_flags_lapsed_customers_and_spares_regulars():
    df = _build(regular_customers=50, lapsed_customers=10, seed=1)
    profile = understand_dataset(df)
    result = assess_retention_risk(df, profile)

    assert result["available"]
    assert result["total_entities"] == 60
    assert result["at_risk_count"] == 10
    flagged_ids = {r["entity"] for r in result["at_risk"]}
    assert flagged_ids == {f"C{i}" for i in range(50, 60)}
    assert all(r["risk_level"] == "high" for r in result["at_risk"])
    assert 25 <= result["typical_return_days"] <= 33


def test_nobody_at_risk_when_everyone_is_current():
    df = _build(regular_customers=40, lapsed_customers=0, seed=2)
    profile = understand_dataset(df)
    result = assess_retention_risk(df, profile)
    assert result["available"]
    assert result["at_risk_count"] == 0
    assert result["at_risk"] == []
    assert "None" in result["summary"]


def test_medium_vs_high_risk_levels():
    """A customer moderately overdue (between 1.5x and 3x the typical
    gap) should be 'medium', not 'high'."""
    rng = np.random.default_rng(3)
    rows = []
    ref_date = pd.Timestamp("2024-06-01")
    for cust in range(40):
        start = ref_date - pd.Timedelta(days=int(rng.integers(300, 400)))
        d = start
        while d < ref_date:
            rows.append((f"C{cust}", d))
            d += pd.Timedelta(days=max(1, int(rng.normal(20, 2))))
    # One customer, last seen ~45 days ago (~2.25x a ~20-day typical gap)
    rows.append(("Medium1", ref_date - pd.Timedelta(days=200)))
    rows.append(("Medium1", ref_date - pd.Timedelta(days=180)))
    rows.append(("Medium1", ref_date - pd.Timedelta(days=45)))
    df = pd.DataFrame(rows, columns=["Customer_ID", "Order_Date"])
    profile = understand_dataset(df)
    result = assess_retention_risk(df, profile)

    assert result["available"]
    med = next(r for r in result["at_risk"] if r["entity"] == "Medium1")
    assert med["risk_level"] == "medium"


def test_declines_without_entity_or_date_column():
    df = pd.DataFrame({"Sales": range(100), "Order_Date": pd.date_range("2023-01-01", periods=100)})
    profile = understand_dataset(df)
    result = assess_retention_risk(df, profile)
    assert not result["available"]


def test_declines_with_too_little_repeat_activity():
    """Everyone shows up exactly once -- no observed return gaps at all,
    so there's nothing to learn a typical window from."""
    df = pd.DataFrame({
        "Customer_ID": [f"C{i}" for i in range(100)],
        "Order_Date": pd.date_range("2023-01-01", periods=100),
    })
    profile = understand_dataset(df)
    result = assess_retention_risk(df, profile)
    assert not result["available"]
    assert "repeat activity" in result["note"] or "repeat visits" in result["note"]
