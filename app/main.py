import io
from typing import Optional
import pandas as pd
import os
from pathlib import Path
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.column_detector import detect_columns
from app.kpi import prepare, compute_kpis, timeseries_monthly, breakdown_by, all_breakdowns, combine_dataframes
from app.relational_join import detect_join_key, join_dataframes
from app.insights import generate_insights
from app.semantic_roles import classify_columns
from app.domains import detect_domain
from app.planner import plan_analyses
from app.executor import execute_all
from app.understanding import understand_dataset
from app.executor_v2 import execute_all as execute_all_v2
from app.analyzers.registry import get_analyzer
from app.data_quality import analyze_data_quality
from app.correlation_center import analyze_correlations, analyze_multicollinearity
from app.simpsons_paradox import check_simpsons_paradox
from app.partial_correlation import analyze_partial_correlations
from app.benford import check_benfords_law
from app.comparison import compare_results
from app.data_cleaning import build_cleaned_csv
from app.cohort_analysis import analyze_cohorts, assess_retention_risk
from app.confidence_intervals import compute_kpi_confidence_intervals
from app.text_analysis import analyze_text_fields
from app.clustering import analyze_segments
from app.anomaly_detection import detect_anomalies
from app.seasonality import decompose_trend
from app.period_comparison import compare_periods
from app.forecasting import forecast_trend
from app.changepoint import detect_changepoint
from app.drivers import analyze_drivers
from app.robustness import analyze_robustness
from app.code_export import generate_script
from app.hypothesis import run_hypothesis_test
from app.share_guard import scan_share_payload, blocking_findings, refusal_message
from app.filtering import MAX_ROWS_FOR_FILTERING
from app.segment_forecast import forecast_top_segments
from app.filtering import build_filterable_data
from app.pdf_report import build_pdf_report
from app.html_report import build_html_report
from app.share_cache import create_share, get_share, check_size as check_share_size
from app.sensitive_data import detect_sensitive_data

import math
import numpy as np
from starlette.responses import JSONResponse as _StarletteJSONResponse


def _sanitize_json(obj):
    """Recursively replace NaN/Infinity floats with None.

    Real-world CSVs are often messy -- columns that are mostly or entirely
    empty are common (stray unnamed columns, partial summary stats pasted
    into the same sheet, etc.), and pandas computations over them (mean,
    std, correlation...) naturally produce NaN. Python's json.dumps as used
    by Starlette's JSONResponse sets allow_nan=False, so a single stray NaN
    anywhere in the response crashes the ENTIRE request with a raw 500 and
    an unparseable body -- the frontend then fails trying to JSON.parse an
    "Internal Server Error" plain-text response. Rather than chase down
    every individual computation that could produce a NaN, this sanitizes
    the whole response once at the API boundary.

    Also converts numpy scalar types (float32, int8, int16, ...) to
    native Python types here -- numpy.float64 happens to subclass
    Python's built-in float (so it always serialized fine by accident),
    but narrower numpy dtypes don't subclass anything JSON-aware. This
    went unnoticed until the chunked CSV reader started actually
    producing float32/int8 columns (for memory savings on large files)
    and every endpoint returning one immediately 500'd -- np.generic
    covers every numpy scalar type, current and future, rather than
    listing each dtype individually."""
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj


class SafeJSONResponse(_StarletteJSONResponse):
    def render(self, content) -> bytes:
        return super().render(_sanitize_json(content))


app = FastAPI(title="DataLens", default_response_class=SafeJSONResponse)

# Where the built frontend is served from. Defaults to app/static (what the
# deploy steps copy frontend/dist into). DATALENS_STATIC_DIR lets the end-to-end
# tests serve a fresh frontend/dist directly, without overwriting app/static.
STATIC_DIR = Path(os.environ.get("DATALENS_STATIC_DIR") or Path(__file__).parent / "static")

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet"}
DEFAULT_MAX_FILE_SIZE_MB = 250


def _max_file_size_mb(raw: Optional[str] = None) -> float:
    """The upload cap, in MB. Overridable with DATALENS_MAX_FILE_MB because the right number
    depends on the machine: running locally 250 MB is fine, but a hosted instance with 512 MB
    of RAM is killed by a ~30 MB CSV (measured: 500,000 rows peaked at ~620 MB). A bad value
    falls back to the default instead of stopping the app from starting."""
    raw = os.environ.get("DATALENS_MAX_FILE_MB") if raw is None else raw
    try:
        value = float(raw) if raw not in (None, "") else DEFAULT_MAX_FILE_SIZE_MB
    except ValueError:
        return float(DEFAULT_MAX_FILE_SIZE_MB)
    return value if value > 0 else float(DEFAULT_MAX_FILE_SIZE_MB)


MAX_FILE_SIZE_MB = _max_file_size_mb()
CSV_CHUNK_ROWS = 100_000
UPLOAD_READ_CHUNK = 1024 * 1024


def _serialize_correlation_pair(pair) -> Optional[dict]:
    """Shared serializer for CorrelationPair so the significance fields
    (n, p_value, significant, strength, caveat) stay consistent between the
    full pairs list and the strongest-positive/negative callouts."""
    if pair is None:
        return None
    return {
        "col1": pair.col1,
        "col2": pair.col2,
        "r": round(pair.r, 3),
        "n": pair.n,
        "p_value": round(pair.p_value, 4) if pair.p_value is not None else None,
        "significant": pair.significant,
        "strength": pair.strength,
        "caveat": pair.caveat,
    }


def _serialize_segments(segments_report: dict) -> dict:
    """Serializer for analyze_segments()'s dict, mirroring how
    _serialize_correlation_pair keeps the Segment dataclass's shape
    consistent wherever it's used in the response."""
    if not segments_report.get("available"):
        return {"available": False, "note": segments_report.get("note")}
    return {
        "available": True,
        "k": segments_report["k"],
        "measures_used": segments_report["measures_used"],
        "row_count_used": segments_report["row_count_used"],
        "note": segments_report["note"],
        "clusters": [
            {
                "id": c.id,
                "label": c.label,
                "description": c.description,
                "size": c.size,
                "pct": c.pct,
                "averages": c.averages,
            }
            for c in segments_report["clusters"]
        ],
    }


