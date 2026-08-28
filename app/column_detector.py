"""
Detects the semantic role of each column in an arbitrary sales CSV.

Roles we care about:
    date        - order/transaction date
    revenue     - sales/revenue amount
    profit      - profit/margin amount (optional)
    cost        - cost amount (optional, used to derive profit if profit absent)
    quantity    - units sold (optional)
    discount    - discount applied (optional)
    customer    - customer identifier/name
    category    - product category / segment (can be multiple)
    region      - geographic grouping (state/region/city/country)

Strategy: name-based fuzzy matching first (fast, high precision), then
dtype-based fallback for anything left unmapped, so the tool still works on
column names it has never seen.
"""
import re
import pandas as pd

# name -> role, checked as substring match against lowercased/underscored column names
NAME_HINTS = {
    "date": ["order date", "order_date", "date", "txn_date", "transaction_date",
             "purchase_date", "sale_date"],
    "revenue": ["sales", "revenue", "amount", "total_amount", "gross_sales",
                "order_value", "total_sales", "price_total"],
    "profit": ["profit", "margin", "net_income", "net_profit"],
    "cost": ["cost", "cogs", "unit_cost", "expense"],
    "quantity": ["quantity", "qty", "units", "unit_count"],
    "discount": ["discount", "disc_pct", "discount_rate"],
    "customer": ["customer", "client", "buyer", "account_name", "cust_id",
                 "customer_id", "customer_name"],
    "category": ["category", "product_category", "segment", "product_type",
                 "sub-category", "sub_category", "product_line"],
    "region": ["region", "state", "city", "country", "territory", "market", "zone"],
}

