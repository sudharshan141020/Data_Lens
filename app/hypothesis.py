"""
A/B and hypothesis-test mode: a DIRECTED question.

Everything else in DataLens is discovery -- it looks at the data and tells you
what stands out. This answers the question people actually bring: "is group B
different from group A on this outcome?" Pick a group column, the two groups to
compare, and an outcome. The test is chosen for you, and the answer comes back
as an effect size, an interval and a plain-language verdict rather than a bare
p-value.

Which test, and why (the reason is returned with the result, never hidden):

* Numeric outcome
    - Welch's t-test (the same one period_comparison.py uses -- the p-value
      comes from that function) when each group has at least 30 rows, or when
      smaller groups pass a normality check. Compares means; does not assume
      equal variances. Effect size: Cohen's d (Hedges-corrected). Interval: the
      95% interval of the difference in means (Welch-Satterthwaite).
    - Mann-Whitney U when a group has fewer than 30 rows AND is visibly
      non-normal (Shapiro-Wilk p < 0.05). Compares whether one group tends to
      have higher values; makes no normality assumption. Effect size:
      rank-biserial correlation and the probability that a random B row beats
      a random A row. Interval: bootstrap interval of the difference in medians.
    - The other test is always run as a cross-check, and the verdict says when
      they disagree (which usually means outliers or heavy skew are deciding it).
* Categorical outcome (including a 0/1 flag)
    - Pearson chi-square when every expected cell count is at least 5; Fisher's
      exact test for a 2x2 table with a smaller expected count. Effect size:
      Cramer's V; for a 2x2 also the rate in each group, the difference with a
      Newcombe-Wilson interval, and the relative risk.

Deliberate limits:
* Two groups at a time. "A vs B" is the question; for a column with more levels
  the caller picks which two. (A multi-group test would answer a different
  question: "is there any difference anywhere?")
* Rows are assumed independent. If the same customer or patient appears in many
  rows, the p-value is too optimistic, and the result says so.
* A p-value answers "could this gap be chance?", not "does it matter?", which is
  why the effect size and the interval are the headline and the p-value is not.
* No multiple-testing correction: it is one question the person chose to ask.
  The result says that running many tests and reporting the best one inflates
  false positives.

Everything is standard scipy plus the arithmetic written out below; no model.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from app.period_comparison import _welch_t_test, SIGNIFICANCE_ALPHA

try:  # scipy is already a dependency (period_comparison, correlation_center)
    from scipy import stats as _stats
except ImportError:  # pragma: no cover
    _stats = None

MIN_PER_GROUP = 5            # same floor as period_comparison.MIN_ROWS_PER_PERIOD
SMALL_GROUP = 30             # below this a group is "small" for choosing between t and Mann-Whitney
NORMALITY_ALPHA = 0.05
MAX_OUTCOME_LEVELS = 10      # a categorical outcome with more levels is not a useful chi-square
N_BOOTSTRAP = 1000
MAX_BOOTSTRAP_ROWS = 5000    # per group; keeps a 100k-row test fast
CONFIDENCE = 0.95


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
MINUS = "\u2212"


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.1f}"
    if a >= 1:
        return f"{v:,.2f}"
    return f"{v:.3g}"


def _signed(v: float) -> str:
    return f"{'+' if v >= 0 else MINUS}{_fmt(abs(v))}"


def _p_text(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _label_d(d: float) -> str:
    a = abs(d)
    return "negligible" if a < 0.2 else "small" if a < 0.5 else "medium" if a < 0.8 else "large"


def _label_r(r: float) -> str:
    a = abs(r)
    return "negligible" if a < 0.1 else "small" if a < 0.3 else "medium" if a < 0.5 else "large"


def _label_v(v: float) -> str:
    return _label_r(v)  # same conventional cut-offs for a 2-column table


def _nan_to_none(x):
    if x is None:
        return None
    try:
        return None if (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x
    except TypeError:
        return x


# ---------------------------------------------------------------------------
# numeric outcome
# ---------------------------------------------------------------------------
def _welch_interval(a: np.ndarray, b: np.ndarray) -> tuple:
    """95% interval for mean(b) - mean(a), Welch-Satterthwaite degrees of freedom."""
    va, vb = a.var(ddof=1), b.var(ddof=1)
    na, nb = len(a), len(b)
    se2 = va / na + vb / nb
    se = math.sqrt(se2)
    diff = float(b.mean() - a.mean())
    if se == 0:
        return diff, diff, diff, float(na + nb - 2)
    df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    t_crit = float(_stats.t.ppf(0.5 + CONFIDENCE / 2, df))
    return diff, diff - t_crit * se, diff + t_crit * se, float(df)


def _hedges_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d with the average of the two variances in the denominator (it
    stays sensible when the variances differ, which is why Welch is used), then
    Hedges' small-sample correction. Positive means B is higher."""
    s = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    if s == 0:
        return 0.0
    d = (b.mean() - a.mean()) / s
    return float(d * (1 - 3 / (4 * (len(a) + len(b)) - 9)))


