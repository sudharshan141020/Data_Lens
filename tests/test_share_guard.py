"""app.share_guard -- the server-side personal-data check on share links.

What matters here is what the guard does NOT trust. A share payload is built by
the caller, so the report of what is sensitive can simply be left out; the server
has to find personal data from the payload itself. These tests build payloads by
hand, the way a script bypassing the UI would, and check four things: real data
is found, a false claim of "masked" does not hide it, an error response never
echoes a value, and no input can make the scan slow (a security check that a
single request can freeze is worse than none)."""
import json
import time

import pytest

from app.share_guard import scan_share_payload, blocking_findings, contains_email, refusal_message

SECRET_EMAIL = "zebra.unique@secret-corp.example"


def _v2(**kw):
    base = {"profile": {"columns": ["Region", "Sales"], "date_columns": []}, "findings": [{"text": "Sales fell 3%."}],
            "filterable_data": {"available": True, "dimension_columns": ["Region"], "measure_columns": ["Sales"],
                                "rows": [{"Region": "West", "Sales": 10}, {"Region": "East", "Sales": 12}]}}
    base.update(kw)
    return base


def _kinds(findings):
    return {(f["column"], f["kind"], f["source"]) for f in findings}


# ---------------------------------------------------------------------------
# finding personal data
# ---------------------------------------------------------------------------
def test_a_clean_result_has_no_findings():
    assert scan_share_payload(_v2()) == []


def test_email_addresses_in_the_row_data_are_found_by_their_values():
    rows = [{"Region": "West", "Contact": f"user{i}@{SECRET_EMAIL.split('@')[1]}"} for i in range(30)]
    v2 = _v2(profile={"columns": ["Region", "Contact"]}, filterable_data={"available": True, "rows": rows, "dimension_columns": ["Region", "Contact"], "measure_columns": []})
    f = scan_share_payload(v2)
    assert ("Contact", "email", "values") in _kinds(f)
    assert all(x["confidence"] == "high" for x in f if x["column"] == "Contact")


def test_a_person_identifier_is_found_by_its_name_even_when_it_is_not_in_the_rows():
    v2 = _v2(profile={"columns": ["Region", "Customer ID", "Sales"]})
    f = scan_share_payload(v2)
    assert ("Customer ID", "person_id", "header") in _kinds(f)
    assert all(x["maskable"] for x in f)


def test_the_at_risk_customer_list_counts_as_carrying_its_entity_column():
    v2 = _v2(profile={"columns": ["Region"]}, cohorts={"at_risk": {"entity_column": "Patient ID", "at_risk": [{"entity": 4001}]}})
    assert ("Patient ID", "person_id", "header") in _kinds(scan_share_payload(v2))


def test_emails_ssns_and_card_numbers_hiding_in_the_text_are_found():
    v2 = _v2(findings=[{"text": f"Top buyer {SECRET_EMAIL} spent 40"}, {"text": "ref 123-45-6789 on file"}],
             notes=["4111 1111 1111 1111"])
    kinds = {k for (_c, k, s) in _kinds(scan_share_payload(v2)) if s == "text"}
    assert kinds == {"email", "gov_id", "card"}
    assert all(not f["maskable"] and f["column"] is None for f in scan_share_payload(v2) if f["source"] == "text")


def test_a_card_number_needs_a_valid_checksum_and_to_be_the_whole_string():
    assert not scan_share_payload(_v2(notes=["4111 1111 1111 1112"]))                   # fails Luhn
    assert not scan_share_payload(_v2(notes=["order 4111111111111111 shipped"]))        # a sentence, not a number
    assert scan_share_payload(_v2(notes=["4111111111111111"]))


def test_dates_and_ordinary_numbers_are_not_mistaken_for_ids():
    v2 = _v2(findings=[{"text": "Between 2024-05-01 and 2024-06-30 sales were 1,234,567 across 162 orders (12.5%)."}])
    assert scan_share_payload(v2) == []


