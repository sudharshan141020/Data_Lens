"""app.hypothesis -- the A/B / hypothesis-test mode.

Three layers of checking, because a wrong p-value that looks plausible is the
worst failure a statistics feature can have:
  1. every number is compared with scipy or a hand calculation;
  2. calibration: with NO real difference about 5% of tests must come out
     "significant", and with a real difference most must (a miswired p-value
     fails this even when each unit test passes);
  3. the words: the verdict must name the right group as higher, say the right
     thing for "no clear difference", and not overclaim."""
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.hypothesis import (run_hypothesis_test, _choose_numeric_test, _welch_interval, _hedges_d,
                            _newcombe_diff, _wilson, _label_d, _label_r)
from app.period_comparison import _welch_t_test


def _run(a, b, kind="auto", **kw):
    groups = ["A"] * len(a) + ["B"] * len(b)
    return run_hypothesis_test(groups, list(a) + list(b), "A", "B", "Arm", "Score", outcome_kind=kind, **kw)


def _rng(seed=0):
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# numeric outcome: numbers
# ---------------------------------------------------------------------------
def test_welch_p_value_is_the_one_period_comparison_already_uses():
    r = _rng(1)
    a, b = r.normal(100, 15, 60), r.normal(108, 15, 70)
    res = _run(a, b)
    assert res["test"]["id"] == "welch_t"
    assert res["p_value"] == pytest.approx(_welch_t_test(a, b))
    assert res["p_value"] == pytest.approx(stats.ttest_ind(b, a, equal_var=False).pvalue)


def test_welch_interval_matches_scipy_exactly():
    r = _rng(2)
    a, b = r.normal(0, 1, 40), r.normal(0.5, 2, 45)
    diff, lo, hi, df = _welch_interval(a, b)
    ref = stats.ttest_ind(b, a, equal_var=False)
    ci = ref.confidence_interval(0.95)
    assert (lo, hi) == pytest.approx((ci.low, ci.high))
    assert df == pytest.approx(ref.df)
    assert diff == pytest.approx(b.mean() - a.mean())


def test_direction_is_b_minus_a_everywhere():
    a, b = _rng(3).normal(10, 2, 50), _rng(4).normal(14, 2, 50)
    res = _run(a, b)
    assert res["difference"] > 0 and res["interval"][0] > 0
    assert res["effect_size"]["value"] > 0
    flipped = _run(b, a)
    assert flipped["difference"] < 0 and flipped["effect_size"]["value"] < 0


def test_hedges_d_recovers_a_known_effect_size():
    r = _rng(5)
    a, b = r.normal(0, 1, 5000), r.normal(0.5, 1, 5000)
    assert _hedges_d(a, b) == pytest.approx(0.5, abs=0.05)
    assert _hedges_d(a, a.copy()) == 0.0


def test_effect_size_uses_the_average_variance_so_unequal_spread_does_not_distort_it():
    a, b = np.array([0.0, 2.0, 4.0, 6.0, 8.0] * 8), np.array([2.0, 4.0, 6.0, 8.0, 10.0] * 8)
    manual = (b.mean() - a.mean()) / math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    assert _hedges_d(a, b) == pytest.approx(manual * (1 - 3 / (4 * 80 - 9)))


def test_effect_size_labels_use_the_conventional_cut_offs():
    assert [_label_d(x) for x in (0.1, 0.3, 0.6, 1.2)] == ["negligible", "small", "medium", "large"]
    assert [_label_r(x) for x in (0.05, 0.2, 0.4, 0.7)] == ["negligible", "small", "medium", "large"]
    assert _label_d(-0.6) == "medium"


# ---------------------------------------------------------------------------
# numeric outcome: choosing the test
# ---------------------------------------------------------------------------
def test_large_groups_get_welch_regardless_of_skew():
    r = _rng(6)
    a, b = r.lognormal(3, 1.2, 200), r.lognormal(3.1, 1.2, 200)
    assert _run(a, b)["test"]["id"] == "welch_t"


def test_small_non_normal_groups_get_mann_whitney_and_the_reason_says_why():
    r = _rng(7)
    a, b = r.lognormal(0, 1.5, 12), r.lognormal(1, 1.5, 12)
    res = _run(a, b)
    assert res["test"]["id"] == "mann_whitney"
    assert "fewer than 30 rows" in res["test"]["why"] and "normally distributed" in res["test"]["why"]
    assert res["p_value"] == pytest.approx(stats.mannwhitneyu(b, a, alternative="two-sided").pvalue)


