"""
Phase 2 — Analysis Planner + Visualization Planner.

Consumes a DatasetProfile (from understanding.py) and produces a list of
AnalysisSpec objects: WHAT to analyze, WHICH chart type fits it best, an
importance score for ranking (so the dashboard can show the "3 most
important" analyses instead of everything at once), and which Analysis
Explorer section it belongs to.

Deliberately has NO dataframe access — it only reasons over the structured
profile, not raw data. That keeps this phase cheaply testable (you can
verify a plan is sensible without needing real chart-rendering or execution
code yet) and keeps execution logic in exactly one place later, rather than
scattered through planning decisions.

Note: this does not yet replace the older app/planner.py that main.py
currently uses live — that swap happens in the wiring phase, at which point
the older module's duplicate title/aggregation logic gets retired rather
than maintained in two places.
"""
from dataclasses import dataclass, field

from app.understanding import DatasetProfile


# ============================================================
# Visualization Planner
# ============================================================

def choose_chart_type(analysis_type: str, cardinality: int = None) -> str:
    """Rule-based chart type selection."""
    if analysis_type == "trend":
        return "line"
    if analysis_type == "histogram":
        return "histogram"
    if analysis_type == "outlier":
        return "boxplot"
    if analysis_type == "correlation":
        return "scatter"
    if analysis_type == "correlation_matrix":
        return "heatmap"
    if analysis_type in ("distribution_count", "distribution_sum"):
        if cardinality is not None and cardinality > 15:
            return "treemap"
        if analysis_type == "distribution_count" and cardinality is not None and cardinality <= 6:
            return "donut"
        return "horizontal_bar"
    return "bar"


# ============================================================
# Analysis Planner
# ============================================================

# Domain-aware titles for dimension-based analyses.
DIMENSION_ROLE_TITLES = {
    "CONDITION":      {"default": "Patient Distribution by {col}"},
    "HOSPITAL":       {"default": "Patient Count by {col}"},
    "INSURANCE":      {"default": "Insurance Distribution by {col}"},
    "ADMISSION_TYPE": {"default": "Admission Type Distribution"},
    "MEDICATION":     {"default": "Medication Frequency"},
    "TEST_RESULT":    {"default": "Test Result Distribution"},
    "GENDER":         {"default": "Gender Distribution"},
    "DEMOGRAPHIC":    {"default": "{col} Distribution"},
    "DEPARTMENT":     {"default": "Department Distribution"},
    "JOB_TITLE":      {"default": "Job Title Distribution"},
    "VEHICLE":        {"default": "Vehicle Type Distribution"},
    "ROOM":           {"default": "Room Distribution"},
    "SUBJECT":        {"default": "{col} Distribution"},
    "CATEGORY":       {"sales": "{col} Breakdown", "default": "{col} Distribution"},
    "LOCATION":       {"sales": "{col} Breakdown", "default": "{col} Distribution"},
}

# NOTE: domain-specific headline dimension weighting used to live here as a
# DOMAIN_HEADLINE_DIMENSIONS dict, keyed by domain string. That's exactly the
# kind of scattered domain logic the plugin architecture (app/analyzers/)
# exists to eliminate — this module no longer knows what "healthcare" or
# "sales" means at all. Each domain analyzer plugin now supplies its own
# headline_dimension_roles directly as a parameter to plan_analyses().

IMPORTANCE_BASE = {
    "trend": 85,
    "distribution_count": 75,   # the entity itself — what this domain is actually about
    "distribution_sum": 55,     # the metric's breakdown by entity — supporting, not primary
    "pivot": 45,                # a single dimension's breakdown, crossed with a second one
    "histogram": 50,
    "correlation_matrix": 40,
    "correlation": 35,
    "outlier": 30,
}
HEADLINE_BOOST = 20

TYPE_TO_SECTION = {
    "trend": "Trends",
    "distribution_count": "Distributions",
    "distribution_sum": "Distributions",
    "pivot": "Relationships",
    "histogram": "Distributions",
    "correlation": "Relationships",
    "correlation_matrix": "Correlations",
    "outlier": "Outliers",
}

MIN_CORRELATION_PAIR_INTEREST = 2  # need at least this many measures to bother with pairwise specs


def _title_for(role: str, col: str, domain: str, table: dict) -> str:
    templates = table.get(role, {})
    return templates.get(domain, templates.get("default", "{col} Distribution")).format(col=col)


def _slug(text: str) -> str:
    return text.lower().replace(" ", "_").replace("/", "_")


@dataclass
class AnalysisSpec:
    id: str
    title: str
    type: str            # trend | histogram | distribution_count | distribution_sum | correlation | correlation_matrix | outlier | pivot
    chart_type: str       # line | histogram | horizontal_bar | donut | treemap | scatter | heatmap | boxplot
    section: str          # Trends | Distributions | Relationships | Correlations | Outliers
    importance: int
    column: str = None
    column2: str = None   # second dimension, for pivot only
    metric_column: str = None
    metric_columns: list = field(default_factory=list)  # for correlation_matrix (3+ measures)
    date_column: str = None
    aggregation: str = None
    reasoning: str = ""


