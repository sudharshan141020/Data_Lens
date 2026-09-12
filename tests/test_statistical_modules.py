"""
Regression tests for the from-scratch statistical modules. Each of
these codifies a correctness check that was originally done manually
during development (see each feature's CHANGES.md) -- most importantly,
the false-positive bugs that were actually caught and fixed along the
way. These tests exist so those specific bugs can never silently come
back.
"""
import numpy as np
import pandas as pd

from app.clustering import analyze_segments
from app.seasonality import decompose_trend
from app.period_comparison import compare_periods
from app.anomaly_detection import detect_anomalies
from app.simpsons_paradox import check_simpsons_paradox
from app.benford import check_benfords_law
from app.understanding import understand_dataset
from app.correlation_center import analyze_correlations


# ---------------------------------------------------------------- clustering

def test_clustering_recovers_known_groups(rng):
    g1 = rng.normal(loc=[20, 5], scale=1.5, size=(100, 2))
    g2 = rng.normal(loc=[80, 5], scale=1.5, size=(100, 2))
    g3 = rng.normal(loc=[50, 40], scale=1.5, size=(100, 2))
    df = pd.DataFrame(np.vstack([g1, g2, g3]), columns=["Revenue", "Discount"])
    profile = understand_dataset(df)
    result = analyze_segments(df, profile)
    assert result["available"]
    assert result["k"] == 3
    assert sorted(c.size for c in result["clusters"]) == [100, 100, 100]


def test_clustering_declines_on_too_few_measures():
    df = pd.DataFrame({"A": range(100)})
    profile = understand_dataset(df)
    result = analyze_segments(df, profile)
    assert not result["available"]


# --------------------------------------------------------------- seasonality

def test_seasonality_rejects_pure_noise_at_every_tested_length(rng):
    """This is the false-positive this module was rebuilt around: pure
    noise at 2.5 years originally scored a seasonal_strength of 0.72."""
    for n_months in (30, 36, 60):
        values = [float(rng.normal(100, 5)) for _ in range(n_months)]
        trend_data = [{"label": f"{2020 + i // 12}-{(i % 12) + 1:02d}", "value": v} for i, v in enumerate(values)]
        result = decompose_trend(trend_data)
        assert not result["available"], f"pure noise at {n_months} months should not be reported as seasonal"


def test_seasonality_detects_known_injected_pattern(rng):
    true_seasonal = {1: -20, 2: -30, 3: -10, 4: 0, 5: 5, 6: 10, 7: 15, 8: 10, 9: 5, 10: 0, 11: 10, 12: 40}
    trend_data = []
    year, month, base = 2021, 1, 100
    for i in range(36):
        value = base + i * 2 + true_seasonal[month] + float(rng.normal(0, 2))
        trend_data.append({"label": f"{year}-{month:02d}", "value": value})
        month += 1
        if month > 12:
            month, year = 1, year + 1

    result = decompose_trend(trend_data)
    assert result["available"]
    assert result["peak_month"]["name"] == "December"
    assert result["trough_month"]["name"] == "February"


# ---------------------------------------------------------- period comparison

def test_period_comparison_flags_significance_correctly(rng):
    dates = pd.to_datetime(["2023-01-15"] * 50 + ["2023-02-15"] * 50)

    clear_jump = list(rng.normal(100, 5, 50)) + list(rng.normal(150, 5, 50))
    df_jump = pd.DataFrame({"Date": dates, "Sales": clear_jump})
    result_jump = compare_periods(df_jump, "Date", "Sales", "avg")
    assert result_jump["available"]
    assert result_jump["significant"]

    noisy = list(rng.normal(100, 30, 50)) + list(rng.normal(102, 30, 50))
    df_noisy = pd.DataFrame({"Date": dates, "Sales": noisy})
    result_noisy = compare_periods(df_noisy, "Date", "Sales", "avg")
    assert result_noisy["available"]
    assert not result_noisy["significant"]


# ----------------------------------------------------------------- anomalies