def test_small_roughly_normal_groups_still_get_welch():
    r = _rng(8)
    a, b = r.normal(50, 5, 15), r.normal(55, 5, 15)
    res = _run(a, b)
    assert res["test"]["id"] == "welch_t" and "roughly normal" in res["test"]["why"]


def test_mann_whitney_effect_size_and_probability_of_superiority_are_consistent():
    r = _rng(9)
    a, b = r.lognormal(0, 1.5, 14), r.lognormal(1.5, 1.5, 14)
    res = _run(a, b)
    assert res["test"]["id"] == "mann_whitney"
    brute = np.mean([(y > x) + 0.5 * (y == x) for x in a for y in b])
    assert res["prob_b_higher"] == pytest.approx(brute)
    assert res["effect_size"]["value"] == pytest.approx(2 * brute - 1)
    assert res["difference"] == pytest.approx(np.median(b) - np.median(a))


def test_bootstrap_interval_is_deterministic_and_brackets_the_median_difference():
    r = _rng(10)
    a, b = r.lognormal(0, 1.2, 14), r.lognormal(1, 1.2, 14)
    one, two = _run(a, b), _run(a, b)
    assert one["interval"] == two["interval"]
    lo, hi = one["interval"]
    assert lo < one["difference"] < hi


def test_the_other_test_is_always_run_as_a_cross_check_and_disagreement_is_surfaced():
    # A real shift of about half a standard deviation, plus ONE huge value in B. The outlier inflates
    # the variance enough that the t-test no longer sees the shift, while the rank test still does.
    r = _rng(11)
    a = r.normal(100, 10, 100)
    b = np.append(r.normal(105, 10, 99), 3000.0)
    res = _run(a, b)
    assert res["test"]["id"] == "welch_t"
    assert res["cross_check"]["test"] == "Mann-Whitney U"
    assert res["cross_check"]["p_value"] == pytest.approx(stats.mannwhitneyu(b, a, alternative="two-sided").pvalue)
    assert res["significant"] is False and res["cross_check"]["p_value"] < 0.05
    assert res["cross_check"]["agrees"] is False
    assert "cross-check" in res["caveats"][0] and "extreme values" in res["caveats"][0]


def test_agreeing_tests_add_no_disagreement_caveat():
    r = _rng(12)
    res = _run(r.normal(0, 1, 100), r.normal(1, 1, 100))
    assert res["cross_check"]["agrees"] is True
    assert not any("cross-check" in c for c in res["caveats"])


# ---------------------------------------------------------------------------
# categorical outcome
# ---------------------------------------------------------------------------
def _binary(k_a, n_a, k_b, n_b, yes="Yes", no="No"):
    groups = ["A"] * n_a + ["B"] * n_b
    outcomes = [yes] * k_a + [no] * (n_a - k_a) + [yes] * k_b + [no] * (n_b - k_b)
    return run_hypothesis_test(groups, outcomes, "A", "B", "Arm", "Converted")


def test_2x2_chi_square_matches_scipy_and_reports_rates_difference_and_relative_risk():
    res = _binary(80, 400, 120, 400)
    assert res["test"]["id"] == "chi_square"
    ref = stats.chi2_contingency([[80, 320], [120, 280]], correction=False)
    assert res["p_value"] == pytest.approx(ref[1])
    assert res["rate"] == {"A": 0.2, "B": 0.3}
    assert res["difference"] == pytest.approx(0.1)
    assert res["relative_risk"] == pytest.approx(1.5)
    assert res["positive_level"] == "Yes"          # sorted last of ["No", "Yes"]
    assert res["effect_size"]["value"] == pytest.approx(math.sqrt(ref[0] / 800))


def test_small_expected_counts_switch_a_2x2_to_fishers_exact():
    res = _binary(1, 10, 6, 10)                      # expected count for "Yes" in a group is 3.5
    assert res["test"]["id"] == "fisher_exact" and "expected count below 5" in res["test"]["why"]
    assert res["p_value"] == pytest.approx(stats.fisher_exact([[1, 9], [6, 4]])[1])
    # and just above the line, the chi-square approximation is trusted again
    assert _binary(2, 12, 9, 14)["test"]["id"] == "chi_square"


def test_newcombe_interval_stays_inside_minus_one_to_one_and_covers_the_difference():
    for k1, n1, k2, n2 in [(0, 30, 5, 30), (30, 30, 25, 30), (10, 100, 20, 100), (1, 10, 9, 10)]:
        lo, hi = _newcombe_diff(k1, n1, k2, n2)
        d = k2 / n2 - k1 / n1
        assert -1 <= lo <= d <= hi <= 1