def _bootstrap_median_diff(a: np.ndarray, b: np.ndarray, seed: int = 42) -> tuple:
    rng = np.random.default_rng(seed)
    if len(a) > MAX_BOOTSTRAP_ROWS:
        a = rng.choice(a, MAX_BOOTSTRAP_ROWS, replace=False)
    if len(b) > MAX_BOOTSTRAP_ROWS:
        b = rng.choice(b, MAX_BOOTSTRAP_ROWS, replace=False)
    ia = rng.integers(0, len(a), (N_BOOTSTRAP, len(a)))
    ib = rng.integers(0, len(b), (N_BOOTSTRAP, len(b)))
    diffs = np.median(b[ib], axis=1) - np.median(a[ia], axis=1)
    lo, hi = np.percentile(diffs, [100 * (1 - CONFIDENCE) / 2, 100 * (1 + CONFIDENCE) / 2])
    return float(lo), float(hi)


def _choose_numeric_test(a: np.ndarray, b: np.ndarray, name_a: str, name_b: str) -> tuple:
    """-> ('welch_t' | 'mann_whitney', reason)"""
    na, nb = len(a), len(b)
    if min(na, nb) >= SMALL_GROUP:
        return "welch_t", (f"Both groups have at least {SMALL_GROUP} rows ({na:,} and {nb:,}), so the comparison of "
                           "averages is reliable even if the values are skewed, and Welch's t-test does not assume equal spread.")
    failed = []
    for arr, name in ((a, name_a), (b, name_b)):
        if len(arr) >= 3 and np.ptp(arr) > 0:
            p = float(_stats.shapiro(arr).pvalue)
            if p < NORMALITY_ALPHA:
                failed.append(name)
    if failed:
        return "mann_whitney", (f"{' and '.join(failed)} {'has' if len(failed) == 1 else 'have'} fewer than {SMALL_GROUP} rows and "
                                "do not look normally distributed, so Mann-Whitney U (which makes no normality assumption) is used instead of a t-test.")
    return "welch_t", (f"A group has fewer than {SMALL_GROUP} rows, but both look roughly normal, so Welch's t-test is appropriate "
                       "(it does not assume equal spread).")


def _numeric_result(a: np.ndarray, b: np.ndarray, name_a: str, name_b: str, outcome: str) -> dict:
    test_id, why = _choose_numeric_test(a, b, name_a, name_b)

    welch_p = _welch_t_test(a, b)
    mw = _stats.mannwhitneyu(b, a, alternative="two-sided")
    mw_p = float(mw.pvalue)
    diff_mean, ci_lo, ci_hi, df = _welch_interval(a, b)
    d = _hedges_d(a, b)

    stats_block = {
        name_a: {"n": int(len(a)), "mean": float(a.mean()), "median": float(np.median(a)), "std": float(a.std(ddof=1))},
        name_b: {"n": int(len(b)), "mean": float(b.mean()), "median": float(np.median(b)), "std": float(b.std(ddof=1))},
    }

    if test_id == "welch_t" and welch_p is None:
        test_id = "mann_whitney"   # Welch could not be computed; fall back rather than fail
        why = "Welch's t-test could not be computed on these values, so Mann-Whitney U is used."

    if test_id == "welch_t":
        p = welch_p
        out = {
            "test": {"id": "welch_t", "name": "Welch's t-test", "why": why},
            "statistic_label": f"Difference in means (B {MINUS} A)",
            "difference": diff_mean, "interval": [ci_lo, ci_hi], "interval_method": "95% interval (Welch-Satterthwaite)",
            "effect_size": {"name": "Cohen's d (Hedges-corrected)", "value": d, "label": _label_d(d)},
            "df": df,
        }
        other_name, other_p = "Mann-Whitney U", mw_p
    else:
        p = mw_p
        # rank-biserial correlation: positive when B tends to be higher
        u_b = float(mw.statistic)                   # U statistic for b vs a
        prob_b_higher = u_b / (len(a) * len(b))     # P(random B > random A) + 0.5 * P(tie)
        rbc = 2 * prob_b_higher - 1
        lo, hi = _bootstrap_median_diff(a, b)
        out = {
            "test": {"id": "mann_whitney", "name": "Mann-Whitney U", "why": why},
            "statistic_label": f"Difference in medians (B {MINUS} A)",
            "difference": float(np.median(b) - np.median(a)), "interval": [lo, hi],
            "interval_method": f"95% bootstrap interval ({N_BOOTSTRAP:,} resamples)",
            "effect_size": {"name": "Rank-biserial correlation", "value": rbc, "label": _label_r(rbc)},
            "prob_b_higher": prob_b_higher,
        }
        other_name, other_p = "Welch's t-test", welch_p

    out.update({
        "kind": "numeric",
        "p_value": float(p),
        "stats": stats_block,
        "cross_check": {"test": other_name, "p_value": _nan_to_none(other_p),
                        "agrees": other_p is not None and ((other_p < SIGNIFICANCE_ALPHA) == (p < SIGNIFICANCE_ALPHA))},
    })
    return out


