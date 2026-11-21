"""
Column-name classification: a role must come from the whole word.

Both halves of this are the same failure: a keyword matched a *fragment* of a
name and decided what the column was. "Paid" contains "id", so it became an
IDENTIFIER and was dropped from every measure; "Usage" and "Package" contain
"age", so they became AGE. Separately, the generic time words were substring
matches too, so a duration like "lead_time" became a DATE and was then coerced
to NaT -- the column disappeared from the dashboard without an error.

These tests pin the rule: a keyword has to line up with whole tokens, camelCase
is split so "CustomerID" still reads as "customer id", and the generic time
words only match a column actually named that.
"""
import pandas as pd
import pytest

from app.semantic_roles import classify_columns
from app.understanding import understand_dataset


def _role(header, values):
    return classify_columns(pd.DataFrame({header: values}))[header]["role"]


@pytest.mark.parametrize("header", ["Paid", "Invalid", "Void", "Rapid"])
def test_an_id_inside_a_word_does_not_make_it_an_identifier(header):
    assert _role(header, [1.5, 2.5, 3.5, 1.5]) != "IDENTIFIER"


@pytest.mark.parametrize("header", ["Usage", "Package", "Mileage", "Language"])
def test_an_id_inside_a_word_does_not_make_it_an_identifier_variant(header):
    assert _role(header, [1.5, 2.5, 3.5, 1.5]) != "AGE"


@pytest.mark.parametrize("header", ["lead_time", "delivery_time_minutes", "response_time", "days_to_ship"])
def test_a_duration_is_not_a_date(header):
    assert _role(header, [1.5, 2.5, 3.5, 1.5]) != "DATE"


@pytest.mark.parametrize("header,values,expected", [
    ("Time", pd.date_range("2024-01-01", periods=4, freq="D"), "DATE"),      # a column actually named that
    ("Order Date", pd.date_range("2024-01-01", periods=4, freq="D"), "DATE"),
    ("delivery_date", pd.date_range("2024-01-01", periods=4, freq="D"), "DATE"),  # confirmed by its values
    ("CustomerID", ["a", "b", "a", "b"], "CUSTOMER"),                       # camelCase still matches
    ("order_id", [10, 11, 12, 13], "IDENTIFIER"),
    ("Gross Sales", [1.5, 2.5, 3.5, 1.5], "FINANCIAL_METRIC"),
])
def test_the_useful_matches_still_work(header, values, expected):
    assert _role(header, values) == expected


# ---------------------------------------------------------------------------
# the profile built on top of those roles
# ---------------------------------------------------------------------------
def _profile(**columns):
    return understand_dataset(pd.DataFrame(columns))


def test_the_date_axis_is_not_a_birth_date():
    """ "Date of Birth" is a DATE column, but it is not the timeline of the file."""
    df = pd.DataFrame({
        "Date of Birth": pd.date_range("1970-01-01", periods=40, freq="D"),
        "Admission Date": pd.date_range("2024-01-01", periods=40, freq="D"),
        "Billing Amount": [100.0 + i for i in range(40)],
    })
    assert understand_dataset(df).date_column == "Admission Date"


def test_the_date_axis_is_chosen_by_completeness_not_by_column_order():
    """The old choice was "whichever DATE column comes first", so a half-empty one
    first in the file produced an empty trend next to a complete one."""
    df = pd.DataFrame({
        "Discharge Date": pd.Series([pd.Timestamp("2024-01-01")] * 20 + [pd.NaT] * 20),
        "Order Date": pd.date_range("2024-01-01", periods=40, freq="D"),
        "Sales": [10.0] * 40,
    })
    assert understand_dataset(df).date_column == "Order Date"


def test_a_binary_flag_is_not_a_measure():
    """The sum of a 0/1 column is its count, not a headline KPI -- and because the
    fallback ran in column order, a flag could take the primary-measure slot."""
    df = pd.DataFrame({
        "Region": ["East", "West", "North", "South"] * 10,
        "Sales": [10.0 + i for i in range(40)],
        "Returned": [0, 1] * 20,
    })
    profile = understand_dataset(df)
    assert "Returned" not in [m.column for m in profile.measures]
    assert profile.primary_measure.column == "Sales"


def test_a_numeric_dimension_is_not_summed_as_a_measure():
    df = pd.DataFrame({
        "Store": [1, 2, 3, 1] * 10,
        "Sales": [10.0 + i for i in range(40)],
    })
    assert "Store" not in [m.column for m in understand_dataset(df).measures]


def test_a_flag_is_still_used_when_it_is_the_only_numeric_column():
    """Excluding flags must not leave a file with nothing to analyse."""
    df = pd.DataFrame({"Region": ["East", "West"] * 20, "Returned": [0, 1] * 20})
    assert [m.column for m in understand_dataset(df).measures] == ["Returned"]