def _serialize_seasonality(seasonality_report: dict) -> dict:
    """Serializer for decompose_trend()'s dict -- the panel only needs the
    summary numbers, not the per-point series (that lives on the
    seasonal_decomposition chart entry in all_analyses instead, so it's
    not duplicated in the response)."""
    if not seasonality_report.get("available"):
        return {"available": False, "note": seasonality_report.get("note")}
    return {
        "available": True,
        "note": None,
        "years_covered": seasonality_report["years_covered"],
        "p_value": seasonality_report["p_value"],
        "seasonal_strength": seasonality_report["seasonal_strength"],
        "trend_strength": seasonality_report["trend_strength"],
        "peak_month": seasonality_report["peak_month"],
        "trough_month": seasonality_report["trough_month"],
        "summary": seasonality_report["summary"],
    }


def _serialize_anomalies(anomaly_report: dict) -> dict:
    """Serializer for detect_anomalies()'s dict -- drops scatter_points
    (that lives on the anomalies_scatter chart entry in all_analyses
    instead) so the summary panel's payload doesn't duplicate it."""
    if not anomaly_report.get("available"):
        return {"available": False, "note": anomaly_report.get("note")}
    return {
        "available": True,
        "note": None,
        "measures_used": anomaly_report["measures_used"],
        "row_count_used": anomaly_report["row_count_used"],
        "anomaly_count": anomaly_report["anomaly_count"],
        "anomaly_pct": anomaly_report["anomaly_pct"],
        "anomalies": anomaly_report["anomalies"][:10],  # panel only needs a handful to list
    }


def _serialize_cohorts(cohort_report: dict, risk_report: dict) -> dict:
    """Drops heatmap_points (lives on the cohort_retention chart entry in
    all_analyses instead) and the full per-cohort retention arrays (the
    chart already has those) -- the panel only needs the headline numbers
    and cohort sizes. Also folds in assess_retention_risk's per-entity
    "overdue to return" flag as a nested "at_risk" section -- same
    Retention panel, same underlying entity/date columns, just a
    different (and independently available) question than the cohort
    curve answers, so it's kept availability-independent: a dataset can
    have one without the other (e.g. one cohort month is too small to
    chart, but there's still enough overall repeat activity to learn a
    typical return window)."""
    if not cohort_report.get("available"):
        result = {"available": False, "note": cohort_report.get("note")}
    else:
        result = {
            "available": True,
            "note": None,
            "entity_noun": cohort_report["entity_noun"],
            "cohort_count": cohort_report["cohort_count"],
            "avg_month1_retention_pct": cohort_report["avg_month1_retention_pct"],
            "summary": cohort_report["summary"],
            "cohort_sizes": [{"cohort": c["cohort"], "size": c["size"]} for c in cohort_report["cohorts"]],
        }
    result["at_risk"] = risk_report if risk_report.get("available") else {"available": False, "note": risk_report.get("note")}
    return result


