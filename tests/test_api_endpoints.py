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


def test_analyze_endpoint_handles_downcast_numpy_dtypes(client, rng):
    """Regression for a real, multi-layered bug: the chunked CSV reader
    downcasts to float32/int8 for memory savings, but numpy.float64
    happens to subclass Python's built-in float (so it always
    serialized fine by accident) while float32/int8 do not subclass
    anything JSON-aware -- every endpoint returning one immediately
    500'd. Needs an int column whose values genuinely fit in int8
    (small integers) to force that specific downcast path."""
    df = pd.DataFrame({
        "Sales": rng.uniform(10, 2000, 500).round(2),
        "SmallCount": rng.integers(1, 100, 500),  # fits in int8 after downcasting
    })
    resp = client.post("/api/analyze", files={"file": ("d.csv", df.to_csv(index=False).encode(), "text/csv")})
    assert resp.status_code == 200
    assert resp.json()["v2"]["profile"]["row_count"] == 500


def test_analyze_combined_endpoint(client, sales_df, healthcare_df):
    resp = client.post("/api/analyze-combined", files=[
        ("files", ("a.csv", sales_df.to_csv(index=False).encode(), "text/csv")),
        ("files", ("b.csv", healthcare_df.to_csv(index=False).encode(), "text/csv")),
    ])
    assert resp.status_code == 200


def test_analyze_endpoint_surfaces_a_changepoint(client, rng):
    """End-to-end: a dataset with an obvious one-time jump in its trend
    should come back with a `changepoint` field on the trend analysis,
    not just pass at the detect_changepoint() unit level."""
    dates, y, m = [], 2021, 1
    for _ in range(36):
        dates.append(pd.Timestamp(f"{y}-{m:02d}-15"))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    n_per_month = 20
    rows = []
    for i, d in enumerate(dates):
        base = 100 if i < 24 else 180
        for _ in range(n_per_month):
            rows.append({"Order Date": d, "Sales": base + float(rng.normal(0, 5))})
    df = pd.DataFrame(rows)

    resp = client.post("/api/analyze", files={
        "file": ("sales.csv", df.to_csv(index=False).encode(), "text/csv"),
    })
    assert resp.status_code == 200
    body = resp.json()

    trend_analyses = [a for a in body["v2"]["all_analyses"] if a.get("type") == "trend"]
    assert trend_analyses
    cps = [a["changepoint"] for a in trend_analyses if a.get("changepoint")]
    assert cps, "expected at least one trend analysis to carry a detected changepoint"
    assert cps[0]["direction"] == "jump"


def test_analyze_endpoint_surfaces_segment_forecasts(client, rng):
    """End-to-end: a dataset with a dimension whose segments move in
    different directions should come back with a segment_forecast
    entry in all_analyses, not just pass at the unit level."""
    dates, y, m = [], 2021, 1
    for _ in range(30):
        dates.append(pd.Timestamp(f"{y}-{m:02d}-15"))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    rows = []
    for i, d in enumerate(dates):
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "Furniture", "Sales": 200 - i * 4 + float(rng.normal(0, 8))})
        for _ in range(15):
            rows.append({"Order Date": d, "Category": "Technology", "Sales": 100 + i * 5 + float(rng.normal(0, 8))})
    df = pd.DataFrame(rows)

    resp = client.post("/api/analyze", files={
        "file": ("sales.csv", df.to_csv(index=False).encode(), "text/csv"),
    })
    assert resp.status_code == 200
    body = resp.json()

    sf = [a for a in body["v2"]["all_analyses"] if a.get("type") == "segment_forecast"]
    assert sf, "expected a segment_forecast entry in all_analyses"
    labels = {s["label"] for s in sf[0]["segments"]}
    assert "Furniture" in labels and "Technology" in labels


def test_analyze_joined_endpoint(client, sales_df):
    customers_df = pd.DataFrame({
        "Customer ID": range(1000, 1100),
        "Customer Segment": ["Consumer", "Corporate", "Home Office"] * 33 + ["Consumer"],
    })
    resp = client.post("/api/analyze-joined", files=[
        ("files", ("orders.csv", sales_df.to_csv(index=False).encode(), "text/csv")),
        ("files", ("customers.csv", customers_df.to_csv(index=False).encode(), "text/csv")),
    ])
    assert resp.status_code == 200
    body = resp.json()
    assert body["join_info"]["key_in_fact_file"] == "Customer ID"
    assert body["join_info"]["matched_rows"] == body["join_info"]["total_rows"]  # every customer ID exists in customers.csv
    assert body["v2"]["profile"]["row_count"] == 300  # every order row survived the join
    assert "Customer Segment" in body["semantic_roles"]  # the joined-in column made it through detection


def test_analyze_joined_endpoint_rejects_unrelated_files(client, sales_df, healthcare_df):
    resp = client.post("/api/analyze-joined", files=[
        ("files", ("a.csv", sales_df.to_csv(index=False).encode(), "text/csv")),
        ("files", ("b.csv", healthcare_df.to_csv(index=False).encode(), "text/csv")),
    ])
    assert resp.status_code == 400


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


def test_export_html_endpoint(client, sales_df):
    analyze_resp = client.post("/api/analyze", files={"file": ("d.csv", sales_df.to_csv(index=False).encode(), "text/csv")})
    v2 = analyze_resp.json()["v2"]
    resp = client.post("/api/export/html", json={"file_name": "d.csv", "v2": v2})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.text.startswith("<!DOCTYPE html>")
    assert "<script src" not in resp.text  # must stay self-contained, no external scripts
    assert "<link " not in resp.text  # no external stylesheets either


def test_export_html_escapes_special_characters(client):
    df = pd.DataFrame({
        "Category": ["<script>alert(1)</script>", "Normal Category"] * 15,
        "Sales": range(1, 31),
    })
    analyze_resp = client.post("/api/analyze", files={"file": ("d.csv", df.to_csv(index=False).encode(), "text/csv")})
    v2 = analyze_resp.json()["v2"]
    resp = client.post("/api/export/html", json={"file_name": "d.csv", "v2": v2})
    assert "<script>alert(1)</script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_share_create_and_retrieve(client, sales_df):
    analyze_resp = client.post("/api/analyze", files={"file": ("d.csv", sales_df.to_csv(index=False).encode(), "text/csv")})
    data = analyze_resp.json()

    share_resp = client.post("/api/share", json={"file_name": "d.csv", "kpis": data["kpis"], "v2": data["v2"]})
    assert share_resp.status_code == 200
    token = share_resp.json()["token"]
    assert share_resp.json()["share_path"] == f"/share/{token}"

    get_resp = client.get(f"/api/share/{token}")
    assert get_resp.status_code == 200
    assert get_resp.json()["file_name"] == "d.csv"
    assert get_resp.json()["v2"]["profile"]["domain"] == data["v2"]["profile"]["domain"]


def test_share_unknown_token_returns_404(client):
    resp = client.get("/api/share/this-token-does-not-exist")
    assert resp.status_code == 404


def test_share_oversized_payload_rejected(client):
    resp = client.post("/api/share", json={"file_name": "d.csv", "v2": {"data": "x" * (20 * 1024 * 1024)}})
    assert resp.status_code == 400


def test_analyze_rejects_empty_file(client):
    resp = client.post("/api/analyze", files={"file": ("empty.csv", b"", "text/csv")})
    assert resp.status_code >= 400
    assert resp.status_code < 500


def test_analyze_rejects_unsupported_extension(client):
    resp = client.post("/api/analyze", files={"file": ("d.xml", b"<data/>", "text/xml")})
    assert resp.status_code == 400