# ---------------------------------------------------------------------------
# what a caller's claims can and cannot hide
# ---------------------------------------------------------------------------
def test_a_declared_mask_suppresses_a_name_based_finding():
    v2 = _v2(profile={"columns": ["Region", "Customer ID"]},
             sensitive_data={"columns": [{"column": "Customer ID", "kind": "person_id", "confidence": "medium", "masked": True}]})
    assert scan_share_payload(v2) == []


def test_a_declared_mask_does_NOT_hide_real_values_still_in_the_rows():
    rows = [{"Region": "West", "Contact": f"user{i}@example.org"} for i in range(30)]
    v2 = _v2(profile={"columns": ["Region", "Contact"]},
             filterable_data={"available": True, "rows": rows, "dimension_columns": ["Region", "Contact"], "measure_columns": []},
             sensitive_data={"columns": [{"column": "Contact", "kind": "email", "confidence": "high", "masked": True}]})
    assert ("Contact", "email", "values") in _kinds(scan_share_payload(v2))        # lying about masking changes nothing


def test_leaving_the_report_out_entirely_does_not_help():
    rows = [{"Region": "West", "Contact": f"user{i}@example.org"} for i in range(30)]
    v2 = _v2(profile={"columns": ["Region", "Contact"]},
             filterable_data={"available": True, "rows": rows, "dimension_columns": ["Region", "Contact"], "measure_columns": []})
    assert "sensitive_data" not in v2
    assert blocking_findings(scan_share_payload(v2))


def test_properly_masked_rows_pass():
    rows = [{"Region": "West", "Contact": f"Contact {i}"} for i in range(30)]                  # pseudonyms, as the UI produces
    v2 = _v2(profile={"columns": ["Region", "Contact"]},
             filterable_data={"available": True, "rows": rows, "dimension_columns": ["Region", "Contact"], "measure_columns": []},
             sensitive_data={"columns": [{"column": "Contact", "kind": "email", "confidence": "high", "masked": True}]})
    assert blocking_findings(scan_share_payload(v2)) == []


def test_only_medium_and_high_confidence_findings_block():
    v2 = _v2(profile={"columns": ["Region", "Address"]})                                       # a bare "Address" header is "low"
    f = scan_share_payload(v2)
    assert f and all(x["confidence"] == "low" for x in f)
    assert blocking_findings(f) == []


def test_findings_are_sorted_strongest_first():
    v2 = _v2(profile={"columns": ["Region", "Address", "Customer ID"]}, findings=[{"text": SECRET_EMAIL}])
    assert [f["confidence"] for f in scan_share_payload(v2)] == ["high", "medium", "low"]


# ---------------------------------------------------------------------------
# the response must never echo a value
# ---------------------------------------------------------------------------
def test_findings_and_the_refusal_message_never_contain_a_raw_value():
    rows = [{"Region": "West", "Contact": SECRET_EMAIL} for _ in range(30)]
    v2 = _v2(profile={"columns": ["Region", "Contact"]},
             filterable_data={"available": True, "rows": rows, "dimension_columns": ["Region", "Contact"], "measure_columns": []},
             findings=[{"text": f"call {SECRET_EMAIL} or 123-45-6789"}], notes=["4111 1111 1111 1111"])
    f = scan_share_payload(v2)
    blob = json.dumps(f) + refusal_message(f)
    for secret in (SECRET_EMAIL, "secret-corp", "123-45-6789", "4111"):
        assert secret not in blob


def test_the_refusal_message_names_columns_and_tells_the_caller_how_to_proceed():
    f = scan_share_payload(_v2(profile={"columns": ["Region", "Customer ID"]}))
    msg = refusal_message(f)
    assert "Customer ID" in msg and "acknowledge_personal_data" in msg and "anyone who has the link" in msg


