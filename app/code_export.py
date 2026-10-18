"""
"Show the code" export.

Turns what DataLens just did into a plain pandas script an analyst can read,
run, and carry on from in a notebook: how the file is loaded and cleaned, the
headline numbers, the groupbys behind each analysis, and the filters that were
active when they exported. It is a TEMPLATE, not a model -- every analysis type
the app can run maps to one fixed snippet that mirrors the code in
executor_v2.py -- so it fits the rest of the app's rule-based design, is
deterministic, and shows nothing is a black box.

The property that makes it trustworthy rather than decorative: the script is
tested by RUNNING it on the same data and comparing every number to what the app
showed (tests/test_code_export.py), including the float32 precision the app's
loader uses. If the generator and executor_v2.py drift apart, that test fails.

Safety: column names, the file name, filter values and analysis titles all come
from the user's data. Names and values only ever enter the script through
repr() (a quoted literal), and titles only as single-line comments, so a column
called  a'); import os  cannot become code.

What it does NOT reproduce, and says so in the header: forecasts, k-means
segments, anomaly scores, cohorts and the statistical tests (p-values,
bootstrap intervals). Those are real analyses with their own modules; the
script covers the groupbys and summaries, which are the part people want to
verify or extend.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

# Analysis types the app executes straight from the dataframe (executor_v2.py).
SUPPORTED_TYPES = {
    "trend", "histogram", "distribution_count", "distribution_sum",
    "pivot", "correlation", "correlation_matrix", "outlier",
}
# Types the dashboard re-computes under the filter bar (filterUtils.FILTER_REACTIVE_TYPES).
FILTER_REACTIVE_TYPES = {"trend", "distribution_sum", "distribution_count"}

TOP_N = 15          # executor_v2.TOP_N
PIVOT_TOP_N = 8     # executor_v2._compute_pivot top_n
HIST_BINS = 10      # executor_v2.HIST_BINS
MAX_SCATTER_POINTS = 400


def _lit(value) -> str:
    """A Python literal for any value that came from user data."""
    return repr(value)


def _comment(text) -> str:
    """Single-line, comment-safe version of arbitrary text."""
    return re.sub(r"\s+", " ", str(text)).strip()


def _ident(raw: str, used: set) -> str:
    base = re.sub(r"\W+", "_", str(raw)).strip("_").lower() or "analysis"
    if base[0].isdigit():
        base = f"a_{base}"
    name, n = base, 2
    while name in used:
        name, n = f"{base}_{n}", n + 1
    used.add(name)
    return name


def _agg(aggregation: Optional[str]) -> str:
    return "mean" if aggregation == "avg" else "sum"


# ---------------------------------------------------------------------------
# fixed sections
# ---------------------------------------------------------------------------
_LOAD_HELPERS = '''
def _coerce_mostly_numeric_columns(frame):
    """A column that is >=90% numbers with a few stray placeholders ('N/A', '-')
    is converted to numeric, the strays becoming missing. DataLens does this so
    one bad cell doesn't push a whole numeric column out of the analysis."""
    frame = frame.copy()
    for col in frame.columns:
        if frame[col].dtype != object and not pd.api.types.is_string_dtype(frame[col]):
            continue
        non_null = frame[col].dropna()
        if len(non_null) == 0:
            continue
        if pd.to_numeric(non_null, errors="coerce").notna().mean() >= 0.90:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def _downcast_numeric(frame):
    """DataLens reads numbers at reduced precision (float32 / small ints) to save
    memory. Kept by default so your totals match the app to the last digit."""
    frame = frame.copy()
    for col in frame.select_dtypes(include=["float64"]).columns:
        frame[col] = pd.to_numeric(frame[col], downcast="float")
    for col in frame.select_dtypes(include=["int64"]).columns:
        frame[col] = pd.to_numeric(frame[col], downcast="integer")
    return frame


def _json_records_to_dataframe(data):
    if isinstance(data, list):
        return pd.json_normalize(data)
    if isinstance(data, dict):
        list_fields = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        if len(list_fields) == 1:
            return pd.json_normalize(list_fields[0])
        return pd.DataFrame(data)
    raise ValueError("Expected a JSON array of records, or an object of columns.")