def _run_v2_pipeline(df: pd.DataFrame, role_overrides: dict = None) -> dict:
    """
    The full new pipeline: Dataset Understanding -> pick the right domain
    Analyzer plugin -> that plugin's dashboard/findings/weak-points. This
    function no longer knows what "healthcare" or "sales" means at all —
    get_analyzer() picks the right plugin, and every domain-specific
    decision (which dimensions matter most, what KPIs this domain cares
    about) lives inside that plugin, not here.
    """
    profile = understand_dataset(df, role_overrides=role_overrides)

    df_exec = df.copy()
    for col, role in profile.semantic_roles.items():
        if role == "DATE":
            df_exec[col] = pd.to_datetime(df_exec[col], errors="coerce")

    analyzer = get_analyzer(profile.domain, df_exec, profile)

    specs = analyzer.choose_visualizations()
    top3 = analyzer.choose_dashboard(n=3)
    top3_ids = {s.id for s in top3}

    all_executed = execute_all_v2(df_exec, specs)

    # Segmentation: auto-discovered natural groups via k-means, additive to
    # the planner-driven specs above rather than routed through it -- the
    # scatter reuses the exact {x, y, group} shape _compute_scatter already
    # produces (see executor_v2.py), so AnalysisExplorerV2's ScatterView
    # renders it with zero frontend changes, colored by segment the same
    # way it already colors by any other dimension.
    segments_report = analyze_segments(df_exec, profile)
    if segments_report.get("available"):
        all_executed.append({
            "id": "segments_scatter",
            "title": f"Natural Groups: {segments_report['x_measure']} vs {segments_report['y_measure']}",
            "type": "segment",
            "chart_type": "scatter",
            "section": "Segments",
            "importance": 0,
            "aggregation": None,
            "metric_column": None,
            "column": None,
            "column2": None,
            "date_column": None,
            "reasoning": f"Found {segments_report['k']} natural groups across "
                         f"{', '.join(segments_report['measures_used'])} — plotted on the two measures "
                         f"that separate the groups most clearly.",
            "x_label": segments_report["x_measure"],
            "y_label": segments_report["y_measure"],
            "color_by": "Segment",
            "data": segments_report["scatter_points"],
        })

    priority_dims = [d for d in analyzer.detect_priority_dimensions() if d.is_chartable]
    segment_forecast_report = forecast_top_segments(df_exec, profile, priority_dims[0] if priority_dims else None)
    if segment_forecast_report.get("available"):
        all_executed.append({
            "id": "segment_forecast",
            "title": f"Segment Forecasts: {segment_forecast_report['metric_column']} by {segment_forecast_report['dimension']}",
            "type": "segment_forecast",
            "chart_type": "segment_forecast",
            "section": "Trend",
            "importance": 0,
            "aggregation": None,
            "metric_column": segment_forecast_report["metric_column"],
            "column": segment_forecast_report["dimension"],
            "column2": None,
            "date_column": None,
            "reasoning": f"The overall {segment_forecast_report['metric_column']} trend is one line, but it can hide "
                         f"individual {segment_forecast_report['dimension']} segments moving in opposite directions — "
                         f"this forecasts the top segments independently so a recovering one isn't hidden behind a "
                         f"declining one, or vice versa.",
            "x_label": "Period",
            "y_label": segment_forecast_report["metric_column"],
            "color_by": segment_forecast_report["dimension"],
            "segments": segment_forecast_report["segments"],
            "data": [],
        })

    anomaly_report = detect_anomalies(df_exec, profile)
    cohort_report = analyze_cohorts(df_exec, profile)
    retention_risk_report = assess_retention_risk(df_exec, profile)
    confidence_interval_report = compute_kpi_confidence_intervals(df_exec, profile)
    text_analysis_report = analyze_text_fields(df_exec, profile)
    if anomaly_report.get("available") and anomaly_report["anomaly_count"] > 0:
        all_executed.append({
            "id": "anomalies_scatter",
            "title": f"Unusual Rows: {anomaly_report['x_measure']} vs {anomaly_report['y_measure']}",
            "type": "anomaly",
            "chart_type": "scatter",
            "section": "Anomalies",
            "importance": 0,
            "aggregation": None,
            "metric_column": None,
            "column": None,
            "column2": None,
            "date_column": None,
            "reasoning": f"Found {anomaly_report['anomaly_count']} rows ({anomaly_report['anomaly_pct']}%) that look "
                         f"unusual across {', '.join(anomaly_report['measures_used'])} taken together — even where "
                         f"no single measure looks extreme on its own.",
            "x_label": anomaly_report["x_measure"],
            "y_label": anomaly_report["y_measure"],
            "color_by": "Status",
            "data": anomaly_report["scatter_points"],
        })

    if cohort_report.get("available"):
        all_executed.append({
            "id": "cohort_retention",
            "title": f"{cohort_report['entity_noun']} Retention by Cohort",
            "type": "pivot",
            "chart_type": "heatmap",
            "section": "Retention",
            "importance": 0,
            "aggregation": None,
            "metric_column": None,
            "column": f"{cohort_report['entity_noun']} Cohort",
            "column2": "Months Since First Activity",
            "date_column": None,
            "reasoning": cohort_report["summary"],
            "x_label": None,
            "y_label": None,
            "color_by": None,
            "value_suffix": "%",
            "data": cohort_report["heatmap_points"],
        })

    # Additive: attach a short linear-trend forecast to any trend/line
    # analysis that has enough history and a clear enough pattern to
    # project. Mutating in place so both top_executed and all_analyses
    # (built from the same dicts below) automatically pick it up.
    #
    # Seasonality decomposition runs on the same trend data, but must run
    # BEFORE forecast_trend appends its projected points below -- it needs
    # the real historical series only, not a synthetic tail.
    seasonality_report = {"available": False, "note": None}
    period_comparison_report = {"available": False, "note": None}
    drivers_report = {"available": False, "note": None, "comparisons": []}
    for a in all_executed:
        if a.get("type") == "trend" and a.get("data"):
            seasonality_report = decompose_trend(a["data"])
            if seasonality_report.get("available"):
                all_executed.append({
                    "id": "seasonal_decomposition",
                    "title": f"Seasonal Pattern: {a.get('metric_column') or a['title']}",
                    "type": "seasonality",
                    "chart_type": "seasonal_decomposition",
                    "section": "Seasonality",
                    "importance": 0,
                    "aggregation": None,
                    "metric_column": a.get("metric_column"),
                    "column": None,
                    "column2": None,
                    "date_column": None,
                    "reasoning": seasonality_report["summary"],
                    "x_label": "Period",
                    "y_label": a.get("metric_column") or "Value",
                    "color_by": None,
                    "data": seasonality_report["points"],
                })

            # Period comparison needs row-level values, so it re-groups
            # df_exec itself (see period_comparison.py) rather than reusing
            # the already-aggregated monthly trend points.
            if a.get("date_column") and a.get("metric_column"):
                period_comparison_report = compare_periods(
                    df_exec, a["date_column"], a["metric_column"], a.get("aggregation") or "sum",
                )

            seasonal_by_month = (
                seasonality_report.get("seasonal_by_month")
                if seasonality_report.get("available") else None
            )

            # Changepoint detection reads the same real historical points,
            # also before forecast_trend appends its projected tail below.
            # Attached directly onto the trend analysis itself (like
            # forecast_note is) rather than as a separate chart entry, so
            # it annotates the SAME trend chart wherever it's shown
            # (Key Analyses, the Explorer) instead of living in a
            # duplicate card the person has to go find.
            changepoint_report = detect_changepoint(a["data"], seasonal_by_month=seasonal_by_month)
            a["changepoint"] = changepoint_report.get("break_point")

            # "Why did it change?": split the latest-month move and (when one
            # was found) the break above by each dimension. Runs here, on the
            # real historical points, for the same reason the two reports
            # above do -- and its break windows ARE changepoint.py's windows.
            if a.get("date_column") and a.get("metric_column"):
                drivers_report = analyze_drivers(
                    df_exec, profile, a["date_column"], a["metric_column"], a.get("aggregation") or "sum",
                    changepoint=a["changepoint"], seasonally_adjusted=bool(seasonal_by_month),
                )
                brk = next((c for c in drivers_report.get("comparisons", []) if c["id"] == "break"), None)
                if a["changepoint"] and brk:
                    a["changepoint"]["driver_headline"] = brk["headline"]

            result = forecast_trend(a["data"], seasonal_by_month=seasonal_by_month)
            if result["forecast_points"]:
                for point in a["data"]:
                    point["is_forecast"] = False
                a["data"] = a["data"] + result["forecast_points"]
            a["forecast_note"] = result["note"]
            break  # plan_analyses only ever produces one trend spec

    top_order = {s.id: i for i, s in enumerate(top3)}
    top_executed = sorted(
        (a for a in all_executed if a["id"] in top3_ids),
        key=lambda a: top_order.get(a["id"], 999),
    )

    insights = analyzer.generate_findings()
    weak_points = analyzer.detect_weak_points()
    story = analyzer.generate_story()
    quality_report = analyze_data_quality(df_exec, profile)
    correlation_report = analyze_correlations(df_exec, profile)
    multicollinearity_report = analyze_multicollinearity(df_exec, profile)
    simpsons_paradox_report = check_simpsons_paradox(df_exec, profile, correlation_report["pairs"])
    partial_correlation_report = analyze_partial_correlations(df_exec, profile, correlation_report["pairs"])
    robustness_report = analyze_robustness(df_exec, profile, correlation_report["pairs"])
    benford_report = check_benfords_law(df_exec, profile)
    filterable_data = build_filterable_data(df_exec, profile)

    return {
        "profile": {
            "domain": profile.domain,
            "domain_confidence": profile.domain_confidence,
            "primary_entity": profile.primary_entity,
            "row_count": profile.row_count,
            "column_count": profile.column_count,
            "data_completeness_pct": profile.data_completeness_pct,
            "key_kpis": analyzer.key_kpis,
            # Names only, used by the "show the code" export to know which
            # columns exist and which were parsed as dates -- no values.
            "columns": [str(c) for c in df.columns],
            "date_columns": [str(c) for c, role in profile.semantic_roles.items() if role == "DATE"],
        },
        "filterable_data": filterable_data,
        "top_analyses": top_executed,
        "all_analyses": all_executed,
        "findings": [
            {"text": i.text, "category": i.category, "score": i.score}
            for i in insights
        ],
        "weak_points": [
            {
                "problem": w.problem, "impact": w.impact, "priority": w.priority,
                "suggested_action": w.suggested_action, "category": w.category,
                "significant": w.significant, "ci_low": w.ci_low, "ci_high": w.ci_high,
            }
            for w in weak_points
        ],
        "story": [
            {"label": b.label, "text": b.text, "tone": b.tone}
            for b in story
        ],
        "data_quality": {
            "missing_by_column": quality_report.missing_by_column,
            "duplicate_row_count": quality_report.duplicate_row_count,
            "duplicate_row_pct": quality_report.duplicate_row_pct,
            "constant_columns": quality_report.constant_columns,
            "high_cardinality_columns": quality_report.high_cardinality_columns,
            "outlier_summary": quality_report.outlier_summary,
            "dtype_breakdown": quality_report.dtype_breakdown,
            "overall_quality_score": quality_report.overall_quality_score,
            "usable_quality_score": quality_report.usable_quality_score,
            "usable_column_count": quality_report.usable_column_count,
            "total_column_count": quality_report.total_column_count,
        },
        "correlation_center": {
            "pairs": [_serialize_correlation_pair(p) for p in correlation_report["pairs"]],
            "strongest_positive": _serialize_correlation_pair(correlation_report["strongest_positive"]),
            "strongest_negative": _serialize_correlation_pair(correlation_report["strongest_negative"]),
            "multicollinearity": {
                "results": [
                    {"column": v.column, "vif": round(v.vif, 2), "severity": v.severity, "note": v.note}
                    for v in multicollinearity_report["results"]
                ],
                "note": multicollinearity_report["note"],
            },
        },
        "segments": _serialize_segments(segments_report),
        "seasonality": _serialize_seasonality(seasonality_report),
        "period_comparison": period_comparison_report,
        "drivers": drivers_report,
        "anomalies": _serialize_anomalies(anomaly_report),
        "simpsons_paradox": simpsons_paradox_report,
        "partial_correlations": partial_correlation_report,
        "benford": benford_report,
        "cohorts": _serialize_cohorts(cohort_report, retention_risk_report),
        "confidence_intervals": confidence_interval_report,
        "robustness": robustness_report,
        "text_analysis": text_analysis_report,
    }


