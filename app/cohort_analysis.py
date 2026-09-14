"""
Cohort / Retention Analysis.

Groups each entity (customer, patient, student, ...) by the calendar
month of their FIRST appearance in the data -- their "cohort" -- then
tracks what fraction of that cohort shows up again in each subsequent
month. The classic retention-curve view: distinct from
period_comparison.py (which compares aggregate totals between two
periods) and seasonality.py (which looks for a repeating calendar
pattern) -- this is specifically about whether the SAME entities keep
coming back, which neither of those touches.

Needs an identifiable entity column (the same "primary entity" concept
understanding.py already uses -- customer ID, patient ID, etc.) and a
date column. Most naturally useful for sales/SaaS (repeat customers),
but works for any domain where rows represent repeatable events tied to
an identifiable entity.
"""
import pandas as pd

MIN_ENTITIES_PER_COHORT = 5
MIN_COHORTS = 2
MAX_COHORTS = 12           # cap for a readable heatmap
MAX_PERIODS_TRACKED = 11   # "Month 0" through "Month 11" -- a year of retention

ENTITY_ROLE_TO_NOUN = {
    "PATIENT": "Patient", "CUSTOMER": "Customer", "STUDENT": "Student",
    "EMPLOYEE": "Employee", "DRIVER": "Driver",
}


def _find_entity_column(profile) -> str:
    return next((c for c, role in profile.semantic_roles.items() if role in ENTITY_ROLE_TO_NOUN), None)


def analyze_cohorts(df: pd.DataFrame, profile) -> dict:
    entity_col = _find_entity_column(profile)
    date_col = profile.date_column
    if not entity_col or not date_col:
        return {
            "available": False,
            "note": "Needs an identifiable entity (like a customer or patient ID) and a date column to track repeat behavior over time.",
        }

    tmp = df[[entity_col, date_col]].dropna()
    if tmp.empty:
        return {"available": False, "note": "No rows with both an entity ID and a date."}

    tmp["_month"] = tmp[date_col].dt.to_period("M")
    first_seen = tmp.groupby(entity_col)["_month"].min().rename("_cohort")
    tmp = tmp.join(first_seen, on=entity_col)
    tmp["_period_index"] = (tmp["_month"] - tmp["_cohort"]).apply(lambda p: p.n)

    cohort_sizes = first_seen.value_counts()
    valid_cohorts = sorted(c for c, n in cohort_sizes.items() if n >= MIN_ENTITIES_PER_COHORT)
    if len(valid_cohorts) < MIN_COHORTS:
        return {
            "available": False,
            "note": f"Needs at least {MIN_COHORTS} cohort months with {MIN_ENTITIES_PER_COHORT}+ {profile.primary_entity.lower()}s "
                    f"each to show a retention pattern -- this dataset doesn't have enough repeat activity concentrated that way.",
        }
    valid_cohorts = valid_cohorts[-MAX_COHORTS:]  # most recent cohorts, capped for chart readability

    max_available_period = int(tmp["_period_index"].max())
    n_periods = min(MAX_PERIODS_TRACKED, max_available_period) + 1

    rows = []
    heatmap_points = []
    for cohort in valid_cohorts:
        size = int(cohort_sizes[cohort])
        sub = tmp[tmp["_cohort"] == cohort]
        retention = []
        for period_idx in range(n_periods):
            active = int(sub.loc[sub["_period_index"] == period_idx, entity_col].nunique())
            pct = round(100 * active / size, 1) if size else None
            retention.append({"period": period_idx, "pct": pct, "n": active})
            heatmap_points.append({"x": f"Month {period_idx}", "y": str(cohort), "value": pct})
        rows.append({"cohort": str(cohort), "size": size, "retention": retention})

    # Headline: average Month-1 retention (the first real repeat-behavior
    # signal) across cohorts that have reached at least that point.
    month1_values = [r["retention"][1]["pct"] for r in rows if len(r["retention"]) > 1 and r["retention"][1]["pct"] is not None]
    avg_month1_retention = round(sum(month1_values) / len(month1_values), 1) if month1_values else None

    if avg_month1_retention is not None:
        summary = (
            f"On average, {avg_month1_retention}% of {profile.primary_entity.lower()}s from a given month's cohort "
            f"are still active the following month."
        )
    else:
        summary = f"Tracking {len(rows)} cohorts, but not enough history yet to report a one-month retention rate."

    return {
        "available": True,
        "note": None,
        "entity_column": entity_col,
        "entity_noun": profile.primary_entity,
        "cohort_count": len(rows),
        "periods_tracked": n_periods,
        "avg_month1_retention_pct": avg_month1_retention,
        "summary": summary,
        "cohorts": rows,
        "heatmap_points": heatmap_points,
    }