def load(path):
    ext = Path(path).suffix.lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".parquet":
        return pd.read_parquet(path)
    if ext == ".json":
        with open(path, encoding="utf-8") as fh:
            return _json_records_to_dataframe(json.load(fh))
    sep = "\\t" if ext == ".tsv" else ","
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
        try:
            frame = pd.read_csv(path, sep=sep, encoding=encoding)
            return _downcast_numeric(frame) if MATCH_APP_PRECISION else frame
        except Exception as exc:  # try the next encoding
            last_error = exc
    raise last_error
'''


def _header(file_name: str, n_analyses: int, skipped: int, filters_active: bool) -> list:
    return [
        '"""',
        f"DataLens analysis script for {_comment(file_name)}",
        f"Generated {date.today().isoformat()} by DataLens. Re-runs, in plain pandas, what the dashboard computed:",
        "loading and cleaning, the headline numbers, and the groupby behind each analysis"
        + (", with the filters that were active when you exported." if filters_active else "."),
        "",
        f"{n_analyses} analyses are reproduced below. DataLens also runs forecasts, k-means segments, anomaly",
        "scoring, cohorts and statistical tests (p-values, bootstrap intervals); those are not in this script."
        + (f" {skipped} further analyses that depend on derived columns are skipped for the same reason." if skipped else ""),
        "",
        "Needs: pandas, numpy (+ openpyxl for .xlsx, pyarrow for .parquet).",
        'Cells are marked with "# %%" so VS Code and Jupyter can run them one at a time.',
        '"""',
        "import json",
        "from pathlib import Path",
        "",
        "import numpy as np",
        "import pandas as pd",
        "",
    ]


def _filters_block(filters: dict, date_column: Optional[str]) -> list:
    """Mirrors filterUtils.applyFilters on the dataframe."""
    out = ["# %% 3. Filters that were active in DataLens"]
    out.append("# The dashboard applies these to the trend and the by-category charts only; the other charts and the")
    out.append("# headline numbers use the full data. This script does the same (df_filtered vs df).")
    out.append("mask = pd.Series(True, index=df.index)")
    d_from, d_to = filters.get("dateFrom"), filters.get("dateTo")
    dcol = filters.get("dateColumn") or date_column
    if dcol and (d_from or d_to):
        out.append(f"_day = pd.to_datetime(df[{_lit(dcol)}], errors=\"coerce\").dt.strftime(\"%Y-%m-%d\")")
        out.append("mask &= _day.notna()  # rows with no date are excluded once a date range is set")
        if d_from:
            out.append(f"mask &= _day >= {_lit(d_from)}")
        if d_to:
            out.append(f"mask &= _day <= {_lit(d_to)}")
    for col, allowed in (filters.get("dimensionFilters") or {}).items():
        if allowed:
            out.append(f"mask &= df[{_lit(col)}].isin({_lit(list(allowed))})")
    out.append("df_filtered = df[mask]")
    out.append('print(f"Filters keep {len(df_filtered):,} of {len(df):,} rows")')
    out.append("")
    return out


def _has_active_filters(filters: Optional[dict]) -> bool:
    if not filters:
        return False
    if filters.get("dateFrom") or filters.get("dateTo"):
        return True
    return any(v for v in (filters.get("dimensionFilters") or {}).values())


# ---------------------------------------------------------------------------
# one snippet per analysis type -- each mirrors executor_v2.py
# ---------------------------------------------------------------------------
def _analysis_code(a: dict, var: str, frame: str) -> Optional[list]:
    t = a["type"]
    metric, col, col2, dcol = a.get("metric_column"), a.get("column"), a.get("column2"), a.get("date_column")
    agg = _agg(a.get("aggregation"))

    if t == "trend" and metric and dcol:
        return [
            f"_t = {frame}.dropna(subset=[{_lit(dcol)}, {_lit(metric)}]).copy()",
            f"_t[\"_month\"] = _t[{_lit(dcol)}].dt.to_period(\"M\").astype(str)",
            f"{var} = _t.groupby(\"_month\")[{_lit(metric)}].{agg}().sort_index()",
        ]
    if t == "distribution_count" and col:
        return [f"{var} = {frame}[{_lit(col)}].value_counts().head({TOP_N})"]
    if t == "distribution_sum" and col and metric:
        return [f"{var} = {frame}.groupby({_lit(col)})[{_lit(metric)}].{agg}().sort_values(ascending=False).head({TOP_N})"]
    if t == "histogram" and metric:
        return [
            f"_s = {frame}[{_lit(metric)}].dropna()",
            f"counts, edges = np.histogram(_s, bins=min({HIST_BINS}, max(_s.nunique(), 1)))",
            f"{var} = pd.DataFrame({{\"bin_start\": edges[:-1], \"bin_end\": edges[1:], \"count\": counts}})",
        ]
    if t == "pivot" and col and col2 and metric:
        return [
            f"_sub = {frame}[[{_lit(col)}, {_lit(col2)}, {_lit(metric)}]].dropna(subset=[{_lit(col)}, {_lit(col2)}])",
            f"_rows = _sub[{_lit(col)}].value_counts().head({PIVOT_TOP_N}).index.tolist()  # most frequent values, by row count",
            f"_cols = _sub[{_lit(col2)}].value_counts().head({PIVOT_TOP_N}).index.tolist()",
            f"_sub = _sub[_sub[{_lit(col)}].isin(_rows) & _sub[{_lit(col2)}].isin(_cols)]",
            f"{var} = _sub.groupby([{_lit(col)}, {_lit(col2)}])[{_lit(metric)}].{agg}().unstack({_lit(col2)}).reindex(index=_rows, columns=_cols)",
        ]
    if t == "correlation":
        xl, yl, color = a.get("x_label"), a.get("y_label"), a.get("color_by")
        if not (xl and yl):
            return None
        lines = [f"{var} = {frame}[[{_lit(xl)}, {_lit(yl)}]].corr().iloc[0, 1]  # Pearson r"]
        cols = [xl, yl] + ([color] if color else [])
        lines += [
            f"{var}_points = {frame}[{_lit(cols)}].dropna()",
            f"if len({var}_points) > {MAX_SCATTER_POINTS}:",
            f"    {var}_points = {var}_points.sample({MAX_SCATTER_POINTS}, random_state=42)  # the dashboard plots a sample",
        ]
        return lines
    if t == "correlation_matrix":
        return None  # needs the column list; handled by caller via _matrix_code
    if t == "outlier" and metric:
        return [
            f"_s = {frame}[{_lit(metric)}].dropna()",
            "_q1, _median, _q3 = _s.quantile(0.25), _s.quantile(0.5), _s.quantile(0.75)",
            "_iqr = _q3 - _q1",
            "_low, _high = _q1 - 1.5 * _iqr, _q3 + 1.5 * _iqr",
            f"{var} = {{",
            "    \"min\": _s.min(), \"q1\": _q1, \"median\": _median, \"q3\": _q3, \"max\": _s.max(),",
            "    \"lower_fence\": max(_low, _s.min()), \"upper_fence\": min(_high, _s.max()),",
            "    \"outlier_count\": int(((_s < _low) | (_s > _high)).sum()),",
            "}",
        ]
    return None


def _referenced_columns(a: dict) -> list:
    t = a["type"]
    if t == "correlation":
        cols = [a.get("x_label"), a.get("y_label"), a.get("color_by")]
    elif t == "correlation_matrix":
        cols = a.get("matrix_columns") or []
    else:
        cols = [a.get("metric_column"), a.get("column"), a.get("column2"), a.get("date_column")]
    return [c for c in cols if c]


def _matrix_columns(a: dict) -> list:
    seen = []
    for cell in a.get("data") or []:
        for k in ("x", "y"):
            if cell.get(k) not in seen:
                seen.append(cell[k])
    return seen


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def generate_script(file_name: str, v2: dict, filters: Optional[dict] = None) -> str:
    profile = v2.get("profile") or {}
    fd = v2.get("filterable_data") or {}
    known = set(profile.get("columns") or [])
    if not known:  # older result without the column list: fall back to what filtering knows
        known = set(fd.get("dimension_columns") or []) | set(fd.get("measure_columns") or [])
        if fd.get("date_column"):
            known.add(fd["date_column"])
    gate = bool(known)

    top_ids = [a.get("id") for a in (v2.get("top_analyses") or [])]
    seen, ordered = set(), []
    for a in list(v2.get("top_analyses") or []) + list(v2.get("all_analyses") or []):
        if a.get("id") in seen:
            continue
        seen.add(a.get("id"))
        ordered.append(a)

    usable, skipped = [], 0
    for a in ordered:
        if a.get("type") not in SUPPORTED_TYPES:
            continue
        if a["type"] == "correlation_matrix":
            a = {**a, "matrix_columns": _matrix_columns(a)}
        cols = _referenced_columns(a)
        if gate and not all(c in known for c in cols):
            skipped += 1
            continue
        usable.append(a)

    active = _has_active_filters(filters)
    date_columns = list(profile.get("date_columns") or ([fd["date_column"]] if fd.get("date_column") else []))

    lines = _header(file_name, len(usable), skipped, active)
    lines += [
        "# %% 1. Load",
        f"DATA_FILE = {_lit(file_name)}  # <- point this at your copy of the file",
        "MATCH_APP_PRECISION = True      # False = read numbers at full float64 precision instead of DataLens's float32",
        "REMOVE_EXACT_DUPLICATES = False  # DataLens analyses every row as loaded; its \"cleaned CSV\" export drops exact duplicates",
        _LOAD_HELPERS.rstrip("\n"),
        "",
        "df = load(DATA_FILE)",
        "df = _coerce_mostly_numeric_columns(df)",
        "",
        "# %% 2. Clean",
    ]
    if date_columns:
        for c in date_columns:
            lines.append(f"df[{_lit(c)}] = pd.to_datetime(df[{_lit(c)}], errors=\"coerce\")  # unparseable dates become missing")
    else:
        lines.append("# (no date columns were detected)")
    lines += [
        "if REMOVE_EXACT_DUPLICATES:",
        "    df = df.drop_duplicates().reset_index(drop=True)",
        'print(f"{len(df):,} rows x {len(df.columns)} columns")',
        "",
    ]

    if active:
        lines += _filters_block(filters, fd.get("date_column"))
    else:
        lines += ["# %% 3. Filters", "# No filters were active when this was exported.", "df_filtered = df", ""]

    results = []  # (analysis id, variable)

    intervals = (v2.get("confidence_intervals") or {}).get("intervals") or []
    lines.append("# %% 4. Headline numbers")
    lines.append("headline = {")
    emitted_headline = False
    for i in intervals:
        m = i.get("measure")
        if not m or (gate and m not in known):
            continue
        fn = "mean" if i.get("aggregation") == "avg" else "sum"
        lines.append(f"    {_lit(m)}: df[{_lit(m)}].dropna().astype(float).{fn}(),  # {'average' if fn == 'mean' else 'total'}")
        emitted_headline = True
    lines.append("}")
    lines.append("print(pd.Series(headline))" if emitted_headline else "# (no numeric measures)")
    lines.append("")

    used = set()
    key_ids = set(top_ids)

    def emit(group_title, items):
        if not items:
            return
        lines.append(f"# %% {group_title}")
        for a in items:
            var = _ident(a.get("id") or a.get("title") or a["type"], used)
            frame = "df_filtered" if a["type"] in FILTER_REACTIVE_TYPES else "df"
            code = _matrix_code(a, var) if a["type"] == "correlation_matrix" else _analysis_code(a, var, frame)
            if not code:
                continue
            note = " (filtered)" if (frame == "df_filtered" and active) else (" (full data)" if active else "")
            lines.append(f"# {_comment(a.get('title') or a['type'])}{note}")
            lines.extend(code)
            lines.append(f"print(\"\\n\" + {_lit(_comment(a.get('title') or a['type']))})")
            lines.append(f"print({var})")
            lines.append("")
            results.append((a.get("id"), var))

    emit("5. Key analyses (the dashboard)", [a for a in usable if a.get("id") in key_ids])
    emit("6. More analyses (the explorer)", [a for a in usable if a.get("id") not in key_ids])

    lines.append("# %% Everything above, keyed by the analysis id DataLens uses")
    lines.append("RESULTS = {")
    for aid, var in results:
        lines.append(f"    {_lit(aid)}: {var},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _matrix_code(a: dict, var: str) -> Optional[list]:
    cols = a.get("matrix_columns") or []
    if len(cols) < 2:
        return None
    return [f"{var} = df[{_lit(cols)}].corr(numeric_only=True)"]
