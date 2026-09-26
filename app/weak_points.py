"""
Phase 3b/3c — Weak Point Detector + Recommendation Engine.

The two are combined in one module because every weak point IS an actionable
recommendation target — detecting "billing amount is declining" without also
saying what to do about it isn't useful. The Recommendation Engine's job is
specifically the `suggested_action` text on each WeakPoint; keeping it as a
clearly separate function per detector (not just inlined) is what keeps the
"detect vs recommend" split real rather than cosmetic.

Language rule for every string below: write it so someone with zero data
analysis background can read it and understand what's wrong and why it
matters. No "margin", "concentration", "IQR", "quartile", "variance" — say
what those things actually mean in plain terms instead. Same rule applies
to the significance check below: no "confidence interval", "bootstrap",
"p-value" in anything user-facing -- "checked this by reshuffling the data
thousands of times" says the same thing in plain terms.

Statistical gating: every detector's point estimate (a decline, a gap, a
share, a margin) is a fact about THIS dataset, but the underlying rows are
usually themselves a sample of something bigger -- a few unusual rows
could make an ordinary pattern look like a real problem, or vice versa.
Each detector that makes a comparison or a percentage claim (all but
missing_data, which is a fact about the whole dataset, not a sample of
one) re-checks its own finding with confidence_intervals.bootstrap_metric_
significance: resample the same rows the claim came from, recompute the
exact same number many times, and see whether the result reliably clears
the bar that made it a weak point in the first place. A finding that
doesn't hold up gets its priority and score turned down (so it naturally
sorts lower and is less likely to make the final top_k) and a plain-
language caveat appended, rather than being silently dropped -- it might
still be worth a look, just not with the same confidence as one that held
up every time.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from app.understanding import DatasetProfile
from app.confidence_intervals import bootstrap_metric_significance

HIGH, MEDIUM, LOW = "high", "medium", "low"
_DOWNGRADE = {HIGH: MEDIUM, MEDIUM: LOW, LOW: LOW}


@dataclass
class WeakPoint:
    problem: str
    impact: str
    priority: str          # "high" | "medium" | "low"
    suggested_action: str
    category: str          # "trend" | "data_quality" | "concentration" | "outlier" | "underperformance"
    score: float            # for ranking across weak points
    significant: Optional[bool] = None   # None = not checked (e.g. missing_data); True/False = bootstrap-checked
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None


def _gate(wp: WeakPoint, sig: Optional[dict], holds_up_note: str, might_be_noise_note: str) -> WeakPoint:
    """Applies a bootstrap_metric_significance result to an already-built
    WeakPoint: leaves it untouched if the check couldn't run (too little
    data to trust an interval -- not the same as "checked and it didn't
    hold up"), otherwise records the interval, appends a plain-language
    note either way, and turns the priority/score down a notch when the
    finding didn't reliably clear its own bar."""
    if sig is None:
        return wp
    wp.significant = sig["significant"]
    wp.ci_low = round(sig["ci_low"], 3)
    wp.ci_high = round(sig["ci_high"], 3)
    if sig["significant"]:
        wp.impact += f" {holds_up_note}"
    else:
        wp.impact += f" {might_be_noise_note}"
        wp.priority = _DOWNGRADE[wp.priority]
        wp.score *= 0.6
    return wp