def plan_analyses(profile: DatasetProfile, headline_roles: set = None) -> list:
    specs = []
    primary = profile.primary_measure
    domain = profile.domain
    headline_roles = headline_roles or set()

    # --- Trend: primary measure over time ---
    if primary and profile.date_column:
        specs.append(AnalysisSpec(
            id="trend_" + _slug(primary.column),
            title=f"{primary.column} Trend",
            type="trend",
            chart_type=choose_chart_type("trend"),
            section=TYPE_TO_SECTION["trend"],
            importance=IMPORTANCE_BASE["trend"],
            metric_column=primary.column,
            date_column=profile.date_column,
            aggregation=primary.aggregation,
            reasoning=f"{primary.column} has a time dimension ({profile.date_column}) — "
                      f"trends over time are clearest as a line, not a bar.",
        ))

    # --- Histogram: every measure's own distribution ---
    for m in profile.measures:
        specs.append(AnalysisSpec(
            id="hist_" + _slug(m.column),
            title=f"{m.column} Distribution",
            type="histogram",
            chart_type=choose_chart_type("histogram"),
            section=TYPE_TO_SECTION["histogram"],
            importance=IMPORTANCE_BASE["histogram"] + (10 if m.is_primary else 0),
            metric_column=m.column,
            aggregation=m.aggregation,
            reasoning=f"Shows the spread of {m.column}, not just its average — a histogram reveals "
                      f"shape and skew that a single summary number would hide.",
        ))

    # --- Outlier check: primary measure, boxplot ---
    if primary:
        specs.append(AnalysisSpec(
            id="outlier_" + _slug(primary.column),
            title=f"{primary.column} Outliers",
            type="outlier",
            chart_type=choose_chart_type("outlier"),
            section=TYPE_TO_SECTION["outlier"],
            importance=IMPORTANCE_BASE["outlier"],
            metric_column=primary.column,
            reasoning=f"Checks whether a small number of extreme {primary.column} values are "
                      f"skewing totals and averages — a box plot shows this at a glance.",
        ))

    # --- Correlation: every pair of measures ---
    if len(profile.measures) >= MIN_CORRELATION_PAIR_INTEREST:
        chartable_dims = [d for d in profile.dimensions if d.is_chartable and d.cardinality <= 8]
        color_dim = next((d for d in chartable_dims if d.role in headline_roles), None) or (chartable_dims[0] if chartable_dims else None)
        for i, m1 in enumerate(profile.measures):
            for m2 in profile.measures[i + 1:]:
                specs.append(AnalysisSpec(
                    id="corr_" + _slug(m1.column) + "_" + _slug(m2.column),
                    title=f"{m1.column} vs {m2.column}",
                    type="correlation",
                    chart_type=choose_chart_type("correlation"),
                    section=TYPE_TO_SECTION["correlation"],
                    importance=IMPORTANCE_BASE["correlation"],
                    metric_columns=[m1.column, m2.column],
                    column=color_dim.column if color_dim else None,
                    reasoning=f"{m1.column} and {m2.column} are both numeric — a scatter plot is the "
                              f"clearest way to see whether they move together"
                              + (f", colored by {color_dim.column} to check whether the relationship "
                                 f"differs across groups." if color_dim else "."),
                ))

    # --- Correlation matrix: heatmap across all measures, if 3+ ---
    if len(profile.measures) >= 3:
        specs.append(AnalysisSpec(
            id="corr_matrix",
            title="Measure Correlations",
            type="correlation_matrix",
            chart_type=choose_chart_type("correlation_matrix"),
            section=TYPE_TO_SECTION["correlation_matrix"],
            importance=IMPORTANCE_BASE["correlation_matrix"],
            metric_columns=[m.column for m in profile.measures],
            reasoning=f"Comparing relationships across all {len(profile.measures)} numeric measures at "
                      f"once — a heatmap surfaces patterns a list of individual scatter plots would hide.",
        ))

    # --- Distributions: every chartable dimension ---
    for d in profile.dimensions:
        if not d.is_chartable:
            continue
        is_headline = d.role in headline_roles
        boost = HEADLINE_BOOST if is_headline else 0

        title = _title_for(d.role, d.column, domain, DIMENSION_ROLE_TITLES)
        count_chart_type = choose_chart_type("distribution_count", d.cardinality)
        count_reason_shape = {
            "donut": f"{d.column} has only {d.cardinality} distinct values — a donut chart reads composition clearly at that size.",
            "treemap": f"{d.column} has {d.cardinality} distinct values — too many for a pie/bar to stay readable, so a treemap groups them by size instead.",
            "horizontal_bar": f"{d.column} has {d.cardinality} categories — a horizontal bar makes them easy to rank and read.",
        }.get(count_chart_type, f"{d.column} is a categorical dimension worth breaking down.")
        headline_note = " It's also the headline dimension for this domain." if is_headline else ""

        specs.append(AnalysisSpec(
            id="count_" + _slug(d.column),
            title=title,
            type="distribution_count",
            chart_type=count_chart_type,
            section=TYPE_TO_SECTION["distribution_count"],
            importance=IMPORTANCE_BASE["distribution_count"] + boost,
            column=d.column,
            reasoning=count_reason_shape + headline_note,
        ))

        if primary and d.column != primary.column:
            verb = "Average" if primary.aggregation == "avg" else "Total"
            specs.append(AnalysisSpec(
                id="sum_" + _slug(d.column),
                title=f"{verb} {primary.column} by {d.column}",
                type="distribution_sum",
                chart_type=choose_chart_type("distribution_sum", d.cardinality),
                section=TYPE_TO_SECTION["distribution_sum"],
                importance=IMPORTANCE_BASE["distribution_sum"] + boost,
                column=d.column,
                metric_column=primary.column,
                aggregation=primary.aggregation,
                reasoning=f"Ranks {d.column} groups by {verb.lower()} {primary.column} — a horizontal "
                          f"bar makes the ranking easy to read at a glance, unlike a raw table.",
            ))

    # --- Pivot: primary measure across the intersection of the two best
    # dimensions. A single dimension's breakdown can hide a pattern that
    # only shows up when two categories are crossed (e.g. discounts might
    # look fine on average per-Region and per-Category separately, but
    # one specific Region+Category combination could be the real problem).
    # Only ONE pivot is planned, same philosophy as correlation_matrix —
    # this is a deep-dive view, not a per-dimension loop.
    pivot_candidates = [d for d in profile.dimensions if d.is_chartable and 2 <= d.cardinality <= 10]
    if primary and len(pivot_candidates) >= 2:
        # Headline dimensions first (most meaningful cross-cut for this
        # domain), then lowest cardinality (keeps the grid compact).
        pivot_candidates.sort(key=lambda d: (d.role not in headline_roles, d.cardinality))
        dim1, dim2 = pivot_candidates[0], pivot_candidates[1]
        verb = "Average" if primary.aggregation == "avg" else "Total"
        specs.append(AnalysisSpec(
            id="pivot_" + _slug(dim1.column) + "_" + _slug(dim2.column),
            title=f"{primary.column} by {dim1.column} & {dim2.column}",
            type="pivot",
            chart_type="heatmap",
            section=TYPE_TO_SECTION["pivot"],
            importance=IMPORTANCE_BASE["pivot"],
            column=dim1.column,
            column2=dim2.column,
            metric_column=primary.column,
            aggregation=primary.aggregation,
            reasoning=f"{verb} {primary.column} broken down by {dim1.column} AND {dim2.column} together — "
                      f"a single dimension's breakdown can hide a pattern that only shows up when two "
                      f"categories are crossed.",
        ))

    return specs