def _semantic_layer(df: pd.DataFrame) -> dict:
    """
    Runs the domain-aware pipeline (Phases 1-4: semantic classification,
    domain detection, analysis planning, execution) and returns domain info
    plus the dynamic analyses list. This is ADDITIVE to the existing
    KPI/insights pipeline below, not a replacement — the existing pipeline
    already works well for sales-shaped data (profit margin, discount risk,
    customer concentration) and there's no reason to risk regressing it
    while this newer, more general layer is still maturing.
    """
    semantic_roles = classify_columns(df)
    domain_result = detect_domain(semantic_roles)
    cardinalities = {c: int(df[c].nunique()) for c in df.columns}
    numeric_cols = set(df.select_dtypes(include="number").columns)

    df_exec = df.copy()
    for col, info in semantic_roles.items():
        if info["role"] == "DATE":
            df_exec[col] = pd.to_datetime(df_exec[col], errors="coerce")

    specs = plan_analyses(semantic_roles, domain_result["domain"], cardinalities, len(df), numeric_cols)
    analyses = execute_all(df_exec, specs)

    return {
        "domain": domain_result["domain"],
        "domain_confidence": domain_result["confidence"],
        "semantic_roles": {c: info["role"] for c, info in semantic_roles.items()},
        "analyses": analyses,
    }


MIN_NUMERIC_COERCION_SUCCESS_RATE = 0.90


def _coerce_mostly_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Real-world CSVs routinely have a numeric column with a handful of
    stray non-numeric placeholder values (a literal "F", "N/A", "-",
    a typo...). Pandas reads the WHOLE column as text the moment it hits
    even one such value, which silently excludes an otherwise perfectly
    good numeric column from every measure, correlation, and VIF check --
    even when 98%+ of the column is real numbers. If coercing a text
    column to numeric succeeds for the large majority of its values,
    convert it; the few unparseable values become NaN (missing), which
    is far more honest than discarding the column's real data entirely.
    Columns that are mostly non-numeric (dates, categories, IDs) fail the
    success-rate check and are left untouched.
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype != object and not pd.api.types.is_string_dtype(df[col]):
            continue
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        coerced = pd.to_numeric(non_null, errors="coerce")
        success_rate = coerced.notna().mean()
        if success_rate >= MIN_NUMERIC_COERCION_SUCCESS_RATE:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _json_records_to_dataframe(data) -> pd.DataFrame:
    """Real-world JSON exports show up in a few common shapes:
    - a flat array of objects: [{"a": 1, "b": 2}, ...]              -> the normal case
    - an object of column arrays: {"a": [1, 2], "b": [3, 4]}        -> "columns" orientation
    - a wrapper object with the actual records nested one level in,
      e.g. {"data": [...]}, {"results": [...]}, {"records": [...]}  -> common API-dump shape
    json_normalize also flattens one level of nested objects (e.g. a
    {"address": {"city": ..., "zip": ...}} field becomes address.city /
    address.zip columns) so moderately nested exports still work without
    the user needing to flatten them first."""
    if isinstance(data, list):
        return pd.json_normalize(data)
    if isinstance(data, dict):
        list_fields = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        if len(list_fields) == 1:
            return pd.json_normalize(list_fields[0])
        return pd.DataFrame(data)  # columns-orientation dict
    raise ValueError("Expected a JSON array of records, or an object of columns.")


