"""app.filtered_reports -- Seasonality, Period Comparison, "Why did it change?" and Robustness on the rows
the dashboard is showing.

The claim worth testing is not "it returns something" but "it gives the answer the full pipeline would give
if the filtered file had been uploaded". So the central tests filter a real dataset two ways -- (a) in pandas,
then run the WHOLE upload pipeline on it, and (b) on the row payload the browser holds, then recompute -- and
require the two to agree. Everything else checks that the transport from rows to a DataFrame is lossless and
that bad input is refused rather than guessed."""
import math
import time
import warnings
from pathlib import Path

import pandas as pd
import pytest

from app.filtered_reports import recompute_reports, RECOMPUTE_MAX_ROWS

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ["demo-sales-data.csv", "sample-healthcare-data.csv", "sample-manufacturing-data.csv"]
KEYS = ["period_comparison", "drivers", "robustness", "seasonality"]


def _close_diff(a, b, path="", tol=2e-3, out=None):
    """Structural comparison with a numeric tolerance (the rows carry float32 values as float64)."""
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'recompute' if k in b else 'pipeline'}")
            else:
                _close_diff(a[k], b[k], f"{path}.{k}", tol, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                _close_diff(x, y, f"{path}[{i}]", tol, out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        if not math.isclose(a, b, rel_tol=tol, abs_tol=tol):
            out.append(f"{path}: {a} vs {b}")
    elif a != b:
        out.append(f"{path}: {str(a)[:60]!r} vs {str(b)[:60]!r}")
    return out


def _columns(frame: pd.DataFrame) -> dict:
    return {c: frame[c].where(frame[c].notna(), None).tolist() for c in frame.columns}


def _analysis(name):
    from app.main import _full_analyze_from_df, _load_dataframe
    path = ROOT / "app/static" / name
    df = _load_dataframe(name, path.read_bytes())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return df, _full_analyze_from_df(df)["v2"]


@pytest.fixture(scope="module")
def analyses():
    return {n: _analysis(n) for n in DATASETS}


def _run(v2, frame):
    fd = v2["filterable_data"]
    return recompute_reports(_columns(frame), fd["date_column"], fd["dimension_columns"], fd["measure_columns"],
                             fd["measure_aggregations"], v2["drivers"]["metric"], v2["drivers"]["aggregation"])


# ---------------------------------------------------------------------------
# agreement with the full pipeline
# ---------------------------------------------------------------------------
def _filters(rows: pd.DataFrame, fd: dict):
    """(id, mask on the row payload, mask on the original frame) for filters that mirror filterUtils.applyFilters."""
    dim, dc = fd["dimension_columns"][0], fd["date_column"]
    counts = rows[dim].value_counts()
    top, second = counts.index[0], counts.index[1]
    days = sorted(rows[dc].dropna().unique())
    lo, hi = days[len(days) // 4], days[3 * len(days) // 4]
    day = lambda frame: pd.to_datetime(frame[dc], errors="coerce").dt.strftime("%Y-%m-%d")
    return [
        ("one-value", lambda r: r[dim] == top, lambda d: d[dim] == top),
        ("two-values", lambda r: r[dim].isin([top, second]), lambda d: d[dim].isin([top, second])),
        ("date-range", lambda r: (r[dc] >= lo) & (r[dc] <= hi), lambda d: (day(d) >= lo) & (day(d) <= hi)),
        ("date-and-value", lambda r: (r[dc] >= lo) & (r[dc] <= hi) & (r[dim] == top), lambda d: (day(d) >= lo) & (day(d) <= hi) & (d[dim] == top)),
    ]


@pytest.mark.parametrize("dataset", DATASETS)
@pytest.mark.parametrize("which", ["one-value", "two-values", "date-range", "date-and-value"])
def test_recompute_agrees_with_running_the_whole_pipeline_on_the_pre_filtered_file(analyses, dataset, which):
    from app.main import _full_analyze_from_df
    df, v2 = analyses[dataset]
    rows = pd.DataFrame(v2["filterable_data"]["rows"])
    _id, row_mask, frame_mask = next(f for f in _filters(rows, v2["filterable_data"]) if f[0] == which)

    sub = rows[row_mask(rows)]
    oracle_df = df[frame_mask(df)].reset_index(drop=True)
    assert len(sub) == len(oracle_df) > 30, "the filter must leave a real dataset on both sides"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        oracle = _full_analyze_from_df(oracle_df)["v2"]
    got = _run(v2, sub)
    assert got["available"] is True and got["rows_used"] == len(sub)
    for key in KEYS:
        assert _close_diff(oracle[key], got[key]) == [], key


def test_the_filtered_answer_really_differs_from_the_full_one(analyses):
    """Guards against a vacuous pass: if filtering changed nothing, agreement would prove nothing."""
    df, v2 = analyses["demo-sales-data.csv"]
    rows = pd.DataFrame(v2["filterable_data"]["rows"])
    dim = v2["filterable_data"]["dimension_columns"][0]
    top = rows[dim].value_counts().index[0]
    got = _run(v2, rows[rows[dim] == top])
    assert got["period_comparison"] != v2["period_comparison"]
    assert got["drivers"]["comparisons"][0]["headline"] != v2["drivers"]["comparisons"][0]["headline"]


def test_unfiltered_rows_reproduce_the_upload_time_reports(analyses):
    """No filter at all must give back what the upload computed."""
    df, v2 = analyses["sample-healthcare-data.csv"]
    got = _run(v2, pd.DataFrame(v2["filterable_data"]["rows"]))
    for key in KEYS:
        assert _close_diff(v2[key], got[key]) == [], key


def test_a_dimension_filtered_down_to_one_value_stops_being_a_breakdown(analyses):
    df, v2 = analyses["demo-sales-data.csv"]
    rows = pd.DataFrame(v2["filterable_data"]["rows"])
    dim = v2["filterable_data"]["dimension_columns"][0]
    got = _run(v2, rows[rows[dim] == rows[dim].value_counts().index[0]])
    split_by = {d["dimension"] for c in got["drivers"]["comparisons"] for d in c["dimensions"]}
    assert dim not in split_by                         # "Region = West explains 100% of the change" would be noise
    assert split_by                                    # but the other dimensions are still there


def test_the_row_payload_carries_each_measures_aggregation(analyses):
    df, v2 = analyses["demo-sales-data.csv"]
    fd = v2["filterable_data"]
    assert set(fd["measure_aggregations"]) == set(fd["measure_columns"])
    assert set(fd["measure_aggregations"].values()) <= {"sum", "avg"}
    assert fd["measure_aggregations"]["Discount"] == "avg"          # a rate is averaged, not summed


# ---------------------------------------------------------------------------
# the transport from rows to a DataFrame
# ---------------------------------------------------------------------------
def _tiny(n=120, **over):
    cycle = lambda values: (values * (n // len(values) + 1))[:n]          # exactly n entries whatever n is
    days = pd.date_range("2023-01-01", periods=n, freq="D").strftime("%Y-%m-%d").tolist()
    cols = {"Date": days, "Region": cycle(["East", "West"]), "Cat": cycle(["A", "B", "C"]),
            "Sales": [float(10 + i % 7) for i in range(n)], "Qty": [float(1 + i % 3) for i in range(n)]}
    cols.update(over)
    return cols


def _call(columns=None, **kw):
    args = dict(date_column="Date", dimension_columns=["Region", "Cat"], measure_columns=["Sales", "Qty"],
                measure_aggregations={"Sales": "sum", "Qty": "avg"}, metric_column="Sales", aggregation="sum")
    args.update(kw)
    return recompute_reports(_tiny() if columns is None else columns, **args)


def test_missing_values_in_any_column_are_tolerated():
    c = _tiny()
    c["Sales"][3] = None
    c["Region"][5] = None
    c["Date"][7] = None
    out = _call(c)
    assert out["available"] and out["rows_used"] == 120


def test_non_numeric_text_in_a_measure_becomes_missing_not_an_error():
    c = _tiny()
    c["Sales"][4] = "n/a"
    c["Qty"][9] = ""
    assert _call(c)["available"] is True


def test_unparseable_dates_are_dropped_not_fatal():
    c = _tiny()
    c["Date"][2] = "not a date"
    assert _call(c)["available"] is True


def test_the_inputs_are_not_modified():
    c = _tiny()
    before = {k: list(v) for k, v in c.items()}
    _call(c)
    assert c == before


def test_the_same_request_gives_the_same_answer_twice():
    assert _call() == _call()


def test_an_empty_payload_is_explained():
    out = _call({})
    assert out["available"] is False and "No rows" in out["note"]


def test_no_rows_matching_the_filter_is_explained():
    out = _call({k: [] for k in _tiny()})
    assert out["available"] is False and "No rows match" in out["note"]


def test_columns_of_different_lengths_are_refused():
    c = _tiny()
    c["Sales"] = c["Sales"][:-1]
    out = _call(c)
    assert out["available"] is False and "different lengths" in out["note"]


@pytest.mark.parametrize("kw", [{"date_column": "Nope"}, {"metric_column": "Nope"}, {"metric_column": "Region"}])
def test_a_missing_date_or_metric_is_explained(kw):
    out = _call(**kw)
    assert out["available"] is False and "missing" in out["note"]


def test_an_unknown_aggregation_falls_back_to_sum_like_the_pipeline_default():
    assert _close_diff(_call(aggregation="median"), _call(aggregation="sum")) == []


def test_missing_measure_aggregations_default_to_sum_without_failing():
    assert _call(measure_aggregations=None)["available"] is True
    assert _call(measure_aggregations={"Sales": "weird"})["available"] is True


def test_dimensions_or_measures_not_in_the_rows_are_ignored():
    assert _call(dimension_columns=["Region", "Ghost"], measure_columns=["Sales", "Qty", "Ghost2"])["available"] is True


def test_a_range_with_no_dated_rows_is_explained():
    c = _tiny(Date=[None] * 120)
    out = _call(c)
    assert out["available"] is False and "date and a value" in out["note"]


def test_the_result_is_plain_json():
    import json
    json.dumps(_call())


def test_fifty_thousand_rows_finish_in_reasonable_time():
    n = RECOMPUTE_MAX_ROWS
    c = _tiny(n)
    started = time.perf_counter()
    out = _call(c)
    assert out["available"] and out["rows_used"] == n
    assert time.perf_counter() - started < 30


# ---------------------------------------------------------------------------
# endpoint
# ---------------------------------------------------------------------------
def _payload(columns=None, **kw):
    body = {"columns": _tiny() if columns is None else columns, "date_column": "Date", "dimension_columns": ["Region", "Cat"],
            "measure_columns": ["Sales", "Qty"], "measure_aggregations": {"Sales": "sum", "Qty": "avg"},
            "metric_column": "Sales", "aggregation": "sum"}
    body.update(kw)
    return body


def test_endpoint_returns_the_four_reports(client):
    resp = client.post("/api/filtered-reports", json=_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True and body["rows_used"] == 120
    assert {"seasonality", "period_comparison", "drivers", "robustness"} <= set(body)


def test_endpoint_refuses_more_rows_than_it_will_recompute(client):
    big = {"Date": ["2023-01-01"] * (RECOMPUTE_MAX_ROWS + 1)}
    resp = client.post("/api/filtered-reports", json=_payload(big))
    assert resp.status_code == 413 and "Too many rows" in resp.json()["detail"]


def test_endpoint_answers_unusable_input_with_a_note_not_an_error(client):
    resp = client.post("/api/filtered-reports", json=_payload({k: [] for k in _tiny()}))
    assert resp.status_code == 200 and resp.json() == {"available": False, "note": "No rows match the current filters."}


def test_endpoint_validates_the_shape_of_the_request(client):
    assert client.post("/api/filtered-reports", json={"date_column": "Date"}).status_code == 422
    assert client.post("/api/filtered-reports", json={**_payload(), "columns": "nope"}).status_code == 422