def top_n(specs: list, n: int = 3) -> list:
    """
    The '3 most important analyses' for the Executive Summary / Intelligent
    Dashboard. Greedy selection by importance, with only ONE constraint:
    never repeat the same underlying column/subject twice — that's what
    stops "Total Billing Amount by Medical Condition" and "Patient
    Distribution by Medical Condition" both winning purely because Medical
    Condition is the headline dimension.

    Earlier this also enforced TYPE diversity (no two distribution_count
    entries at all), which sounds reasonable but actively fights against
    entity-heavy domains — a healthcare dataset's two most important facts
    are often "Patient Distribution by Medical Condition" AND "Admission
    Type Distribution", both legitimately distribution_count, both about
    completely different columns. Blocking the second one in favor of a
    weaker trend analysis was a real regression, caught by testing.
    """
    ranked = sorted(specs, key=lambda s: s.importance, reverse=True)
    chosen = []
    seen_subjects = set()
    type_counts = {}
    max_per_type = max(1, (n + 1) // 2)  # e.g. 2 for n=3 — allows a domain's
    # entity distributions to take 2 of 3 slots without shutting a trend or
    # other type out of the dashboard entirely

    def subject_of(spec):
        return spec.column or spec.metric_column or tuple(spec.metric_columns or [])

    for spec in ranked:
        if len(chosen) >= n:
            break
        subject = subject_of(spec)
        if subject in seen_subjects or type_counts.get(spec.type, 0) >= max_per_type:
            continue
        chosen.append(spec)
        seen_subjects.add(subject)
        type_counts[spec.type] = type_counts.get(spec.type, 0) + 1

    if len(chosen) < n:
        for spec in ranked:
            if spec in chosen:
                continue
            chosen.append(spec)
            if len(chosen) >= n:
                break

    return chosen
