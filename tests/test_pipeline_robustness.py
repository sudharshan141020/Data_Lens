"""
Pipeline robustness tests.

The project's own history flags a recurring bug pattern: name-based
column classification with no data-quality check, appearing
independently across ~5 code paths before being fixed. These tests
target that failure mode directly -- a column whose NAME suggests one
thing but whose DATA doesn't support it -- plus general edge cases
(tiny data, all-NaN columns, single column) that a growing codebase can
easily regress on without anyone noticing until a real upload breaks.
"""
import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from app.main import _run_v2_pipeline


def test_pipeline_does_not_crash_on_misleadingly_named_garbage_column():
    """A column literally named 'Revenue' but containing no usable
    numeric data shouldn't be blindly trusted as the revenue measure --
    the exact class of bug this project has hit before."""
    df = pd.DataFrame({
        "Revenue": ["not", "a", "number", "at", "all"] * 20,
        "Category": ["A", "B"] * 50,
    })
    result = _run_v2_pipeline(df)  # must not raise
    assert "profile" in result


def test_pipeline_does_not_crash_on_all_nan_column():
    df = pd.DataFrame({
        "Sales": [np.nan] * 100,
        "Category": ["A", "B"] * 50,
    })
    result = _run_v2_pipeline(df)
    assert "profile" in result


def test_pipeline_does_not_crash_on_single_column():
    df = pd.DataFrame({"Value": range(50)})
    result = _run_v2_pipeline(df)
    assert "profile" in result


def test_pipeline_does_not_crash_on_tiny_dataset():
    df = pd.DataFrame({"Sales": [10, 20, 30], "Category": ["A", "B", "A"]})
    result = _run_v2_pipeline(df)
    assert "profile" in result


def test_pipeline_does_not_crash_on_constant_columns():
    """Every row identical in a numeric column -- this specific shape
    has broken standardization-based modules (clustering, anomaly
    detection) before via division by a zero standard deviation."""
    df = pd.DataFrame({
        "Sales": [100.0] * 100,
        "Profit": np.random.default_rng(0).normal(20, 5, 100),
        "Category": ["A", "B"] * 50,
    })
    result = _run_v2_pipeline(df)
    assert "profile" in result


def test_pipeline_does_not_crash_on_single_row():
    df = pd.DataFrame({"Sales": [100], "Category": ["A"]})
    result = _run_v2_pipeline(df)
    assert "profile" in result


def test_all_new_statistical_sections_degrade_gracefully_on_thin_data():
    """On a dataset too small/thin for any of this session's new
    features to run, every one of them should report unavailable with a
    note -- never raise, never silently fabricate a result."""
    df = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": ["x", "y", "x", "y", "x"]})
    result = _run_v2_pipeline(df)

    for key in ("segments", "seasonality", "period_comparison", "anomalies", "simpsons_paradox", "benford", "cohorts", "confidence_intervals", "text_analysis"):
        assert key in result, f"missing key: {key}"
        assert result[key]["available"] is False


def test_150k_rows_completes_quickly():
    """Performance regression guard -- the project has a documented
    150K-row performance bottleneck that was fixed once already."""
    import time
    rng = np.random.default_rng(0)
    n = 150_000
    df = pd.DataFrame({
        "Order Date": pd.date_range("2020-01-01", periods=n, freq="min"),
        "Sales": rng.normal(500, 150, n),
        "Profit": rng.normal(50, 20, n),
        "Category": rng.choice(["A", "B", "C"], n),
    })
    start = time.time()
    result = _run_v2_pipeline(df)
    elapsed = time.time() - start
    assert "profile" in result
    assert elapsed < 30, f"pipeline took {elapsed:.1f}s on 150K rows -- investigate before this regresses further"


def test_low_cardinality_dirty_numeric_column_still_coerces_correctly():
    """Regression for a real bug in the chunked CSV reader: a numeric
    column with few distinct values (so it would look like a category
    candidate) and a handful of stray text placeholders must still end
    up numeric, not get sidetracked into category dtype before the
    existing mostly-numeric coercion logic gets to clean it up."""
    from app.main import _load_dataframe
    rng = np.random.default_rng(0)
    n = 5000
    values = list(rng.choice([10, 20, 30, 40, 50], n - 10).astype(str)) + ["N/A"] * 5 + ["-"] * 5
    csv_text = "Score,Category\n" + "\n".join(f"{v},{c}" for v, c in zip(values, rng.choice(["A", "B"], n)))
    df = _load_dataframe("test.csv", csv_text.encode())
    assert pd.api.types.is_numeric_dtype(df["Score"])
    assert df["Score"].isna().sum() == 10


def test_oversized_file_rejected_with_clear_message():
    from app.main import _load_dataframe
    import app.main as main_module
    original_cap = main_module.MAX_FILE_SIZE_MB
    main_module.MAX_FILE_SIZE_MB = 1
    try:
        oversized = b"A,B\n" + b"1,2\n" * 500_000  # ~2MB, exceeds the 1MB test cap
        with pytest.raises(HTTPException):
            _load_dataframe("big.csv", oversized)
    finally:
        main_module.MAX_FILE_SIZE_MB = original_cap
