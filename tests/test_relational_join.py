"""
Regression tests for app.relational_join -- auto-detecting a shared key
column between two differently-shaped files and joining them, as
opposed to kpi.py's combine_dataframes which stacks same-shaped files'
rows.
"""
import pandas as pd

from app.relational_join import detect_join_key, join_dataframes


def _orders_customers():
    customers = pd.DataFrame({
        "Customer_ID": ["C1", "C2", "C3", "C4", "C5"],
        "Customer Name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
        "Region": ["East", "West", "East", "West", "East"],
    })
    orders = pd.DataFrame({
        "Order_ID": ["O1", "O2", "O3", "O4", "O5", "O6", "O7"],
        "Customer_ID": ["C1", "C1", "C2", "C3", "C9", "C4", "C5"],  # C9 has no match in customers
        "Sales": [100, 150, 200, 80, 300, 50, 90],
        # Same column NAME as customers.Region but a totally different
        # meaning/value set -- must not be picked as the join key despite
        # matching by name, since it fails the uniqueness-on-one-side test.
        "Region": ["Furniture", "Tech", "Furniture", "Office", "Tech", "Furniture", "Office"],
    })
    return orders, customers


def test_detects_the_real_key_not_the_decoy_name_collision():
    orders, customers = _orders_customers()
    key = detect_join_key(orders, customers)
    assert key is not None
    assert key["column_a"] == "Customer_ID"
    assert key["column_b"] == "Customer_ID"
    assert key["overlap"] == 1.0


def test_join_keeps_all_fact_rows_including_unmatched():
    orders, customers = _orders_customers()
    key = detect_join_key(orders, customers)
    joined, info = join_dataframes(orders, customers, key, "orders.csv", "customers.csv")

    assert len(joined) == len(orders)  # every order row survives
    assert info["fact_file"] == "orders.csv"
    assert info["dimension_file"] == "customers.csv"
    assert info["matched_rows"] == 6
    assert info["unmatched_rows"] == 1
    assert info["match_rate_pct"] == 85.7

    unmatched_row = joined[joined["Customer_ID"] == "C9"].iloc[0]
    assert pd.isna(unmatched_row["Customer Name"])


def test_colliding_column_names_get_suffixed_not_silently_mangled():
    orders, customers = _orders_customers()
    key = detect_join_key(orders, customers)
    joined, info = join_dataframes(orders, customers, key, "orders.csv", "customers.csv")

    assert "Region (orders)" in joined.columns
    assert "Region (customers)" in joined.columns
    assert "Region" not in joined.columns  # the ambiguous original name shouldn't survive unqualified
    assert info["shared_column_names"] == ["Region"]
    # the two columns kept their own, unrelated values -- not merged/overwritten
    row = joined[joined["Order_ID"] == "O1"].iloc[0]
    assert row["Region (orders)"] == "Furniture"
    assert row["Region (customers)"] == "East"


def test_fact_side_detected_regardless_of_argument_order():
    """join_dataframes should figure out which side is the 'many' side
    from the key's own uniqueness, not from which argument came first."""
    orders, customers = _orders_customers()
    key = detect_join_key(orders, customers)
    # pass customers first, orders second -- should still treat orders as the fact side
    joined, info = join_dataframes(customers, orders, key, "customers.csv", "orders.csv")
    assert info["fact_file"] == "orders.csv"
    assert len(joined) == len(orders)


def test_no_key_found_between_unrelated_files():
    a = pd.DataFrame({"Widget": ["x", "y", "z"], "Price": [1, 2, 3]})
    b = pd.DataFrame({"Country": ["US", "UK"], "Population": [331, 67]})
    assert detect_join_key(a, b) is None


def test_low_cardinality_shared_category_is_not_treated_as_a_key():
    """Two files that both happen to have a 'Category' column with the
    same handful of values shouldn't be joined on it -- that's a shared
    dimension, not a relational key, and joining on it would fan out
    into a many-to-many cartesian mess instead of attaching one record
    to another."""
    a = pd.DataFrame({"Category": ["Furniture", "Tech", "Furniture", "Office"] * 5, "Sales": range(20)})
    b = pd.DataFrame({"Category": ["Furniture", "Tech", "Office"] * 5, "Budget": range(15)})
    assert detect_join_key(a, b) is None


def test_overlap_below_threshold_is_rejected():
    """Matching column name and high uniqueness on both sides, but the
    actual ID values barely overlap -- these are probably just two
    unrelated ID columns that happen to share a name, not a real
    relationship between the two files."""
    a = pd.DataFrame({"ID": [f"A{i}" for i in range(20)], "Sales": range(20)})
    b = pd.DataFrame({"ID": [f"B{i}" for i in range(20)], "Budget": range(20)})
    assert detect_join_key(a, b) is None
