"""
Partial Correlations.

correlation_center.py answers "how correlated are X and Y overall". This
answers the next question a careful analyst asks: is that because X and Y
are actually related, or because some third variable Z moves both of them
at once? Controlling for Z isolates whatever relationship survives once
Z's shared influence is removed.

Both flavors of "control" work by residualizing X and Y against Z, then
correlating what's left:
  - Z is a numeric measure -> classic linear partial correlation:
    regress X on Z and Y on Z, correlate the two sets of residuals.
    Equivalent to the textbook formula
    r_xy.z = (r_xy - r_xz*r_yz) / sqrt((1-r_xz^2)(1-r_yz^2)).
  - Z is a categorical dimension -> within-group demeaning (ANCOVA-style):
    subtract each category's own mean from X and Y before correlating.
    This removes exactly the "groups differ on average" effect.

Distinct from simpsons_paradox.py, which only ever looks at categorical
dimensions and only flags the extreme, all-or-nothing case (the sign
reverses in EVERY subgroup). This module also checks numeric controls
(something Simpson's paradox can't express at all), and reports a
gradient -- "still holds", "partially explained by", "mostly explained
by", "reverses when you control for" -- for whichever single control most
changes the relationship, rather than requiring a full reversal to say
anything. The two modules can legitimately flag the same pair from
different angles: Simpson's paradox says whether it flips in every
subgroup; this says how much of it survives controlling for the
strongest candidate confound found (categorical or numeric).
"""
from typing import Optional
import math
import numpy as np
import pandas as pd

from app.correlation_center import MIN_INTEREST_R

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a listed dependency
    _HAS_SCIPY = False

PARTIAL_MIN_SAMPLE_SIZE = 15    # residualizing costs degrees of freedom -- a higher floor than a plain pairwise correlation
PARTIAL_MIN_R = 0.15            # a partial |r| below this is noise, not a real reversal -- mirrors simpsons_paradox.MIN_SUBGROUP_R
EXPLAIN_DROP_THRESHOLD = 0.15   # minimum drop in |r| for a control to count as "explaining part of" the relationship
MIN_DIMENSION_CARDINALITY = 2
MAX_DIMENSION_CARDINALITY = 8   # same bounds as simpsons_paradox.py -- more categories dilutes group means past usefulness
MAX_PAIRS_CHECKED = 5           # top correlation pairs by |r|, keeps this cheap and keeps the output focused
MAX_CONTROLS_PER_PAIR = 8       # bounds compute on datasets with many measures/dimensions
SIGNIFICANCE_ALPHA = 0.05


def _std_normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _partial_p_value(r: float, df: int) -> Optional[float]:
    """Two-sided significance test for a partial correlation with the
    given residual degrees of freedom -- NOT the same df a plain pairwise
    correlation would use, since controlling for Z spends some of it."""
    if df <= 0:
        return None
    if abs(r) >= 1:
        return 0.0
    t_stat = r * math.sqrt(df / (1 - r ** 2))
    if _HAS_SCIPY:
        p = 2 * _scipy_stats.t.sf(abs(t_stat), df)
    else:
        # Normal-approximation fallback, same shape as correlation_center's.
        x = t_stat * (1 - 1 / (4 * df)) / math.sqrt(1 + t_stat ** 2 / (2 * df))
        p = 2 * (1 - _std_normal_cdf(x))
    return max(0.0, min(1.0, float(p)))


def _residualize_numeric(x: np.ndarray, z: np.ndarray) -> Optional[np.ndarray]:
    if z.std(ddof=0) == 0:
        return None
    try:
        slope, intercept = np.polyfit(z, x, 1)
    except (np.linalg.LinAlgError, ValueError):
        return None
    return x - (slope * z + intercept)


def _residualize_categorical(x: pd.Series, groups: pd.Series) -> np.ndarray:
    means = x.groupby(groups).transform("mean")
    return (x - means).to_numpy(dtype=float)


def _text_for(c1: str, c2: str, overall_r: float, partial_r: float, control: str, classification: str) -> str:
    if classification == "reverses":
        return (
            f"Controlling for {control}, {c1} and {c2} actually reverse -- "
            f"r goes from {overall_r:.2f} to {partial_r:.2f}."
        )
    if classification == "mostly_explained":
        return (
            f"Most of the correlation between {c1} and {c2} looks explained by {control} -- "
            f"r drops from {overall_r:.2f} to {partial_r:.2f} once it's controlled for."
        )
    return (  # partially_explained
        f"Part of the correlation between {c1} and {c2} is explained by {control} -- "
        f"r drops from {overall_r:.2f} to {partial_r:.2f} once it's controlled for."
    )


