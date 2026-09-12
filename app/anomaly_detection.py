"""
Multivariate Anomaly Detection.

The existing outlier detection (see data_quality.py / weak_points.py)
flags unusual values one column at a time. That misses the more
interesting case: a row where no single measure looks extreme, but the
*combination* is -- a customer with completely ordinary revenue and a
completely ordinary order count, except normally those two move
together and this one doesn't. Mahalanobis distance answers exactly
that: it measures how far a row sits from the center of the data,
accounting for how the measures correlate with each other, not just
their individual spread.

From-scratch with numpy/scipy only, same "no external ML library"
pattern as clustering.py's k-means and correlation_center.py's VIF.
Under the (imperfect but standard) assumption that the measures are
roughly multivariate-normal, squared Mahalanobis distance follows a
chi-square distribution with degrees of freedom equal to the number of
measures -- so unlike an arbitrary "top N by distance" cutoff, the flag
threshold here is a real p-value, same significance-testing spirit as
seasonality.py and period_comparison.py.
"""
from typing import Optional
import numpy as np
import pandas as pd

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a listed dependency
    _HAS_SCIPY = False

MIN_MEASURES = 2
MAX_MEASURES = 6           # same cap/rationale as clustering.py -- interpretability, not just speed
MIN_ROWS_PER_MEASURE = 10  # rule-of-thumb minimum for a stable covariance estimate
MIN_ROWS = 30
SIGNIFICANCE_ALPHA = 0.01  # stricter than the usual 0.05 -- flagging a row as anomalous is a stronger claim than "these differ"
MAX_ANOMALIES_RETURNED = 50
MAX_SCATTER_POINTS = 400   # matches executor_v2.MAX_SCATTER_POINTS
TRAIT_Z_THRESHOLD = 0.5    # a measure has to actually look unusual on its own to be named in the "why" --
                            # otherwise a row flagged purely for breaking a correlation (no single measure
                            # extreme) would misleadingly describe an average value as "unusually high"


def _chi2_p_value(d_squared: np.ndarray, df: int) -> Optional[np.ndarray]:
    if not _HAS_SCIPY:
        return None
    return _scipy_stats.chi2.sf(d_squared, df)


def _pick_display_axes(df_used: pd.DataFrame, is_anomaly: np.ndarray, cols: list) -> tuple:
    """Same idea as clustering.py's axis picker: show the 2 measures that
    differ most between the flagged and normal rows, via a between/within
    variance ratio, so the scatter people see is the one where the
    anomalies are actually visible."""
    if len(cols) <= 2 or not is_anomaly.any() or is_anomaly.all():
        return cols[0], cols[1]

    X = df_used[cols].to_numpy(dtype=float)
    overall_mean = X.mean(axis=0)
    between = np.zeros(X.shape[1])
    within = np.zeros(X.shape[1])
    for mask in (is_anomaly, ~is_anomaly):
        members = X[mask]
        if len(members) == 0:
            continue
        between += len(members) * (members.mean(axis=0) - overall_mean) ** 2
        within += np.sum((members - members.mean(axis=0)) ** 2, axis=0)
    ratio = between / np.where(within > 0, within, 1e-9)
    top2 = np.argsort(ratio)[::-1][:2]
    return cols[top2[0]], cols[top2[1]]


