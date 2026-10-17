"""app.robustness -- does the result hold without the extreme rows?

Every case is built so the right answer is known by hand: a mean dragged by
a few giant values, a correlation that is really one point in the corner, a
sign that only appears because of outliers, and clean data that must NOT be
called sensitive (false alarms would teach people to ignore the panel)."""
import numpy as np
import pandas as pd
import pytest

from app.correlation_center import analyze_correlations
from app.robustness import analyze_robustness, _fences, _kpi_check, _pair_check
from app.understanding import Measure


def _profile(*measures):
    class P:
        pass
    p = P()
    p.measures = [Measure(column=c, role="MEASURE", aggregation=agg) for c, agg in measures]
    return p


def _run(df, *measures):
    prof = _profile(*measures)
    pairs = analyze_correlations(df, prof, min_r=0.0)["pairs"]
    return analyze_robustness(df, prof, pairs)


def _kpi(report, name):
    return next(k for k in report["kpis"] if k["measure"] == name)


def _corr(report, a, b):
    return next(c for c in report["correlations"] if {c["col1"], c["col2"]} == {a, b})


def test_fences_are_the_textbook_tukey_rule():
    s = pd.Series(range(1, 101), dtype=float)          # Q1=25.75, Q3=75.25, IQR=49.5
    lo, hi = _fences(s)
    assert lo == pytest.approx(25.75 - 1.5 * 49.5)
    assert hi == pytest.approx(75.25 + 1.5 * 49.5)


def test_no_spread_means_no_fences():
    assert _fences(pd.Series([0.0] * 90 + [5.0] * 10)) is None


def test_an_averaged_kpi_dragged_by_a_few_giant_values_is_called_sensitive():
    rng = np.random.default_rng(0)
    amount = np.concatenate([rng.normal(100, 10, 197), [5000, 6000, 7000]])
    df = pd.DataFrame({"Amount": amount})
    k = _kpi(_run(df, ("Amount", "avg")), "Amount")
    assert k["n_flagged"] == 3 and k["verdict"] == "sensitive" and k["material"] is True
    assert k["full"] > 150 and k["trimmed"] == pytest.approx(100, abs=3)
    assert k["change_pct"] < -40
    assert "Without the 3 extreme rows" in k["note"]


def test_a_summed_kpi_is_judged_by_how_much_the_extremes_carry_not_by_the_drop():
    rng = np.random.default_rng(1)
    amount = np.concatenate([rng.normal(100, 10, 197), [4000, 4000, 4000]])
    k = _kpi(_run(pd.DataFrame({"Amount": amount}), ("Amount", "sum")), "Amount")
    assert k["verdict"] == "concentrated" and k["material"] is True
    assert k["flagged_share_pct"] == pytest.approx(100 * 12000 / (amount.sum()), abs=3.0)
    assert "of the total" in k["note"]


def test_clean_symmetric_data_is_robust_and_gets_no_false_alarm():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"A": rng.normal(100, 10, 500), "B": rng.normal(50, 5, 500)})
    df["B"] = df["B"] + 0.5 * (df["A"] - 100)
    out = _run(df, ("A", "avg"), ("B", "avg"))
    assert out["overall"]["verdict"] == "robust"
    assert not any(k["material"] for k in out["kpis"])
    assert _corr(out, "A", "B")["verdict"] == "holds"


def test_mild_outliers_that_barely_move_the_mean_are_flagged_but_not_material():
    rng = np.random.default_rng(3)
    amount = np.concatenate([rng.normal(100, 10, 400), [145, 146, 55]])
    k = _kpi(_run(pd.DataFrame({"Amount": amount}), ("Amount", "avg")), "Amount")
    assert k["n_flagged"] >= 1 and k["material"] is False and k["verdict"] == "stable"


def test_a_correlation_that_is_really_one_corner_point_loses_significance():
    rng = np.random.default_rng(4)
    x, y = rng.normal(0, 1, 60), rng.normal(0, 1, 60)
    df = pd.DataFrame({"X": np.append(x, 40.0), "Y": np.append(y, 40.0)})
    out = _run(df, ("X", "avg"), ("Y", "avg"))
    c = _corr(out, "X", "Y")
    assert c["r_full"] > 0.9
    assert abs(c["r_trimmed"]) < 0.4
    assert c["verdict"] == "lost_significance" and c["material"] is True
    assert out["overall"]["verdict"] == "sensitive"