# ---------------------------------------------------------------------------
# email detection
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("a@b.co", True), ("see ann.lee+tag@corp.example.org today", True), ("x" * 200 + "@y.com", True),
    ("not an email", False), ("@handle", False), ("user@", False), ("user@host", False), ("user@host.c", False),
    ("a@b@c.com", True), ("tweet me @someone", False), ("price @ 5.99 each", False), ("", False),
])
def test_contains_email(text, expected):
    assert contains_email(text) is expected


# ---------------------------------------------------------------------------
# a security check must not be a denial-of-service
# ---------------------------------------------------------------------------
# NOTE: the payloads are built INSIDE the test from a small factory, never passed as parametrize
# values. pytest puts a test's parameters in its name, and the name goes into the PYTEST_CURRENT_TEST
# environment variable; a multi-megabyte parameter made that name multi-megabyte, which Windows
# rejects (environment variables are capped at 32,767 characters) while Linux does not -- so this
# passed in CI and failed on a Windows machine. conftest.py now fails collection if any test name is long.
_HOSTILE = {
    "long-run-with-no-at-sign": lambda: "x" * 14_000_000,      # the case that froze the first version
    "long-run-ending-in-at": lambda: "x" * 5_000_000 + "@",
    "nothing-but-at-signs": lambda: "@" * 5_000_000,
    "many-half-emails": lambda: "a@" * 2_500_000,
    "long-local-part-then-junk-domain": lambda: ("a" * 60 + "@") * 50_000,
    "long-digit-run": lambda: "1" * 5_000_000,
    "dashes-and-dots": lambda: ".-" * 3_000_000,
}


@pytest.mark.parametrize("case", list(_HOSTILE))
def test_pathological_text_is_scanned_in_linear_time(case):
    payload = _HOSTILE[case]()
    started = time.perf_counter()
    scan_share_payload(_v2(findings=[{"text": payload}]))
    assert time.perf_counter() - started < 5.0, f"too slow on: {case}"


def test_a_huge_number_of_columns_and_rows_does_not_blow_up():
    rows = [{f"c{j}": f"value {i}" for j in range(20)} for i in range(5_000)]
    v2 = _v2(profile={"columns": [f"c{j}" for j in range(20)]}, filterable_data={"available": True, "rows": rows, "dimension_columns": [], "measure_columns": []})
    started = time.perf_counter()
    scan_share_payload(v2)
    assert time.perf_counter() - started < 10.0


@pytest.mark.parametrize("v2", [None, [], "x", 5, {}, {"filterable_data": "nope"}, {"filterable_data": {"rows": "nope"}},
                                {"filterable_data": {"rows": [1, 2, 3]}}, {"profile": {"columns": [None, 5, ["x"]]}},
                                {"sensitive_data": {"columns": "nope"}}, {"cohorts": {"at_risk": "nope"}}])
def test_malformed_payloads_never_crash_the_scan(v2):
    scan_share_payload(v2)


# ---------------------------------------------------------------------------
# through the real endpoint
# ---------------------------------------------------------------------------
def _share(client, v2, **extra):
    return client.post("/api/share", json={"file_name": "d.csv", "kpis": {}, "v2": v2, **extra})


def test_endpoint_refuses_with_409_and_names_what_it_found_without_echoing_it(client):
    v2 = _v2(findings=[{"text": f"Top buyer {SECRET_EMAIL}"}], profile={"columns": ["Region", "Customer ID"]})
    resp = _share(client, v2)
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "personal_data" and body["detail"]
    assert {f["kind"] for f in body["findings"]} == {"email", "person_id"}
    assert SECRET_EMAIL not in resp.text and "secret-corp" not in resp.text


def test_endpoint_accepts_it_when_the_caller_explicitly_acknowledges(client):
    v2 = _v2(findings=[{"text": f"Top buyer {SECRET_EMAIL}"}])
    assert _share(client, v2).status_code == 409
    ok = _share(client, v2, acknowledge_personal_data=True)
    assert ok.status_code == 200
    assert client.get(f"/api/share/{ok.json()['token']}").status_code == 200


