"""
Domain detection regression tests.

Each of the 11 domains should be detected correctly on a dataset with
that domain's distinctive columns, and -- just as importantly -- should
NOT light up on datasets belonging to a different domain. The
domains.py module has its own documented history of a false-positive
("Titanic" example in its docstring); these tests exist so the next
false positive gets caught here, not in production.
"""
from app.domains import detect_domain
from app.semantic_roles import classify_columns
from app.main import _run_v2_pipeline


def _detected_domain(df):
    roles = classify_columns(df)
    return detect_domain(roles)


def test_sales_domain_detected(sales_df):
    result = _detected_domain(sales_df)
    assert result["domain"] == "sales"


def test_healthcare_domain_detected(healthcare_df):
    result = _detected_domain(healthcare_df)
    assert result["domain"] == "healthcare"


def test_real_estate_domain_detected(real_estate_df):
    result = _detected_domain(real_estate_df)
    assert result["domain"] == "real_estate"


def test_saas_domain_detected(saas_df):
    result = _detected_domain(saas_df)
    assert result["domain"] == "saas"


def test_real_estate_dominates_incidental_overlap(real_estate_df):
    """Regression guard for the exact failure mode domains.py's own
    docstring warns about: an unrelated domain outscoring or coming
    close to the correct one due to an overly generic keyword. Some
    small incidental overlap in a legitimately shared role is fine and
    expected -- the bar is that the correct domain wins clearly, not
    that every other domain scores exactly zero."""
    result = _detected_domain(real_estate_df)
    assert result["domain"] == "real_estate"
    other_scores = [v for k, v in result["scores"].items() if k != "real_estate"]
    assert result["scores"]["real_estate"] > 2 * max(other_scores, default=0)


def test_saas_dominates_incidental_overlap(saas_df):
    """Same guard for saas -- a Customer ID column legitimately overlaps
    with sales' CUSTOMER signal, so some incidental score there is
    expected; saas should still win by a clear margin."""
    result = _detected_domain(saas_df)
    assert result["domain"] == "saas"
    other_scores = [v for k, v in result["scores"].items() if k != "saas"]
    assert result["scores"]["saas"] > 2 * max(other_scores, default=0)


def test_full_pipeline_resolves_correct_analyzer_for_new_domains(real_estate_df, saas_df):
    """End-to-end: the new domains should route through their own
    analyzer (not silently fall back to generic), evidenced by their
    domain-specific key_kpis showing up in the profile."""
    re_result = _run_v2_pipeline(real_estate_df)
    assert re_result["profile"]["domain"] == "real_estate"
    assert "Days on Market" in re_result["profile"]["key_kpis"]

    saas_result = _run_v2_pipeline(saas_df)
    assert saas_result["profile"]["domain"] == "saas"
    assert "MRR" in saas_result["profile"]["key_kpis"]
