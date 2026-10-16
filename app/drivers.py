"""
"Why did it change?" -- driver analysis.

period_comparison.py says the total moved (and whether that is bigger than
chance); changepoint.py says WHEN a break happened. Neither says which part
of the business the movement landed in, which is the first thing anyone asks
next. This splits a change by each dimension and reports where it came from,
e.g. "70% of the drop is Region=West, mostly Furniture".

It is deliberately plain arithmetic, no new statistics:

* Every segment's contribution is (its value in the "after" window) minus
  (its value in the "before" window), and the contributions add up EXACTLY to
  the total change. Nothing is estimated, so there is nothing to tune.
* "Value" is defined so the totals reproduce what the rest of the app
  already shows. For a summed metric, a window's value is the mean monthly
  total (the same thing changepoint.py's before_mean/after_mean are, and equal
  to the plain monthly total for the one-month-vs-one-month comparison in
  period_comparison.py). For an averaged metric it is the mean of the monthly
  averages, split by each segment's weighted share of that month, which is
  the one decomposition of an average that stays additive.
* It describes where the change landed, not why it happened. A segment can
  carry the whole change and still be a symptom of something upstream (a price
  change, one big customer leaving). The panel says so.

Two comparisons are run when the data supports them: the latest month vs the
one before (the same pair period_comparison.py tests), and the stretch before
vs after a detected structural break (changepoint.py's windows).

Offsetting moves are handled explicitly. If the net change is small next to
the gross movement (West +100, East -95), "share of the change" would be a
meaningless 2000%, so shares are then reported against gross movement and the
headline says the segments are cancelling each other out.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

MIN_ROWS_PER_WINDOW = 5          # same floor as period_comparison.MIN_ROWS_PER_PERIOD
MAX_DIMENSIONS = 6               # dimensions reported, best first
MAX_SEGMENTS_SHOWN = 6           # rows in a waterfall before the rest fold into "Other"
FLAT_PCT = 1.0                   # |change| under 1% of the base is "flat": nothing to explain
OFFSETTING_RATIO = 0.2           # |net change| below 20% of gross movement => offsetting
CONCENTRATED_SHARE_PCT = 40.0    # a segment must carry at least this much to be named as "the driver"
DRILL_MIN_SHARE_PCT = 50.0       # second-level driver must carry at least this much of the first's change
BLANK = "(blank)"


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 1:
        return f"{v:,.0f}" if round(v, 1) == round(v) else f"{v:,.1f}"
    return f"{v:,.2f}"


def _segment_values(tmp: pd.DataFrame, dim: str, metric: str, aggregation: str,
                    months_before: list, months_after: list) -> pd.DataFrame:
    """Per-segment value in each window. Rows: segments. Columns: before, after.
    `tmp` must already have a `_month` column and no null date/metric."""
    work = tmp[tmp["_month"].isin(months_before + months_after)]
    grouped = work.groupby(["_month", dim])[metric].sum()
    if aggregation == "avg":
        month_n = work.groupby("_month")[metric].count()
        # segment's weighted share of that month's average: sum_im / n_m
        grouped = grouped / grouped.index.get_level_values("_month").map(month_n).to_numpy()
    table = grouped.unstack("_month").fillna(0.0)

    def window(months: list) -> pd.Series:
        cols = [m for m in months if m in table.columns]
        if not cols:
            return pd.Series(0.0, index=table.index)
        return table[cols].sum(axis=1) / len(months)

    out = pd.DataFrame({"before": window(months_before), "after": window(months_after)})
    out["change"] = out["after"] - out["before"]
    return out


def _breakdown(values: pd.DataFrame, total_change: float) -> dict:
    """Turn a per-segment table into the reported structure."""
    values = values[(values["before"] != 0) | (values["after"] != 0)]
    if values.empty:
        return {}
    gross = float(values["change"].abs().sum())
    offsetting = gross > 0 and abs(total_change) < OFFSETTING_RATIO * gross

    order = values["change"].abs().sort_values(ascending=False).index
    rows = []
    for seg in order:
        r = values.loc[seg]
        rows.append({
            "segment": str(seg),
            "before": round(float(r["before"]), 2),
            "after": round(float(r["after"]), 2),
            "change": round(float(r["change"]), 2),
            "share_of_change_pct": None if offsetting or total_change == 0 else round(float(r["change"]) / total_change * 100, 1),
            "share_of_movement_pct": round(float(abs(r["change"])) / gross * 100, 1) if gross else 0.0,
        })

    shown, rest = rows[:MAX_SEGMENTS_SHOWN], rows[MAX_SEGMENTS_SHOWN:]
    other = None
    if rest:
        ch = sum(r["change"] for r in rest)
        other = {
            "count": len(rest),
            "before": round(sum(r["before"] for r in rest), 2),
            "after": round(sum(r["after"] for r in rest), 2),
            "change": round(ch, 2),
            "share_of_change_pct": None if offsetting or total_change == 0 else round(ch / total_change * 100, 1),
        }

    k = len(rows)
    top_move = rows[0]["share_of_movement_pct"] if rows else 0.0
    # How much more concentrated than an even spread: 0 for an even split, up to ~100.
    lift = round(top_move - 100.0 / k, 1) if k else 0.0
    return {
        "segments": shown,
        "other": other,
        "segment_count": k,
        "offsetting": offsetting,
        "concentration": lift,
    }


def _dimension_report(tmp, dim, metric, aggregation, mb, ma, total_change):
    values = _segment_values(tmp, dim, metric, aggregation, mb, ma)
    bd = _breakdown(values, total_change)
    if not bd or not bd["segments"]:
        return None
    return {"dimension": dim, **bd}


def _direction_word(change: float, noun: bool = False) -> str:
    if noun:
        return "rise" if change >= 0 else "drop"
    return "rose" if change >= 0 else "fell"


def _headline(metric: str, label_b: str, label_a: str, change: float, change_pct: Optional[float],
              best: Optional[dict], drill: Optional[dict], ranges: bool = False) -> str:
    if change_pct is None:
        pct = _fmt(abs(change))
    else:
        pct = f"{abs(change_pct):.1f}%" if abs(change_pct) < 10 else f"{abs(change_pct):.0f}%"
    span = f"between {label_b} and {label_a} (monthly average)" if ranges else f"from {label_b} to {label_a}"
    if change_pct is not None and abs(change_pct) < FLAT_PCT:
        return f"{metric} was essentially flat ({'+' if change >= 0 else '-'}{pct} {span}), so there is no real change to explain."
    lead = f"{metric} {_direction_word(change)} {pct} {span}"
    if not best:
        return f"{lead}."
    top = best["segments"][0]
    dim = best["dimension"]
    if best["offsetting"]:
        movers = sorted(best["segments"], key=lambda s: s["change"])
        down, up = movers[0], movers[-1]
        if down["change"] < 0 < up["change"]:
            return (f"{lead}, but that hides opposing moves by {dim}: {up['segment']} {_fmt(up['change'])} up, "
                    f"{down['segment']} {_fmt(abs(down['change']))} down, largely cancelling out.")
        return f"{lead}; the net is small next to the movement underneath it, which is spread across {dim}."
    share = top["share_of_change_pct"]
    if share is not None and share > 100 and top["change"] * change > 0:
        # One segment moved more than the whole net change; the others pulled the other way.
        text = (f"{lead}: {dim}={top['segment']} alone accounts for more than all of the "
                f"{_direction_word(change, noun=True)} ({share:.0f}%), partly offset by the other {dim} values")
        if drill:
            text += f". Within it, mostly {drill['dimension']}={drill['segment']} ({drill['share_pct']:.0f}% of {top['segment']}'s change)"
        return text + "."
    if share is not None and share >= CONCENTRATED_SHARE_PCT and top["change"] * change > 0:
        text = f"{lead}: {share:.0f}% of the {_direction_word(change, noun=True)} is {dim}={top['segment']}"
        if drill:
            text += f", mostly {drill['dimension']}={drill['segment']} ({drill['share_pct']:.0f}% of {top['segment']}'s change)"
        return text + "."
    return (f"{lead}. No single {dim} value explains it: the largest contributor, {top['segment']}, "
            f"carries {abs(share) if share is not None else 0:.0f}% and the rest is spread out.")


def _find_drill(tmp, dims, best, metric, aggregation, mb, ma) -> Optional[dict]:
    """Within the biggest segment of the best dimension, which OTHER dimension
    concentrates its change? One level only: deeper cuts get too thin to trust."""
    if best.get("offsetting"):
        return None
    top = best["segments"][0]
    seg_change = top["change"]
    if seg_change == 0:
        return None
    sub = tmp[tmp[best["dimension"]].astype(str) == top["segment"]]
    if sub.empty:
        return None
    candidates = []
    for d in dims:
        if d == best["dimension"]:
            continue
        values = _segment_values(sub, d, metric, aggregation, mb, ma)
        values = values[(values["before"] != 0) | (values["after"] != 0)]
        if len(values) < 2:
            continue
        # If the segment's own sub-moves mostly cancel, "X is 975% of its
        # change" is arithmetic noise, not a finding -- skip that dimension.
        gross = float(values["change"].abs().sum())
        if gross == 0 or abs(seg_change) < OFFSETTING_RATIO * gross:
            continue
        seg = values["change"].abs().idxmax()
        share = float(values.loc[seg, "change"]) / seg_change * 100
        if values.loc[seg, "change"] * seg_change > 0 and share <= 100.0:
            candidates.append((share, d, str(seg)))
    if not candidates:
        return None
    share, d, seg = max(candidates)
    if share < DRILL_MIN_SHARE_PCT:
        return None
    return {"dimension": d, "segment": seg, "share_pct": round(share, 1)}


def _compare(tmp, dims, metric, aggregation, mb, ma, cid, title) -> Optional[dict]:
    in_b = tmp[tmp["_month"].isin(mb)]
    in_a = tmp[tmp["_month"].isin(ma)]
    if len(in_b) < MIN_ROWS_PER_WINDOW or len(in_a) < MIN_ROWS_PER_WINDOW:
        return None

    # Total change straight from the rows, independent of any dimension.
    def window_value(frame, months):
        s = frame.groupby("_month")[metric].mean() if aggregation == "avg" else frame.groupby("_month")[metric].sum()
        return float(s.reindex(months).fillna(0.0).sum() / len(months))

    v_b, v_a = window_value(in_b, mb), window_value(in_a, ma)
    change = v_a - v_b
    change_pct = round(change / abs(v_b) * 100, 1) if v_b else None

    reports = []
    for d in dims:
        rep = _dimension_report(tmp, d, metric, aggregation, mb, ma, change)
        if rep:
            rep["drill"] = None
            reports.append(rep)
    if not reports:
        return None
    reports.sort(key=lambda r: (-r["concentration"], r["dimension"]))
    reports = reports[:MAX_DIMENSIONS]

    best = reports[0]
    drill = _find_drill(tmp, [r["dimension"] for r in reports], best, metric, aggregation, mb, ma)
    best["drill"] = drill
    label_b = mb[0] if len(mb) == 1 else f"{mb[0]} \u2013 {mb[-1]}"
    label_a = ma[0] if len(ma) == 1 else f"{ma[0]} \u2013 {ma[-1]}"
    return {
        "id": cid,
        "title": title,
        "before": {"label": label_b, "months": len(mb), "rows": int(len(in_b)), "value": round(v_b, 2)},
        "after": {"label": label_a, "months": len(ma), "rows": int(len(in_a)), "value": round(v_a, 2)},
        "change": round(change, 2),
        "change_pct": change_pct,
        "headline": _headline(metric, label_b, label_a, change, change_pct, best, drill, ranges=len(mb) > 1 or len(ma) > 1),
        "best_dimension": best["dimension"],
        "dimensions": reports,
    }


def _months_between(months: list, start: str, end: str) -> list:
    return [m for m in months if start <= m <= end]


def analyze_drivers(df: pd.DataFrame, profile, date_column: Optional[str], metric_column: Optional[str],
                    aggregation: str = "sum", changepoint: Optional[dict] = None,
                    seasonally_adjusted: bool = False) -> dict:
    """df is the working dataframe (date column already parsed). `changepoint`
    is the break_point dict from detect_changepoint (or None)."""
    unavailable = {"available": False, "note": None, "comparisons": []}
    if not date_column or not metric_column or date_column not in df.columns or metric_column not in df.columns:
        return {**unavailable, "note": "Needs a date column and a measure to explain a change over time."}

    dims = [d.column for d in profile.dimensions
            if d.is_chartable and d.column in df.columns and d.column not in (date_column, metric_column)]
    if not dims:
        return {**unavailable, "note": "Needs at least one category column (like Region or Category) to split a change by."}

    tmp = df.dropna(subset=[date_column, metric_column]).copy()
    if tmp.empty:
        return {**unavailable, "note": "No rows with both a date and this measure."}
    tmp[metric_column] = pd.to_numeric(tmp[metric_column], errors="coerce")
    tmp = tmp.dropna(subset=[metric_column])
    tmp["_month"] = tmp[date_column].dt.to_period("M").astype(str)
    for d in dims:
        tmp[d] = tmp[d].astype("object").where(tmp[d].notna(), BLANK).astype(str)

    months = sorted(tmp["_month"].unique())
    if len(months) < 2:
        return {**unavailable, "note": "Needs at least two calendar months of data."}

    comparisons = []
    c = _compare(tmp, dims, metric_column, aggregation, [months[-2]], [months[-1]],
                 "latest_month", "Latest month vs. the one before")
    if c:
        comparisons.append(c)

    if changepoint:
        mb = _months_between(months, changepoint["before_label"], changepoint["before_end_label"])
        ma = _months_between(months, changepoint["label"], changepoint["after_label"])
        if mb and ma:
            c = _compare(tmp, dims, metric_column, aggregation, mb, ma, "break", "Before vs. after the detected break")
            if c:
                comparisons.append(c)

    if not comparisons:
        return {**unavailable, "note": f"Needs at least {MIN_ROWS_PER_WINDOW} records in each period to split a change fairly."}

    return {
        "available": True,
        "note": None,
        "metric": metric_column,
        "aggregation": aggregation,
        "seasonally_adjusted_break": bool(seasonally_adjusted and changepoint),
        "comparisons": comparisons,
    }
