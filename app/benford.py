"""
Benford's Law Check.

Many naturally-occurring numerical datasets -- transaction amounts,
invoice totals, financial figures spanning several orders of magnitude --
have leading digits that follow a predictable, distinctly non-uniform
distribution: about 30% start with 1, only about 4.6% start with 9. A
column that deviates significantly from that expected distribution
(tested with a chi-square goodness-of-fit test, not just eyeballing a
bar chart) is a well-known data-integrity signal worth a second look --
though deviation isn't proof of anything by itself, and this module says
so rather than overclaiming.

Only run on columns semantically identified as monetary (FINANCIAL_METRIC,
PROFIT, UNIT_COST roles from semantic_roles.py) -- Benford's Law doesn't
apply to arbitrary numeric columns like ages, percentages, or IDs, so
this deliberately doesn't touch every numeric measure the way clustering
or anomaly detection do.
"""
import numpy as np
import pandas as pd

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a listed dependency
    _HAS_SCIPY = False

MONEY_ROLES = {"FINANCIAL_METRIC", "PROFIT", "UNIT_COST"}
MIN_N = 100                  # Benford's Law needs a reasonably large sample to be meaningful
MIN_MAGNITUDE_SPAN = 100     # values should span at least 2 orders of magnitude for the test to make sense
MAX_COLUMNS_CHECKED = 3
SIGNIFICANCE_ALPHA = 0.05

BENFORD_EXPECTED = {d: np.log10(1 + 1 / d) for d in range(1, 10)}


def _leading_digits(values: np.ndarray) -> np.ndarray:
    v = values[values > 0]
    magnitudes = np.floor(np.log10(v))
    digits = (v / (10 ** magnitudes)).astype(int)
    return np.clip(digits, 1, 9)  # guards rare floating-point edge cases landing on 10


def _check_column(df: pd.DataFrame, col: str) -> dict:
    values = df[col].dropna().to_numpy(dtype=float)
    values = np.abs(values)
    values = values[values > 0]

    if len(values) < MIN_N:
        return {"column": col, "checked": False, "note": f"Only {len(values)} usable values -- Benford's Law needs at least {MIN_N} to be meaningful."}

    span = values.max() / values.min()
    if span < MIN_MAGNITUDE_SPAN:
        return {"column": col, "checked": False, "note": "Values don't span enough orders of magnitude for this test to be meaningful."}

    digits = _leading_digits(values)
    observed_counts = np.array([np.sum(digits == d) for d in range(1, 10)])
    expected_props = np.array([BENFORD_EXPECTED[d] for d in range(1, 10)])
    expected_counts = expected_props * len(values)

    if not _HAS_SCIPY:
        return {"column": col, "checked": False, "note": "Couldn't run the significance test in this environment."}

    chi2_stat, p_value = _scipy_stats.chisquare(observed_counts, expected_counts)

    observed_props = observed_counts / len(values)
    deviations = observed_props - expected_props
    worst_digit = int(np.argmax(np.abs(deviations))) + 1
    worst_deviation_pct = round(float(deviations[worst_digit - 1]) * 100, 1)

    deviates = p_value < SIGNIFICANCE_ALPHA

    if deviates:
        summary = (
            f"{col}'s leading digits deviate from Benford's Law (chi²={chi2_stat:.1f}, p={p_value:.4f}) -- "
            f"digit {worst_digit} appears {'more' if worst_deviation_pct > 0 else 'less'} often than expected "
            f"({abs(worst_deviation_pct):.1f} points off). Worth a closer look, though rounding, caps, or a "
            f"restricted value range can also cause this without anything being wrong."
        )
    else:
        summary = f"{col}'s leading digits follow Benford's Law closely (p={p_value:.2f}) -- no data-integrity signal here."

    return {
        "column": col,
        "checked": True,
        "n": int(len(values)),
        "chi2": round(float(chi2_stat), 2),
        "p_value": round(float(p_value), 5),
        "deviates": bool(deviates),
        "observed": {str(d): round(float(observed_props[d - 1]), 4) for d in range(1, 10)},
        "expected": {str(d): round(float(expected_props[d - 1]), 4) for d in range(1, 10)},
        "summary": summary,
    }


def check_benfords_law(df: pd.DataFrame, profile) -> dict:
    candidates = [m.column for m in profile.measures if profile.semantic_roles.get(m.column) in MONEY_ROLES]
    if not candidates:
        return {"available": False, "note": "No monetary-style columns (revenue, cost, profit, etc.) found to check.", "results": []}

    candidates = candidates[:MAX_COLUMNS_CHECKED]
    results = [_check_column(df, c) for c in candidates]
    checked = [r for r in results if r["checked"]]

    if not checked:
        return {"available": False, "note": results[0]["note"] if results else None, "results": results}

    return {"available": True, "note": None, "results": results}