def test_endpoint_accepts_a_clean_result_without_any_flag(client):
    assert _share(client, _v2()).status_code == 200


def test_endpoint_accepts_a_correctly_masked_result(client):
    v2 = _v2(profile={"columns": ["Region", "Customer ID"]},
             sensitive_data={"columns": [{"column": "Customer ID", "kind": "person_id", "confidence": "medium", "masked": True}]})
    assert _share(client, v2).status_code == 200


def test_endpoint_bypassing_the_ui_with_no_report_is_refused(client):
    rows = [{"Region": "West", "Contact": f"u{i}@example.org"} for i in range(30)]
    v2 = _v2(profile={"columns": ["Region", "Contact"]}, filterable_data={"available": True, "rows": rows, "dimension_columns": ["Region", "Contact"], "measure_columns": []})
    assert _share(client, v2).status_code == 409


def test_oversized_payloads_are_rejected_before_they_are_scanned(client):
    started = time.perf_counter()
    resp = _share(client, {"data": "x" * (20 * 1024 * 1024)})
    assert resp.status_code == 400 and "too large" in resp.json()["detail"]
    assert time.perf_counter() - started < 5.0


def test_the_real_pipeline_output_is_refused_then_accepted_when_acknowledged(client, sales_df):
    data = client.post("/api/analyze", files={"file": ("d.csv", sales_df.to_csv(index=False).encode(), "text/csv")}).json()
    first = client.post("/api/share", json={"file_name": "d.csv", "kpis": data["kpis"], "v2": data["v2"]})
    assert first.status_code == 409
    assert "Customer ID" in {f["column"] for f in first.json()["findings"]}
    second = client.post("/api/share", json={"file_name": "d.csv", "kpis": data["kpis"], "v2": data["v2"], "acknowledge_personal_data": True})
    assert second.status_code == 200


def test_a_real_email_column_that_reaches_the_payload_is_refused_even_after_the_client_report_is_stripped(client, sales_df):
    # five distinct addresses: low enough cardinality to become a chart category and row-level column
    emails = [f"person{i % 5}@example.org" for i in range(len(sales_df))]
    df = sales_df.drop(columns=["Customer ID"]).assign(Contact=emails)
    data = client.post("/api/analyze", files={"file": ("d.csv", df.to_csv(index=False).encode(), "text/csv")}).json()
    v2 = data["v2"]
    assert any(c["column"] == "Contact" for c in v2["sensitive_data"]["columns"])         # the app did notice...
    assert "person0@example.org" in json.dumps(v2)                                        # ...and the values really are in the result
    v2.pop("sensitive_data")                                                              # ...but a bypassing caller drops the report
    resp = client.post("/api/share", json={"file_name": "d.csv", "kpis": data["kpis"], "v2": v2})
    assert resp.status_code == 409
    assert "Contact" in {f["column"] for f in resp.json()["findings"]}
    assert "person0@example.org" not in resp.text


def test_a_personal_column_whose_values_never_reach_the_payload_does_not_block_sharing(client, sales_df):
    """The guard protects what is being PUBLISHED, not what was uploaded. 300 unique addresses are too many to be a
    chart category or a row-level column, so the analysis never carries them and the link cannot leak them."""
    emails = [f"person{i}@example.org" for i in range(len(sales_df))]
    df = sales_df.drop(columns=["Customer ID"]).assign(Contact=emails)
    data = client.post("/api/analyze", files={"file": ("d.csv", df.to_csv(index=False).encode(), "text/csv")}).json()
    v2 = data["v2"]
    assert "person0@example.org" not in json.dumps(v2)
    v2.pop("sensitive_data")
    assert client.post("/api/share", json={"file_name": "d.csv", "kpis": data["kpis"], "v2": v2}).status_code == 200
