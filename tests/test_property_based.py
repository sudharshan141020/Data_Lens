"""
Property-based tests (Hypothesis).

The rest of the suite is example-based: specific inputs, specific
expected outputs. That's the right tool for "does this recover a known
answer" (a synthetic dataset with an injected pattern), but it can only
ever check the examples someone thought to write. This file instead
states invariants that should hold for ANY valid input -- "cluster
sizes always sum to the row count", "a confidence interval always
contains its own point estimate" -- and lets Hypothesis search for
inputs that violate them.

This is a direct response to how many real, non-obvious bugs turned up
in this session while building the chunked-CSV-reading feature (a
category-dtype ordering bug, a cross-cutting date-column crash, a
numpy-dtype JSON serialization bug) -- exactly the class of failure
property-based fuzzing is built to catch before a real upload does.

Kept to a modest example count (`max_examples`) and a relaxed deadline:
these wrap real pandas computation (covariance matrices, bootstrap
resampling), which is slower per-call than the pure-function cases
Hypothesis handles most efficiently, and this suite's whole purpose is
to run on every change, not to be a slow, separate fuzzing job.
"""
import numpy as np
import pandas as pd
from hypothesis import given, settings, strategies as st, HealthCheck

from app.understanding import understand_dataset
from app.clustering import analyze_segments
from app.anomaly_detection import detect_anomalies
from app.confidence_intervals import compute_kpi_confidence_intervals
from app.benford import check_benfords_law
from app.main import _load_dataframe

SUITE_SETTINGS = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])

finite_floats = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


def _two_measure_df(values_a, values_b):
    n = min(len(values_a), len(values_b))
    return pd.DataFrame({"A": values_a[:n], "B": values_b[:n]})


@SUITE_SETTINGS
@given(
    st.lists(finite_floats, min_size=60, max_size=300),
    st.lists(finite_floats, min_size=60, max_size=300),
)
def test_clustering_cluster_sizes_always_sum_to_row_count(values_a, values_b):
    df = _two_measure_df(values_a, values_b)
    if df["A"].std() == 0 or df["B"].std() == 0:
        return  # constant columns are correctly rejected elsewhere; not this property's concern
    profile = understand_dataset(df)
    result = analyze_segments(df, profile)
    if not result["available"]:
        return
    assert sum(c.size for c in result["clusters"]) == result["row_count_used"]
    assert 2 <= result["k"] <= 5


@SUITE_SETTINGS
@given(
    st.lists(finite_floats, min_size=40, max_size=250),
    st.lists(finite_floats, min_size=40, max_size=250),
)
def test_anomaly_detection_never_crashes_and_counts_are_internally_consistent(values_a, values_b):
    df = _two_measure_df(values_a, values_b)
    if df["A"].std() == 0 or df["B"].std() == 0:
        return
    profile = understand_dataset(df)
    result = detect_anomalies(df, profile)  # must not raise
    if not result["available"]:
        return
    assert result["anomaly_count"] == len(result["all_anomaly_row_indices"])
    assert all(0 <= idx < result["row_count_used"] for idx in result["all_anomaly_row_indices"])
    assert 0.0 <= result["anomaly_pct"] <= 100.0


@SUITE_SETTINGS
@given(st.lists(finite_floats, min_size=15, max_size=200))
def test_confidence_interval_always_contains_point_estimate(values):
    df = pd.DataFrame({"Value": values})
    if df["Value"].std() == 0:
        return
    profile = understand_dataset(df)
    result = compute_kpi_confidence_intervals(df, profile)
    if not result["available"]:
        return
    for interval in result["intervals"]:
        assert interval["ci_low"] <= interval["point_estimate"] <= interval["ci_high"]


@SUITE_SETTINGS
@given(st.lists(st.floats(min_value=1.0, max_value=1e9, allow_nan=False, allow_infinity=False), min_size=100, max_size=400))
def test_benford_proportions_always_sum_to_one_and_p_value_in_range(values):
    df = pd.DataFrame({"Revenue": values})
    profile = understand_dataset(df)
    if profile.semantic_roles.get("Revenue") != "FINANCIAL_METRIC":
        return  # only meaningful on columns the module would actually check
    result = check_benfords_law(df, profile)
    for r in result.get("results", []):
        if not r["checked"]:
            continue
        # observed/expected are rounded to 4 decimals each for display (see
        # benford.py) before being stored, so summing 9 of them can
        # accumulate up to ~9*0.00005 rounding error -- this checks that
        # they sum to ~1 within THAT expected tolerance, not raw float
        # precision, which is what the first version of this test
        # incorrectly assumed.
        assert abs(sum(r["observed"].values()) - 1.0) < 1e-3
        assert abs(sum(r["expected"].values()) - 1.0) < 1e-3
        assert 0.0 <= r["p_value"] <= 1.0


@SUITE_SETTINGS
@given(st.lists(finite_floats, min_size=5, max_size=500), st.lists(st.integers(min_value=-128, max_value=127), min_size=5, max_size=500))
def test_csv_round_trip_preserves_row_count_and_numeric_dtype(float_values, int_values):
    """Regression-style property test for the chunked CSV reader
    specifically -- given ANY numeric data (not just the hand-picked
    examples in test_pipeline_robustness.py), row count must survive the
    read exactly, and numeric columns must stay numeric."""
    n = min(len(float_values), len(int_values))
    if n < 5:
        return
    df = pd.DataFrame({"F": float_values[:n], "I": int_values[:n]})
    csv_bytes = df.to_csv(index=False).encode()
    loaded = _load_dataframe("test.csv", csv_bytes)
    assert len(loaded) == n
    assert pd.api.types.is_numeric_dtype(loaded["F"])
    assert pd.api.types.is_numeric_dtype(loaded["I"])
