"""
Relational Join.

"Combine" (kpi.py's combine_dataframes) stacks rows from same-shaped
files on top of each other -- same columns, more rows, like two months
of the same export. This is the other half of multi-file support:
merging DIFFERENTLY-shaped files side-by-side on a shared key column,
the way real business data actually comes split up (orders.csv +
customers.csv + products.csv), rather than only ever being one flat
file.

Auto-detects which column is the shared key between two uploads --
rather than asking the user to know pandas terminology like "foreign
key" -- using two signals together:
  1. The column names match (normalized: case/punctuation-insensitive).
  2. The values in those two columns actually overlap meaningfully.

A shared *name* alone isn't enough -- two files could both have a
"Status" column that means something completely different in each. A
plausible-looking *key* alone isn't enough either, since a low-
cardinality shared category (both files happen to have a "Region"
column with the same four values) would overlap heavily by chance
without being a real relational key -- joining on it would multiply
every row in one file by every matching row in the other instead of
attaching one record to another. Requiring the key column to also be
(close to) unique on at least one side -- a real ID, not a shared
category -- is what rules that out. Requiring both name match and
value overlap at once is what makes this safe to run automatically
with no column names the user has to recognize or type themselves.
"""
import re
from typing import Optional

import pandas as pd

MIN_KEY_OVERLAP = 0.2       # at least this fraction of the smaller side's distinct values must appear on the other side
MIN_KEY_UNIQUENESS = 0.9    # on at least one side, the column must be this close to one-value-per-row to count as a real key
MAX_CANDIDATES_CHECKED = 30  # bounds compute on very wide files


def _normalize_name(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower())


def _stem(filename: str) -> str:
    return re.sub(r"\.[^.]+$", "", str(filename))


def _uniqueness_ratio(series: pd.Series) -> float:
    non_null = series.dropna()
    if non_null.empty:
        return 0.0
    return non_null.nunique() / len(non_null)


def _overlap_ratio(a: pd.Series, b: pd.Series) -> float:
    set_a = set(a.dropna().astype(str).str.strip().str.lower())
    set_b = set(b.dropna().astype(str).str.strip().str.lower())
    if not set_a or not set_b:
        return 0.0
    smaller = min(len(set_a), len(set_b))
    return len(set_a & set_b) / smaller


def detect_join_key(df_a: pd.DataFrame, df_b: pd.DataFrame) -> Optional[dict]:
    """Returns the single best candidate key as {"column_a", "column_b",
    "overlap", "uniqueness_a", "uniqueness_b"}, or None if nothing in
    either file qualifies as a shared key. Checks every pair of
    identically-named columns (there's normally just one or two
    candidates -- most files don't have many columns whose normalized
    name collides), scores each by value overlap, and returns the
    strongest one."""
    name_map_b = {}
    for col in df_b.columns:
        name_map_b.setdefault(_normalize_name(col), []).append(col)

    candidates = []
    checked = 0
    for col_a in df_a.columns:
        if checked >= MAX_CANDIDATES_CHECKED:
            break
        norm = _normalize_name(col_a)
        if not norm or norm not in name_map_b:
            continue
        for col_b in name_map_b[norm]:
            checked += 1
            uniq_a = _uniqueness_ratio(df_a[col_a])
            uniq_b = _uniqueness_ratio(df_b[col_b])
            if uniq_a < MIN_KEY_UNIQUENESS and uniq_b < MIN_KEY_UNIQUENESS:
                continue  # neither side looks like a real key -- probably a shared category, not an id
            overlap = _overlap_ratio(df_a[col_a], df_b[col_b])
            if overlap < MIN_KEY_OVERLAP:
                continue
            candidates.append({
                "column_a": col_a, "column_b": col_b,
                "overlap": overlap, "uniqueness_a": uniq_a, "uniqueness_b": uniq_b,
            })

    if not candidates:
        return None
    candidates.sort(key=lambda c: (c["overlap"], max(c["uniqueness_a"], c["uniqueness_b"])), reverse=True)
    return candidates[0]


def join_dataframes(df_a: pd.DataFrame, df_b: pd.DataFrame, key: dict, name_a: str, name_b: str) -> tuple:
    """Left-joins from whichever side looks like the 'many'/fact side
    (lower uniqueness on the key -- e.g. orders, one row per sale) onto
    the 'one'/dimension side (higher uniqueness -- e.g. customers, one
    row per person), so every fact row survives even with no match, and
    matched attributes from the other file get attached alongside it.
    A tie (equally unique on both sides -- e.g. two files that are
    themselves both one-row-per-entity) keeps df_a's rows as the base.

    Returns (joined_df, info) where info is an honest, on-screen-ready
    summary of what happened: which column matched which, how many rows
    found a match versus didn't, and which columns existed in both
    files and got disambiguated with a "(filename)" suffix rather than
    pandas' opaque default."""
    col_a, col_b = key["column_a"], key["column_b"]
    # Recomputed fresh from the actual df_a/df_b passed in here, rather than
    # trusting key["uniqueness_a"/"uniqueness_b"] -- those were computed by
    # detect_join_key against whichever dataframes it happened to be called
    # with, and silently mean the wrong thing if this function is ever
    # called with df_a/df_b in a different order than that original call.
    many_is_a = _uniqueness_ratio(df_a[col_a]) <= _uniqueness_ratio(df_b[col_b])
    left, right = (df_a, df_b) if many_is_a else (df_b, df_a)
    left_key, right_key = (col_a, col_b) if many_is_a else (col_b, col_a)
    left_name, right_name = (name_a, name_b) if many_is_a else (name_b, name_a)

    overlap_cols = (set(left.columns) & set(right.columns)) - {left_key, right_key}
    left_r = left.rename(columns={c: f"{c} ({_stem(left_name)})" for c in overlap_cols})
    right_r = right.rename(columns={c: f"{c} ({_stem(right_name)})" for c in overlap_cols})

    right_r = right_r.copy()
    right_r["_datalens_matched"] = True

    if right_key == left_key:
        joined = left_r.merge(right_r, how="left", on=left_key)
    else:
        joined = left_r.merge(right_r, how="left", left_on=left_key, right_on=right_key)
        if right_key in joined.columns:
            joined = joined.drop(columns=[right_key])

    matched_mask = joined["_datalens_matched"].fillna(False)
    joined = joined.drop(columns=["_datalens_matched"])

    total_left = len(left)
    matched_count = int(matched_mask.sum())

    info = {
        "fact_file": left_name,
        "dimension_file": right_name,
        "key_in_fact_file": left_key,
        "key_in_dimension_file": right_key,
        "total_rows": total_left,
        "matched_rows": matched_count,
        "unmatched_rows": total_left - matched_count,
        "match_rate_pct": round(100 * matched_count / total_left, 1) if total_left else 0.0,
        "shared_column_names": sorted(overlap_cols),
        "row_count_after_join": len(joined),
    }
    return joined, info