def test_wilson_interval_matches_a_hand_calculation():
    z = 1.959964
    lo, hi = _wilson(20, 100, z)
    assert (lo, hi) == pytest.approx((0.1338, 0.2889), abs=1e-3)


def test_newcombe_interval_matches_an_independent_calculation_from_scipys_wilson_intervals():
    # Method 10 (hybrid score): built here from scipy's own Wilson intervals, not from app code.
    k1, n1, k2, n2 = 48, 80, 56, 70
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = (getattr(stats.binomtest(k1, n1).proportion_ci(method="wilson"), x) for x in ("low", "high"))
    l2, u2 = (getattr(stats.binomtest(k2, n2).proportion_ci(method="wilson"), x) for x in ("low", "high"))
    expected = ((p2 - p1) - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2),
                (p2 - p1) + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2))
    assert _newcombe_diff(k1, n1, k2, n2) == pytest.approx(expected, abs=1e-6)
    assert expected[0] == pytest.approx(0.0524, abs=1e-3)      # matches the published lower bound for this example


def test_numeric_zero_one_flag_is_treated_as_a_proportion_not_an_average():
    groups = ["A"] * 100 + ["B"] * 100
    outcomes = [1] * 20 + [0] * 80 + [1] * 35 + [0] * 65
    res = run_hypothesis_test(groups, outcomes, "A", "B", "Arm", "Bought")
    assert res["kind"] == "categorical" and res["positive_level"] == "1"
    assert res["rate"] == {"A": 0.2, "B": 0.35}


def test_the_positive_level_can_be_chosen_and_a_multi_level_outcome_collapses_to_it():
    groups = ["A"] * 90 + ["B"] * 90
    outcomes = (["low"] * 30 + ["mid"] * 30 + ["high"] * 30) + (["low"] * 20 + ["mid"] * 30 + ["high"] * 40)
    res = run_hypothesis_test(groups, outcomes, "A", "B", "Arm", "Tier", positive_level="high")
    assert res["rate"]["A"] == pytest.approx(30 / 90) and res["rate"]["B"] == pytest.approx(40 / 90)
    assert res["difference"] == pytest.approx(10 / 90)


def test_multi_level_outcome_uses_cramers_v_and_names_the_biggest_gap():
    groups = ["A"] * 90 + ["B"] * 90
    outcomes = (["low"] * 40 + ["mid"] * 30 + ["high"] * 20) + (["low"] * 10 + ["mid"] * 30 + ["high"] * 50)
    res = run_hypothesis_test(groups, outcomes, "A", "B", "Arm", "Tier")
    ref = stats.chi2_contingency(np.array([[20, 40, 30], [50, 10, 30]]), correction=False)  # columns: high, low, mid
    assert res["test"]["id"] == "chi_square" and res["interval"] is None
    assert res["p_value"] == pytest.approx(ref[1])
    assert res["effect_size"]["value"] == pytest.approx(math.sqrt(ref[0] / 180))
    assert res["biggest_gap"]["level"] in {"low", "high"}
    assert res["significant"] is True and "biggest gap" in res["headline"]


# ---------------------------------------------------------------------------
# verdict wording
# ---------------------------------------------------------------------------
def test_verdict_names_the_higher_group_with_numbers_and_the_effect_size():
    a, b = _rng(20).normal(100, 10, 80), _rng(21).normal(110, 10, 80)
    h = _run(a, b)["headline"]
    assert h.startswith("B has a higher average Score than A")
    assert "unlikely to be chance" in h and "effect is large" in h and "95% interval +" in h
    h2 = _run(b, a)["headline"]
    assert h2.startswith("B has a higher average Score than A") is False and h2.startswith("A has a higher")


def test_a_non_significant_result_says_no_clear_difference_and_what_cannot_be_ruled_out():
    r = _rng(22)
    res = _run(r.normal(100, 20, 25), r.normal(101, 20, 25))
    assert res["significant"] is False
    assert res["headline"].startswith("No clear difference in Score between A and B")
    lo, hi = res["interval"]
    assert f"consistent with a real difference anywhere from" in res["headline"]
    assert lo < 0 < hi
    assert "unlikely to be chance" not in res["headline"]


def test_a_tiny_but_significant_effect_is_called_negligible_not_important():
    r = _rng(23)
    res = _run(r.normal(100, 10, 20000), r.normal(100.6, 10, 20000))
    assert res["significant"] is True and res["effect_size"]["label"] == "negligible"
    assert "effect is negligible" in res["headline"]


