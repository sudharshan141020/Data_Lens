"""
API endpoint smoke tests -- every endpoint the frontend actually calls
should return 200 on a normal request and a clean 4xx (never a raw
500/stack trace) on a bad one. These hit the real FastAPI app through
TestClient, the same way the frontend hits it over HTTP.
"""
import json

import pandas as pd


def test_analyze_endpoint(client, sales_df):
    resp = client.post("/api/analyze", files={"file": ("d.csv", sales_df.to_csv(index=False).encode(), "text/csv")})
    assert resp.status_code == 200
    v2 = resp.json()["v2"]
    assert v2["profile"]["domain"] == "sales"


def test_analyze_combined_endpoint(client, sales_df, healthcare_df):
    resp = client.post("/api/analyze-combined", files=[
        ("files", ("a.csv", sales_df.to_csv(index=False).encode(), "text/csv")),
        ("files", ("b.csv", healthcare_df.to_csv(index=False).encode(), "text/csv")),
    ])
    assert resp.status_code == 200


def test_compare_endpoint(client, sales_df):
    half_a, half_b = sales_df.iloc[:150], sales_df.iloc[150:]
    resp = client.post("/api/compare", files={
        "file_a": ("a.csv", half_a.to_csv(index=False).encode(), "text/csv"),
        "file_b": ("b.csv", half_b.to_csv(index=False).encode(), "text/csv"),
    })
    assert resp.status_code == 200
    diff = resp.json()["diff"]
    assert "kpi_deltas" in diff


def test_compare_endpoint_rejects_file_with_no_numeric_metric(client, sales_df):
    no_metric = pd.DataFrame({"Name": ["A", "B"], "City": ["X", "Y"]})
    resp = client.post("/api/compare", files={
        "file_a": ("a.csv", sales_df.to_csv(index=False).encode(), "text/csv"),
        "file_b": ("b.csv", no_metric.to_csv(index=False).encode(), "text/csv"),
    })
    assert resp.status_code == 400


def test_export_pdf_endpoint(client, sales_df):
    analyze_resp = client.post("/api/analyze", files={"file": ("d.csv", sales_df.to_csv(index=False).encode(), "text/csv")})
    v2 = analyze_resp.json()["v2"]
    resp = client.post("/api/export/pdf", json={"file_name": "d.csv", "v2": v2})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_export_cleaned_csv_endpoint(client, sales_df):
    resp = client.post("/api/export/cleaned-csv", files={"file": ("d.csv", sales_df.to_csv(index=False).encode(), "text/csv")})
    assert resp.status_code == 200
    assert "flagged_as_unusual" in resp.text.splitlines()[0]
    summary = json.loads(resp.headers["x-clean-summary"])
    assert "duplicates_removed" in summary


def test_analyze_rejects_empty_file(client):
    resp = client.post("/api/analyze", files={"file": ("empty.csv", b"", "text/csv")})
    assert resp.status_code >= 400
    assert resp.status_code < 500


def test_analyze_rejects_unsupported_extension(client):
    resp = client.post("/api/analyze", files={"file": ("d.xml", b"<data/>", "text/xml")})
    assert resp.status_code == 400
