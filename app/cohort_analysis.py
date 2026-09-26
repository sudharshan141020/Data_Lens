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

assess_retention_risk answers a different, more actionable question than
the cohort curve does: not "how does a typical cohort decay over months"
but "which SPECIFIC entities look overdue to return, right now". It's a
simple rule: find how long entities here typically go between visits
(the median gap across every entity with at least two), then flag anyone
whose current gap since their last visit already run well past that --
"past their typical return window", the same idea a rule-based CRM churn
flag would use, kept deliberately simple rather than a predictive model.
"""
import pandas as pd

MIN_ENTITIES_PER_COHORT = 5
MIN_COHORTS = 2
MAX_COHORTS = 12           # cap for a readable heatmap
MAX_PERIODS_TRACKED = 11   # "Month 0" through "Month 11" -- a year of retention

MIN_GAPS_FOR_TYPICAL_WINDOW = 10   # need this many observed return gaps before a "typical window" means anything
RISK_MEDIUM_MULTIPLIER = 1.5       # overdue by 1.5x the typical gap -- worth a look
RISK_HIGH_MULTIPLIER = 3.0         # overdue by 3x -- very likely already lost
MAX_AT_RISK_LISTED = 20            # cap the individual call-out list; at_risk_count/pct still reflect everyone flagged

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


def assess_retention_risk(df: pd.DataFrame, profile) -> dict:
    """Flags entities that look overdue to return, using each entity's own
    last-seen date against a "typical return window" learned from
    everyone else's actual behavior (the median gap between consecutive
    visits, across every entity that has more than one) -- not a fixed
    number of days picked in advance, so it adapts to whatever this
    dataset's normal repeat cadence actually is (days for a delivery app,
    months for an annual-checkup clinic)."""
    entity_col = _find_entity_column(profile)
    date_col = profile.date_column
    if not entity_col or not date_col:
        return {
            "available": False,
            "note": "Needs an identifiable entity (like a customer or patient ID) and a date column to flag who's overdue to return.",
        }

    tmp = df[[entity_col, date_col]].dropna().drop_duplicates()
    if tmp.empty:
        return {"available": False, "note": "No rows with both an entity ID and a date."}

    tmp = tmp.sort_values([entity_col, date_col])
    tmp["_prev"] = tmp.groupby(entity_col)[date_col].shift(1)
    gaps_days = (tmp[date_col] - tmp["_prev"]).dt.days.dropna()
    gaps_days = gaps_days[gaps_days > 0]  # same-day duplicate events contribute a 0-day "gap" -- not a return

    if len(gaps_days) < MIN_GAPS_FOR_TYPICAL_WINDOW:
        return {
            "available": False,
            "note": f"Needs at least {MIN_GAPS_FOR_TYPICAL_WINDOW} observed repeat visits across "
                    f"{profile.primary_entity.lower()}s to learn a typical return window -- this dataset "
                    f"doesn't have enough repeat activity to tell what's normal here.",
        }

    typical_gap_days = float(gaps_days.median())
    if typical_gap_days <= 0:
        return {"available": False, "note": "Couldn't establish a meaningful typical return window from this data."}

    reference_date = tmp[date_col].max()
    last_seen = tmp.groupby(entity_col)[date_col].max()
    days_since = (reference_date - last_seen).dt.days
    overdue_ratio = days_since / typical_gap_days

    at_risk_mask = overdue_ratio >= RISK_MEDIUM_MULTIPLIER
    total_entities = len(last_seen)
    at_risk_count = int(at_risk_mask.sum())

    if at_risk_count == 0:
        summary = (
            f"None of the {total_entities} {profile.primary_entity.lower()}s tracked are overdue -- everyone's "
            f"within their usual return window of about {typical_gap_days:.0f} days."
        )
    else:
        at_risk_pct = round(100 * at_risk_count / total_entities, 1)
        summary = (
            f"{at_risk_count} of {total_entities} {profile.primary_entity.lower()}s ({at_risk_pct}%) haven't "
            f"returned in longer than usual -- {profile.primary_entity.lower()}s here typically come back "
            f"within about {typical_gap_days:.0f} days."
        )

    flagged = pd.DataFrame({
        "entity": last_seen.index[at_risk_mask],
        "last_seen": last_seen[at_risk_mask].dt.date.astype(str),
        "days_since_last_seen": days_since[at_risk_mask].astype(int),
        "overdue_ratio": overdue_ratio[at_risk_mask].round(2),
    })
    flagged["risk_level"] = flagged["overdue_ratio"].apply(lambda r: "high" if r >= RISK_HIGH_MULTIPLIER else "medium")
    flagged = flagged.sort_values("overdue_ratio", ascending=False)

    return {
        "available": True,
        "note": None,
        "entity_column": entity_col,
        "entity_noun": profile.primary_entity,
        "typical_return_days": round(typical_gap_days, 1),
        "reference_date": str(reference_date.date()),
        "total_entities": total_entities,
        "at_risk_count": at_risk_count,
        "at_risk_pct": round(100 * at_risk_count / total_entities, 1) if total_entities else None,
        "risk_level_counts": {
            "high": int((flagged["risk_level"] == "high").sum()),
            "medium": int((flagged["risk_level"] == "medium").sum()),
        },
        "summary": summary,
        "at_risk": flagged.head(MAX_AT_RISK_LISTED).to_dict("records"),
    }