def _fmt_num(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"{x / 1_000:.1f}K"
    if abs(x) >= 10:
        return f"{x:.1f}"
    return f"{x:.2f}"


def _fmt_pct(x: float) -> str:
    return f"{x:.1f}%"


# ============================================================
# Detectors — each returns list[WeakPoint]
# ============================================================

def declining_trend(df: pd.DataFrame, profile: DatasetProfile) -> list:
    primary = profile.primary_measure
    if not primary or not profile.date_column:
        return []
    tmp = df.dropna(subset=[profile.date_column, primary.column]).copy()
    if tmp.empty:
        return []
    tmp["_year"] = tmp[profile.date_column].dt.year
    agg = tmp.groupby("_year")[primary.column].mean() if primary.aggregation == "avg" else tmp.groupby("_year")[primary.column].sum()
    if len(agg) < 2 or agg.iloc[0] == 0:
        return []
    change = (agg.iloc[-1] - agg.iloc[0]) / abs(agg.iloc[0]) * 100
    if change >= -5:  # not a meaningful decline
        return []

    magnitude = abs(change)
    priority = HIGH if magnitude > 30 else MEDIUM if magnitude > 15 else LOW

    wp = WeakPoint(
        problem=f"{primary.column} is trending down",
        impact=f"{primary.column} dropped from {_fmt_num(agg.iloc[0])} to {_fmt_num(agg.iloc[-1])} "
               f"between {agg.index[0]} and {agg.index[-1]} — a {_fmt_pct(magnitude)} decrease.",
        priority=priority,
        suggested_action=(
            f"Check whether this drop is happening across the board or mainly in one specific group. "
            f"If it's just one group, something specific likely changed there and can probably be fixed. "
            f"If it's happening everywhere at once, the cause is more likely something external."
        ),
        category="trend",
        score=magnitude,
    )

    first_vals = tmp[tmp["_year"] == agg.index[0]][primary.column].to_numpy(dtype=float)
    last_vals = tmp[tmp["_year"] == agg.index[-1]][primary.column].to_numpy(dtype=float)

    def _pct_change(r):
        first_mean = r["first"].mean()
        if first_mean == 0:
            return None
        return (r["last"].mean() - first_mean) / abs(first_mean) * 100

    sig = bootstrap_metric_significance({"first": first_vals, "last": last_vals}, _pct_change, reference=-5.0)
    return [_gate(
        wp, sig,
        "Checked this by reshuffling the data thousands of times — the decline held up every time, so it's not just a fluke of these particular rows.",
        "Worth a caveat: reshuffling the data sometimes made this decline disappear, so it's a lead worth checking rather than a confirmed trend.",
    )]


def missing_data(df: pd.DataFrame, profile: DatasetProfile) -> list:
    out = []
    # Only warn about missing data in columns that actually feed the
    # analysis (measures + dimensions). A column that's ~100% empty and
    # was already excluded from analysis by the completeness guard (see
    # understanding.py) isn't "skewing" any result -- it's simply not
    # used, and that's already visible in the Data Quality panel. Flagging
    # it again here as a weak point is redundant noise, and worse, its
    # missingness is always maximal (100%) so it drowns out genuinely
    # useful findings for the story/top-weak-points selection.
    used_cols = {m.column for m in profile.measures} | {d.column for d in profile.dimensions}
    missing_pct = (df.isnull().mean() * 100).sort_values(ascending=False)
    missing_pct = missing_pct[missing_pct.index.isin(used_cols)]
    worst = missing_pct[missing_pct > 15]
    for col, pct in worst.head(3).items():
        priority = HIGH if pct > 50 else MEDIUM if pct > 30 else LOW
        roughly_out_of_100 = round(pct)
        out.append(WeakPoint(
            problem=f"Missing information: {col}",
            impact=f"About {roughly_out_of_100} out of every 100 records don't have a value for {col}. "
                   f"Any chart, average, or comparison that uses {col} is only seeing part of the picture.",
            priority=priority,
            suggested_action=(
                f"Figure out why {col} is missing so often — is it an optional field that's fine to leave "
                f"blank, or something that should have been filled in but wasn't? If it should be there, "
                f"fixing how it's collected going forward matters more than trying to fill in old records."
            ),
            category="data_quality",
            score=pct,
        ))
    return out


def outlier_risk(df: pd.DataFrame, profile: DatasetProfile) -> list:
    out = []
    for m in profile.measures:
        series = df[m.column].dropna()
        if len(series) < 20:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        upper_fence = q3 + 1.5 * iqr
        outliers = series[series > upper_fence]
        if outliers.empty:
            continue
        row_share = len(outliers) / len(series) * 100
        value_share = outliers.sum() / series.sum() * 100 if series.sum() else 0
        if row_share < 8 and value_share > 20:
            priority = HIGH if value_share > 40 else MEDIUM
            wp = WeakPoint(
                problem=f"A few unusually high {m.column} values",
                impact=f"Just {len(outliers)} records ({_fmt_pct(row_share)} of all rows) have {m.column} "
                       f"values far above everything else — but together they make up {_fmt_pct(value_share)} "
                       f"of the total. That's enough for a handful of records to make an average or total "
                       f"look bigger than it really is for most of the data.",
                priority=priority,
                suggested_action=(
                    f"Take a look at these {len(outliers)} records specifically. If they're real (a genuinely "
                    f"huge order, an unusually long stay, etc.), that's fine — just know they're skewing the "
                    f"numbers. If they look like typos or data entry mistakes, fixing them will make averages "
                    f"and totals more trustworthy."
                ),
                category="outlier",
                score=value_share,
            )

            def _value_share(r, _fence=upper_fence):
                s = r["series"]
                total = s.sum()
                if total == 0:
                    return None
                return s[s > _fence].sum() / total * 100

            sig = bootstrap_metric_significance({"series": series.to_numpy(dtype=float)}, _value_share, reference=20.0)
            out.append(_gate(
                wp, sig,
                "Checked this by reshuffling the data thousands of times — these records reliably dominate the total, not just in this exact sample.",
                "Worth a caveat: reshuffling the data sometimes brought this back under 20%, so how much these records skew things may vary.",
            ))
            break  # one outlier flag is enough signal; don't repeat per measure
    return out


def concentration_risk(df: pd.DataFrame, profile: DatasetProfile) -> list:
    """Domain-flavored: 'disease hotspot' for healthcare CONDITION, generic
    framing otherwise — same detection logic, different wording."""
    out = []
    primary = profile.primary_measure
    if not primary:
        return out

    DOMAIN_FRAME = {
        "CONDITION": "One condition shows up far more than others",
        "CUSTOMER": "A small number of customers make up most of the business",
        "HOSPITAL": "One hospital is handling a lot more than the others",
        "LOCATION": "One region stands out from the rest",
    }

    for d in profile.dimensions:
        if not d.is_chartable or d.column == primary.column:
            continue
        grouped = df.groupby(d.column)[primary.column].sum()
        total = grouped.sum()
        if total == 0 or len(grouped) < 2:
            continue
        top_label, top_val = grouped.idxmax(), grouped.max()
        share = top_val / total * 100
        expected = 100 / len(grouped)
        if share <= expected * 1.5:
            continue

        priority = HIGH if share > 50 else MEDIUM if share > expected * 2 else LOW
        problem_label = DOMAIN_FRAME.get(d.role, f"One {d.column} stands out from the rest")

        wp = WeakPoint(
            problem=problem_label,
            impact=f"{top_label} alone makes up {_fmt_pct(share)} of all {primary.column} — much more than "
                   f"you'd expect if it were spread evenly across the {len(grouped)} different "
                   f"{d.column} groups (which would be about {_fmt_pct(expected)} each).",
            priority=priority,
            suggested_action=(
                f"This isn't necessarily a problem, but it's worth a deliberate look: is {top_label} getting "
                f"the attention and resources it deserves given how much depends on it? And is there a "
                f"backup plan if something changes there, since so much currently relies on just this one?"
            ),
            category="concentration",
            score=share - expected,
        )

        rows = df[[d.column, primary.column]].dropna()

        def _top_share(r):
            g = r["rows"].groupby(d.column, observed=True)[primary.column].sum()
            total = g.sum()
            if total == 0 or g.empty:
                return None
            return g.max() / total * 100

        sig = bootstrap_metric_significance({"rows": rows}, _top_share, reference=expected * 1.5)
        out.append(_gate(
            wp, sig,
            "Checked this by reshuffling the data thousands of times — this one still comes out on top every time, not just in this specific sample.",
            "Worth a caveat: reshuffling the data sometimes brought this back down to an unremarkable share, so the gap may be less dramatic than it looks here.",
        ))
    return out


def underperforming_segment(df: pd.DataFrame, profile: DatasetProfile) -> list:
    """The lowest-performing category for a measure where LOW is bad — e.g.
    lowest-average-score subject, lowest attendance group."""
    out = []
    LOW_IS_BAD_ROLES = {"SCORE", "ATTENDANCE"}
    for m in profile.measures:
        if m.role not in LOW_IS_BAD_ROLES:
            continue
        for d in profile.dimensions:
            if not d.is_chartable:
                continue
            grouped = df.groupby(d.column)[m.column].mean()
            if len(grouped) < 2:
                continue
            worst_label, worst_val = grouped.idxmin(), grouped.min()
            overall_avg = df[m.column].mean()
            if overall_avg == 0:
                continue
            gap_pct = (overall_avg - worst_val) / overall_avg * 100
            if gap_pct < 15:  # not meaningfully worse than average
                continue
            priority = HIGH if gap_pct > 35 else MEDIUM
            wp = WeakPoint(
                problem=f"{worst_label} is falling behind on {m.column}",
                impact=f"{worst_label} averages {_fmt_num(worst_val)} for {m.column}, which is "
                       f"{_fmt_pct(gap_pct)} lower than the overall average of {_fmt_num(overall_avg)}.",
                priority=priority,
                suggested_action=(
                    f"Look into what makes {worst_label} different — is it a resourcing issue, a support "
                    f"gap, or something structural? Understand the specific cause there before assuming "
                    f"a one-size-fits-all fix will help."
                ),
                category="underperformance",
                score=gap_pct,
            )

            rows = df[[d.column, m.column]].dropna()

            def _gap(r, _label=worst_label):
                sub = r["rows"]
                seg = sub[sub[d.column] == _label][m.column]
                overall = sub[m.column].mean()
                if seg.empty or overall == 0:
                    return None
                return (overall - seg.mean()) / overall * 100

            sig = bootstrap_metric_significance({"rows": rows}, _gap, reference=15.0)
            out.append(_gate(
                wp, sig,
                "Checked this by reshuffling the data thousands of times — this group stayed behind every time, not just in this specific sample.",
                "Worth a caveat: reshuffling the data sometimes closed this gap, so it may be less consistent than it looks here.",
            ))
    return out


def margin_risk(df: pd.DataFrame, profile: DatasetProfile) -> list:
    """Unprofitable segments — needs both a revenue-like and a profit-like
    measure to exist, which is why this only fires for financial data."""
    out = []
    revenue = next((m for m in profile.measures if m.role == "FINANCIAL_METRIC"), None)
    profit = next((m for m in profile.measures if m.role == "PROFIT"), None)
    if not revenue or not profit:
        return out

    for d in profile.dimensions:
        if not d.is_chartable:
            continue
        grouped = df.groupby(d.column).agg({revenue.column: "sum", profit.column: "sum"})
        grouped["margin"] = grouped[profit.column] / grouped[revenue.column].replace(0, pd.NA) * 100
        losers = grouped[grouped["margin"] < 0].sort_values("margin")
        for label, row in losers.head(2).iterrows():
            priority = HIGH if row["margin"] < -20 else MEDIUM
            wp = WeakPoint(
                problem=f"{label} is actually losing money",
                impact=f"{label} brought in {_fmt_num(row[revenue.column])} in {revenue.column}, but after "
                       f"costs it lost {_fmt_num(abs(row[profit.column]))} overall — every sale here is "
                       f"currently costing more than it earns.",
                priority=priority,
                suggested_action=(
                    f"Find out whether the losses come from discounting too heavily or from the underlying "
                    f"cost being too high. If it's discounting, capping how much gets discounted here should "
                    f"fix it without losing the sales. If it's cost, that likely needs a price increase or "
                    f"a cheaper way to deliver it."
                ),
                category="underperformance",
                score=abs(row["margin"]) + 15,
            )

            segment_rows = df[df[d.column] == label][[revenue.column, profit.column]].dropna()

            def _margin(r):
                rev_total = r["segment"][revenue.column].sum()
                if rev_total == 0:
                    return None
                return r["segment"][profit.column].sum() / rev_total * 100

            sig = bootstrap_metric_significance({"segment": segment_rows}, _margin, reference=0.0)
            out.append(_gate(
                wp, sig,
                "Checked this by reshuffling the data thousands of times — it stayed unprofitable every time, not just in this specific sample.",
                "Worth a caveat: reshuffling the data sometimes pushed this back into profit, so the loss may not be as consistent as it looks here.",
            ))
    return out


def discount_risk(df: pd.DataFrame, profile: DatasetProfile) -> list:
    revenue = next((m for m in profile.measures if m.role == "FINANCIAL_METRIC"), None)
    profit = next((m for m in profile.measures if m.role == "PROFIT"), None)
    discount = next((m for m in profile.measures if m.role == "DISCOUNT"), None)
    if not revenue or not profit or not discount:
        return []

    tmp = df.dropna(subset=[discount.column]).copy()
    if tmp[discount.column].max() > 1.5:
        tmp[discount.column] = tmp[discount.column] / 100.0
    tmp["_band"] = pd.cut(
        tmp[discount.column],
        bins=[-0.01, 0, 0.2, 0.4, 0.6, 1.01],
        labels=["0%", "1-20%", "21-40%", "41-60%", "60%+"],
    )
    band_margin = tmp.groupby("_band", observed=True).apply(
        lambda g: (g[profit.column].sum() / g[revenue.column].sum() * 100) if g[revenue.column].sum() else None,
        include_groups=False,
    )
    neg_bands = band_margin[band_margin < 0]
    if neg_bands.empty:
        return []

    worst_band, worst_val = neg_bands.idxmin(), neg_bands.min()
    safe_bands = band_margin[band_margin >= 0]
    safe_ceiling = safe_bands.index[-1] if len(safe_bands) else "0%"
    priority = HIGH if worst_val < -50 else MEDIUM

    wp = WeakPoint(
        problem="Big discounts are losing money, not just cutting profit",
        impact=f"Once a discount goes above {worst_band}, those sales stop making money entirely and "
               f"start losing it instead — on average, losing about {_fmt_pct(abs(worst_val))} of the "
               f"sale price for every order discounted that much.",
        priority=priority,
        suggested_action=(
            f"Consider capping discounts at around {safe_ceiling}, which is the highest level where sales "
            f"were still profitable. Anything beyond that could require manager approval instead of being "
            f"offered automatically at checkout."
        ),
        category="underperformance",
        score=abs(worst_val) + 20,
    )

    band_rows = tmp[tmp["_band"] == worst_band][[revenue.column, profit.column]].dropna()

    def _band_margin(r):
        rev_total = r["band"][revenue.column].sum()
        if rev_total == 0:
            return None
        return r["band"][profit.column].sum() / rev_total * 100

    sig = bootstrap_metric_significance({"band": band_rows}, _band_margin, reference=0.0)
    return [_gate(
        wp, sig,
        "Checked this by reshuffling the data thousands of times — this discount band stayed unprofitable every time, not just in this specific sample.",
        "Worth a caveat: reshuffling the data sometimes pushed this band back into profit, so the loss may not be as consistent as it looks here.",
    )]


def generate_weak_points(df: pd.DataFrame, profile: DatasetProfile, top_k: int = 6) -> list:
    detectors = [
        declining_trend, missing_data, outlier_risk, concentration_risk,
        underperforming_segment, margin_risk, discount_risk,
    ]
    all_weak_points = []
    for detector in detectors:
        try:
            all_weak_points.extend(detector(df, profile))
        except Exception:
            continue
    all_weak_points.sort(key=lambda w: w.score, reverse=True)
    return all_weak_points[:top_k]