def test_proportion_verdict_reads_in_percentage_points():
    h = _binary(80, 400, 120, 400)["headline"]
    assert h.startswith("B has a higher rate of Converted = Yes than A: 30.0% vs 20.0% (+10.0 points")
    assert "95% interval +" in h


def test_every_result_carries_the_standing_caveats_and_a_small_group_warning():
    res = _run(_rng(24).normal(0, 1, 8), _rng(25).normal(0, 1, 8))
    text = " ".join(res["caveats"])
    assert "independent observation" in text and "chose before looking" in text
    assert "not enough data to tell" in text


def test_very_unequal_group_sizes_are_flagged():
    r = _rng(26)
    res = _run(r.normal(0, 1, 400), r.normal(0, 1, 40))
    assert any("very different in size" in c for c in res["caveats"])


# ---------------------------------------------------------------------------
# calibration: the check that catches a miswired p-value
# ---------------------------------------------------------------------------
def test_with_no_real_difference_about_five_percent_of_tests_are_significant():
    r = _rng(100)
    hits = sum(_run(r.normal(0, 1, 50), r.normal(0, 1, 50))["significant"] for _ in range(600))
    assert 0.025 <= hits / 600 <= 0.085


def test_with_a_real_difference_most_tests_find_it_and_none_point_the_wrong_way():
    r = _rng(101)
    results = [_run(r.normal(0, 1, 50), r.normal(0.8, 1, 50)) for _ in range(200)]
    assert sum(x["significant"] for x in results) / 200 > 0.9
    assert all(x["difference"] > 0 for x in results if x["significant"])


def test_proportion_test_is_also_calibrated_under_the_null():
    r = _rng(102)
    hits = 0
    for _ in range(400):
        a, b = int(r.binomial(100, 0.3)), int(r.binomial(100, 0.3))
        hits += _binary(a, 100, b, 100)["significant"]
    assert 0.02 <= hits / 400 <= 0.09


# ---------------------------------------------------------------------------
# input handling
# ---------------------------------------------------------------------------
def test_missing_values_in_either_column_are_dropped_not_counted():
    r = _rng(30)
    a, b = list(r.normal(0, 1, 40)), list(r.normal(1, 1, 40))
    groups = ["A"] * 40 + ["B"] * 40 + [None, "A", "B"]
    outcomes = a + b + [5.0, None, float("nan")]
    res = run_hypothesis_test(groups, outcomes, "A", "B", "Arm", "Score")
    assert res["stats"]["A"]["n"] == 40 and res["stats"]["B"]["n"] == 40


def test_other_groups_in_the_column_are_ignored():
    r = _rng(31)
    groups = ["A"] * 30 + ["B"] * 30 + ["C"] * 30
    res = run_hypothesis_test(groups, list(r.normal(0, 1, 30)) + list(r.normal(1, 1, 30)) + list(r.normal(100, 1, 30)), "A", "B", "Arm", "Score")
    assert res["stats"]["A"]["n"] == 30 and res["difference"] < 5


def test_numeric_looking_group_labels_compare_by_text():
    groups = [1] * 30 + [2] * 30
    r = _rng(32)
    res = run_hypothesis_test(groups, list(r.normal(0, 1, 30)) + list(r.normal(2, 1, 30)), 1, 2, "Tier", "Score")
    assert res["available"] and res["group_a"] == "1" and res["difference"] > 0


@pytest.mark.parametrize("groups,outcomes,a,b,note", [
    (["A"] * 3 + ["B"] * 10, list(range(13)), "A", "B", "at least 5 rows"),
    (["A"] * 10 + ["B"] * 10, list(range(20)), "A", "A", "two different groups"),
    (["A"] * 10 + ["B"] * 10, [4.0] * 20, "A", "B", "only one value"),
    (["A"] * 10 + ["B"] * 10, ["x"] * 20, "A", "B", "only one value"),
    (["A"] * 10 + ["B"] * 10, [f"v{i}" for i in range(20)], "A", "B", "different values"),
    (["A"] * 10 + ["B"] * 9, list(range(19)), "A", "B", "at least 5 rows"),
])
def test_unusable_inputs_are_explained_not_guessed(groups, outcomes, a, b, note):
    if note == "at least 5 rows" and len(groups) == 19:
        groups, outcomes = ["A"] * 10 + ["B"] * 4, list(range(14))
    res = run_hypothesis_test(groups, outcomes, a, b, "g", "o")
    assert res["available"] is False and note in res["note"]


