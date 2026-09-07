"""
Executes AnalysisSpec objects (from analysis_planner.py) against the actual
dataframe. This is separate from the older executor.py, which still serves
the older planner.py's dict-shaped specs live in main.py — keeping them
apart avoids breaking what's currently wired while this new pipeline
matures, consistent with how every previous phase in this rebuild has
avoided touching working code until the replacement is proven.

Handles all seven analysis types from the new planner: trend, histogram,
distribution_count, distribution_sum, correlation (scatter), correlation_matrix
(heatmap), and outlier (boxplot stats) — the three new ones this phase adds
execution logic for.
"""
import numpy as np
import pandas as pd

TOP_N = 15
HIST_BINS = 10
MAX_SCATTER_POINTS = 400


def _compute_trend(df, metric_col, date_col, aggregation):
    tmp = df.dropna(subset=[date_col, metric_col]).copy()
    if tmp.empty:
        return []
    tmp["_month"] = tmp[date_col].dt.to_period("M").astype(str)
    grouped = tmp.groupby("_month")[metric_col].mean() if aggregation == "avg" else tmp.groupby("_month")[metric_col].sum()
    grouped = grouped.sort_index()
    return [{"label": m, "value": float(v)} for m, v in grouped.items()]


def _compute_histogram(df, col, bins=HIST_BINS):
    series = df[col].dropna()
    if series.empty:
        return []
    n_bins = min(bins, max(series.nunique(), 1))
    try:
        counts, edges = np.histogram(series, bins=n_bins)
    except Exception:
        return []
    result = []
    for i in range(len(counts)):
        lo, hi = edges[i], edges[i + 1]
        label = f"{lo:.0f}-{hi:.0f}" if max(abs(lo), abs(hi)) >= 10 else f"{lo:.1f}-{hi:.1f}"
        result.append({"label": label, "value": int(counts[i])})
    return result


def _compute_distribution_count(df, col, top_n=TOP_N):
    vc = df[col].value_counts().head(top_n)
    return [{"label": str(k), "value": int(v)} for k, v in vc.items()]


def _compute_distribution_sum(df, col, metric_col, aggregation, top_n=TOP_N):
    grouped = df.groupby(col)[metric_col].mean() if aggregation == "avg" else df.groupby(col)[metric_col].sum()
    grouped = grouped.sort_values(ascending=False).head(top_n)
    return [{"label": str(k), "value": float(v)} for k, v in grouped.items()]


def _compute_scatter(df, col1, col2, color_col=None, max_points=MAX_SCATTER_POINTS):
    cols = [col1, col2] + ([color_col] if color_col else [])
    tmp = df[cols].dropna()
    if tmp.empty:
        return []
    if len(tmp) > max_points:
        tmp = tmp.sample(max_points, random_state=42)
    result = []
    for _, row in tmp.iterrows():
        point = {"x": float(row[col1]), "y": float(row[col2])}
        if color_col:
            point["group"] = str(row[color_col])
        result.append(point)
    return result


def _compute_correlation_matrix(df, cols):
    try:
        corr = df[cols].corr(numeric_only=True)
    except Exception:
        return []
    cells = []
    for c1 in cols:
        for c2 in cols:
            r = corr.loc[c1, c2]
            cells.append({"x": c1, "y": c2, "value": float(r) if pd.notna(r) else 0.0})
    return cells


