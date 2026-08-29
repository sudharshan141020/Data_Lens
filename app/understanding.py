"""
Dataset Understanding Engine.

This is the new foundation layer: instead of the rest of the app each
re-deriving "what's the metric, what's chartable" in their own way (which is
exactly the duplication the redesign brief calls out), everything downstream
— the analysis planner, visualization planner, insight engine, weak-point
detector — should consume ONE structured DatasetProfile produced here.

Builds directly on the existing semantic_roles.classify_columns() and
domains.detect_domain() — this phase does not throw that work away, it
gives it a proper home and a richer output shape (an entity name, a full
list of measures instead of just one, a full list of dimensions) instead of
the narrower "primary_metric_col" the old planner used.
"""
from dataclasses import dataclass, field
import pandas as pd

from app.semantic_roles import classify_columns
from app.domains import detect_domain

# Roles that represent "what each row is about" — the primary entity.
ENTITY_ROLE_TO_NOUN = {
    "PATIENT": "Patient",
    "CUSTOMER": "Customer",
    "STUDENT": "Student",
    "EMPLOYEE": "Employee",
    "DRIVER": "Driver",
}

# Fallback when no column explicitly matched an entity role — a healthcare
# file's rows are patients by definition of the domain, even if the
# identity column happened to just be called "Name" rather than
# "Patient Name". This only kicks in once the domain itself is confidently
# known, so it never overrides genuine "generic" datasets with a guess.
DOMAIN_DEFAULT_ENTITY = {
    "healthcare": "Patient",
    "sales": "Customer",
    "education": "Student",
    "hr": "Employee",
    "finance": "Account",
}

# Roles that represent something worth measuring/aggregating numerically,
# with the aggregation that's actually meaningful for that role. This is the
# single canonical source for aggregation rules — nothing else in the
# codebase should redefine "sum vs avg" independently.
MEASURE_ROLES = {
    "FINANCIAL_METRIC": "sum",
    "PROFIT": "sum",
    "DISCOUNT": "avg",
    "AGE": "avg",
    "SCORE": "avg",
    "ATTENDANCE": "avg",
    "LENGTH_OF_STAY": "avg",
    "TENURE": "avg",
    "CONGESTION": "avg",
    "ACCIDENT": "sum",
    "SPEED": "avg",
    "INVENTORY_LEVEL": "sum",
    "REORDER_POINT": "avg",
    "UNIT_COST": "avg",
    "DEFECT_RATE": "avg",
    "DOWNTIME": "sum",
    "UNITS_PRODUCED": "sum",
    "IMPRESSIONS": "sum",
    "CLICKS": "sum",
    "CTR": "avg",
    "CONVERSION_RATE": "avg",
    "CPC": "avg",
    "ROAS": "avg",
    "AD_SPEND": "sum",
}

# Roles that represent a "slice by this" dimension.
DIMENSION_ROLES = {
    "CONDITION", "HOSPITAL", "INSURANCE", "MEDICATION", "TEST_RESULT",
    "ADMISSION_TYPE", "GENDER", "DEMOGRAPHIC", "DEPARTMENT", "JOB_TITLE",
    "VEHICLE", "ROOM", "SUBJECT", "CATEGORY", "LOCATION",
    "STORE", "SUPPLIER", "WAREHOUSE",
    "MACHINE", "SHIFT", "PRODUCTION_LINE",
    "CAMPAIGN", "CHANNEL",
}


@dataclass
class Measure:
    column: str
    role: str
    aggregation: str  # "sum" | "avg"
    is_primary: bool = False


@dataclass
class Dimension:
    column: str
    role: str
    cardinality: int
    is_chartable: bool = True


@dataclass
class DatasetProfile:
    domain: str
    domain_confidence: float
    primary_entity: str          # human noun, e.g. "Patient", or "Record" if unknown
    row_count: int
    column_count: int
    data_completeness_pct: float
    date_column: str | None
    measures: list = field(default_factory=list)      # list[Measure]
    dimensions: list = field(default_factory=list)     # list[Dimension]
    semantic_roles: dict = field(default_factory=dict)  # column -> role, for transparency/debugging

    @property
    def primary_measure(self):
        """The single headline measure, if any — FINANCIAL_METRIC wins if present,
        otherwise the first measure found. Kept for backward compatibility with
        code that only needs one metric; new code should prefer `measures`."""
        for m in self.measures:
            if m.is_primary:
                return m
        return self.measures[0] if self.measures else None


def _is_chartable(cardinality: int, row_count: int) -> bool:
    return 2 <= cardinality <= min(30, max(row_count * 0.5, 2))


MIN_NONNULL_FRACTION_FOR_ANALYSIS = 0.10  # require at least 10% real values...
MIN_NONNULL_COUNT_FOR_ANALYSIS = 5        # ...and at least 5 real values regardless of dataset size