def test_infinite_values_and_text_forced_to_numeric_are_rejected():
    groups = ["A"] * 10 + ["B"] * 10
    assert not run_hypothesis_test(groups, [1.0] * 9 + [float("inf")] + list(range(10)), "A", "B", "g", "o", outcome_kind="numeric")["available"]
    assert "non-numeric" in run_hypothesis_test(groups, ["x"] * 20, "A", "B", "g", "o", outcome_kind="numeric")["note"]


def test_unknown_positive_level_and_bad_kind_are_explained():
    groups = ["A"] * 20 + ["B"] * 20
    out = ["Yes", "No"] * 20
    assert "does not appear" in run_hypothesis_test(groups, out, "A", "B", "g", "o", positive_level="Maybe")["note"]
    assert "outcome_kind" in run_hypothesis_test(groups, out, "A", "B", "g", "o", outcome_kind="weird")["note"]


def test_mismatched_lengths_are_rejected():
    assert not run_hypothesis_test(["A"] * 10, [1.0] * 9, "A", "B", "g", "o")["available"]


def test_result_is_plain_json_serialisable():
    import json
    res = _run(_rng(40).normal(0, 1, 50), _rng(41).normal(0.4, 1, 50))
    json.dumps(res)
    json.dumps(_binary(30, 100, 45, 100))


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------
def test_endpoint_runs_a_test_and_returns_the_full_result(client):
    r = _rng(50)
    body = {"group_column": "Arm", "outcome_column": "Score", "group_a": "A", "group_b": "B",
            "groups": ["A"] * 60 + ["B"] * 60, "outcomes": list(r.normal(0, 1, 60)) + list(r.normal(1, 1, 60))}
    resp = client.post("/api/hypothesis-test", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["available"] and out["test"]["id"] == "welch_t" and out["significant"] is True
    assert out["group_column"] == "Arm" and out["outcome_column"] == "Score"


def test_endpoint_returns_unavailable_with_a_note_instead_of_an_error_for_unusable_input(client):
    body = {"group_column": "g", "outcome_column": "o", "group_a": "A", "group_b": "B", "groups": ["A", "B"], "outcomes": [1, 2]}
    resp = client.post("/api/hypothesis-test", json=body)
    assert resp.status_code == 200 and resp.json()["available"] is False and "at least 5 rows" in resp.json()["note"]


def test_endpoint_validates_the_request_shape(client):
    assert client.post("/api/hypothesis-test", json={"group_a": "A"}).status_code == 422


def test_a_numeric_outcome_with_no_spread_inside_either_group_has_nothing_to_test():
    groups = ["A"] * 10 + ["B"] * 10
    res = run_hypothesis_test(groups, [4.0] * 10 + [5.0] * 10, "A", "B", "g", "o", outcome_kind="numeric")
    assert res["available"] is False and "no variation" in res["note"]


# ---------------------------------------------------------------------------
# real data: the shapes the app actually produces
# ---------------------------------------------------------------------------
import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["demo-sales-data.csv", "sample-healthcare-data.csv", "sample-manufacturing-data.csv"])
def test_works_on_the_row_data_the_app_actually_holds_for_every_sample_dataset(name):
    from app.main import _full_analyze_from_df, _load_dataframe
    path = _ROOT / "app/static" / name
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v2 = _full_analyze_from_df(_load_dataframe(name, path.read_bytes()))["v2"]
    fd = v2["filterable_data"]
    rows = fd["rows"]
    ran = 0
    for dim in fd["dimension_columns"]:
        counts = pd.Series([r[dim] for r in rows if r.get(dim) not in (None, "")]).value_counts()
        if len(counts) < 2:
            continue
        a, b = str(counts.index[0]), str(counts.index[1])
        for outcome in fd["measure_columns"][:2] + [d for d in fd["dimension_columns"] if d != dim][:1]:
            res = run_hypothesis_test([r[dim] for r in rows], [r.get(outcome) for r in rows], a, b, dim, outcome,
                                      outcome_kind="categorical" if outcome in fd["dimension_columns"] else "auto")
            assert "available" in res
            if res["available"]:
                ran += 1
                assert 0 <= res["p_value"] <= 1 and isinstance(res["significant"], bool) and res["headline"]
                assert res["test"]["id"] in {"welch_t", "mann_whitney", "chi_square", "fisher_exact"}
            else:
                assert res["note"]
    assert ran >= 3, "the check would be vacuous"