def _compute_pivot(df, dim1, dim2, metric, aggregation, top_n=8):
    """Cross-tab: metric aggregated over every (dim1, dim2) combination.
    Capped to the top N most frequent values per dimension (by row count,
    not by the metric itself) -- a 20x20 grid stops being readable long
    before a 20-category single dimension chart would. Cells with no
    rows for that combination come back as None rather than 0, so the
    frontend can render them as "no data" instead of a misleading zero."""
    sub = df[[dim1, dim2, metric]].dropna(subset=[dim1, dim2])
    top1 = sub[dim1].value_counts().head(top_n).index.tolist()
    top2 = sub[dim2].value_counts().head(top_n).index.tolist()
    sub = sub[sub[dim1].isin(top1) & sub[dim2].isin(top2)]

    grouped = sub.groupby([dim1, dim2])[metric]
    agg = grouped.mean() if aggregation == "avg" else grouped.sum()

    cells = []
    for d1 in top1:
        for d2 in top2:
            try:
                val = agg.loc[(d1, d2)]
                val = float(val) if pd.notna(val) else None
            except KeyError:
                val = None
            cells.append({"x": str(d2), "y": str(d1), "value": val})
    return cells


def _compute_boxplot(df, col):
    series = df[col].dropna()
    if series.empty:
        return {}
    q1, median, q3 = series.quantile(0.25), series.quantile(0.5), series.quantile(0.75)
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    outliers = series[(series < lower_fence) | (series > upper_fence)]
    return {
        "min": float(series.min()),
        "q1": float(q1),
        "median": float(median),
        "q3": float(q3),
        "max": float(series.max()),
        "lower_fence": float(max(lower_fence, series.min())),
        "upper_fence": float(min(upper_fence, series.max())),
        "outlier_count": int(len(outliers)),
        "outlier_sample": [float(v) for v in outliers.head(30)],
    }


def _interpret_r(r):
    abs_r = abs(r)
    if abs_r < 0.15:
        return "No meaningful relationship"
    strength = "Strong" if abs_r >= 0.7 else "Moderate" if abs_r >= 0.4 else "Weak"
    direction = "positive" if r > 0 else "negative"
    return f"{strength} {direction} relationship"


def execute_spec(df: pd.DataFrame, spec) -> dict:
    """spec is an AnalysisSpec dataclass instance. Returns a plain dict with
    a 'data' key added — never raises, a bad spec just gets empty data."""
    base = {
        "id": spec.id, "title": spec.title, "type": spec.type,
        "chart_type": spec.chart_type, "section": spec.section,
        "importance": spec.importance, "aggregation": spec.aggregation,
        "metric_column": spec.metric_column,
        "column": spec.column,
        "column2": spec.column2,
        "date_column": spec.date_column,
        "reasoning": spec.reasoning,
    }
    try:
        t = spec.type
        if t == "trend":
            data = _compute_trend(df, spec.metric_column, spec.date_column, spec.aggregation or "sum")
        elif t == "histogram":
            data = _compute_histogram(df, spec.metric_column)
        elif t == "distribution_count":
            data = _compute_distribution_count(df, spec.column)
        elif t == "distribution_sum":
            data = _compute_distribution_sum(df, spec.column, spec.metric_column, spec.aggregation or "sum")
        elif t == "pivot":
            data = _compute_pivot(df, spec.column, spec.column2, spec.metric_column, spec.aggregation or "sum")
        elif t == "correlation":
            c1, c2 = spec.metric_columns[0], spec.metric_columns[1]
            data = _compute_scatter(df, c1, c2, color_col=spec.column)
            base["x_label"] = c1
            base["y_label"] = c2
            base["color_by"] = spec.column
            try:
                r = float(df[[c1, c2]].corr().iloc[0, 1])
            except Exception:
                r = None
            base["r"] = round(r, 3) if r is not None else None
            base["interpretation"] = _interpret_r(r) if r is not None else None
        elif t == "correlation_matrix":
            data = _compute_correlation_matrix(df, spec.metric_columns)
        elif t == "outlier":
            data = _compute_boxplot(df, spec.metric_column)
        else:
            data = []
    except Exception:
        data = [] if t != "outlier" else {}

    base["data"] = data
    return base


def execute_all(df: pd.DataFrame, specs: list) -> list:
    executed = [execute_spec(df, spec) for spec in specs]
    return [a for a in executed if a["data"]]
