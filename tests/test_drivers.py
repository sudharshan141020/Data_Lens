"""app.drivers -- splitting a change by dimension.

The core promise is arithmetic: segment contributions add up EXACTLY to the
total change, for summed and averaged metrics alike. Everything else (the
headline, offsetting handling, drill-down, windows from a changepoint) is
checked against datasets built so the right answer is known by hand."""
import numpy as np
import pandas as pd
import pytest

from app.drivers import analyze_drivers, _segment_values
from app.understanding import Dimension, understand_dataset


def _profile(*cols):
    class P:
        dimensions = [Dimension(column=c, role="CATEGORY", cardinality=2, is_chartable=True) for c in cols]
    return P()


def _cells(months, values, rows_per_cell=10):
    """values: {(region, category): {month: per-row value}} -> long frame."""
    out = []
    for m in months:
        for (region, category), by_month in values.items():
            v = by_month.get(m, by_month.get("default"))
            for i in range(rows_per_cell):
                out.append({"Date": pd.Timestamp(f"{m}-{1 + i:02d}"), "Region": region, "Category": category, "Sales": float(v)})
    return pd.DataFrame(out)


MONTHS = [f"2023-{m:02d}" for m in range(1, 7)]


def _west_furniture_drop():
    base = {"default": 10}
    return _cells(MONTHS, {
        ("West", "Furniture"): {"default": 10, "2023-06": 3},   # cell total 100 -> 30  (-70)
        ("East", "Furniture"): {"default": 10, "2023-06": 9},   # 100 -> 90             (-10)
        ("West", "Technology"): base,
        ("East", "Technology"): base,
    })


def test_contributions_add_up_exactly_to_the_total_change():
    df = _west_furniture_drop()
    out = analyze_drivers(df, _profile("Region", "Category"), "Date", "Sales", "sum")
    c = out["comparisons"][0]
    assert c["change"] == -80.0
    for dim in c["dimensions"]:
        total = sum(s["change"] for s in dim["segments"]) + (dim["other"]["change"] if dim["other"] else 0)
        assert total == pytest.approx(c["change"], abs=0.02)


def test_names_the_driver_and_drills_one_level_down():
    out = analyze_drivers(_west_furniture_drop(), _profile("Region", "Category"), "Date", "Sales", "sum")
    c = out["comparisons"][0]
    assert c["best_dimension"] == "Category"
    best = c["dimensions"][0]
    assert best["segments"][0]["segment"] == "Furniture"
    assert best["segments"][0]["share_of_change_pct"] == 100.0
    assert best["drill"] == {"dimension": "Region", "segment": "West", "share_pct": 87.5}
    assert "100% of the drop is Category=Furniture, mostly Region=West (88% of Furniture's change)" in c["headline"]
    assert c["headline"].startswith("Sales fell 20% from 2023-05 to 2023-06")


def test_region_view_is_available_too_and_east_west_split_is_right():
    out = analyze_drivers(_west_furniture_drop(), _profile("Region", "Category"), "Date", "Sales", "sum")
    region = next(d for d in out["comparisons"][0]["dimensions"] if d["dimension"] == "Region")
    by = {s["segment"]: s for s in region["segments"]}
    assert by["West"]["change"] == -70.0 and by["West"]["share_of_change_pct"] == 87.5
    assert by["East"]["change"] == -10.0 and by["East"]["share_of_change_pct"] == 12.5


def test_averaged_metric_still_adds_up_and_matches_the_monthly_mean():
    rng = np.random.default_rng(5)
    rows = []
    for m in MONTHS:
        for i in range(60):
            rows.append({"Date": pd.Timestamp(f"{m}-{1 + i % 27:02d}"), "Region": rng.choice(["East", "West", "North"]),
                         "Category": rng.choice(["A", "B"]), "Sales": float(rng.normal(100 + (30 if m == "2023-06" and i % 2 else 0), 10))})
    df = pd.DataFrame(rows)
    out = analyze_drivers(df, _profile("Region", "Category"), "Date", "Sales", "avg")
    c = out["comparisons"][0]
    monthly = df.assign(m=df["Date"].dt.to_period("M").astype(str)).groupby("m")["Sales"].mean()
    assert c["before"]["value"] == pytest.approx(monthly["2023-05"], abs=0.01)
    assert c["after"]["value"] == pytest.approx(monthly["2023-06"], abs=0.01)
    for dim in c["dimensions"]:
        total = sum(s["change"] for s in dim["segments"]) + (dim["other"]["change"] if dim["other"] else 0)
        assert total == pytest.approx(c["change"], abs=0.05)


