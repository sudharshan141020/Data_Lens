"""
Shared fixtures for the DataLens test suite.

Datasets here are synthetic and deliberately small/fast -- this suite is
meant to run in seconds on every change, not to be a substitute for the
manual testing against real sample data that happens during development
(see each feature's CHANGES.md for that). Its job is to catch
regressions: things that used to work breaking silently as the codebase
grows, especially the kind of "fixed in one place, still broken in
another" bug this project has a documented history of.
"""
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def rng():
    return np.random.default_rng(42)


@pytest.fixture
def sales_df(rng):
    n = 300
    dates = pd.date_range("2022-01-01", periods=24, freq="MS")
    return pd.DataFrame({
        "Order Date": rng.choice(dates, n),
        "Customer ID": rng.integers(1000, 1100, n),
        "Category": rng.choice(["Furniture", "Technology", "Office Supplies"], n),
        "Region": rng.choice(["East", "West", "North", "South"], n),
        "Sales": rng.uniform(10, 2000, n).round(2),
        "Profit": rng.uniform(-200, 500, n).round(2),
        "Discount": rng.uniform(0, 0.6, n).round(2),
        "Quantity": rng.integers(1, 10, n),
    })


@pytest.fixture
def healthcare_df(rng):
    n = 300
    return pd.DataFrame({
        "Patient ID": rng.integers(1, 400, n),
        "Admission Date": pd.date_range("2023-01-01", periods=n, freq="D"),
        "Condition": rng.choice(["Diabetes", "Hypertension", "Asthma", "Flu"], n),
        "Hospital": rng.choice(["General", "St. Mary's", "City Med"], n),
        "Billing Amount": rng.uniform(500, 20000, n).round(2),
        "Age": rng.integers(1, 95, n),
    })


@pytest.fixture
def real_estate_df(rng):
    n = 300
    sqft = rng.normal(1800, 500, n).clip(500, 5000)
    bedrooms = rng.integers(1, 6, n)
    listing_price = sqft * 180 + bedrooms * 5000 + rng.normal(0, 20000, n)
    return pd.DataFrame({
        "Property Type": rng.choice(["House", "Condo", "Townhouse", "Apartment"], n),
        "Square Footage": sqft.round(0),
        "Bedrooms": bedrooms,
        "Bathrooms": rng.integers(1, 4, n),
        "Listing Price": listing_price.round(0),
        "Sale Price": (listing_price * rng.uniform(0.92, 1.02, n)).round(0),
        "Days on Market": rng.integers(5, 120, n),
        "City": rng.choice(["Austin", "Denver", "Portland", "Nashville"], n),
    })


@pytest.fixture
def saas_df(rng):
    n = 300
    plans = rng.choice(["Free", "Starter", "Pro", "Enterprise"], n)
    mrr = rng.exponential(80, n) * np.where(plans == "Enterprise", 10, np.where(plans == "Pro", 3, 1))
    return pd.DataFrame({
        "Subscription Plan": plans,
        "MRR": mrr.round(2),
        "Churn Status": rng.choice(["Active", "Churned"], n, p=[0.85, 0.15]),
        "Seats": rng.integers(1, 50, n),
        "NPS Score": rng.integers(-100, 100, n),
        "Customer ID": [f"CUST{i}" for i in range(n)],
    })
