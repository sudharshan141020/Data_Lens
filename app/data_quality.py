"""
Data Quality Center.

Distinct from the Weak Point Detector: weak_points.py flags PROBLEMS worth
recommending action on (a specific missing-data weak point only fires past
a severity threshold). This module answers a different question — "what
does this dataset structurally look like" — as visualizable data regardless
of severity, for a dedicated Data Quality section rather than buried in
prose findings.
"""
from dataclasses import dataclass, field
import pandas as pd

from app.understanding import DatasetProfile


@dataclass
class DataQualityReport:
    missing_by_column: list = field(default_factory=list)
    duplicate_row_count: int = 0
    duplicate_row_pct: float = 0.0
    constant_columns: list = field(default_factory=list)
    high_cardinality_columns: list = field(default_factory=list)
    outlier_summary: list = field(default_factory=list)
    dtype_breakdown: dict = field(default_factory=dict)
    overall_quality_score: float = 100.0
    # "Usable data" score: computed only over the columns that actually feed
    # the analysis (measures + dimensions + the date column, if any) rather
    # than every column in the raw file. A file can carry a lot of empty or
    # junk columns (stray unnamed columns, partial summary stats pasted into
    # the same sheet) that tank the raw score without meaning the columns
    # actually being analyzed are unreliable -- this gives that distinction
    # a number instead of leaving it invisible.
    usable_quality_score: float = 100.0
    usable_column_count: int = 0
    total_column_count: int = 0


def _quality_score(missing_frac: float, dup_frac: float, n_constant: int, n_cols: int) -> float:
    score = 100.0
    score -= missing_frac * 40   # missingness is the heaviest-weighted issue
    score -= dup_frac * 20
    score -= (n_constant / max(n_cols, 1)) * 15
    return max(0.0, round(score, 1))


def analyze_data_quality(df: pd.DataFrame, profile: DatasetProfile) -> DataQualityReport:
    missing_pct = df.isnull().mean() * 100
    missing_by_column = [
        {"column": c, "missing_pct": round(v, 1)}
        for c, v in missing_pct[missing_pct > 0].sort_values(ascending=False).items()
    ]

    dup_count = int(df.duplicated().sum())
    dup_pct = round(dup_count / len(df) * 100, 1) if len(df) else 0.0

    constant_columns = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]

    high_cardinality_columns = []
    for c in df.columns:
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            ratio = df[c].nunique() / max(len(df), 1)
            if ratio > 0.9:
                high_cardinality_columns.append(c)

    outlier_summary = []
    for m in profile.measures:
        series = df[m.column].dropna()
        if len(series) < 20:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        outliers = series[(series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)]
        if len(outliers):
            outlier_summary.append({
                "column": m.column,
                "outlier_count": int(len(outliers)),
                "outlier_pct": round(len(outliers) / len(series) * 100, 1),
            })
    outlier_summary.sort(key=lambda o: o["outlier_pct"], reverse=True)

    dtype_breakdown = {
        "numeric": int(len(df.select_dtypes(include="number").columns)),
        "date": sum(1 for r in profile.semantic_roles.values() if r == "DATE"),
        "categorical": len(profile.dimensions),
        "identifier_or_text": len(high_cardinality_columns),
    }

    missing_frac_overall = df.isnull().mean().mean() if len(df.columns) else 0
    score = _quality_score(missing_frac_overall, dup_pct / 100, len(constant_columns), len(df.columns))

    used_cols = {m.column for m in profile.measures} | {d.column for d in profile.dimensions}
    # The date column the pipeline actually charts (understanding._pick_date_column),
    # not merely the first DATE-role one: those differ whenever a file leads with a
    # mostly-empty or birth-date column, and scoring the unused one made this number
    # describe a column nothing else in the app analyses.
    date_col = profile.date_column or next((c for c, r in profile.semantic_roles.items() if r == "DATE"), None)
    if date_col:
        used_cols.add(date_col)
    used_cols = [c for c in used_cols if c in df.columns]

    if used_cols:
        used_missing_frac = df[used_cols].isnull().mean().mean()
        used_constant_count = sum(1 for c in used_cols if c in constant_columns)
        usable_score = _quality_score(used_missing_frac, dup_pct / 100, used_constant_count, len(used_cols))
    else:
        # Nothing was identified as a measure/dimension to analyze -- fall
        # back to the raw score rather than claiming a usable subset exists.
        usable_score = score

    return DataQualityReport(
        missing_by_column=missing_by_column,
        duplicate_row_count=dup_count,
        duplicate_row_pct=dup_pct,
        constant_columns=constant_columns,
        high_cardinality_columns=high_cardinality_columns,
        outlier_summary=outlier_summary,
        dtype_breakdown=dtype_breakdown,
        overall_quality_score=score,
        usable_quality_score=usable_score,
        usable_column_count=len(used_cols),
        total_column_count=len(df.columns),
    )
