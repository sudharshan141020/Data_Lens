"""
Filterable data payload.

The backend is intentionally stateless -- nothing is stored server-side
after a request completes, and there's no session to re-query when the
user changes a filter. So instead of a `/api/filter` endpoint, this builds
a compact row-level slice (date + dimensions + measures only, never every
raw column) that ships once alongside the rest of the v2 analysis. The
frontend filters and re-aggregates it entirely client-side from then on --
no further server round trips, and nothing about the "nothing persisted"
design changes, since this only ever lives in the browser's memory for the
current page session.

Deliberately NOT sent for very large datasets -- shipping 200k+ rows to
the browser just for filtering isn't worth the payload size or client-side
aggregation cost. This is the same tradeoff HANDOFF.md's roadmap already
flags under "performance/caching for very large datasets" -- filtering is
simply not available past that point, and the frontend is told so
explicitly rather than silently doing nothing.
"""
import pandas as pd

from app.understanding import DatasetProfile

MAX_ROWS_FOR_FILTERING = 100_000


def build_filterable_data(df: pd.DataFrame, profile: DatasetProfile) -> dict:
    cols = []
    if profile.date_column:
        cols.append(profile.date_column)
    dim_cols = [d.column for d in profile.dimensions if d.is_chartable and d.column in df.columns]
    measure_cols = [m.column for m in profile.measures if m.column in df.columns]
    cols += dim_cols + measure_cols
    cols = [c for c in dict.fromkeys(cols) if c in df.columns]  # de-dupe, preserve order

    if not cols:
        return {"available": False, "reason": "no_filterable_columns", "rows": []}

    if len(df) > MAX_ROWS_FOR_FILTERING:
        return {"available": False, "reason": "dataset_too_large", "rows": []}

    sub = df[cols].copy()
    if profile.date_column and profile.date_column in sub.columns:
        sub[profile.date_column] = pd.to_datetime(sub[profile.date_column], errors="coerce").dt.strftime("%Y-%m-%d")

    rows = sub.where(pd.notnull(sub), None).to_dict(orient="records")

    return {
        "available": True,
        "date_column": profile.date_column,
        "dimension_columns": dim_cols,
        "measure_columns": measure_cols,
        "rows": rows,
    }