def test_a_sign_that_only_exists_because_of_outliers_is_reported_as_a_flip():
    rng = np.random.default_rng(5)
    x = rng.uniform(0, 10, 80)
    y = -2 * x + rng.normal(0, 2, 80)                     # clearly negative
    x = np.concatenate([x, [200, 210, 220, 230, 240, 250]])
    y = np.concatenate([y, [900, 950, 1000, 1050, 1100, 1150]])   # far-out points pull r positive
    df = pd.DataFrame({"X": x, "Y": y})
    c = _corr(_run(df, ("X", "avg"), ("Y", "avg")), "X", "Y")
    assert c["r_full"] > 0 > c["r_trimmed"]
    assert c["verdict"] == "flips" and "sign reverses" in c["note"]


def test_extremes_that_were_hiding_a_relationship_are_reported_as_strengthening():
    rng = np.random.default_rng(6)
    x = rng.normal(0, 1, 200)
    y = 0.9 * x + rng.normal(0, 0.4, 200)
    y[:6] = rng.choice([-80, 80], 6)                       # noise points far above/below
    df = pd.DataFrame({"X": x, "Y": y})
    c = _corr(_run(df, ("X", "avg"), ("Y", "avg")), "X", "Y")
    assert c["verdict"] == "strengthens" and abs(c["r_trimmed"]) > abs(c["r_full"]) + 0.15
    assert "hiding it" in c["note"]


def test_sign_wobble_between_two_near_zero_values_is_not_called_a_flip():
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"X": rng.normal(0, 1, 300), "Y": rng.normal(0, 1, 300)})
    df.loc[0, ["X", "Y"]] = [30.0, -30.0]
    c = _corr(_run(df, ("X", "avg"), ("Y", "avg")), "X", "Y")
    assert c["verdict"] != "flips" or (abs(c["r_full"]) >= 0.1 and abs(c["r_trimmed"]) >= 0.1)


def test_too_few_rows_left_after_trimming_says_so_instead_of_guessing():
    x = np.array([1, 1, 2, 2, 3, 3, 4, 4, 100, 100, 101, 101, 102.0])
    df = pd.DataFrame({"X": x, "Y": x * 2 + np.arange(13) % 3})
    pair = _pair_check(df, "X", "Y", {"X": (0.0, 5.0), "Y": (0.0, 12.0)})
    assert pair["verdict"] == "insufficient" and pair["r_trimmed"] is None and pair["material"] is True


def test_a_column_with_no_spread_is_reported_not_crashed_on():
    df = pd.DataFrame({"Refund": [0.0] * 95 + [10.0] * 5, "Sales": np.arange(100.0)})
    k = _kpi(_run(df, ("Refund", "sum"), ("Sales", "sum")), "Refund")
    assert k["verdict"] == "no_spread" and k["n_flagged"] == 0 and k["material"] is False


def test_no_extreme_rows_anywhere_says_nothing_depends_on_a_few_rows():
    df = pd.DataFrame({"A": np.linspace(0, 100, 200), "B": np.linspace(5, 50, 200) + np.sin(np.arange(200))})
    out = _run(df, ("A", "avg"), ("B", "avg"))
    assert out["overall"]["verdict"] == "robust"
    assert "No extreme values" in out["overall"]["headline"]


def test_overall_headline_counts_what_moved():
    rng = np.random.default_rng(4)
    x, y = rng.normal(0, 1, 60), rng.normal(0, 1, 60)
    df = pd.DataFrame({"X": np.append(x, 40.0), "Y": np.append(y, 40.0)})
    h = _run(df, ("X", "avg"), ("Y", "avg"))["overall"]["headline"]
    assert h.startswith("Sensitive to extreme rows") and "top correlation" in h


def test_inputs_are_never_modified():
    rng = np.random.default_rng(8)
    df = pd.DataFrame({"A": np.append(rng.normal(100, 10, 100), [9999.0]), "B": rng.normal(0, 1, 101)})
    before = df.copy(deep=True)
    _run(df, ("A", "avg"), ("B", "avg"))
    pd.testing.assert_frame_equal(df, before)


