"""Input caps and diagnostics from the Medium/Low audit pass.

Each test here pins one thing a caller could otherwise use to make the server do
unbounded work, or a failure that used to be invisible.
"""
import json
import logging

import pandas as pd
import pytest
from fastapi import HTTPException

from app import main as main_module
from app.data_quality import analyze_data_quality
from app.main import MAX_COMBINED_FILES, _load_dataframe
from app.understanding import understand_dataset

CSV = b"a,b\n1,2\n3,4\n"


def _files(n):
    return [("files", (f"f{i}.csv", CSV, "text/csv")) for i in range(n)]


# ---------------------------------------------------------------------------
# /api/analyze-combined: the per-file cap bounded nothing on its own
# ---------------------------------------------------------------------------
def test_combining_too_many_files_is_refused(client):
    resp = client.post("/api/analyze-combined", files=_files(MAX_COMBINED_FILES + 1))
    assert resp.status_code == 400
    assert str(MAX_COMBINED_FILES) in resp.json()["detail"]


def test_the_total_size_of_a_combined_upload_is_capped(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_COMBINED_UPLOAD_BYTES", 10)
    resp = client.post("/api/analyze-combined", files=_files(2))
    assert resp.status_code == 400
    assert "limit for a combined analysis" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /api/filtered-reports: rows were capped, values were not
# ---------------------------------------------------------------------------
def _filtered_payload(rows):
    return {
        "columns": {
            "Day": ["2024-01-01"] * rows,
            "Region": ["West"] * rows,
            "Sales": [10] * rows,
        },
        "date_column": "Day",
        "dimension_columns": ["Region"],
        "measure_columns": ["Sales"],
        "metric_column": "Sales",
        "aggregation": "sum",
    }


def test_filtered_reports_refuses_a_request_with_too_many_values(client, monkeypatch):
    monkeypatch.setattr(main_module, "RECOMPUTE_MAX_CELLS", 50)
    resp = client.post("/api/filtered-reports", json=_filtered_payload(20))
    assert resp.status_code == 413
    assert "50" in resp.json()["detail"]


def test_filtered_reports_still_answers_under_the_cap(client):
    resp = client.post("/api/filtered-reports", json=_filtered_payload(12))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# a JSON file with more than one list of records
# ---------------------------------------------------------------------------
def test_a_json_file_with_several_record_lists_is_refused_with_a_clear_message():
    raw = json.dumps({"orders": [{"id": 1}], "items": [{"sku": "a"}]}).encode()
    with pytest.raises(HTTPException) as exc:
        _load_dataframe("d.json", raw)
    assert exc.value.status_code == 400
    assert "single list of records" in exc.value.detail


def test_a_single_record_list_still_loads():
    raw = json.dumps({"data": [{"id": 1, "v": 2}]}).encode()
    assert len(_load_dataframe("d.json", raw)) == 1


# ---------------------------------------------------------------------------
# a derived column must not be reported as a column of the file
# ---------------------------------------------------------------------------
def test_a_derived_profit_role_does_not_leak_into_detected_columns(client):
    df = pd.DataFrame({
        "Order Date": pd.date_range("2024-01-01", periods=40, freq="D"),
        "Region": ["West", "East"] * 20,
        "Sales": [100.0 + i for i in range(40)],
        "Cost": [60.0 + i for i in range(40)],
    })
    data = client.post(
        "/api/analyze", files={"file": ("d.csv", df.to_csv(index=False).encode(), "text/csv")},
    ).json()

    # The file has no Profit column; "_derived_profit" is one kpi.py computes.
    assert "_derived_profit" not in data["detected_columns"].values()
    assert "_derived_profit" not in data["unmapped_columns"]
    # ...and it is still reported and charted, because the stats use the derived role.
    assert data["kpis"]["total_profit"] == pytest.approx(float((df["Sales"] - df["Cost"]).sum()))
    assert "profit" in data["monthly_trend"][0]


# ---------------------------------------------------------------------------
# the usable quality score must describe the date column the pipeline charts
# ---------------------------------------------------------------------------
def test_the_usable_quality_score_ignores_a_date_column_the_pipeline_does_not_use():
    n = 200
    order_date = pd.Series(pd.date_range("2023-01-01", periods=n, freq="D"))
    order_date[:80] = pd.NaT                      # 40% empty, but first among the DATE roles
    df = pd.DataFrame({
        "Order Date": order_date,
        "Ship Date": pd.date_range("2023-06-01", periods=n, freq="D"),
        "Region": ["West", "East", "North", "South"] * (n // 4),
        "Sales": [100.0 + i for i in range(n)],
    })
    profile = understand_dataset(df)
    # The pipeline charts the column that parses completely, not the first DATE role.
    assert profile.date_column == "Ship Date"

    report = analyze_data_quality(df, profile)
    # Scoring "Order Date" (the first DATE role) instead used to report 94.7 for a
    # subset that has no missing values in any column the analysis actually reads.
    assert report.usable_quality_score == 100.0


# ---------------------------------------------------------------------------
# failures that used to be silent
# ---------------------------------------------------------------------------
def test_a_failing_sensitive_data_scan_is_logged_not_silently_dropped(client, monkeypatch, caplog):
    def boom(_df):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(main_module, "detect_sensitive_data", boom)

    df = pd.DataFrame({
        "Order Date": pd.date_range("2024-01-01", periods=30, freq="D"),
        "Region": ["West", "East"] * 15,
        "Sales": [100.0 + i for i in range(30)],
    })
    with caplog.at_level(logging.WARNING, logger="app.main"):
        resp = client.post(
            "/api/analyze", files={"file": ("d.csv", df.to_csv(index=False).encode(), "text/csv")},
        )

    assert resp.status_code == 200                       # advisory: never fails the analysis
    assert any("sensitive-data scan failed" in r.message for r in caplog.records)


def test_a_failing_pdf_export_is_logged_with_its_cause(client, monkeypatch, caplog):
    def boom(*_args, **_kwargs):
        raise RuntimeError("reportlab fell over")

    monkeypatch.setattr(main_module, "build_pdf_report", boom)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        resp = client.post("/api/export/pdf", json={"file_name": "d.csv", "v2": {"profile": {}}})

    assert resp.status_code == 500
    assert any("PDF report generation failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# a build without an index.html
# ---------------------------------------------------------------------------
def test_a_build_without_index_html_returns_404_instead_of_500(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "STATIC_ROOT", tmp_path)
    assert client.get("/some/spa/route").status_code == 404
