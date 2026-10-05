"""
Regression tests for app.segment_forecast -- forecasting the top
segments of a dimension independently, as distinct from
forecasting.py's single overall-aggregate forecast.
"""
import numpy as np
import pandas as pd

from app.understanding import understand_dataset
from app.segment_forecast import forecast_top_segments


def _dates(n):
    out, y, m = [], 2021, 1
    for _ in range(n):
        out.append(pd.Timestamp(f"{y}-{m:02d}-15"))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _category_dim(profile):
    return next(d for d in profile.dimensions if d.column == "Category")


def test_diverging_segments_detected_in_opposite_directions():
    rng = np.random.default_rng(1)
    rows = []
    for i, d in enumerate(_dates(30)):
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "Furniture", "Sales": 200 - i * 4 + rng.normal(0, 8)})
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "Technology", "Sales": 100 + i * 5 + rng.normal(0, 8)})
    df = pd.DataFrame(rows)
    profile = understand_dataset(df)

    result = forecast_top_segments(df, profile, _category_dim(profile))
    assert result["available"]
    by_label = {s["label"]: s for s in result["segments"]}
    assert by_label["Furniture"]["direction"] == "down"
    assert by_label["Technology"]["direction"] == "up"


def test_too_noisy_segment_is_left_out_not_guessed():
    rng = np.random.default_rng(1)
    rows = []
    for i, d in enumerate(_dates(30)):
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "Furniture", "Sales": 200 - i * 4 + rng.normal(0, 8)})
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "Office Supplies", "Sales": 80 + rng.normal(0, 15)})
    df = pd.DataFrame(rows)
    profile = understand_dataset(df)

    result = forecast_top_segments(df, profile, _category_dim(profile))
    labels = {s["label"] for s in result["segments"]}
    assert "Furniture" in labels
    assert "Office Supplies" not in labels  # too noisy for forecast_trend's own R^2 gate


def test_segments_sorted_by_magnitude_of_change_descending():
    rng = np.random.default_rng(2)
    rows = []
    for i, d in enumerate(_dates(30)):
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "BigMover", "Sales": 100 + i * 10 + rng.normal(0, 5)})
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "SmallMover", "Sales": 100 + i * 1 + rng.normal(0, 3)})
    df = pd.DataFrame(rows)
    profile = understand_dataset(df)

    result = forecast_top_segments(df, profile, _category_dim(profile))
    assert result["available"]
    assert result["segments"][0]["label"] == "BigMover"


def test_caps_at_max_segments():
    rng = np.random.default_rng(3)
    rows = []
    cats = [f"Cat{i}" for i in range(6)]
    for i, d in enumerate(_dates(24)):
        for c_idx, c in enumerate(cats):
            for _ in range(15):
                rows.append({"Order Date": d, "Category": c, "Sales": (100 - c_idx * 5) + i * 3 + rng.normal(0, 4)})
    df = pd.DataFrame(rows)
    profile = understand_dataset(df)

    result = forecast_top_segments(df, profile, _category_dim(profile), max_segments=4)
    assert len(result["segments"]) <= 4


def test_declines_without_date_or_measure():
    df = pd.DataFrame({"Category": ["A", "B"] * 10})
    profile = understand_dataset(df)
    # no numeric measure, no date column at all -- primary_measure/date_column will be None
    result = forecast_top_segments(df, profile, None)
    assert result["available"] is False
    assert result["segments"] == []


def test_declines_when_no_segment_has_enough_rows():
    rng = np.random.default_rng(4)
    rows = []
    for i, d in enumerate(_dates(10)):
        rows.append({"Order Date": d, "Category": "A" if i % 2 == 0 else "B", "Sales": 100 + rng.normal(0, 5)})
    df = pd.DataFrame(rows)
    profile = understand_dataset(df)

    result = forecast_top_segments(df, profile, _category_dim(profile))
    assert result["available"] is False
    assert "enough history" in result["note"]
