"""
Segment-Level Forecasting.

forecasting.py's forecast_trend only ever runs on the overall
aggregate -- one line for the whole dataset. That hides exactly the
thing a decision-maker usually wants to know: not "is the business
trending down," but "which PART of the business is trending down, and
is anything actually recovering." Two segments heading in opposite
directions average out to a flat-looking overall line that tells you
nothing useful.

This runs the exact same forecast_trend (seasonality-aware, with
confidence bands) independently on each of the top few segments of the
dataset's most relevant dimension -- same "top N by volume" pattern
weak_points.py and cohort_analysis.py already use, and the same
dimension-priority-ranking (detect_priority_dimensions, headline roles
first) the domain analyzer plugins already compute for picking which
dimension matters most here. A segment whose own history is too thin
or too noisy to forecast confidently is simply left out, rather than
shown with a misleading projection -- same gate forecast_trend already
applies to the overall trend, just applied per segment here too.
"""
from typing import Optional
import pandas as pd

from app.executor_v2 import _compute_trend
from app.forecasting import forecast_trend, MIN_POINTS_FOR_FORECAST
from app.seasonality import decompose_trend

MAX_SEGMENTS = 4
MIN_SEGMENT_ROWS = 20   # enough rows in a segment before its own trend means anything


def forecast_top_segments(df: pd.DataFrame, profile, dimension, max_segments: int = MAX_SEGMENTS) -> dict:
    """dimension is a Dimension object from profile.dimensions (the
    caller picks which one -- typically the domain's top chartable
    priority dimension). Returns {"available", "note", "dimension",
    "metric_column", "segments": [...]}, where each segment has label,
    data (historical + forecast points, same shape forecast_trend
    produces), forecast_note, projected_change_pct, direction, and a
    one-line summary -- sorted by |projected_change_pct| descending, so
    the segment moving the most (in either direction) leads."""
    date_col = profile.date_column
    primary = profile.primary_measure
    if not date_col or not primary or dimension is None:
        return {"available": False, "note": None, "segments": []}

    sub = df[[dimension.column, date_col, primary.column]].dropna()
    if sub.empty:
        return {"available": False, "note": None, "segments": []}

    top_labels = (
        sub.groupby(dimension.column)[primary.column]
        .sum()
        .sort_values(ascending=False)
        .head(max_segments)
        .index.tolist()
    )

    segments = []
    for label in top_labels:
        seg_df = sub[sub[dimension.column] == label]
        if len(seg_df) < MIN_SEGMENT_ROWS:
            continue

        trend_data = _compute_trend(seg_df, primary.column, date_col, primary.aggregation)
        if len(trend_data) < MIN_POINTS_FOR_FORECAST:
            continue

        seasonality = decompose_trend(trend_data)
        seasonal_by_month = seasonality.get("seasonal_by_month") if seasonality.get("available") else None
        forecast = forecast_trend(trend_data, seasonal_by_month=seasonal_by_month)
        if not forecast["forecast_points"]:
            continue  # too noisy to forecast confidently on its own -- leave it out, don't guess

        last_actual = trend_data[-1]["value"]
        last_forecast = forecast["forecast_points"][-1]["value"]
        change_pct = round((last_forecast - last_actual) / abs(last_actual) * 100, 1) if last_actual else None
        direction = "up" if (change_pct or 0) > 0 else "down" if (change_pct or 0) < 0 else "flat"

        segments.append({
            "label": str(label),
            "data": trend_data + forecast["forecast_points"],
            "projected_change_pct": change_pct,
            "direction": direction,
            "summary": f"{label}: {forecast['note']}",
        })

    if not segments:
        return {
            "available": False,
            "note": f"None of the top {dimension.column} segments had enough history on their own to forecast confidently.",
            "segments": [],
        }

    segments.sort(key=lambda s: abs(s["projected_change_pct"] or 0), reverse=True)

    return {
        "available": True,
        "note": None,
        "dimension": dimension.column,
        "metric_column": primary.column,
        "segments": segments,
    }
