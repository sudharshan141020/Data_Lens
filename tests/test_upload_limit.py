"""The upload size cap: configurable, and enforced WHILE reading.

Why this exists: a hosted instance with 512 MB of RAM was measured at ~620 MB peak on a 32 MB CSV
(500,000 rows), so the old fixed 250 MB cap would let one upload kill the process, and every
in-memory share link with it. And the old check ran after `await file.read()` had already pulled the
whole file into memory, so even a refused upload used the RAM first."""
import asyncio

import pytest
from fastapi import HTTPException

import app.main as main_module
from app.main import _max_file_size_mb, _read_upload, DEFAULT_MAX_FILE_SIZE_MB

MB = 1024 * 1024


class FakeUpload:
    """Hands out `chunks` of `size` bytes and counts how much was actually read."""
    def __init__(self, total_bytes, size=MB):
        self.remaining, self.size, self.reads, self.bytes_read = total_bytes, size, 0, 0

    async def read(self, n=-1):
        take = min(self.remaining, n if n and n > 0 else self.remaining, self.size)
        self.remaining -= take
        self.reads += 1
        self.bytes_read += take
        return b"x" * take


@pytest.fixture
def cap(monkeypatch):
    def set_cap(mb):
        monkeypatch.setattr(main_module, "MAX_FILE_SIZE_MB", mb)
    return set_cap


# ---------------------------------------------------------------------------
# the setting
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    (None, DEFAULT_MAX_FILE_SIZE_MB), ("", DEFAULT_MAX_FILE_SIZE_MB), ("15", 15.0), ("0.5", 0.5), ("  20 ", 20.0),
    ("abc", DEFAULT_MAX_FILE_SIZE_MB), ("0", DEFAULT_MAX_FILE_SIZE_MB), ("-5", DEFAULT_MAX_FILE_SIZE_MB),
    ("nan", DEFAULT_MAX_FILE_SIZE_MB), ("1e3", 1000.0),
])
def test_the_cap_comes_from_the_environment_and_a_bad_value_never_stops_the_app_starting(raw, expected, monkeypatch):
    monkeypatch.delenv("DATALENS_MAX_FILE_MB", raising=False)
    if raw is not None:
        monkeypatch.setenv("DATALENS_MAX_FILE_MB", raw)
    assert _max_file_size_mb() == expected


def test_an_explicit_argument_overrides_the_environment(monkeypatch):
    monkeypatch.setenv("DATALENS_MAX_FILE_MB", "99")
    assert _max_file_size_mb("7") == 7.0


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------
def test_a_file_under_the_cap_is_returned_byte_for_byte(cap):
    cap(5)
    up = FakeUpload(int(2.5 * MB))
    assert len(asyncio.run(_read_upload(up))) == int(2.5 * MB)


def test_an_empty_upload_is_an_empty_result_not_an_error(cap):
    cap(5)
    assert asyncio.run(_read_upload(FakeUpload(0))) == b""


def test_exactly_at_the_cap_is_accepted_and_one_byte_over_is_refused(cap):
    cap(2)
    assert len(asyncio.run(_read_upload(FakeUpload(2 * MB)))) == 2 * MB
    with pytest.raises(HTTPException) as e:
        asyncio.run(_read_upload(FakeUpload(2 * MB + 1)))
    assert e.value.status_code == 400


def test_an_oversized_upload_is_abandoned_part_way_not_read_to_the_end(cap):
    cap(2)
    up = FakeUpload(500 * MB)                   # a 500 MB upload against a 2 MB cap
    with pytest.raises(HTTPException):
        asyncio.run(_read_upload(up))
    assert up.bytes_read <= 3 * MB, f"read {up.bytes_read / MB:.0f} MB before refusing; it should stop at the cap"
    assert up.remaining > 490 * MB


def test_the_message_names_the_limit_in_force_not_a_hardcoded_number(cap):
    cap(15)
    with pytest.raises(HTTPException) as e:
        asyncio.run(_read_upload(FakeUpload(20 * MB)))
    assert "over the 15 MB limit" in e.value.detail and "splitting it into smaller files" in e.value.detail
    cap(0.5)
    with pytest.raises(HTTPException) as e:
        asyncio.run(_read_upload(FakeUpload(1 * MB)))
    assert "over the 0.5 MB limit" in e.value.detail


# ---------------------------------------------------------------------------
# the real endpoints
# ---------------------------------------------------------------------------
def _csv(n):
    return ("A,B\n" + "1,2\n" * n).encode()


@pytest.mark.parametrize("path,files", [
    ("/api/analyze", lambda big: {"file": ("big.csv", big, "text/csv")}),
])
def test_analyze_refuses_an_oversized_file_with_a_clear_message(client, cap, path, files):
    cap(1)
    resp = client.post(path, files=files(_csv(600_000)))      # ~2.3 MB
    assert resp.status_code == 400
    assert "over the 1 MB limit" in resp.json()["detail"]


def test_analyze_still_accepts_a_file_under_the_cap(client, cap, sales_df):
    cap(5)
    resp = client.post("/api/analyze", files={"file": ("ok.csv", sales_df.to_csv(index=False).encode(), "text/csv")})
    assert resp.status_code == 200


@pytest.mark.parametrize("path", ["/api/analyze-combined", "/api/analyze-joined"])
def test_the_multi_file_endpoints_enforce_it_too(client, cap, sales_df, path):
    cap(1)
    small = sales_df.to_csv(index=False).encode()
    resp = client.post(path, files=[("files", ("a.csv", small, "text/csv")), ("files", ("b.csv", _csv(600_000), "text/csv"))])
    assert resp.status_code == 400
    assert "over the 1 MB limit" in resp.json()["detail"]


def test_the_compare_endpoint_enforces_it_too(client, cap, sales_df):
    cap(1)
    small = sales_df.to_csv(index=False).encode()
    resp = client.post("/api/compare", files={"file_a": ("a.csv", small, "text/csv"), "file_b": ("b.csv", _csv(600_000), "text/csv")})
    assert resp.status_code == 400
    assert "over the 1 MB limit" in resp.json()["detail"]


def test_health_reports_the_cap_in_force(client, cap):
    assert client.get("/api/health").json() == {"status": "ok", "max_file_mb": main_module.MAX_FILE_SIZE_MB}
    cap(10)
    assert client.get("/api/health").json()["max_file_mb"] == 10
