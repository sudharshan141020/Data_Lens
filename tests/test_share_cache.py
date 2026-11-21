"""
The share cache's memory bounds.

MAX_ENTRIES alone never bounded memory: 500 entries at the 15MB per-entry cap is
7.5GB, far past the 512MB instance this app is deployed on. These tests pin the
total-byte budget and the eviction that keeps it, which is the cap that actually
matters on a small host.
"""
import pytest

from app import share_cache


@pytest.fixture(autouse=True)
def _clean_store(monkeypatch):
    monkeypatch.setattr(share_cache, "_store", {})
    monkeypatch.setattr(share_cache, "_total_bytes", 0)
    yield


def _payload(size: int) -> dict:
    """A payload whose JSON serialisation is roughly `size` bytes."""
    return {"v2": {"data": "x" * size}}


def test_the_total_budget_evicts_instead_of_growing(monkeypatch):
    monkeypatch.setattr(share_cache, "MAX_ENTRIES", 500)       # the count cap is not what binds
    monkeypatch.setattr(share_cache, "MAX_ENTRY_BYTES", 10_000)
    monkeypatch.setattr(share_cache, "MAX_TOTAL_BYTES", 5_000)

    tokens = [share_cache.create_share(_payload(1_000))[0] for _ in range(10)]

    assert share_cache._total_bytes <= 5_000
    assert len(share_cache._store) <= 5
    # The newest link survives; the oldest was evicted to make room for it.
    assert share_cache.get_share(tokens[-1]) is not None
    assert share_cache.get_share(tokens[0]) is None


def test_a_payload_larger_than_the_whole_budget_is_refused_not_stored(monkeypatch):
    monkeypatch.setattr(share_cache, "MAX_ENTRY_BYTES", 10_000)
    monkeypatch.setattr(share_cache, "MAX_TOTAL_BYTES", 500)
    with pytest.raises(ValueError):
        share_cache.create_share(_payload(1_000))
    assert share_cache._store == {} and share_cache._total_bytes == 0


def test_the_per_entry_cap_still_applies(monkeypatch):
    monkeypatch.setattr(share_cache, "MAX_ENTRY_BYTES", 100)
    with pytest.raises(ValueError):
        share_cache.create_share(_payload(1_000))


def test_an_expired_entry_gives_its_bytes_back(monkeypatch):
    monkeypatch.setattr(share_cache, "TTL_SECONDS", -1)        # already expired on insert
    token, _ = share_cache.create_share(_payload(1_000))
    assert share_cache._total_bytes > 0

    assert share_cache.get_share(token) is None
    assert share_cache._store == {}
    assert share_cache._total_bytes == 0


def test_a_retrieved_share_is_unchanged(monkeypatch):
    token, expires_at = share_cache.create_share(_payload(50))
    assert share_cache.get_share(token) == _payload(50)
    assert expires_at > 0
