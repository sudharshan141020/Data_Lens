"""
Regression tests for app.partial_correlation -- both the numeric-control
path (classic partial correlation via residualization) and the
categorical-control path (within-group demeaning), plus the "robust"
case where a relationship survives everything tested.
"""
import numpy as np
import pandas as pd

from app.understanding import understand_dataset
from app.correlation_center import analyze_correlations
from app.partial_correlation import analyze_partial_correlations


def _xy_result(result, col_a="X", col_b="Y"):
    return next(
        (r for r in result["results"] if {r["col1"], r["col2"]} == {col_a, col_b}),
        None,
    )


def test_numeric_confound_gets_explained_away(rng):
    """X and Y are both just noisy copies of Z -- their apparent
    correlation should almost entirely disappear once Z is controlled
    for."""
    n = 300
    z = rng.normal(50, 10, n)
    x = z + rng.normal(0, 1, n)
    y = z + rng.normal(0, 1, n)
    df = pd.DataFrame({"X": x, "Y": y, "Z": z})
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)

    result = analyze_partial_correlations(df, profile, corr["pairs"])
    assert result["available"]

    xy = _xy_result(result)
    assert xy is not None
    assert not xy["robust"]
    controls = {e["control"]: e for e in xy["explained_by"]}
    assert "Z" in controls
    assert controls["Z"]["classification"] == "mostly_explained"
    assert abs(controls["Z"]["partial_r"]) < abs(xy["overall_r"])


def test_categorical_confound_gets_explained_away(rng):
    """Classic ecological-correlation setup: X and Y jump together across
    two groups but have no real relationship within either group. The
    apparent correlation is an artifact of the group split."""
    n = 150
    xa, ya = rng.normal(10, 1, n), rng.normal(10, 1, n)
    xb, yb = rng.normal(30, 1, n), rng.normal(30, 1, n)
    df = pd.DataFrame({
        "X": np.concatenate([xa, xb]),
        "Y": np.concatenate([ya, yb]),
        "Group": ["A"] * n + ["B"] * n,
    })
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)

    result = analyze_partial_correlations(df, profile, corr["pairs"])
    xy = _xy_result(result)
    assert xy is not None
    controls = {e["control"]: e for e in xy["explained_by"]}
    assert "Group" in controls
    assert controls["Group"]["classification"] in ("mostly_explained", "reverses")
    assert abs(controls["Group"]["partial_r"]) < abs(xy["overall_r"])


def test_partial_correlation_flags_reversal():
    """Same setup as the Simpson's paradox reversal test: overall a
    positive relationship, but every group actually has a negative slope.
    The partial correlation controlling for Group should recover the
    true, reversed sign."""
    rng = np.random.default_rng(11)
    n = 200
    xa = rng.normal(10, 2, n)
    ya = -0.8 * xa + 50 + rng.normal(0, 2, n)
    xb = rng.normal(30, 2, n)
    yb = -0.8 * xb + 80 + rng.normal(0, 2, n)
    df = pd.DataFrame({
        "X": np.concatenate([xa, xb]),
        "Y": np.concatenate([ya, yb]),
        "Group": ["A"] * n + ["B"] * n,
    })
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)

    result = analyze_partial_correlations(df, profile, corr["pairs"])
    xy = _xy_result(result)
    assert xy is not None
    controls = {e["control"]: e for e in xy["explained_by"]}
    assert "Group" in controls
    assert controls["Group"]["classification"] == "reverses"
    assert (controls["Group"]["partial_r"] > 0) != (xy["overall_r"] > 0)


def test_relationship_holds_up_when_third_variable_is_unrelated(rng):
    """A genuine relationship shouldn't get flagged just because some
    other, unrelated variable happens to be in the dataset."""
    n = 300
    x = rng.normal(0, 1, n)
    y = 2 * x + rng.normal(0, 0.3, n)
    z = rng.normal(0, 1, n)  # independent of both X and Y
    df = pd.DataFrame({"X": x, "Y": y, "Z": z})
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)

    result = analyze_partial_correlations(df, profile, corr["pairs"])
    xy = _xy_result(result)
    assert xy is not None
    assert xy["robust"]
    assert xy["explained_by"] == []


def test_declines_without_correlation_pairs():
    df = pd.DataFrame({"A": range(50)})
    profile = understand_dataset(df)
    result = analyze_partial_correlations(df, profile, [])
    assert not result["available"]
    assert result["results"] == []


def test_declines_when_no_other_variable_to_control_for(rng):
    n = 100
    x = rng.normal(0, 1, n)
    y = 2 * x + rng.normal(0, 0.2, n)
    df = pd.DataFrame({"X": x, "Y": y})
    profile = understand_dataset(df)
    corr = analyze_correlations(df, profile)

    result = analyze_partial_correlations(df, profile, corr["pairs"])
    assert not result["available"]
    assert "Not enough other variables" in result["note"]