def detect_anomalies(df: pd.DataFrame, profile) -> dict:
    all_cols = [m.column for m in profile.measures]
    cols = all_cols[:MAX_MEASURES]
    if len(cols) < MIN_MEASURES:
        return {"available": False, "note": "Needs at least two numeric measures to check for unusual combinations."}

    usable = df[cols].dropna()
    usable = usable.loc[:, usable.std(ddof=0) > 0]  # constant columns break the covariance matrix
    cols = list(usable.columns)
    if len(cols) < MIN_MEASURES:
        return {"available": False, "note": "The numeric measures here don't vary enough to check for anomalies."}
    if len(usable) < max(MIN_ROWS, MIN_ROWS_PER_MEASURE * len(cols)):
        return {"available": False, "note": f"Needs at least {MIN_ROWS_PER_MEASURE * len(cols)} complete rows across these measures for a stable estimate."}

    if not _HAS_SCIPY:
        return {"available": False, "note": "Couldn't run the significance test in this environment."}

    X = usable.to_numpy(dtype=float)
    mean = X.mean(axis=0)
    cov = np.cov(X, rowvar=False)
    try:
        inv_cov = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        # near-singular covariance -- usually near-perfectly correlated
        # measures (the same thing correlation_center.py's VIF flags).
        # A pseudo-inverse degrades gracefully rather than crashing.
        inv_cov = np.linalg.pinv(cov)

    diff = X - mean
    d_squared = np.einsum("ij,jk,ik->i", diff, inv_cov, diff)
    d_squared = np.clip(d_squared, 0, None)  # guard tiny negative values from floating-point noise

    p_values = _chi2_p_value(d_squared, df=len(cols))
    is_anomaly = p_values < SIGNIFICANCE_ALPHA

    original_indices = usable.index.to_numpy()  # preserve the original file's row numbers
    usable = usable.reset_index(drop=True)
    overall_mean = usable.mean()
    overall_std = usable.std(ddof=0)

    anomaly_idx = np.where(is_anomaly)[0]
    order = anomaly_idx[np.argsort(-d_squared[anomaly_idx])][:MAX_ANOMALIES_RETURNED]

    anomalies = []
    for i in order:
        row = usable.iloc[i]
        z_scores = {c: float((row[c] - overall_mean[c]) / overall_std[c]) if overall_std[c] else 0.0 for c in cols}
        top_traits = sorted(z_scores.items(), key=lambda kv: -abs(kv[1]))[:2]
        top_traits = [(c, z) for c, z in top_traits if abs(z) >= TRAIT_Z_THRESHOLD]
        if top_traits:
            why = " and ".join(
                f"{'unusually high' if z > 0 else 'unusually low'} {c} (z={z:.1f})" for c, z in top_traits
            )
        else:
            # No single measure looks extreme -- it's the *combination* that's
            # off (e.g. two measures that normally move together, here don't).
            why = f"an unusual combination of {' and '.join(cols)} relative to how they typically move together"
        anomalies.append({
            "row_index": int(original_indices[i]),
            "distance": round(float(np.sqrt(d_squared[i])), 2),
            "p_value": round(float(p_values[i]), 5),
            "why": why,
            "values": {c: round(float(row[c]), 2) for c in cols},
        })

    x_col, y_col = _pick_display_axes(usable, is_anomaly, cols)
    n_points = len(usable)
    rng = np.random.default_rng(42)
    if n_points > MAX_SCATTER_POINTS:
        # keep every anomaly, fill the rest of the budget with a random
        # sample of normal points -- otherwise a random sample on a large,
        # mostly-normal dataset could easily miss displaying the anomalies at all.
        normal_idx = np.where(~is_anomaly)[0]
        budget = max(0, MAX_SCATTER_POINTS - len(anomaly_idx))
        sampled_normal = rng.choice(normal_idx, size=min(budget, len(normal_idx)), replace=False) if len(normal_idx) else np.array([], dtype=int)
        display_idx = np.concatenate([anomaly_idx, sampled_normal])
    else:
        display_idx = np.arange(n_points)

    scatter_points = [
        {"x": float(usable.iloc[i][x_col]), "y": float(usable.iloc[i][y_col]), "group": "Anomaly" if is_anomaly[i] else "Normal"}
        for i in display_idx
    ]

    return {
        "available": True,
        "note": None,
        "measures_used": cols,
        "row_count_used": int(n_points),
        "anomaly_count": int(is_anomaly.sum()),
        "anomaly_pct": round(100 * is_anomaly.sum() / n_points, 2),
        "x_measure": x_col,
        "y_measure": y_col,
        "anomalies": anomalies,
        "all_anomaly_row_indices": [int(v) for v in original_indices[is_anomaly]],  # uncapped, unlike `anomalies` above -- for callers (like cleaned-CSV export) that need every flagged row, not just the top N with a full explanation
        "scatter_points": scatter_points,
    }