def _downcast_numeric_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """Only touches already-numeric columns -- float64->float32,
    int64->the smallest int type that fits. Deliberately does NOT
    convert string columns to category dtype here: a column with mostly
    numbers and a few stray text values (see _coerce_mostly_numeric_columns
    below) is read as object dtype by the CSV parser, and converting it
    to category dtype before that cleanup runs would make it skip the
    coercion check entirely (category dtype is neither plain object nor
    treated as string dtype), silently breaking the exact bug that
    function exists to catch. Categorical conversion happens as a
    separate pass, after numeric coercion, in _load_dataframe."""
    for col in chunk.select_dtypes(include=["float64"]).columns:
        chunk[col] = pd.to_numeric(chunk[col], downcast="float")
    for col in chunk.select_dtypes(include=["int64"]).columns:
        chunk[col] = pd.to_numeric(chunk[col], downcast="integer")
    return chunk


def _read_csv_chunked(raw: bytes, sep: str, encoding: str) -> pd.DataFrame:
    """Reads and downcasts numeric columns in CSV_CHUNK_ROWS-row pieces
    rather than one single pd.read_csv call -- the whole file still ends
    up in memory (every analysis module needs the complete dataframe, so
    true streaming isn't compatible with how this app works end to end),
    but the FINAL dataframe is meaningfully smaller than a single-shot
    read would produce, which is the part of "large file" pain that's
    actually fixable here. Measured on a 2M row / 124MB synthetic CSV:
    120MB -> 90MB final dataframe memory (~25% smaller).

    Deliberately numeric-only, not also converting low-cardinality string
    columns to category dtype -- tried that first, and it broke: a date
    column with few distinct months got miscategorized as a category,
    and unrelated code elsewhere in the pipeline (kpi.py's date-range
    calculation) called .min()/.max() on it expecting a datetime, which
    raises on an unordered Categorical. Numeric downcasting can't cause
    that class of bug -- float32 and int8 behave identically to float64
    and int64 for every comparison/arithmetic operation anything else in
    this codebase does, just with less precision/range, which is a
    trade-off, not a type-semantics change."""
    chunks = [
        _downcast_numeric_chunk(chunk)
        for chunk in pd.read_csv(io.BytesIO(raw), sep=sep, encoding=encoding, chunksize=CSV_CHUNK_ROWS)
    ]
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def _too_big_message(size_mb: float) -> str:
    return (f"This file is {size_mb:.0f} MB, which is over the {MAX_FILE_SIZE_MB:g} MB limit. "
            f"Try trimming it down or splitting it into smaller files.")


async def _read_upload(upload) -> bytes:
    """Read an upload in chunks and STOP once it passes the size cap. `await upload.read()`
    pulls the whole file into memory first and checks afterwards, so on a small hosted
    instance a huge upload used the RAM before being refused."""
    limit = int(MAX_FILE_SIZE_MB * 1024 * 1024)
    parts, total = [], 0
    while True:
        chunk = await upload.read(UPLOAD_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            # the true size is unknown (we stopped reading), so say "over the limit", not a number
            raise HTTPException(400, f"This file is over the {MAX_FILE_SIZE_MB:g} MB limit. "
                                     f"Try trimming it down or splitting it into smaller files.")
        parts.append(chunk)
    return b"".join(parts)


def _load_dataframe(filename: str, raw: bytes) -> pd.DataFrame:
    ext = Path(filename).suffix.lower()

    size_mb = len(raw) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(400, _too_big_message(size_mb))

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Upload a .csv, .tsv, .xlsx, .xls, .json, or .parquet file.",
        )

    if ext in (".xlsx", ".xls"):
        try:
            return _coerce_mostly_numeric_columns(pd.read_excel(io.BytesIO(raw)))
        except Exception as e:
            raise HTTPException(400, f"Couldn't read the Excel file: {e}")

    if ext == ".parquet":
        try:
            return _coerce_mostly_numeric_columns(pd.read_parquet(io.BytesIO(raw)))
        except Exception as e:
            raise HTTPException(400, f"Couldn't read the Parquet file: {e}")

    if ext == ".json":
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise HTTPException(400, f"Couldn't parse the JSON file: {e}")
        try:
            df = _json_records_to_dataframe(data)
        except Exception as e:
            raise HTTPException(400, f"Couldn't convert the JSON structure into a table: {e}")
        return _coerce_mostly_numeric_columns(df)

    sep = "\t" if ext == ".tsv" else ","
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        try:
            return _coerce_mostly_numeric_columns(_read_csv_chunked(raw, sep, encoding))
        except Exception as e:
            last_error = e
            continue
    raise HTTPException(400, f"Couldn't parse the file: {last_error}")


# Maps the legacy pipeline's fixed role keys (shown in the Column Mapping
# UI) to the v2 pipeline's semantic role tags, so a single manual
# correction from the user ("no, use THIS column for Revenue") can be
# applied consistently to both pipelines rather than only fixing the
# cosmetic legacy label while the actual v2 dashboard stays wrong.
LEGACY_ROLE_TO_V2_ROLE = {
    "date": "DATE",
    "revenue": "FINANCIAL_METRIC",
    "profit": "PROFIT",
    "cost": "UNIT_COST",
    "quantity": "QUANTITY",
    "discount": "DISCOUNT",
    "customer": "CUSTOMER",
    "category": "CATEGORY",
    "region": "LOCATION",
}