def _normalize(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", col.strip().lower()).strip("_")


MIN_NONNULL_FRACTION_FOR_MATCH = 0.10  # require at least 10% real values...
MIN_NONNULL_COUNT_FOR_MATCH = 5        # ...and at least 5 real values regardless of dataset size


def _is_usable_column(df: pd.DataFrame, col: str) -> bool:
    """Same guard as understanding.py's _is_usable_column, duplicated here
    rather than imported to keep this legacy module's dependencies as they
    were (it doesn't otherwise import from understanding.py). A column
    that's almost entirely empty shouldn't win a name match just because
    it's called "Sales" or "Revenue" -- e.g. a handful of stray leftover
    values from a summary table pasted into the same CSV as the real data
    would otherwise get picked as THE revenue column."""
    non_null = int(df[col].notna().sum())
    if non_null < MIN_NONNULL_COUNT_FOR_MATCH:
        return False
    if len(df) and (non_null / len(df)) < MIN_NONNULL_FRACTION_FOR_MATCH:
        return False
    return True


def _exact_and_substring_matches(columns, df):
    """
    Two-pass matcher across ALL columns at once (not per-column), so a real
    exact match (e.g. a column literally named 'Region') always wins over a
    weaker substring match on a different column (e.g. 'Country' containing
    hint 'country'). Returns (mapping, confidence, assigned_cols).
    """
    norm_cols = {col: _normalize(col) for col in columns}
    # Usability doesn't depend on which role/hint is being checked -- it's
    # purely a property of the column's own data -- so compute it once per
    # column here rather than inside the nested role x hint x column loops
    # below. Without this, a wide NAME_HINTS dictionary times many columns
    # meant redundantly re-scanning the same column's non-null count
    # potentially hundreds of times; at 150k rows that alone was the
    # single largest cost in the whole analyze request (~3s of ~4.6s).
    usable_cols = {c for c in columns if _is_usable_column(df, c)}
    assigned = set()
    mapping, confidence = {}, {}

    # Pass 1: exact matches, hint-order and role-declaration-order determine priority
    for role, hints in NAME_HINTS.items():
        for hint in hints:
            hint_norm = _normalize(hint)
            match = next((c for c in columns if c not in assigned and norm_cols[c] == hint_norm and c in usable_cols), None)
            if match:
                mapping[role] = match
                confidence[role] = "name"
                assigned.add(match)
                break

    # Pass 2: substring matches for roles still unmapped
    for role, hints in NAME_HINTS.items():
        if role in mapping:
            continue
        best_col, best_len = None, 0
        for hint in hints:
            hint_norm = _normalize(hint)
            for c in columns:
                if c in assigned or c not in usable_cols:
                    continue
                if hint_norm in norm_cols[c] and len(hint_norm) > best_len:
                    best_col, best_len = c, len(hint_norm)
        if best_col:
            mapping[role] = best_col
            confidence[role] = "name"
            assigned.add(best_col)

    return mapping, confidence, assigned


def _dtype_fallback(series: pd.Series):
    """Guess a role for columns that name-matching couldn't place."""
    non_null = series.dropna()
    if non_null.empty:
        return None

    # try date parse
    if pd.api.types.is_string_dtype(series) or series.dtype == object or "datetime" in str(series.dtype):
        try:
            # Parsing every value with dateutil's lenient fallback parser
            # is expensive at scale (100k+ rows) even when the column
            # correctly turns out not to be a date -- a sample is
            # statistically just as reliable for this yes/no check.
            sample = non_null if len(non_null) <= 1000 else non_null.sample(1000, random_state=0)
            parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() > 0.9:
                return "date"
        except Exception:
            pass

    if pd.api.types.is_numeric_dtype(series):
        vals = non_null.astype(float)
        is_all_int = (vals == vals.round()).all()

        # identifier-like: near-unique integers, or a perfectly sequential
        # counter (1,2,3...) — these are row identifiers, never a real metric,
        # regardless of how large their sum happens to be
        uniq_ratio = non_null.nunique() / max(len(non_null), 1)
        if is_all_int and uniq_ratio > 0.9 and len(non_null) > 10:
            sorted_vals = vals.sort_values().reset_index(drop=True)
            looks_sequential = (sorted_vals.diff().dropna() == 1).mean() > 0.9 if len(sorted_vals) > 1 else False
            if looks_sequential or uniq_ratio > 0.98:
                return "identifier_like"

        # binary/near-constant flags (e.g. a 0/1 survived column) aren't a
        # meaningful "quantity" — exclude before the quantity check below
        if non_null.nunique() <= 2:
            return "categorical"

        # quantity-like: small non-negative integers -> check BEFORE discount,
        # since a small item-count column can otherwise look "discount-shaped"
        if is_all_int and vals.min() >= 0 and vals.max() <= 1000 and vals.nunique() < 50:
            # still allow the discount check below to override if this integer
            # column steps in typical percent increments (0, 5, 10, 15, 20...)
            steps_like_percent = (vals % 5 == 0).mean() > 0.9 and vals.max() <= 100 and vals.nunique() > 3
            if not steps_like_percent:
                return "quantity"

        # discount-like: fractional 0-1, or integer percent with typical steps
        if vals.between(0, 1).mean() > 0.95 and vals.max() <= 1 and not is_all_int:
            return "discount"
        if is_all_int and vals.between(0, 100).mean() > 0.95 and vals.nunique() < 20 and (vals % 5 == 0).mean() > 0.9:
            return "discount"

        # otherwise treat as a currency-like measure; caller decides revenue vs profit
        return "numeric_measure"

    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        uniq_ratio = non_null.nunique() / max(len(non_null), 1)
        if uniq_ratio < 0.5:
            return "categorical"
        if uniq_ratio > 0.8:
            return "identifier_like"

    return None


def detect_columns(df: pd.DataFrame) -> dict:
    """
    Returns:
        {
          "mapping": {role: column_name, ...},   # confident role -> single best column
          "unmapped": [column_name, ...],         # columns we couldn't confidently place
          "extra_categoricals": [column_name,...] # categorical columns beyond the primary category/region
          "confidence": {role: "name" | "inferred"}
        }
    """
    unmapped = []
    extra_categoricals = []
    numeric_measures = []

    columns = list(df.columns)
    mapping, confidence, assigned = _exact_and_substring_matches(columns, df)

    for col in columns:
        if col in assigned:
            continue
        if not _is_usable_column(df, col):
            unmapped.append(col)
            continue
        # no name hint matched -> dtype fallback
        guess = _dtype_fallback(df[col])
        if guess == "numeric_measure":
            numeric_measures.append(col)
        elif guess == "categorical" and "category" not in mapping:
            mapping["category"] = col
            confidence["category"] = "inferred"
        elif guess == "categorical":
            extra_categoricals.append(col)
        elif guess in ("date", "discount", "quantity") and guess not in mapping:
            mapping[guess] = col
            confidence[guess] = "inferred"
        elif guess is None or guess == "identifier_like":
            unmapped.append(col)
        else:
            unmapped.append(col)

    # if revenue wasn't found by name, take the largest-magnitude leftover numeric measure
    if "revenue" not in mapping and numeric_measures:
        sums = {c: df[c].abs().sum() for c in numeric_measures}
        best = max(sums, key=sums.get)
        mapping["revenue"] = best
        confidence["revenue"] = "inferred"
        numeric_measures.remove(best)

    # remaining numeric measures: only claim one as profit if there's a real
    # signal it's profit-shaped (can take negative values, unlike a price/cost
    # column which is normally always positive) — otherwise leave it unmapped
    # rather than guessing, since a wrong profit column produces confidently
    # wrong margin insights
    if "profit" not in mapping and numeric_measures:
        profit_like = [c for c in numeric_measures if (df[c] < 0).any()]
        if profit_like:
            mapping["profit"] = profit_like[0]
            confidence["profit"] = "inferred"
            numeric_measures.remove(profit_like[0])

    unmapped.extend(numeric_measures)

    return {
        "mapping": mapping,
        "unmapped": unmapped,
        "extra_categoricals": extra_categoricals,
        "confidence": confidence,
    }
