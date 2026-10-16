"""
The dataset and captured backend response behind the frontend's integration
tests (frontend/src/App.test.jsx).

Why this exists: a frontend test that mocks /api/analyze with a hand-written
object only proves the UI works against what the author *imagined* the
backend returns. Capturing a REAL response from the real backend, and
failing a backend test when its shape drifts from the capture
(tests/test_frontend_fixture_contract.py), closes that gap -- the frontend
tests can't quietly keep passing against a response shape that no longer
exists.

Regenerate after any intentional change to the API response shape:

    python scripts/regenerate_frontend_fixture.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "test" / "fixtures"
CSV_PATH = FIXTURE_DIR / "analysis.csv"
JSON_PATH = FIXTURE_DIR / "analysis.json"
UPLOAD_NAME = "sales.csv"


def make_csv() -> bytes:
    """A small, fully deterministic sales-style file, shaped so the
    interesting features actually fire: one declining and one growing
    category (segment forecasts, trend), discounts that eat profit (margin /
    discount weak points), and repeat customers (cohorts)."""
    rng = np.random.default_rng(7)
    months = pd.date_range("2023-01-01", periods=18, freq="MS")
    customers = [1000 + i for i in range(40)]
    categories = (
        ("Furniture", 220.0, -6.0, -0.05),
        ("Technology", 120.0, 7.0, 0.30),
        ("Office Supplies", 90.0, 0.5, 0.18),
    )
    rows = []
    for m_i, month in enumerate(months):
        for category, base, slope, margin in categories:
            for _ in range(3):
                discount = float(rng.choice([0.0, 0.1, 0.2, 0.4]))
                sales = round(max(base + slope * m_i + float(rng.normal(0, 8)), 5.0), 2)
                profit = round(sales * (margin - discount * 0.6) + float(rng.normal(0, 2)), 2)
                rows.append({
                    "Order Date": (month + pd.Timedelta(days=int(rng.integers(0, 28)))).strftime("%Y-%m-%d"),
                    "Customer ID": int(rng.choice(customers)),
                    "Category": category,
                    "Region": str(rng.choice(["East", "West", "North"])),
                    "Sales": sales,
                    "Profit": profit,
                    "Discount": discount,
                    "Quantity": int(rng.integers(1, 8)),
                })
    return pd.DataFrame(rows).to_csv(index=False).encode()


def capture_response(client) -> dict:
    """POST the fixture CSV to the real /api/analyze and return its JSON."""
    resp = client.post("/api/analyze", files={"file": (UPLOAD_NAME, make_csv(), "text/csv")})
    assert resp.status_code == 200, resp.text
    return resp.json()