def _analyze_df(df: pd.DataFrame, mapping: dict, confidence: dict, unmapped: list, extra_categoricals: list, v2_role_overrides: dict = None) -> dict:
    df_prepared = prepare(df, mapping)
    response = {
        "detected_columns": mapping,
        "detection_confidence": confidence,
        "unmapped_columns": unmapped,
        "kpis": compute_kpis(df_prepared, mapping),
        "monthly_trend": timeseries_monthly(df_prepared, mapping),
        "breakdowns": all_breakdowns(df_prepared, mapping, extra_categoricals),
        "insights": generate_insights(df_prepared, mapping, extra_categoricals),
    }
    response.update(_semantic_layer(df))
    response["v2"] = _run_v2_pipeline(df, role_overrides=v2_role_overrides)
    return response


def _categorical_only_analysis(df: pd.DataFrame, detection: dict, v2_role_overrides: dict = None) -> dict:
    """
    Fallback for files with no usable numeric metric at all (e.g. a roster of
    names/categories, plain text data). Rather than failing outright, still
    return row/column counts and frequency breakdowns of the categorical
    columns — genuinely useful, just without revenue-style KPIs or charts
    that don't apply to this kind of data.
    """
    row_count = int(len(df))
    col_count = int(len(df.columns))
    missing_frac = df.isnull().mean().mean() if col_count else 0
    completeness = float(round((1 - missing_frac) * 100, 1))

    insight_text = (
        f"This file has {row_count} rows and {col_count} columns but no clear "
        f"numeric metric (like a sales amount, price, or score column) to "
        f"analyze trends or KPIs against."
    )

    response = {
        "detected_columns": detection["mapping"],
        "detection_confidence": detection["confidence"],
        "unmapped_columns": detection["unmapped"],
        "kpis": {
            "row_count": row_count,
            "column_count": col_count,
            "data_completeness_pct": completeness,
        },
        "monthly_trend": [],
        "breakdowns": [],
        "insights": [{
            "text": insight_text,
            "recommendation": (
                "If there is a numeric column meant to be the main metric, try "
                "renaming it to something like 'Amount', 'Value', or 'Score' so "
                "it gets picked up automatically."
            ),
            "score": 1,
            "type": "data_quality",
        }],
        "no_numeric_metric": True,
    }
    response.update(_semantic_layer(df))
    response["v2"] = _run_v2_pipeline(df, role_overrides=v2_role_overrides)
    return response


def _load_and_detect(filename: str, raw: bytes):
    """Returns (df_prepared, mapping) or raises HTTPException."""
    df = _load_dataframe(filename, raw)
    if df.empty:
        raise HTTPException(400, f"{filename} has no rows.")

    detection = detect_columns(df)
    mapping = detection["mapping"]
    if "revenue" not in mapping:
        raise HTTPException(
            422,
            f"{filename}: has no numeric column to use as the primary metric, "
            "so it can't be combined with other files. Try analyzing it on its own instead.",
        )
    df_prepared = prepare(df, mapping)
    return df_prepared, mapping


def _attach_sensitive_report(result: dict, df: pd.DataFrame) -> dict:
    """Scan the dataframe for personal-data columns and store the report in
    `v2.sensitive_data` (column names + kinds only, never raw values). It
    lives inside v2 on purpose: the share/export guard in the frontend reads
    it from the same object that is about to be shared."""
    try:
        report = detect_sensitive_data(df)
    except Exception:
        report = None  # detection is advisory -- never let it fail an analysis
    if report is not None and isinstance(result.get("v2"), dict):
        result["v2"]["sensitive_data"] = report
    return result


def _full_analyze_from_df(df: pd.DataFrame, column_overrides: str = None) -> dict:
    """Shared by /api/analyze and /api/compare -- column detection through
    to the full response dict. Pulled out once so both endpoints run the
    exact same logic rather than risking two copies drifting apart (the
    project has a documented history of that exact failure mode)."""
    if df.empty:
        raise HTTPException(400, "The uploaded file has no rows.")

    detection = detect_columns(df)
    mapping = detection["mapping"]
    confidence = detection["confidence"]

    v2_role_overrides = None
    if column_overrides:
        try:
            overrides = json.loads(column_overrides)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(400, "column_overrides must be valid JSON.")
        v2_role_overrides = {}
        for legacy_role, column in overrides.items():
            if column not in df.columns:
                raise HTTPException(400, f"'{column}' is not a column in this file.")
            mapping[legacy_role] = column
            confidence[legacy_role] = "manual"
            if legacy_role in LEGACY_ROLE_TO_V2_ROLE:
                v2_role_overrides[column] = LEGACY_ROLE_TO_V2_ROLE[legacy_role]

    unmapped = detection["unmapped"]
    if column_overrides and v2_role_overrides is not None:
        mapped_columns = set(mapping.values())
        unmapped = [c for c in unmapped if c not in mapped_columns]
        detection["unmapped"] = unmapped

    if "revenue" not in mapping:
        # No usable numeric metric anywhere in the file — don't fail, fall
        # back to a categorical/overview-only analysis instead.
        return _attach_sensitive_report(
            _categorical_only_analysis(df, detection, v2_role_overrides=v2_role_overrides), df)

    return _attach_sensitive_report(
        _analyze_df(df, mapping, confidence, unmapped, detection["extra_categoricals"], v2_role_overrides=v2_role_overrides), df)


class AnalyzeResponse(BaseModel):
    """Top-level shape only -- `v2` and `analyses` hold this session's
    17+ analysis modules, each with its own evolving nested shape (some
    domain-dependent). Modeling those exhaustively would go stale the
    next time a module's output changes, so they're documented as
    generic objects here; the field NAMES and top-level TYPES are still
    real, accurate documentation, which is the actual gap this closes --
    previously every endpoint showed no response schema at all in
    /docs."""
    detected_columns: dict
    detection_confidence: dict
    unmapped_columns: list
    kpis: dict
    monthly_trend: list
    breakdowns: dict
    insights: list
    domain: str
    domain_confidence: float
    semantic_roles: dict
    analyses: list
    v2: dict
    no_numeric_metric: bool = False
    source_files: Optional[list] = None
    join_info: Optional[dict] = None