def test_unavailable_cases_are_explained():
    assert analyze_robustness(pd.DataFrame({"x": [1, 2]}), _profile())["available"] is False
    out = analyze_robustness(pd.DataFrame({"x": [1.0, 2.0, 3.0]}), _profile(("x", "avg")))
    assert out["available"] is False and "at least 10" in out["note"]


def test_nan_heavy_columns_use_only_the_rows_that_exist():
    rng = np.random.default_rng(9)
    a = rng.normal(100, 10, 200)
    a[:100] = np.nan
    k = _kpi(analyze_robustness(pd.DataFrame({"A": a}), _profile(("A", "avg"))), "A")
    assert k["n"] == 100


def test_end_to_end_through_the_real_pipeline(sales_df):
    from app.main import _run_v2_pipeline
    r = _run_v2_pipeline(sales_df)["robustness"]
    assert r["available"] is True
    assert r["overall"]["verdict"] in {"robust", "sensitive"}
    assert r["kpis"] and all({"measure", "full", "trimmed", "verdict"} <= set(k) for k in r["kpis"])


def test_a_tiny_change_that_crosses_a_strength_label_boundary_is_not_a_finding():
    # r goes 0.702 -> 0.687: "strong" -> "moderate" by label, but not a real change.
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"A": rng.normal(100, 10, 500), "B": rng.normal(50, 5, 500)})
    df["B"] = df["B"] + 0.5 * (df["A"] - 100)
    c = _corr(_run(df, ("A", "avg"), ("B", "avg")), "A", "B")
    assert c["r_full"] > 0.7 > c["r_trimmed"]
    assert c["verdict"] == "holds" and c["material"] is False


def test_a_tiered_measure_with_many_rows_outside_the_fences_is_skewed_not_outlier_driven():
    # discount tiers 0 / 0.1 / 0.2 / 0.7: the 0.7 rows (10%) are a real tier, not stray outliers.
    d = np.array([0.0] * 100 + [0.1] * 40 + [0.2] * 40 + [0.7] * 20)
    k = _kpi(analyze_robustness(pd.DataFrame({"Discount": d}), _profile(("Discount", "avg"))), "Discount")
    assert k["flagged_pct"] > 5 and k["verdict"] == "skewed" and k["material"] is False
    assert "natural tiers" in k["note"]


def test_a_skewed_measure_never_makes_the_overall_verdict_sensitive():
    d = np.array([0.0] * 100 + [0.1] * 40 + [0.2] * 40 + [0.7] * 20)
    out = analyze_robustness(pd.DataFrame({"Discount": d}), _profile(("Discount", "avg")))
    assert out["overall"]["verdict"] == "robust"


def test_a_heavy_trim_weakening_is_noted_but_not_called_material():
    rng = np.random.default_rng(11)
    x = rng.normal(0, 1, 300)
    y = 0.8 * x + rng.normal(0, 0.5, 300)
    x[:30], y[:30] = rng.normal(8, 0.5, 30), rng.normal(-6, 0.5, 30)   # 10% of rows far out, against the trend
    c = _corr(_run(pd.DataFrame({"X": x, "Y": y}), ("X", "avg"), ("Y", "avg")), "X", "Y")
    assert c["removed_pct"] > 5
    if c["verdict"] in {"weakens", "strengthens"}:
        assert c["material"] is False and "skewed measure" in c["note"]


def test_a_flip_is_still_called_out_even_when_many_rows_were_set_aside():
    rng = np.random.default_rng(5)
    x = rng.uniform(0, 10, 60)
    y = -2 * x + rng.normal(0, 2, 60)
    x = np.concatenate([x, np.linspace(200, 260, 12)])
    y = np.concatenate([y, np.linspace(900, 1200, 12)])
    c = _corr(_run(pd.DataFrame({"X": x, "Y": y}), ("X", "avg"), ("Y", "avg")), "X", "Y")
    assert c["removed_pct"] > 5 and c["verdict"] == "flips" and c["material"] is True