def test_anomaly_detection_finds_injected_multivariate_anomalies(rng):
    n = 300
    orders = rng.normal(50, 10, n)
    revenue = orders * 20 + rng.normal(0, 30, n)
    injected_positions = [10, 50, 120, 200, 280]
    for pos in injected_positions:
        orders[pos] = 50
        revenue[pos] = 200
    df = pd.DataFrame({"Orders": orders, "Revenue": revenue})
    profile = understand_dataset(df)
    result = detect_anomalies(df, profile)
    assert result["available"]
    flagged = {a["row_index"] for a in result["anomalies"]}
    assert all(pos in flagged for pos in injected_positions)


def test_anomaly_why_never_describes_an_average_value_as_unusual(rng):
    """Regression for a real bug: the 'why' explanation could describe a
    z-score of ~0 as 'unusually high' just because it was the larger of
    only two available measures."""
    n = 300
    orders = rng.normal(50, 10, n)
    revenue = orders * 20 + rng.normal(0, 30, n)
    orders[10] = 50  # exactly average
    revenue[10] = 200  # anomalous
    df = pd.DataFrame({"Orders": orders, "Revenue": revenue})
    profile = understand_dataset(df)
    result = detect_anomalies(df, profile)
    row = next(a for a in result["anomalies"] if a["row_index"] == 10)
    assert "Orders" not in row["why"]  # z~0 must not be named as a reason


def test_anomaly_row_index_survives_nan_gaps(rng):
    """Regression for a real bug: row_index used to refer to position
    after dropna(), not the original file's row number."""
    n = 200
    orders = rng.normal(50, 10, n)
    revenue = orders * 20 + rng.normal(0, 30, n)
    orders[5] = np.nan
    orders[50] = 50
    revenue[50] = 200
    df = pd.DataFrame({"Orders": orders, "Revenue": revenue})
    profile = understand_dataset(df)
    result = detect_anomalies(df, profile)
    flagged = {a["row_index"] for a in result["anomalies"]}
    assert 50 in flagged
    assert 5 not in flagged


# ------------------------------------------------------------ simpson's paradox

def test_simpsons_paradox_detects_classic_reversal(rng):
    n = 200
    xa = rng.normal(10, 2, n)
    ya = -0.8 * xa + 50 + rng.normal(0, 2, n)
    xb = rng.normal(30, 2, n)
    yb = -0.8 * xb + 80 + rng.normal(0, 2, n)
    df = pd.DataFrame({
        "X": np.concatenate([xa, xb]), "Y": np.concatenate([ya, yb]),
        "Group": ["A"] * n + ["B"] * n,
    })
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)
    result = check_simpsons_paradox(df, profile, corr["pairs"])
    assert result["available"]
    assert len(result["flags"]) == 1
    assert result["flags"][0]["overall_r"] > 0
    assert all(s["r"] < 0 for s in result["flags"][0]["subgroups"])


def test_simpsons_paradox_no_false_positive_on_consistent_correlation(rng):
    n = 400
    x = rng.normal(50, 15, n)
    y = 0.7 * x + rng.normal(0, 10, n)
    df = pd.DataFrame({"X": x, "Y": y, "Group": rng.choice(["A", "B"], n)})
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)
    result = check_simpsons_paradox(df, profile, corr["pairs"])
    assert result["flags"] == []


# ------------------------------------------------------------------- benford

def test_benford_passes_compliant_data(rng):
    exponents = rng.uniform(1, 6, 5000)
    df = pd.DataFrame({"Revenue": 10 ** exponents})
    profile = understand_dataset(df)
    result = check_benfords_law(df, profile)
    assert result["available"]
    checked = next(r for r in result["results"] if r["checked"])
    assert not checked["deviates"]


def test_benford_flags_noncompliant_data(rng):
    digits = rng.integers(1, 10, 2000)
    magnitudes = rng.integers(1, 4, 2000)
    values = digits * (10.0 ** magnitudes) + rng.uniform(0, 10 ** magnitudes.astype(float))
    df = pd.DataFrame({"Amount": values})
    profile = understand_dataset(df)
    result = check_benfords_law(df, profile)
    assert result["available"]
    checked = next(r for r in result["results"] if r["checked"])
    assert checked["deviates"]