class CompareResponse(BaseModel):
    result_a: AnalyzeResponse
    result_b: AnalyzeResponse
    diff: dict


class HealthResponse(BaseModel):
    status: str
    # The upload cap in force. Lets a deployment check confirm that the host's configuration
    # (DATALENS_MAX_FILE_MB) was actually applied, without uploading a large file to find out.
    max_file_mb: float


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...), column_overrides: str = Form(None)):
    raw = await _read_upload(file)
    df = _load_dataframe(file.filename, raw)
    return SafeJSONResponse(_full_analyze_from_df(df, column_overrides=column_overrides))


@app.post("/api/compare", response_model=CompareResponse)
async def compare(file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    """Compares two SEPARATE analyses (e.g. this month's export vs. last
    month's) -- different from /api/analyze-combined, which merges two
    files' rows into one dataset. Each file runs through the exact same
    pipeline as a normal single-file upload, independently; comparison.py
    then diffs the two already-computed results."""
    raw_a, raw_b = await _read_upload(file_a), await _read_upload(file_b)
    df_a = _load_dataframe(file_a.filename, raw_a)
    df_b = _load_dataframe(file_b.filename, raw_b)

    result_a = _full_analyze_from_df(df_a)
    result_b = _full_analyze_from_df(df_b)

    if result_a.get("no_numeric_metric") or result_b.get("no_numeric_metric"):
        raise HTTPException(400, "Both files need a usable numeric metric to compare.")

    diff = compare_results(result_a, result_b, file_a.filename, file_b.filename)
    return SafeJSONResponse({"result_a": result_a, "result_b": result_b, "diff": diff})


@app.post("/api/analyze-combined", response_model=AnalyzeResponse)
async def analyze_combined(files: list[UploadFile] = File(...)):
    if len(files) < 2:
        raise HTTPException(400, "Select at least two files to combine.")

    prepared_with_mappings = []
    source_names = []
    for f in files:
        raw = await _read_upload(f)
        df_prepared, mapping = _load_and_detect(f.filename, raw)
        prepared_with_mappings.append((df_prepared, mapping))
        source_names.append(f.filename)

    combined_df, combined_mapping = combine_dataframes(prepared_with_mappings, source_names)

    # combined_mapping is role->role (already canonical), so every role in it
    # is "combined" confidence, not name-matched or inferred from a single file
    confidence = {role: "combined" for role in combined_mapping}

    result = {
        "detected_columns": combined_mapping,
        "detection_confidence": confidence,
        "unmapped_columns": [],
        "kpis": compute_kpis(combined_df, combined_mapping),
        "monthly_trend": timeseries_monthly(combined_df, combined_mapping),
        "breakdowns": all_breakdowns(combined_df, combined_mapping, []),
        "insights": generate_insights(combined_df, combined_mapping),
        "source_files": source_names,
    }
    result.update(_semantic_layer(combined_df))
    result["v2"] = _run_v2_pipeline(combined_df)
    _attach_sensitive_report(result, combined_df)
    return SafeJSONResponse(result)


@app.post("/api/analyze-joined", response_model=AnalyzeResponse)
async def analyze_joined(files: list[UploadFile] = File(...)):
    """The relational counterpart to /api/analyze-combined: that one
    stacks two same-shaped files' ROWS on top of each other; this one
    merges two DIFFERENTLY-shaped files' COLUMNS side by side on a
    shared key it detects automatically (app/relational_join.py), the
    way orders.csv + customers.csv actually relate to each other in
    real exports. Runs the merged table through the exact same
    _full_analyze_from_df pipeline as a normal single-file upload, so
    every stat is computed on the real joined rows."""
    if len(files) != 2:
        raise HTTPException(400, "Select exactly two files to join.")

    raw_a, raw_b = await _read_upload(files[0]), await _read_upload(files[1])
    df_a = _load_dataframe(files[0].filename, raw_a)
    df_b = _load_dataframe(files[1].filename, raw_b)

    if df_a.empty or df_b.empty:
        raise HTTPException(400, "Both files need at least one row to join.")

    key = detect_join_key(df_a, df_b)
    if key is None:
        raise HTTPException(
            400,
            "Couldn't find a column shared between these two files that looks like a real join key "
            "— matching column name, with enough overlapping values, and closer to one-value-per-row "
            "on at least one side. If these files share an ID column under different names, try "
            "renaming it to match in both files and re-uploading. If these are really the same kind "
            "of data (same columns, different rows), use Combine instead of Join.",
        )

    joined_df, join_info = join_dataframes(df_a, df_b, key, files[0].filename, files[1].filename)

    result = _full_analyze_from_df(joined_df)
    result["join_info"] = join_info
    result["source_files"] = [files[0].filename, files[1].filename]
    return SafeJSONResponse(result)


@app.get("/api/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "max_file_mb": MAX_FILE_SIZE_MB}


class PdfExportRequest(BaseModel):
    file_name: str
    v2: dict


class CodeExportRequest(BaseModel):
    file_name: str
    v2: dict
    filters: Optional[dict] = None   # {dateColumn, dateFrom, dateTo, dimensionFilters: {col: [values]}}


class HypothesisTestRequest(BaseModel):
    group_column: str
    outcome_column: str
    group_a: str
    group_b: str
    groups: list           # one entry per row, parallel to `outcomes`
    outcomes: list
    outcome_kind: str = "auto"            # auto | numeric | categorical
    positive_level: Optional[str] = None  # which outcome value to measure the rate of (categorical)


class ShareRequest(BaseModel):
    file_name: str
    kpis: dict = {}
    v2: dict
    # The explicit, deliberate "share it as is" decision (the UI's "Continue without
    # masking"). Without it, a payload that appears to contain personal data is refused.
    acknowledge_personal_data: bool = False


class ShareCreateResponse(BaseModel):
    token: str
    expires_at: float
    share_path: str


@app.post("/api/share", response_model=ShareCreateResponse)
def create_share_link(payload: ShareRequest):
    """Stores a snapshot of an already-computed analysis (kpis + v2,
    filterable_data included so the recipient gets the same interactive
    filtering the original session has, not a stripped static view) and
    returns a token -- share_cache.py explains why this is in-memory and
    ephemeral rather than a database.

    A share link is the one place this app makes data public, so it is also
    where personal data is refused unless the caller says otherwise
    (share_guard.py explains what is checked and what is deliberately not
    trusted). The refusal lists column names and kinds, never values."""
    # Refuse an oversized request before inspecting it, not after.
    try:
        check_share_size({"file_name": payload.file_name, "kpis": payload.kpis, "v2": payload.v2})
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not payload.acknowledge_personal_data:
        findings = blocking_findings(scan_share_payload(payload.v2))
        if findings:
            return SafeJSONResponse(
                status_code=409,
                content={"detail": refusal_message(findings), "code": "personal_data", "findings": findings},
            )
    try:
        token, expires_at = create_share({"file_name": payload.file_name, "kpis": payload.kpis, "v2": payload.v2})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ShareCreateResponse(token=token, expires_at=expires_at, share_path=f"/share/{token}")


@app.get("/api/share/{token}")
def get_share_link(token: str):
    payload = get_share(token)
    if payload is None:
        raise HTTPException(404, "This share link has expired or doesn't exist.")
    return SafeJSONResponse(payload)


@app.post(
    "/api/export/cleaned-csv",
    responses={200: {"content": {"text/csv": {}}, "description": "The cleaned CSV file, as a direct download."}},
)
async def export_cleaned_csv(file: UploadFile = File(...)):
    """Stateless like the other export endpoints -- takes a fresh upload
    of the same file (the raw dataframe isn't kept server-side between
    requests) and returns a cleaned CSV: exact duplicate rows removed,
    and a `flagged_as_unusual` column added rather than removing
    anything else -- see data_cleaning.py for why deletion isn't the
    default here."""
    raw = await _read_upload(file)
    df = _load_dataframe(file.filename, raw)
    if df.empty:
        raise HTTPException(400, "The uploaded file has no rows.")

    profile = understand_dataset(df)
    cleaned, summary = build_cleaned_csv(df, profile)

    csv_bytes = cleaned.to_csv(index=False).encode("utf-8")
    safe_name = "".join(c for c in file.filename.rsplit(".", 1)[0] if c.isalnum() or c in ("-", "_")) or "datalens-data"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_cleaned.csv"',
            "X-Clean-Summary": json.dumps(summary),
        },
    )


