"""Sensitive-data detector: what it must flag, what it must NOT flag, and
the one hard rule -- the report never contains a raw value (it is stored in
`v2`, which is exactly what a share link / export carries)."""
import json

import numpy as np
import pandas as pd
import pytest

from app.sensitive_data import detect_sensitive_data, _luhn_ok


def _kinds(report):
    return {c["column"]: (c["kind"], c["confidence"]) for c in report["columns"]}


def _frame(n=200, **cols):
    return pd.DataFrame({k: (v(n) if callable(v) else v) for k, v in cols.items()})


def test_flags_emails_by_header_and_values_as_high_confidence():
    df = _frame(Email=lambda n: [f"user{i}@example.com" for i in range(n)])
    assert _kinds(detect_sensitive_data(df))["Email"] == ("email", "high")


def test_flags_emails_by_values_alone_even_under_a_vague_header():
    df = _frame(Contact=lambda n: [f"a{i}@b.org" for i in range(n)])
    assert _kinds(detect_sensitive_data(df))["Contact"] == ("email", "high")


def test_phone_numbers_by_value_pattern_and_by_header():
    rng = np.random.default_rng(0)
    df = _frame(Mobile=lambda n: [f"+91 98{rng.integers(10**7, 10**8 - 1)}" for _ in range(n)],
                Phone=lambda n: [f"555-01{i % 100:02d}" for i in range(n)])
    k = _kinds(detect_sensitive_data(df))
    assert k["Mobile"][0] == "phone" and k["Phone"][0] == "phone"


def test_card_numbers_need_a_valid_luhn_checksum():
    assert _luhn_ok("4111111111111111")
    assert not _luhn_ok("4111111111111112")
    good = _frame(X=lambda n: ["4111 1111 1111 1111"] * n)
    bad = _frame(X=lambda n: ["4111 1111 1111 1112"] * n)
    assert _kinds(detect_sensitive_data(good)).get("X") == ("card", "high")
    assert "X" not in _kinds(detect_sensitive_data(bad))


def test_government_id_patterns():
    df = _frame(Ref=lambda n: [f"{100 + i % 800:03d}-{10 + i % 80:02d}-{1000 + i:04d}" for i in range(n)])
    assert _kinds(detect_sensitive_data(df))["Ref"] == ("gov_id", "high")


def test_person_ids_flag_but_row_order_product_ids_do_not():
    rng = np.random.default_rng(1)
    df = _frame(**{
        "Customer ID": lambda n: rng.integers(1000, 1040, n),
        "patient_id": lambda n: [f"P{i}" for i in range(n)],
        "EmployeeID": lambda n: rng.integers(1, 50, n),
        "Order ID": lambda n: [f"CA-2023-{i}" for i in range(n)],
        "Row ID": lambda n: list(range(n)),
        "Product ID": lambda n: [f"FUR-{i}" for i in range(n)],
    })
    k = _kinds(detect_sensitive_data(df))
    assert {"Customer ID", "patient_id", "EmployeeID"} <= set(k)
    assert not ({"Order ID", "Row ID", "Product ID"} & set(k))


def test_numeric_measures_are_never_mistaken_for_phone_numbers():
    rng = np.random.default_rng(2)
    df = _frame(Sales=lambda n: rng.normal(1_000_000, 5000, n).round(2),
                Units=lambda n: rng.integers(1_000_000_000, 9_999_999_999, n))
    assert detect_sensitive_data(df)["has_sensitive"] is False


def test_dates_and_ordinary_categories_are_not_flagged():
    df = _frame(**{
        "Order Date": lambda n: pd.date_range("2023-01-01", periods=n).strftime("%Y-%m-%d"),
        "Region": lambda n: ["East", "West"] * (n // 2),
        "Product Name": lambda n: [f"Widget {i}" for i in range(n)],
        "City": lambda n: ["Pune", "Delhi"] * (n // 2),
    })
    assert detect_sensitive_data(df)["has_sensitive"] is False


def test_header_hints_describing_something_about_the_field_are_ignored():
    df = _frame(**{"Phone Model": lambda n: ["Pixel"] * n, "Address Type": lambda n: ["Home"] * n,
                   "Email Count": lambda n: list(range(n)), "Mail Order": lambda n: ["Y", "N"] * (n // 2)})
    assert detect_sensitive_data(df)["has_sensitive"] is False


def test_person_names_need_name_shaped_values_with_high_cardinality():
    first = ["Asha", "Ravi", "Meera", "Karthik", "Divya", "Arjun", "Sneha", "Vikram", "Pooja", "Nikhil"]
    last = ["Rao", "Iyer", "Nair", "Shah", "Das", "Menon", "Gupta", "Reddy", "Patel", "Singh"]
    names = [f"{a} {b}" for a in first for b in last][:100]
    df = pd.DataFrame({"Customer Name": names, "Product Name": [f"Gadget {i}" for i in range(100)]})
    k = _kinds(detect_sensitive_data(df))
    assert k["Customer Name"][0] == "person_name"
    assert "Product Name" not in k


def test_risk_level_follows_the_strongest_finding():
    low = pd.DataFrame({"Address": ["x"] * 50})
    high = pd.DataFrame({"Email": [f"a{i}@b.com" for i in range(50)]})
    assert detect_sensitive_data(low)["risk"] == "low"
    assert detect_sensitive_data(high)["risk"] == "high"
    assert detect_sensitive_data(pd.DataFrame({"Sales": [1.0, 2.0]}))["risk"] == "none"


def test_report_never_contains_a_raw_value():
    secret_email, secret_card = "zebra.unique@secret-corp.example", "4111 1111 1111 1111"
    df = pd.DataFrame({"Email": [secret_email] * 30, "Card": [secret_card] * 30, "Customer ID": range(30)})
    blob = json.dumps(detect_sensitive_data(df))
    assert "zebra" not in blob and "secret-corp" not in blob and "4111" not in blob


def test_empty_and_odd_frames_do_not_crash():
    assert detect_sensitive_data(pd.DataFrame())["has_sensitive"] is False
    odd = pd.DataFrame({"Email": [None, None], "x": [object(), object()], "mixed": [1, "a@b.co"]})
    detect_sensitive_data(odd)  # must simply not raise


def test_only_a_sample_is_inspected_but_rates_still_hold_on_big_files():
    n = 50_000
    df = pd.DataFrame({"Email": [f"u{i}@x.io" for i in range(n)]})
    r = detect_sensitive_data(df)
    assert r["rows_scanned"] == 2000 and _kinds(r)["Email"] == ("email", "high")
