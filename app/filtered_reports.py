"""
Filter-aware reports.

The dashboard filters and re-aggregates its charts in the browser from the row-level data it already
holds (filtering.py). A few reports can't be done that way: Period Comparison, "Why did it change?",
Robustness and Seasonality need real statistics and groupbys, and they used to always describe the
FULL dataset, so with a filter on, the trend chart said one thing and the reports beside it another.

This recomputes exactly those four on the rows the dashboard is showing, by calling the SAME functions the
upload pipeline calls (decompose_trend, compare_periods, detect_changepoint, analyze_drivers,
analyze_correlations, analyze_robustness) on a DataFrame rebuilt from the rows. There is deliberately no
second implementation: a JavaScript re-implementation would be a copy that can silently drift, which is
the failure this app's tests exist to prevent. tests/test_filtered_reports.py runs the full pipeline on a
pre-filtered file and requires this to agree.

Stateless like every other endpoint: the rows arrive in the request, nothing is kept.

Why rows come as columns ({"Region": [...], "Sales": [...]}) rather than a list of records: it repeats no
keys, so the request is much smaller, and a small hosted instance has little memory to parse it with.

What it does NOT cover: Segments, Anomalies, Cohorts, Correlation Center, Data Quality and the rest of Deep
Dive still describe the full dataset, and so does the changepoint marker on the trend chart. The interface
says which is which.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

import pandas as pd

from app.changepoint import detect_changepoint
from app.correlation_center import analyze_correlations
from app.drivers import analyze_drivers
from app.executor_v2 import _compute_trend
from app.period_comparison import compare_periods
from app.robustness import analyze_robustness
from app.seasonality import decompose_trend
from app.understanding import Dimension, Measure, _is_chartable

RECOMPUTE_MAX_ROWS = 50_000     # beyond this the request is refused (a hosted instance has little memory to parse it)
VALID_AGGREGATIONS = {"sum", "avg"}


def _unavailable(note: str) -> dict:
    return {"available": False, "note": note}


def recompute_reports(columns: dict, date_column: str, dimension_columns: list, measure_columns: list,
                      measure_aggregations: Optional[dict], metric_column: str, aggregation: str = "sum") -> dict:
    if not isinstance(columns, dict) or not columns:
        return _unavailable("No rows to analyse.")
    lengths = {len(v) for v in columns.values() if isinstance(v, list)}
    if len(lengths) != 1 or any(not isinstance(v, list) for v in columns.values()):
        return _unavailable("The columns have different lengths.")
    n = lengths.pop()
    if n == 0:
        return _unavailable("No rows match the current filters.")

    dims = [c for c in (dimension_columns or []) if c in columns]
    measures = [c for c in (measure_columns or []) if c in columns]
    if date_column not in columns or metric_column not in columns or metric_column not in measures:
        return _unavailable("The date column or the measure to analyse is missing from the rows.")
    aggregation = aggregation if aggregation in VALID_AGGREGATIONS else "sum"
    aggs = measure_aggregations if isinstance(measure_aggregations, dict) else {}

    df = pd.DataFrame({c: columns[c] for c in dict.fromkeys([date_column, *dims, *measures])})
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    for m in measures:
        df[m] = pd.to_numeric(df[m], errors="coerce")

    # A dimension is chartable by the pipeline's own rule (understanding._is_chartable), evaluated on the rows now
    # in view: filter on Region = West and Region has one value left, so it stops being a breakdown, exactly as
    # it would if the filtered file had been uploaded. (A column that was NOT chartable on the full data is not in
    # the rows at all, so it cannot become chartable here: the one case this cannot reproduce.)
    dimensions = []
    for d in dims:
        cardinality = int(df[d].nunique())
        if _is_chartable(cardinality, len(df)):
            dimensions.append(Dimension(column=d, role="CATEGORY", cardinality=cardinality, is_chartable=True))
    # The two things the pipeline reads from its profile (and nothing else): the measures with their
    # aggregation, in profile order, and the chartable dimensions.
    profile = SimpleNamespace(
        measures=[Measure(column=m, role="MEASURE", aggregation=aggs.get(m) if aggs.get(m) in VALID_AGGREGATIONS else "sum") for m in measures],
        dimensions=dimensions,
    )

    points = _compute_trend(df, metric_column, date_column, aggregation)
    if not points:
        return _unavailable("No rows with both a date and a value match the current filters.")

    seasonality = decompose_trend(points)
    seasonal_by_month = seasonality.get("seasonal_by_month") if seasonality.get("available") else None
    period_comparison = compare_periods(df, date_column, metric_column, aggregation)
    changepoint = detect_changepoint(points, seasonal_by_month=seasonal_by_month).get("break_point")
    drivers = analyze_drivers(df, profile, date_column, metric_column, aggregation,
                              changepoint=changepoint, seasonally_adjusted=bool(seasonal_by_month))
    robustness = analyze_robustness(df, profile, analyze_correlations(df, profile)["pairs"])

    return {
        "available": True,
        "rows_used": int(n),
        "seasonality": seasonality,
        "period_comparison": period_comparison,
        "drivers": drivers,
        "robustness": robustness,
    }
