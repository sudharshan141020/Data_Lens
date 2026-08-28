"""
Phase 2 — Domain detection.

Takes the per-column semantic roles produced by semantic_roles.classify_columns()
and scores which domain the dataset most likely belongs to. This module knows
nothing about column names or dataframes directly — it only ever looks at the
ROLE labels Phase 1 already assigned, which is what keeps the two phases
cleanly separable (and testable independently, per the phased-build plan).

Adding a new domain later means adding one new entry to DOMAIN_SIGNALS —
nothing else in this file, or in semantic_roles.py, needs to change.
"""
from collections import Counter

# domain -> {semantic_role: weight}
# IMPORTANT: only roles that are genuinely DISTINCTIVE of a domain belong
# here. CATEGORY, QUANTITY, and FINANCIAL_METRIC were deliberately left out
# after testing — they show up across nearly every domain (a healthcare
# file has "categories" too, a traffic file has "quantities" too), so
# including them let unrelated datasets accumulate enough incidental score
# to falsely claim a domain. A real test case caught this: Titanic scored
# as "sales" purely from 3 incidental CATEGORY columns + 2 QUANTITY columns,
# despite having zero PRODUCT, DISCOUNT, or CUSTOMER signal — the roles that
# actually mean something for "sales."
DOMAIN_SIGNALS = {
    "healthcare": {
        "CONDITION": 3, "HOSPITAL": 3, "MEDICATION": 3, "TEST_RESULT": 3,
        "ADMISSION_TYPE": 2, "INSURANCE": 2, "PATIENT": 2, "DOCTOR": 2,
        "NURSE": 2, "ROOM": 1, "LENGTH_OF_STAY": 1,
    },
    "sales": {
        "PRODUCT": 3, "DISCOUNT": 3, "CUSTOMER": 2,
    },
    "retail": {
        "INVENTORY_LEVEL": 3, "REORDER_POINT": 3, "SUPPLIER": 3,
        "STORE": 2, "WAREHOUSE": 2, "UNIT_COST": 2,
    },
    "manufacturing": {
        "DEFECT_RATE": 3, "DOWNTIME": 3, "MACHINE": 2,
        "PRODUCTION_LINE": 2, "UNITS_PRODUCED": 2, "SHIFT": 1,
    },
    "education": {
        "SUBJECT": 3, "SCORE": 3, "ATTENDANCE": 2, "STUDENT": 2, "TEACHER": 2,
    },
    "hr": {
        "EMPLOYEE": 3, "DEPARTMENT": 2, "JOB_TITLE": 2, "TENURE": 2,
    },
    "finance": {
        "ACCOUNT": 3, "INTEREST_RATE": 3, "LOAN": 3,
    },
    "traffic": {
        "VEHICLE": 3, "ACCIDENT": 2, "CONGESTION": 2, "SPEED": 1, "DRIVER": 1,
    },
}

# A domain needs at least this much weighted signal to be claimed at all —
# stops a single incidental role match from confidently mislabeling a
# generic file.
MIN_SCORE_THRESHOLD = 3


def detect_domain(column_roles: dict) -> dict:
    """
    column_roles: the dict returned by semantic_roles.classify_columns()
    Returns: {
        "domain": str,              # winning domain, or "generic"
        "confidence": float,        # 0-1, share of total weighted signal
        "scores": {domain: score, ...},  # raw score per domain, for transparency
    }
    """
    role_counts = Counter(info["role"] for info in column_roles.values())

    scores = {}
    for domain, weights in DOMAIN_SIGNALS.items():
        scores[domain] = sum(role_counts.get(role, 0) * weight for role, weight in weights.items())

    best_domain = max(scores, key=scores.get)
    best_score = scores[best_domain]

    if best_score < MIN_SCORE_THRESHOLD:
        return {"domain": "generic", "confidence": 0.0, "scores": scores}

    total_signal = sum(scores.values()) or 1
    confidence = round(best_score / total_signal, 2)

    return {"domain": best_domain, "confidence": confidence, "scores": scores}