def test_offsetting_moves_are_called_out_instead_of_giving_silly_percentages():
    df = _cells(MONTHS, {
        ("West", "A"): {"default": 10, "2023-06": 20},   # +100
        ("East", "A"): {"default": 10, "2023-06": 1},    # -90
        ("West", "B"): {"default": 10},
        ("East", "B"): {"default": 10},
    })
    out = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum")
    c = out["comparisons"][0]
    region = c["dimensions"][0]
    assert region["offsetting"] is True
    assert all(s["share_of_change_pct"] is None for s in region["segments"])
    assert "opposing moves by Region" in c["headline"]
    assert "West 100 up" in c["headline"] and "East 90 down" in c["headline"]


def test_a_spread_out_change_does_not_name_a_fake_driver():
    cats = [f"C{i}" for i in range(8)]
    values = {("R", c): {"default": 10, "2023-06": 8} for c in cats}  # every segment -20
    out = analyze_drivers(_cells(MONTHS, values), _profile("Category"), "Date", "Sales", "sum")
    h = out["comparisons"][0]["headline"]
    assert "No single Category value explains it" in h


def test_segments_beyond_the_cap_fold_into_other_and_still_add_up():
    cats = [f"C{i}" for i in range(10)]
    values = {("R", c): {"default": 10, "2023-06": 10 - (i + 1) * 0.5} for i, c in enumerate(cats)}
    out = analyze_drivers(_cells(MONTHS, values), _profile("Category"), "Date", "Sales", "sum")
    dim = out["comparisons"][0]["dimensions"][0]
    assert len(dim["segments"]) == 6
    assert dim["other"]["count"] == 4
    assert dim["segment_count"] == 10
    total = sum(s["change"] for s in dim["segments"]) + dim["other"]["change"]
    assert total == pytest.approx(out["comparisons"][0]["change"], abs=0.05)


def test_blank_values_are_kept_as_their_own_segment_so_totals_still_add_up():
    df = _west_furniture_drop()
    june = df.index[df["Date"].dt.to_period("M").astype(str) == "2023-06"]
    df.loc[june[:5], "Region"] = None
    out = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum")
    region = out["comparisons"][0]["dimensions"][0]
    names = {s["segment"] for s in region["segments"]}
    assert "(blank)" in names
    total = sum(s["change"] for s in region["segments"]) + (region["other"]["change"] if region["other"] else 0)
    assert total == pytest.approx(out["comparisons"][0]["change"], abs=0.02)


def test_break_comparison_uses_the_changepoint_windows():
    months = [f"2023-{m:02d}" for m in range(1, 13)]
    df = _cells(months, {
        ("West", "A"): {"default": 10, **{m: 4 for m in months[6:]}},   # West drops from month 7 on
        ("East", "A"): {"default": 10},
    })
    cp = {"label": "2023-07", "before_label": "2023-01", "before_end_label": "2023-06", "after_label": "2023-12"}
    out = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum", changepoint=cp, seasonally_adjusted=True)
    assert [c["id"] for c in out["comparisons"]] == ["latest_month", "break"]
    brk = out["comparisons"][1]
    assert brk["before"]["months"] == 6 and brk["after"]["months"] == 6
    assert brk["before"]["label"] == "2023-01 \u2013 2023-06"
    assert brk["change"] == -60.0     # mean monthly total 200 -> 140
    assert brk["dimensions"][0]["segments"][0]["segment"] == "West"
    assert out["seasonally_adjusted_break"] is True


def test_unequal_windows_compare_monthly_averages_not_raw_totals():
    months = [f"2023-{m:02d}" for m in range(1, 13)]
    df = _cells(months, {("West", "A"): {"default": 10}, ("East", "A"): {"default": 10}})  # flat
    cp = {"label": "2023-10", "before_label": "2023-01", "before_end_label": "2023-09", "after_label": "2023-12"}
    brk = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum", changepoint=cp)["comparisons"][1]
    assert brk["change"] == 0.0   # 9 months vs 3 months of the same level must not look like a drop


@pytest.mark.parametrize("kwargs,note", [
    ({"date_column": None}, "date column"),
    ({"metric_column": None}, "date column"),
])
def test_unavailable_without_date_or_metric(kwargs, note):
    args = {"date_column": "Date", "metric_column": "Sales", **kwargs}
    out = analyze_drivers(_west_furniture_drop(), _profile("Region"), args["date_column"], args["metric_column"])
    assert out["available"] is False and note in out["note"]


def test_unavailable_without_a_dimension_or_with_one_month():
    df = _west_furniture_drop()
    assert "category column" in analyze_drivers(df, _profile(), "Date", "Sales")["note"]
    one = df[df["Date"].dt.to_period("M").astype(str) == "2023-01"]
    assert "two calendar months" in analyze_drivers(one, _profile("Region"), "Date", "Sales")["note"]


def test_too_few_rows_in_a_period_is_explained_not_guessed():
    df = _west_furniture_drop()
    last = df["Date"].dt.to_period("M").astype(str) == "2023-06"
    df = pd.concat([df[~last], df[last].head(3)])
    out = analyze_drivers(df, _profile("Region"), "Date", "Sales")
    assert out["available"] is False and "at least 5 records" in out["note"]


