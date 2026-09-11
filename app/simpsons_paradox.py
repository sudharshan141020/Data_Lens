"""
Simpson's Paradox Check.

Takes the significant correlation pairs correlation_center.py already
found and checks whether each one's sign reverses once you split the
data by a categorical dimension -- the classic pattern where an overall
trend disappears or flips once you control for a confounding variable
(textbook example: a drug looks worse overall but better within every
patient subgroup, because the subgroups differ in who tends to get it).

Strict definition used here: flag only when the correlation sign in
EVERY sufficiently-large subgroup is the opposite of the overall sign --
not just "most" subgroups. A looser rule would generate more flags but
more of them would just be noise in a couple of small subgroups; this is
a case where under-claiming is the right instinct for something that's
easy to say confidently and easy to get wrong.
"""
import numpy as np
import pandas as pd

try:
    from scipy import stats as _scipy_stats
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a listed dependency
    _HAS_SCIPY = False

MIN_SUBGROUP_SIZE = 15
MIN_VALID_SUBGROUPS = 2
MIN_SUBGROUP_R = 0.15       # a within-group correlation this weak isn't really a "reversal", just noise
MIN_DIMENSION_CARDINALITY = 2
MAX_DIMENSION_CARDINALITY = 8   # more categories than this dilutes subgroup sizes past usefulness
MAX_PAIRS_CHECKED = 5           # top correlation pairs by |r|, keeps this cheap and keeps the output focused


def _correlation(x: np.ndarray, y: np.ndarray):
    if len(x) < MIN_SUBGROUP_SIZE or x.std(ddof=0) == 0 or y.std(ddof=0) == 0:
        return None
    if _HAS_SCIPY:
        r, _p = _scipy_stats.pearsonr(x, y)
        return float(r)
    return float(np.corrcoef(x, y)[0, 1])


def check_simpsons_paradox(df: pd.DataFrame, profile, correlation_pairs: list) -> dict:
    dims = [d for d in profile.dimensions if d.is_chartable and MIN_DIMENSION_CARDINALITY <= d.cardinality <= MAX_DIMENSION_CARDINALITY]
    if not dims or not correlation_pairs:
        return {"available": False, "note": None, "flags": []}

    if not _HAS_SCIPY:
        return {"available": False, "note": "Couldn't test for this in the current environment.", "flags": []}

    candidates = sorted(correlation_pairs, key=lambda p: -abs(p.r))[:MAX_PAIRS_CHECKED]
    flags = []

    for pair in candidates:
        overall_sign = 1 if pair.r > 0 else -1
        c1, c2 = pair.col1, pair.col2

        for dim in dims:
            sub = df[[c1, c2, dim.column]].dropna()
            if sub.empty:
                continue

            subgroup_results = []
            for category, group in sub.groupby(dim.column):
                r = _correlation(group[c1].to_numpy(dtype=float), group[c2].to_numpy(dtype=float))
                if r is None or abs(r) < MIN_SUBGROUP_R:
                    continue
                subgroup_results.append({"category": str(category), "r": r, "n": int(len(group))})

            if len(subgroup_results) < MIN_VALID_SUBGROUPS:
                continue

            all_reversed = all((1 if s["r"] > 0 else -1) != overall_sign for s in subgroup_results)
            if not all_reversed:
                continue

            reversed_direction = "negative" if overall_sign > 0 else "positive"
            overall_direction = "positive" if overall_sign > 0 else "negative"
            summary = (
                f"Overall, {c1} and {c2} show a {overall_direction} relationship (r={pair.r:.2f}) -- but split by "
                f"{dim.column}, every group ({', '.join(s['category'] for s in subgroup_results)}) actually shows a "
                f"{reversed_direction} relationship instead. The aggregate trend is being driven by how the groups "
                f"differ, not by a real {overall_direction} relationship within any of them."
            )

            flags.append({
                "col1": c1,
                "col2": c2,
                "dimension": dim.column,
                "overall_r": round(pair.r, 3),
                "subgroups": subgroup_results,
                "summary": summary,
            })

    return {"available": True, "note": None, "flags": flags}
