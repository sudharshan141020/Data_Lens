"""
File format loading tests. CSV, TSV, JSON (in its several real-world
shapes), and Parquet should all produce an equivalent DataFrame, and
everything downstream should treat them identically -- format is a
loading-time concern only, never a pipeline concern.
"""
import io
import json

import pandas as pd
import pytest

from app.main import _load_dataframe


def test_csv_and_json_records_produce_equivalent_dataframe(sales_df):
    csv_bytes = sales_df.to_csv(index=False).encode()
    json_bytes = json.dumps(
        sales_df.assign(**{"Order Date": sales_df["Order Date"].astype(str)}).to_dict(orient="records")
    ).encode()

    df_csv = _load_dataframe("data.csv", csv_bytes)
    df_json = _load_dataframe("data.json", json_bytes)

    assert list(df_csv.columns) == list(df_json.columns)
    assert len(df_csv) == len(df_json)


def test_json_wrapped_records_shape(sales_df):
    """{"data": [...]} -- a common API-export wrapper shape."""
    wrapped = {"meta": {"count": len(sales_df)}, "data": sales_df.head(10).assign(
        **{"Order Date": sales_df.head(10)["Order Date"].astype(str)}
    ).to_dict(orient="records")}
    df = _load_dataframe("data.json", json.dumps(wrapped).encode())
    assert len(df) == 10


def test_json_columns_orientation():
    data = {"Name": ["A", "B", "C"], "Value": [1, 2, 3]}
    df = _load_dataframe("data.json", json.dumps(data).encode())
    assert len(df) == 3
    assert list(df.columns) == ["Name", "Value"]


def test_json_one_level_nested_flattens():
    data = [{"Name": "A", "Address": {"City": "SF", "Zip": "94103"}}]
    df = _load_dataframe("data.json", json.dumps(data).encode())
    assert "Address.City" in df.columns
    assert "Address.Zip" in df.columns


def test_malformed_json_raises_clean_error():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _load_dataframe("data.json", b"{not valid json")


def test_parquet_round_trip(sales_df):
    buf = io.BytesIO()
    sales_df.to_parquet(buf, index=False)
    df = _load_dataframe("data.parquet", buf.getvalue())
    assert df.shape == sales_df.shape
    assert list(df.columns) == list(sales_df.columns)


def test_corrupt_parquet_raises_clean_error():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _load_dataframe("data.parquet", b"not a real parquet file")


def test_unsupported_extension_raises_clean_error():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _load_dataframe("data.xml", b"<data></data>")


def test_tsv_delimiter_parsed_correctly():
    tsv_text = "Name\tRevenue\nAcme\t100\nBeta\t200\n"
    df = _load_dataframe("data.tsv", tsv_text.encode())
    assert list(df.columns) == ["Name", "Revenue"]
    assert len(df) == 2