# ---------------------------------------------------------------------------
# categorical outcome
# ---------------------------------------------------------------------------
def _wilson(k: int, n: int, z: float) -> tuple:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _newcombe_diff(k1: int, n1: int, k2: int, n2: int) -> tuple:
    """Newcombe-Wilson interval for p2 - p1 (hybrid score method). Behaves well
    near 0% and 100%, where the usual normal-approximation interval does not."""
    z = float(_stats.norm.ppf(0.5 + CONFIDENCE / 2))
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = _wilson(k1, n1, z)
    l2, u2 = _wilson(k2, n2, z)
    d = p2 - p1
    lo = d - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    hi = d + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)
    return lo, hi


def _cramers_v(chi2: float, n: int, r: int, c: int) -> float:
    k = min(r - 1, c - 1)
    return float(math.sqrt(chi2 / (n * k))) if n and k else 0.0


def _categorical_result(table: pd.DataFrame, name_a: str, name_b: str, positive: Optional[str]) -> dict:
    """`table` has the two groups as rows (a first) and outcome levels as columns."""
    levels = [str(c) for c in table.columns]
    n_a, n_b = int(table.loc[name_a].sum()), int(table.loc[name_b].sum())
    counts = {name_a: {str(c): int(table.loc[name_a, c]) for c in table.columns},
              name_b: {str(c): int(table.loc[name_b, c]) for c in table.columns}}
    rates = [{"level": str(c), "rate_a": table.loc[name_a, c] / n_a, "rate_b": table.loc[name_b, c] / n_b} for c in table.columns]

    # 2x2: either a binary outcome, or one level singled out against "everything else"
    collapsed = None
    if len(levels) == 2 or positive is not None:
        pos = positive if positive is not None else levels[-1]
        k_a, k_b = int(table.loc[name_a, pos]), int(table.loc[name_b, pos])
        collapsed = (str(pos), k_a, k_b)
        grid = np.array([[k_a, n_a - k_a], [k_b, n_b - k_b]])
    else:
        grid = table.to_numpy()

    chi2, p_chi, dof, expected = _stats.chi2_contingency(grid, correction=False)
    small_expected = bool((expected < 5).any())
    is_2x2 = grid.shape == (2, 2)

    if is_2x2 and small_expected:
        odds, p = _stats.fisher_exact(grid)
        test = {"id": "fisher_exact", "name": "Fisher's exact test",
                "why": "A 2\u00d72 table with an expected count below 5 makes the chi-square approximation unreliable, so the exact test is used."}
    else:
        p = float(p_chi)
        test = {"id": "chi_square", "name": "Chi-square test of independence",
                "why": ("Every expected count is at least 5, so the chi-square approximation is reliable."
                        if not small_expected else
                        "Some expected counts are below 5 (more than 2\u00d72, so there is no exact option here); treat the p-value as approximate and consider merging rare categories.")}

    v = _cramers_v(float(chi2), int(grid.sum()), *grid.shape)
    out = {
        "kind": "categorical",
        "test": test,
        "p_value": float(p),
        "counts": counts,
        "rates": rates,
        "effect_size": {"name": "Cramer's V" if not is_2x2 else "Cramer's V (phi)", "value": v, "label": _label_v(v)},
        "stats": {name_a: {"n": n_a}, name_b: {"n": n_b}},
        "outcome_levels": levels,
    }
    if collapsed:
        pos, k_a, k_b = collapsed
        r_a, r_b = k_a / n_a, k_b / n_b
        lo, hi = _newcombe_diff(k_a, n_a, k_b, n_b)
        out.update({
            "positive_level": pos,
            "difference": r_b - r_a, "interval": [lo, hi],
            "interval_method": "95% Newcombe-Wilson interval",
            "statistic_label": f"Difference in rate of \"{pos}\" (B {MINUS} A)",
            "rate": {name_a: r_a, name_b: r_b},
            "relative_risk": (r_b / r_a) if r_a > 0 else None,
        })
    else:
        # Where is the gap biggest? Useful because V alone doesn't say.
        gap = max(out["rates"], key=lambda r: abs(r["rate_b"] - r["rate_a"]))
        out["biggest_gap"] = gap
        out["interval"] = None
        out["interval_method"] = None
    return out


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------
def _verdict(res: dict, name_a: str, name_b: str, outcome: str) -> dict:
    p = res["p_value"]
    sig = p < SIGNIFICANCE_ALPHA
    pt = _p_text(p)
    es = res["effect_size"]

    if res["kind"] == "numeric":
        is_welch = res["test"]["id"] == "welch_t"
        stat = "average" if is_welch else "typical (median)"
        sa, sb = res["stats"][name_a], res["stats"][name_b]
        va, vb = (sa["mean"], sb["mean"]) if is_welch else (sa["median"], sb["median"])
        diff, (lo, hi) = res["difference"], res["interval"]
        interval = f"95% interval {_signed(lo)} to {_signed(hi)}"
        if sig:
            higher, lower = (name_b, name_a) if diff > 0 else (name_a, name_b)
            head = (f"{higher} has a higher {stat} {outcome} than {lower}: "
                    f"{_fmt(vb)} vs {_fmt(va)} ({_signed(diff)}, {interval}). "
                    f"That gap is unlikely to be chance ({pt}), and the effect is {es['label']}.")
        else:
            head = (f"No clear difference in {outcome} between {name_a} and {name_b}: the gap of {_signed(diff)} "
                    f"is within what chance alone can produce ({pt}). "
                    f"The data are consistent with a real difference anywhere from {_signed(lo)} to {_signed(hi)} (B \u2212 A).")
        if not is_welch and sig:
            head += (f" A random {name_b} row is higher than a random {name_a} row "
                     f"{res['prob_b_higher'] * 100:.0f}% of the time (50% would mean no difference).")
    else:
        if "rate" in res:
            r = res["rate"]
            diff, (lo, hi) = res["difference"], res["interval"]
            pos = res["positive_level"]
            pts = lambda x: f"{'+' if x >= 0 else MINUS}{abs(x) * 100:.1f} points"
            interval = f"95% interval {pts(lo)} to {pts(hi)}"
            if sig:
                higher, lower = (name_b, name_a) if diff > 0 else (name_a, name_b)
                head = (f"{higher} has a higher rate of {outcome} = {pos} than {lower}: "
                        f"{r[name_b] * 100:.1f}% vs {r[name_a] * 100:.1f}% ({pts(diff)}, {interval}). "
                        f"That gap is unlikely to be chance ({pt}), and the effect is {es['label']}.")
            else:
                head = (f"No clear difference in the rate of {outcome} = {pos} between {name_a} and {name_b}: "
                        f"{r[name_b] * 100:.1f}% vs {r[name_a] * 100:.1f}% ({pts(diff)}) is within what chance alone "
                        f"can produce ({pt}). The data are consistent with a real difference anywhere from {pts(lo)} to {pts(hi)} (B {MINUS} A).")
        else:
            gap = res["biggest_gap"]
            if sig:
                head = (f"The mix of {outcome} differs between {name_a} and {name_b} ({pt}), and the effect is {es['label']}. "
                        f"The biggest gap is {gap['level']}: {gap['rate_b'] * 100:.1f}% in {name_b} vs {gap['rate_a'] * 100:.1f}% in {name_a}.")
            else:
                head = (f"No clear difference in the mix of {outcome} between {name_a} and {name_b}: "
                        f"what you see is within what chance alone can produce ({pt}).")

    caveats = [
        "Assumes each row is an independent observation. If the same customer, patient or product appears in many rows, "
        "the p-value is more optimistic than it should be.",
        "A p-value says whether a gap could be chance, not whether it matters. Judge size by the effect and the interval.",
        "Run on a question you chose before looking. Testing many pairs and reporting the best one produces false positives.",
    ]
    cc = res.get("cross_check")
    if cc and not cc["agrees"]:
        caveats.insert(0, f"The cross-check ({cc['test']}, {_p_text(cc['p_value']) if cc['p_value'] is not None else 'n/a'}) reaches a "
                          "different conclusion. That usually means a few extreme values or heavy skew are deciding the result, so be cautious.")
    ratio = max(res["stats"][name_a]["n"], res["stats"][name_b]["n"]) / max(1, min(res["stats"][name_a]["n"], res["stats"][name_b]["n"]))
    if ratio >= 5:
        caveats.append(f"The groups are very different in size (about {ratio:.0f} to 1), so the smaller group limits how precise this can be.")
    if not sig and min(res["stats"][name_a]["n"], res["stats"][name_b]["n"]) < SMALL_GROUP:
        caveats.append("With a group this small, 'no clear difference' mostly means 'not enough data to tell'.")
    return {"significant": bool(sig), "headline": head, "caveats": caveats}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def _unavailable(note: str) -> dict:
    return {"available": False, "note": note}