def test_segment_values_helper_matches_a_hand_calculation():
    df = _west_furniture_drop()
    df["_month"] = df["Date"].dt.to_period("M").astype(str)
    v = _segment_values(df, "Region", "Sales", "sum", ["2023-05"], ["2023-06"])
    assert v.loc["West", "before"] == 200 and v.loc["West", "after"] == 130
    assert v.loc["East", "after"] == 190


def test_end_to_end_through_the_real_pipeline(sales_df):
    from app.main import _run_v2_pipeline
    v2 = _run_v2_pipeline(sales_df)
    d = v2["drivers"]
    assert d["available"] is True
    c = d["comparisons"][0]
    assert c["id"] == "latest_month" and c["dimensions"]
    pc = v2["period_comparison"]
    assert c["before"]["label"] == pc["period_b"]["label"] and c["after"]["label"] == pc["period_a"]["label"]
    assert c["after"]["value"] == pytest.approx(pc["period_a"]["value"], abs=0.01)
    assert c["before"]["value"] == pytest.approx(pc["period_b"]["value"], abs=0.01)


def test_a_segment_bigger_than_the_whole_change_is_described_honestly():
    # West -100, East +40 -> net -60: West is 167% of the net drop.
    df = _cells(MONTHS, {
        ("West", "A"): {"default": 20, "2023-06": 10},   # -100
        ("East", "A"): {"default": 10, "2023-06": 14},   # +40
        ("North", "A"): {"default": 10},
        ("South", "A"): {"default": 10},
    })
    h = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum")["comparisons"][0]["headline"]
    assert "Region=West alone accounts for more than all of the drop (167%)" in h
    assert "partly offset" in h


def test_drill_down_is_skipped_when_the_segment_moves_internally_cancel():
    # Furniture is the driver, but inside it West +100 and East -110 nearly cancel (net -10).
    df = _cells(MONTHS, {
        ("West", "Furniture"): {"default": 10, "2023-06": 20},
        ("East", "Furniture"): {"default": 21, "2023-06": 10},
        ("West", "Tech"): {"default": 10},
        ("East", "Tech"): {"default": 10},
    })
    out = analyze_drivers(df, _profile("Region", "Category"), "Date", "Sales", "sum")
    c = out["comparisons"][0]
    best = next(d for d in c["dimensions"] if d["dimension"] == c["best_dimension"])
    assert best["drill"] is None
    assert "mostly" not in c["headline"]


def test_a_flat_period_says_so_instead_of_inventing_a_story():
    df = _cells(MONTHS, {("West", "A"): {"default": 10, "2023-06": 10.04}, ("East", "A"): {"default": 10}})
    h = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum")["comparisons"][0]["headline"]
    assert "essentially flat" in h and "no real change to explain" in h


def test_a_range_comparison_reads_naturally():
    months = [f"2023-{m:02d}" for m in range(1, 13)]
    df = _cells(months, {("West", "A"): {"default": 10, **{m: 4 for m in months[6:]}}, ("East", "A"): {"default": 10}})
    cp = {"label": "2023-07", "before_label": "2023-01", "before_end_label": "2023-06", "after_label": "2023-12"}
    h = analyze_drivers(df, _profile("Region"), "Date", "Sales", "sum", changepoint=cp)["comparisons"][1]["headline"]
    assert "between 2023-01 \u2013 2023-06 and 2023-07 \u2013 2023-12 (monthly average)" in h


def test_real_changepoint_flows_into_the_break_comparison_and_the_break_note():
    from app.main import _full_analyze_from_df
    rng = np.random.default_rng(3)
    rows = []
    for i, m in enumerate(pd.date_range("2022-01-01", periods=30, freq="MS")):
        for region in ["West", "East", "North"]:
            for cat in ["Furniture", "Technology"]:
                for _ in range(8):
                    v = 100 + rng.normal(0, 6)
                    if i >= 18 and region == "West":
                        v *= 0.1 if cat == "Furniture" else 0.8
                    rows.append({"Order Date": (m + pd.Timedelta(days=int(rng.integers(0, 27)))).strftime("%Y-%m-%d"),
                                 "Region": region, "Category": cat, "Sales": round(v, 2), "Quantity": int(rng.integers(1, 6))})
    v2 = _full_analyze_from_df(pd.DataFrame(rows))["v2"]
    brk = next(c for c in v2["drivers"]["comparisons"] if c["id"] == "break")
    assert "Region=West" in brk["headline"] and "Category=Furniture" in brk["headline"]
    trend = next(a for a in v2["all_analyses"] if a.get("changepoint"))
    assert trend["changepoint"]["driver_headline"] == brk["headline"]