@app.post(
    "/api/export/pdf",
    responses={200: {"content": {"application/pdf": {}}, "description": "The PDF report, as a direct download."}},
)
def export_pdf(payload: PdfExportRequest):
    """Stateless PDF export: the frontend already has the full analysis
    result in memory (same shape /api/analyze returns), so it sends that
    straight back here to be rendered. Nothing about the original file or
    its data is stored server-side -- this matches the rest of the app's
    'nothing is persisted' design, it's just a formatter."""
    if not payload.v2:
        raise HTTPException(400, "No analysis data provided.")
    try:
        pdf_bytes = build_pdf_report(payload.file_name, payload.v2)
    except Exception:
        raise HTTPException(500, "Could not generate the PDF report.")

    safe_name = "".join(c for c in payload.file_name.rsplit(".", 1)[0] if c.isalnum() or c in ("-", "_")) or "datalens-report"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_report.pdf"'},
    )


@app.post(
    "/api/export/html",
    responses={200: {"content": {"text/html": {}}, "description": "The self-contained HTML report, as a direct download."}},
)
def export_html(payload: PdfExportRequest):
    """Same stateless shape as /api/export/pdf -- reuses the same
    PdfExportRequest model since the payload is identical (file_name +
    v2), just rendered into a self-contained HTML document instead."""
    if not payload.v2:
        raise HTTPException(400, "No analysis data provided.")
    try:
        html_str = build_html_report(payload.file_name, payload.v2)
    except Exception:
        raise HTTPException(500, "Could not generate the HTML report.")

    safe_name = "".join(c for c in payload.file_name.rsplit(".", 1)[0] if c.isalnum() or c in ("-", "_")) or "datalens-report"
    return Response(
        content=html_str.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_report.html"'},
    )


@app.post("/api/hypothesis-test")
def hypothesis_test(payload: HypothesisTestRequest):
    """A directed A-vs-B question on rows the browser already holds (the same
    filtered rows the dashboard shows). Stateless like the exports: nothing is
    stored, and an unusable question comes back as available=false with a
    plain-language note rather than as an error."""
    if len(payload.groups) > MAX_ROWS_FOR_FILTERING:
        raise HTTPException(413, "Too many rows for an interactive test.")
    result = run_hypothesis_test(
        payload.groups, payload.outcomes, payload.group_a, payload.group_b,
        payload.group_column, payload.outcome_column, payload.outcome_kind, payload.positive_level,
    )
    return SafeJSONResponse(result)


@app.post(
    "/api/export/code",
    responses={200: {"content": {"text/x-python": {}}, "description": "A pandas script that reproduces the analysis, as a direct download."}},
)
def export_code(payload: CodeExportRequest):
    """Template-based (no LLM) pandas script for the analysis the user is
    looking at. Stateless like the other exports: it needs only the result the
    frontend already holds plus the active filters, and never sees the data."""
    if not payload.v2:
        raise HTTPException(400, "No analysis data provided.")
    try:
        script = generate_script(payload.file_name, payload.v2, payload.filters)
    except Exception:
        raise HTTPException(500, "Could not generate the script.")

    safe_name = "".join(c for c in payload.file_name.rsplit(".", 1)[0] if c.isalnum() or c in ("-", "_")) or "datalens"
    return Response(
        content=script.encode("utf-8"),
        media_type="text/x-python",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_datalens.py"'},
    )


# ---- Serve the built frontend (if present) ----
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Any non-API path returns the SPA's index.html; the React app handles the rest.
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