def _classify(c1: str, c2: str, overall_r: float, overall_sign: int, partial_r: float,
              p_value: Optional[float], n: int, control: str, control_type: str) -> Optional[dict]:
    drop = round(abs(overall_r) - abs(partial_r), 3)
    partial_sign = 1 if partial_r > 0 else -1

    if partial_sign != overall_sign and abs(partial_r) >= PARTIAL_MIN_R:
        classification = "reverses"
    elif drop >= EXPLAIN_DROP_THRESHOLD and abs(partial_r) < MIN_INTEREST_R:
        classification = "mostly_explained"
    elif drop >= EXPLAIN_DROP_THRESHOLD:
        classification = "partially_explained"
    else:
        return None  # this control doesn't meaningfully change the relationship -- not worth reporting

    return {
        "control": control,
        "control_type": control_type,
        "partial_r": round(partial_r, 3),
        "p_value": round(p_value, 4) if p_value is not None else None,
        "significant": (p_value < SIGNIFICANCE_ALPHA) if p_value is not None else None,
        "n": n,
        "drop": drop,
        "classification": classification,
        "text": _text_for(c1, c2, overall_r, partial_r, control, classification),
    }


def analyze_partial_correlations(df: pd.DataFrame, profile, correlation_pairs: list) -> dict:
    """correlation_pairs is correlation_center.analyze_correlations()'s
    "pairs" list (CorrelationPair objects). For each of the top few, tests
    every other numeric measure and every usable categorical dimension as
    a potential control, and reports whichever ones meaningfully change
    the relationship -- or, if none do, that the relationship held up
    against everything tested."""
    if not correlation_pairs:
        return {"available": False, "note": None, "results": []}

    numeric_cols = [m.column for m in profile.measures]
    dims = [
        d for d in profile.dimensions
        if d.is_chartable and MIN_DIMENSION_CARDINALITY <= d.cardinality <= MAX_DIMENSION_CARDINALITY
    ]

    if len(numeric_cols) < 3 and not dims:
        return {"available": False, "note": "Not enough other variables in this dataset to control for.", "results": []}

    candidates = sorted(correlation_pairs, key=lambda p: -abs(p.r))[:MAX_PAIRS_CHECKED]
    results = []

    for pair in candidates:
        c1, c2, overall_r = pair.col1, pair.col2, pair.r
        overall_sign = 1 if overall_r > 0 else -1
        controls_tested = 0
        explained_by = []

        for z_col in numeric_cols:
            if controls_tested >= MAX_CONTROLS_PER_PAIR:
                break
            if z_col in (c1, c2):
                continue
            sub = df[[c1, c2, z_col]].dropna()
            n = len(sub)
            if n < PARTIAL_MIN_SAMPLE_SIZE:
                continue

            x_resid = _residualize_numeric(sub[c1].to_numpy(dtype=float), sub[z_col].to_numpy(dtype=float))
            y_resid = _residualize_numeric(sub[c2].to_numpy(dtype=float), sub[z_col].to_numpy(dtype=float))
            if x_resid is None or y_resid is None or x_resid.std(ddof=0) == 0 or y_resid.std(ddof=0) == 0:
                continue

            partial_r = float(np.corrcoef(x_resid, y_resid)[0, 1])
            if pd.isna(partial_r):
                continue
            controls_tested += 1
            p_value = _partial_p_value(partial_r, n - 3)
            item = _classify(c1, c2, overall_r, overall_sign, partial_r, p_value, n, z_col, "measure")
            if item:
                explained_by.append(item)

        for dim in dims:
            if controls_tested >= MAX_CONTROLS_PER_PAIR:
                break
            sub = df[[c1, c2, dim.column]].dropna()
            n = len(sub)
            if n < PARTIAL_MIN_SAMPLE_SIZE:
                continue
            k = sub[dim.column].nunique()
            if k < 2:
                continue

            x_resid = _residualize_categorical(sub[c1].astype(float), sub[dim.column])
            y_resid = _residualize_categorical(sub[c2].astype(float), sub[dim.column])
            if x_resid.std(ddof=0) == 0 or y_resid.std(ddof=0) == 0:
                continue

            partial_r = float(np.corrcoef(x_resid, y_resid)[0, 1])
            if pd.isna(partial_r):
                continue
            controls_tested += 1
            p_value = _partial_p_value(partial_r, n - k - 1)
            item = _classify(c1, c2, overall_r, overall_sign, partial_r, p_value, n, dim.column, "dimension")
            if item:
                explained_by.append(item)

        if controls_tested == 0:
            continue  # nothing testable for this pair on this dataset -- skip silently, not a finding

        explained_by.sort(key=lambda e: e["drop"], reverse=True)
        if explained_by:
            summary = explained_by[0]["text"]
        else:
            summary = (
                f"{c1} and {c2} remain correlated (r={overall_r:.2f}) even after controlling for the "
                f"other {controls_tested} available variable{'s' if controls_tested != 1 else ''} -- "
                f"doesn't look like it's explained by anything else measured here."
            )

        results.append({
            "col1": c1,
            "col2": c2,
            "overall_r": round(overall_r, 3),
            "controls_tested": controls_tested,
            "robust": len(explained_by) == 0,
            "explained_by": explained_by,
            "summary": summary,
        })

    note = None if results else "None of the top correlated pairs had another variable available to control for."
    return {"available": bool(results), "note": note, "results": results}