def _is_usable_column(df: pd.DataFrame, col: str) -> bool:
    """A column that's almost entirely empty can't meaningfully be "the
    metric" or "the breakdown" for any analysis, even if its name matches a
    known semantic role -- e.g. a column named "Sales" that's 99.9% NaN
    (a handful of stray values left over from a pasted-in summary table,
    say) shouldn't get treated the same as a real, populated Sales column.
    Same category of guard as the existing identifier-column exclusion:
    role classification is name-based and doesn't know how much real data
    backs the column, so this is checked separately, after the fact."""
    non_null = int(df[col].notna().sum())
    if non_null < MIN_NONNULL_COUNT_FOR_ANALYSIS:
        return False
    if len(df) and (non_null / len(df)) < MIN_NONNULL_FRACTION_FOR_ANALYSIS:
        return False
    return True


def understand_dataset(df: pd.DataFrame) -> DatasetProfile:
    """
    The single entry point for the entire downstream pipeline. Everything
    else (analysis planner, insight engine, weak-point detector) should take
    a DatasetProfile as input rather than re-deriving roles from a raw
    dataframe.
    """
    semantic_roles = classify_columns(df)
    # Domain scoring only considers columns with enough real data to matter --
    # otherwise a column that's 97% empty but happens to be named e.g.
    # "diagnosis" can swing the entire dataset's domain classification to
    # "healthcare" at full confidence off a handful of stray values. The
    # full (unfiltered) semantic_roles dict is still used for everything
    # else below -- this filtering is specific to domain detection.
    domain_scoring_roles = {c: info for c, info in semantic_roles.items() if _is_usable_column(df, c)}
    domain_result = detect_domain(domain_scoring_roles)
    numeric_cols = set(df.select_dtypes(include="number").columns)

    row_count = int(len(df))
    col_count = int(len(df.columns))
    missing_frac = df.isnull().mean().mean() if col_count else 0
    completeness = float(round((1 - missing_frac) * 100, 1))

    date_column = next((c for c, info in semantic_roles.items() if info["role"] == "DATE"), None)

    # --- Entity ---
    entity_role = next((info["role"] for info in semantic_roles.values() if info["role"] in ENTITY_ROLE_TO_NOUN), None)
    if entity_role:
        primary_entity = ENTITY_ROLE_TO_NOUN[entity_role]
    elif domain_result["domain"] in DOMAIN_DEFAULT_ENTITY:
        primary_entity = DOMAIN_DEFAULT_ENTITY[domain_result["domain"]]
    else:
        primary_entity = "Record"

    # --- Measures ---
    measures = []
    primary_set = False
    # FINANCIAL_METRIC always gets first shot at being primary, if present
    ordered_roles = ["FINANCIAL_METRIC"] + [r for r in MEASURE_ROLES if r != "FINANCIAL_METRIC"]
    for role in ordered_roles:
        for col, info in semantic_roles.items():
            if info["role"] == role and col in numeric_cols and _is_usable_column(df, col):
                is_primary = not primary_set
                measures.append(Measure(column=col, role=role, aggregation=MEASURE_ROLES[role], is_primary=is_primary))
                if is_primary:
                    primary_set = True

    # Fallback: any numeric column with real, usable data that didn't match
    # one of the named roles above still deserves to be a measure -- e.g.
    # a role like QUANTITY isn't in MEASURE_ROLES (it's excluded from
    # DIMENSION_ROLES too, as a count rather than a category), so without
    # this it's silently unusable as either, no matter how legitimate the
    # data is. Same story for any role classify_columns() falls back to by
    # dtype alone (GENERIC_NUMERIC) on datasets with no domain-specific
    # column names to match. Defaults to "sum", the aggregation most of
    # the named roles above already use. IDENTIFIER-role columns are
    # still excluded here -- a sequential ID isn't a real measure either
    # way (see the existing PassengerId-as-revenue caution in HANDOFF.md).
    claimed = {m.column for m in measures}
    for col, info in semantic_roles.items():
        if col in claimed or col not in numeric_cols:
            continue
        if info["role"] == "IDENTIFIER":
            continue
        if not _is_usable_column(df, col):
            continue
        is_primary = not primary_set
        measures.append(Measure(column=col, role=info["role"], aggregation="sum", is_primary=is_primary))
        if is_primary:
            primary_set = True

    # --- Dimensions ---
    dimensions = []
    for col, info in semantic_roles.items():
        role = info["role"]
        if role not in DIMENSION_ROLES:
            continue
        if not _is_usable_column(df, col):
            continue
        cardinality = int(df[col].nunique())
        dimensions.append(Dimension(
            column=col,
            role=role,
            cardinality=cardinality,
            is_chartable=_is_chartable(cardinality, row_count),
        ))

    return DatasetProfile(
        domain=domain_result["domain"],
        domain_confidence=domain_result["confidence"],
        primary_entity=primary_entity,
        row_count=row_count,
        column_count=col_count,
        data_completeness_pct=completeness,
        date_column=date_column,
        measures=measures,
        dimensions=dimensions,
        semantic_roles={c: info["role"] for c, info in semantic_roles.items()},
    )
