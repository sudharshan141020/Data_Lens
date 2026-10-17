"""
Robustness check: "does this hold without the outliers?"

The rest of the app already asks whether a result could be sampling noise
(bootstrap confidence intervals, the gated weak points). That is a different
failure mode from this one: a result that is perfectly real for the data in
hand but is really about a handful of extreme rows. An average order value
that is mostly three enormous orders, or a correlation of 0.8 that is one
point in the corner of the scatter, is not noise -- resampling the same rows
would reproduce it every time -- and a confidence interval will not warn you.

So this re-runs the headline numbers and the top correlations with extreme
values set aside, and reports anything that moves materially or flips:

* "Extreme" is the textbook Tukey fence: outside Q1 - 1.5*IQR .. Q3 + 1.5*IQR
  of that measure. No tuning knob a reader has to trust. Fences are computed
  once per measure on the full column, and a row is set aside for a
  correlation if it is extreme on EITHER of the two columns.
* A summed KPI is judged differently from an averaged one. Dropping 3% of
  the rows from a total always lowers it, so "the total fell" proves nothing;
  what matters is how much of the total those few rows carry. An averaged KPI
  is compared directly (full mean vs trimmed mean).
* A correlation is reported as holds / weakens / strengthens / loses
  significance / flips. "Material" is the size of the change in r, never a
  crossing of a label boundary: 0.702 -> 0.687 is not a finding just because
  one of those is called "strong" and the other "moderate". "Flips" needs both versions to be meaningful (|r| >=
  0.1), so a wobble between +0.03 and -0.04 is not called a sign flip.
* When more than 5% of rows fall outside the fences the measure is called
  "skewed" rather than "sensitive": a few outliers is a claim about a few
  rows, and a tiered measure (discount levels, price bands) has legitimate
  values out there. A sign flip or lost significance still counts regardless.
* Correlation is recomputed with the same function the Correlation Center
  uses (_correlate_pair), so the "full" side matches what is already on screen.

It sets the rows aside to test sensitivity; it does not say they are errors,
and it never changes any number elsewhere in the app. Genuine extreme rows
are often the most important rows in the data -- the point is to know when
the story depends on them.

Nothing here is a new statistic: quantiles, means, sums and the Pearson r the
app already computes.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.correlation_center import _correlate_pair, SIGNIFICANCE_ALPHA

FENCE_K = 1.5
MIN_ROWS = 10                  # same floor as confidence_intervals.MIN_ROWS
MIN_ROWS_AFTER_TRIM = 10       # a correlation on fewer rows than this is not worth reporting
MAX_MEASURES = 6               # same measures the KPI confidence intervals cover
MAX_PAIRS = 8                  # top correlations by |r|

AVG_MATERIAL_PCT = 10.0        # an averaged KPI moving this much (either way) is material
SUM_MATERIAL_SHARE_PCT = 20.0  # a summed KPI is material when extreme rows carry this much of it
R_MATERIAL_DELTA = 0.15        # correlation moving this much is material
HEAVY_TRIM_PCT = 5.0            # more than this share of rows outside the fences is a skewed/tiered measure, not "a few outliers"
R_FLIP_MIN = 0.10              # both sides need at least this |r| to call it a sign flip


def _fences(values: pd.Series, k: float = FENCE_K) -> Optional[tuple]:
    """(low, high) Tukey fences, or None when the column has no spread to
    define "extreme" against (IQR of zero: e.g. mostly zeros)."""
    q1, q3 = values.quantile([0.25, 0.75])
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr <= 0:
        return None
    return float(q1 - k * iqr), float(q3 + k * iqr)


def _round(v: float) -> float:
    return round(float(v), 2)


def _kpi_check(df: pd.DataFrame, measure) -> Optional[dict]:
    vals = df[measure.column].dropna().astype(float)
    n = len(vals)
    if n < MIN_ROWS:
        return None

    avg = measure.aggregation == "avg"
    full = float(vals.mean() if avg else vals.sum())
    base = {"measure": measure.column, "aggregation": measure.aggregation, "n": int(n)}

    fences = _fences(vals)
    if fences is None:
        return {**base, "n_flagged": 0, "flagged_pct": 0.0, "full": _round(full), "trimmed": _round(full),
                "change_pct": 0.0, "flagged_share_pct": 0.0, "low_fence": None, "high_fence": None,
                "material": False, "verdict": "no_spread",
                "note": "Most values are identical, so there is no spread to call anything extreme."}

    low, high = fences
    kept = vals[(vals >= low) & (vals <= high)]
    n_flagged = int(n - len(kept))
    if kept.empty:
        return None
    trimmed = float(kept.mean() if avg else kept.sum())

    change_pct = round((trimmed - full) / abs(full) * 100, 1) if full else None
    share_pct = round((full - trimmed) / abs(full) * 100, 1) if (full and not avg) else None
    flagged_pct = round(n_flagged / n * 100, 1)

    if n_flagged == 0:
        verdict, material = "stable", False
        note = "No extreme values, so nothing to set aside."
    elif flagged_pct > HEAVY_TRIM_PCT:
        # "A few rows drive this" is not what is going on when one row in
        # ten is outside the fences: the measure is skewed or has natural
        # tiers (discount levels, price bands). Say so rather than crying outlier.
        verdict, material = "skewed", False
        moved = (f" The {'average' if avg else 'total'} would move {abs(change_pct if avg else share_pct):.1f}% without them."
                 if (change_pct if avg else share_pct) is not None else "")
        note = (f"{n_flagged} rows ({flagged_pct}%) fall outside the fences, too many to be a few outliers: "
                f"this measure is skewed or has natural tiers.{moved}")
    elif avg:
        material = change_pct is not None and abs(change_pct) >= AVG_MATERIAL_PCT
        verdict = "sensitive" if material else "stable"
        word = "falls" if (change_pct or 0) < 0 else "rises"
        note = (f"Without the {n_flagged} extreme row{'s' if n_flagged != 1 else ''} ({flagged_pct}%), the average "
                f"{word} {abs(change_pct):.1f}%." if change_pct is not None else "No baseline to compare against.")
    else:
        material = share_pct is not None and abs(share_pct) >= SUM_MATERIAL_SHARE_PCT
        verdict = "concentrated" if material else "stable"
        note = (f"The {n_flagged} extreme row{'s' if n_flagged != 1 else ''} ({flagged_pct}% of rows) "
                f"carr{'ies' if n_flagged == 1 else 'y'} {share_pct:.1f}% of the total." if share_pct is not None
                else "No baseline to compare against.")

    return {**base, "n_flagged": n_flagged, "flagged_pct": flagged_pct, "full": _round(full), "trimmed": _round(trimmed),
            "change_pct": change_pct, "flagged_share_pct": share_pct,
            "low_fence": _round(low), "high_fence": _round(high), "material": bool(material),
            "verdict": verdict, "note": note}


def _pair_check(df: pd.DataFrame, c1: str, c2: str, fences: dict) -> Optional[dict]:
    full = _correlate_pair(df, c1, c2)
    if full is None:
        return None
    r0, n0, p0 = full

    pair = df[[c1, c2]].dropna()
    keep = pd.Series(True, index=pair.index)
    for c in (c1, c2):
        f = fences.get(c)
        if f is not None:
            keep &= (pair[c] >= f[0]) & (pair[c] <= f[1])
    removed = int(len(pair) - keep.sum())

    out = {"col1": c1, "col2": c2, "r_full": round(float(r0), 3), "n_full": int(n0),
           "p_full": round(float(p0), 4), "n_removed": removed, "removed_pct": round(removed / n0 * 100, 1)}

    if removed == 0:
        return {**out, "r_trimmed": out["r_full"], "n_trimmed": int(n0), "p_trimmed": out["p_full"], "delta": 0.0,
                "verdict": "holds", "material": False, "note": "No extreme rows in either column, so nothing changes."}

    trimmed = df.loc[pair.index[keep.to_numpy()], [c1, c2]]
    t = _correlate_pair(trimmed, c1, c2) if len(trimmed) >= MIN_ROWS_AFTER_TRIM else None
    if t is None:
        return {**out, "r_trimmed": None, "n_trimmed": int(len(trimmed)), "p_trimmed": None, "delta": None,
                "verdict": "insufficient", "material": True,
                "note": "Too few rows (or no spread) are left without the extreme rows to say whether it holds."}
    r1, n1, p1 = t
    delta = float(r1 - r0)
    out.update({"r_trimmed": round(float(r1), 3), "n_trimmed": int(n1), "p_trimmed": round(float(p1), 4),
                "delta": round(delta, 3)})

    sig0, sig1 = p0 < SIGNIFICANCE_ALPHA, p1 < SIGNIFICANCE_ALPHA
    word = f"{removed} extreme row{'s' if removed != 1 else ''}"
    if r0 * r1 < 0 and abs(r0) >= R_FLIP_MIN and abs(r1) >= R_FLIP_MIN:
        verdict, material = "flips", True
        note = f"The sign reverses without {word}: r goes from {r0:+.2f} to {r1:+.2f}."
    elif sig0 and not sig1:
        verdict, material = "lost_significance", True
        note = f"Significant with all rows (r={r0:+.2f}), not significant without {word} (r={r1:+.2f})."
    elif abs(delta) >= R_MATERIAL_DELTA:
        material = True
        if abs(r1) < abs(r0):
            verdict, note = "weakens", f"Weaker without {word}: r goes from {r0:+.2f} to {r1:+.2f}."
        else:
            verdict, note = "strengthens", f"Stronger without {word}: r goes from {r0:+.2f} to {r1:+.2f}, so the extremes were hiding it."
    else:
        verdict, material = "holds", False
        note = f"Holds without {word}: r {r0:+.2f} to {r1:+.2f}."

    removed_pct = round(removed / n0 * 100, 1)
    out["removed_pct"] = removed_pct
    if removed_pct > HEAVY_TRIM_PCT and verdict in {"weakens", "strengthens"}:
        material = False
        note += f" That is {removed_pct}% of the rows, so read it as a skewed measure rather than a few outliers."
    return {**out, "verdict": verdict, "material": material, "note": note}


def _overall(kpis: list, corrs: list) -> dict:
    mk = [k for k in kpis if k["material"]]
    flips = [c for c in corrs if c["verdict"] == "flips"]
    mc = [c for c in corrs if c["material"]]
    flagged_any = any(k["n_flagged"] for k in kpis) or any(c["n_removed"] for c in corrs)

    if not flagged_any:
        return {"verdict": "robust", "material_kpis": 0, "material_correlations": 0, "flipped_correlations": 0,
                "headline": "No extreme values by the standard outlier rule, so nothing here depends on a few rows."}
    if not mk and not mc:
        return {"verdict": "robust", "material_kpis": 0, "material_correlations": 0, "flipped_correlations": 0,
                "headline": "The headline numbers and top correlations hold with the extreme rows set aside."}

    parts = []
    if mk:
        parts.append(f"{len(mk)} of {len(kpis)} headline number{'s' if len(kpis) != 1 else ''} move materially")
    if mc:
        flip_txt = f", {len(flips)} reverse{'s' if len(flips) == 1 else ''} sign" if flips else ""
        parts.append(f"{len(mc)} of {len(corrs)} top correlation{'s' if len(corrs) != 1 else ''} change{'s' if len(mc) == 1 else ''}{flip_txt}")
    return {"verdict": "sensitive", "material_kpis": len(mk), "material_correlations": len(mc),
            "flipped_correlations": len(flips),
            "headline": "Sensitive to extreme rows: " + "; ".join(parts) + " without them."}


def analyze_robustness(df: pd.DataFrame, profile, correlation_pairs: Optional[list] = None) -> dict:
    """`correlation_pairs` are CorrelationPair objects from analyze_correlations
    (already sorted by |r|); the top few are re-tested."""
    unavailable = {"available": False, "note": None, "kpis": [], "correlations": []}
    measures = list(profile.measures)[:MAX_MEASURES]
    if not measures:
        return {**unavailable, "note": "Needs at least one numeric measure to test."}

    kpis = []
    for m in measures:
        if m.column in df.columns:
            k = _kpi_check(df, m)
            if k:
                kpis.append(k)
    if not kpis:
        return {**unavailable, "note": f"Needs at least {MIN_ROWS} non-missing values in a measure."}

    # fences for every measure that appears in a correlation, not only the six KPIs
    fences = {}
    for p in (correlation_pairs or [])[:MAX_PAIRS]:
        for c in (p.col1, p.col2):
            if c not in fences and c in df.columns:
                v = df[c].dropna().astype(float)
                fences[c] = _fences(v) if len(v) >= MIN_ROWS else None

    corrs = []
    for p in (correlation_pairs or [])[:MAX_PAIRS]:
        c = _pair_check(df, p.col1, p.col2, fences)
        if c:
            corrs.append(c)

    return {
        "available": True,
        "note": None,
        "method": f"Rows outside the usual outlier fences (Q1 \u2212 {FENCE_K}\u00d7IQR to Q3 + {FENCE_K}\u00d7IQR) are set aside "
                  "and each number is recomputed. The rows are not removed from anything else.",
        "thresholds": {"avg_pct": AVG_MATERIAL_PCT, "sum_share_pct": SUM_MATERIAL_SHARE_PCT, "r_delta": R_MATERIAL_DELTA},
        "overall": _overall(kpis, corrs),
        "kpis": kpis,
        "correlations": corrs,
    }