def run_hypothesis_test(groups, outcomes, group_a: str, group_b: str, group_name: str = "group",
                        outcome_name: str = "outcome", outcome_kind: str = "auto",
                        positive_level: Optional[str] = None) -> dict:
    """`groups` and `outcomes` are parallel lists (one entry per row)."""
    if _stats is None:  # pragma: no cover
        return _unavailable("SciPy is not installed on the server.")
    if len(groups) != len(outcomes):
        return _unavailable("The group and outcome columns have different lengths.")
    group_a, group_b = str(group_a), str(group_b)
    if group_a == group_b:
        return _unavailable("Pick two different groups to compare.")

    df = pd.DataFrame({"g": pd.Series(groups, dtype=object), "o": pd.Series(outcomes, dtype=object)})
    df = df[df["g"].notna() & df["o"].notna()]
    df["g"] = df["g"].astype(str)
    df = df[df["g"].isin([group_a, group_b])]
    na, nb = int((df["g"] == group_a).sum()), int((df["g"] == group_b).sum())
    if na < MIN_PER_GROUP or nb < MIN_PER_GROUP:
        missing = group_a if na < MIN_PER_GROUP else group_b
        return _unavailable(f"Needs at least {MIN_PER_GROUP} rows with a value in each group; "
                            f"{missing} has {min(na, nb)}.")

    numeric = pd.to_numeric(df["o"], errors="coerce")
    all_numeric = bool(numeric.notna().all())
    if outcome_kind == "auto":
        kind = "numeric" if (all_numeric and numeric.nunique() > 2) else "categorical"
    elif outcome_kind in ("numeric", "categorical"):
        kind = outcome_kind
    else:
        return _unavailable("outcome_kind must be 'auto', 'numeric' or 'categorical'.")

    if kind == "numeric":
        if not all_numeric:
            return _unavailable(f"{outcome_name} has non-numeric values, so it cannot be compared as a number.")
        a = numeric[df["g"] == group_a].to_numpy(dtype=float)
        b = numeric[df["g"] == group_b].to_numpy(dtype=float)
        if not (np.isfinite(a).all() and np.isfinite(b).all()):
            return _unavailable("The outcome contains infinite values.")
        if a.std(ddof=1) == 0 and b.std(ddof=1) == 0:
            return _unavailable(f"{outcome_name} has no variation within either group, so there is nothing to test.")
        res = _numeric_result(a, b, group_a, group_b, outcome_name)
    else:
        outcome_str = df["o"].map(lambda v: str(int(v)) if isinstance(v, float) and float(v).is_integer() else str(v))
        levels = sorted(outcome_str.unique())
        if len(levels) < 2:
            return _unavailable(f"{outcome_name} has only one value in these groups, so there is nothing to compare.")
        if len(levels) > MAX_OUTCOME_LEVELS and positive_level is None:
            return _unavailable(f"{outcome_name} has {len(levels)} different values; pick one value to test, "
                                f"or use a column with at most {MAX_OUTCOME_LEVELS}.")
        if positive_level is not None:
            positive_level = str(positive_level)
            if positive_level not in levels:
                return _unavailable(f"\"{positive_level}\" does not appear in {outcome_name} for these groups.")
        table = pd.crosstab(df["g"], outcome_str).reindex([group_a, group_b])
        res = _categorical_result(table, group_a, group_b, positive_level)

    verdict = _verdict(res, group_a, group_b, outcome_name)
    return {
        "available": True,
        "group_column": group_name,
        "outcome_column": outcome_name,
        "group_a": group_a,
        "group_b": group_b,
        "alpha": SIGNIFICANCE_ALPHA,
        **res,
        **verdict,
    }
