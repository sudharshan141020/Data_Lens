import io
from typing import Optional
import pandas as pd
from pathlib import Path
import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.column_detector import detect_columns
from app.kpi import prepare, compute_kpis, timeseries_monthly, breakdown_by, all_breakdowns, combine_dataframes
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
from app.benford import check_benfords_law
from app.comparison import compare_results
from app.clustering import analyze_segments
from app.anomaly_detection import detect_anomalies
from app.seasonality import decompose_trend
from app.period_comparison import compare_periods
from app.forecasting import forecast_trend
from app.filtering import build_filterable_data
from app.pdf_report import build_pdf_report

import math
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
    the whole response once at the API boundary."""
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

STATIC_DIR = Path(__file__).parent / "static"

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet"}


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

    anomaly_report = detect_anomalies(df_exec, profile)
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

            result = forecast_trend(a["data"])
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
        "anomalies": _serialize_anomalies(anomaly_report),
        "simpsons_paradox": simpsons_paradox_report,
        "benford": benford_report,
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


def _load_dataframe(filename: str, raw: bytes) -> pd.DataFrame:
    ext = Path(filename).suffix.lower()

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
            return _coerce_mostly_numeric_columns(pd.read_csv(io.BytesIO(raw), sep=sep, encoding=encoding))
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
        return _categorical_only_analysis(df, detection, v2_role_overrides=v2_role_overrides)

    return _analyze_df(df, mapping, confidence, unmapped, detection["extra_categoricals"], v2_role_overrides=v2_role_overrides)


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), column_overrides: str = Form(None)):
    raw = await file.read()
    df = _load_dataframe(file.filename, raw)
    return _full_analyze_from_df(df, column_overrides=column_overrides)


@app.post("/api/compare")
async def compare(file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    """Compares two SEPARATE analyses (e.g. this month's export vs. last
    month's) -- different from /api/analyze-combined, which merges two
    files' rows into one dataset. Each file runs through the exact same
    pipeline as a normal single-file upload, independently; comparison.py
    then diffs the two already-computed results."""
    raw_a, raw_b = await file_a.read(), await file_b.read()
    df_a = _load_dataframe(file_a.filename, raw_a)
    df_b = _load_dataframe(file_b.filename, raw_b)

    result_a = _full_analyze_from_df(df_a)
    result_b = _full_analyze_from_df(df_b)

    if result_a.get("no_numeric_metric") or result_b.get("no_numeric_metric"):
        raise HTTPException(400, "Both files need a usable numeric metric to compare.")

    diff = compare_results(result_a, result_b, file_a.filename, file_b.filename)
    return {"result_a": result_a, "result_b": result_b, "diff": diff}


@app.post("/api/analyze-combined")
async def analyze_combined(files: list[UploadFile] = File(...)):
    if len(files) < 2:
        raise HTTPException(400, "Select at least two files to combine.")

    prepared_with_mappings = []
    source_names = []
    for f in files:
        raw = await f.read()
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
    return result


@app.get("/api/health")
def health():
    return {"status": "ok"}


class PdfExportRequest(BaseModel):
    file_name: str
    v2: dict


@app.post("/api/export/pdf")
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
