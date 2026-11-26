"""
The share cache's memory bounds.

MAX_ENTRIES alone never bounded memory: 500 entries at the 15MB per-entry cap is
7.5GB, far past the 512MB instance this app is deployed on. These tests pin the
total-byte budget and the eviction that keeps it, which is the cap that actually
matters on a small host.
"""
import time

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
    token, _expires, _revoke = share_cache.create_share(_payload(1_000))
    assert share_cache._total_bytes > 0

    assert share_cache.get_share(token) is None
    assert share_cache._store == {}
    assert share_cache._total_bytes == 0


def test_a_retrieved_share_is_unchanged(monkeypatch):
    token, expires_at, _revoke = share_cache.create_share(_payload(50))
    assert share_cache.get_share(token) == _payload(50)
    assert expires_at > 0


# ---------------------------------------------------------------------------
# revoking a link early
# ---------------------------------------------------------------------------
def test_a_link_can_be_revoked_before_it_expires():
    token, _expires, revoke_token = share_cache.create_share(_payload(1_000))
    assert share_cache.revoke_share(token, revoke_token) == "revoked"

    assert share_cache.get_share(token) is None
    assert share_cache._store == {}
    assert share_cache._total_bytes == 0                  # the budget is given back
    assert share_cache.revoke_share(token, revoke_token) == "not_found"


def test_the_wrong_revoke_secret_leaves_the_link_alone():
    token, _expires, _revoke = share_cache.create_share(_payload(100))
    assert share_cache.revoke_share(token, "not-the-secret") == "forbidden"
    assert share_cache.revoke_share(token, "") == "forbidden"
    assert share_cache.get_share(token) == _payload(100)
    assert share_cache._total_bytes > 0


def test_each_link_gets_its_own_revoke_secret():
    a, _ea, revoke_a = share_cache.create_share(_payload(10))
    b, _eb, revoke_b = share_cache.create_share(_payload(10))
    assert revoke_a != revoke_b
    assert share_cache.revoke_share(b, revoke_a) == "forbidden"
    assert share_cache.revoke_share(a, revoke_a) == "revoked"


def test_the_revoke_secret_is_not_stored_in_plaintext():
    """The store is small and in memory, but a secret should not sit there
    readable by anything that happens to dump it."""
    token, _expires, revoke_token = share_cache.create_share(_payload(10))
    assert revoke_token not in str(share_cache._store[token])


def test_revoking_an_already_expired_link_reports_not_found(monkeypatch):
    monkeypatch.setattr(share_cache, "TTL_SECONDS", -1)
    token, _expires, revoke_token = share_cache.create_share(_payload(10))
    assert share_cache.revoke_share(token, revoke_token) == "not_found"
    assert share_cache._total_bytes == 0


# ---------------------------------------------------------------------------
# what a token says about its own lifetime
# ---------------------------------------------------------------------------
def test_a_token_carries_the_expiry_it_was_issued_with():
    token, expires_at, _revoke = share_cache.create_share(_payload(10))
    assert share_cache.expiry_of(token) == pytest.approx(expires_at)


def test_an_arbitrary_string_is_unknown_not_expired():
    for junk in ("", "not-a-token", "abc", "abc_def-", "_123", "abc_", "x" * 5_000):
        assert share_cache.expiry_of(junk) is None, junk[:20]


def test_a_revoked_token_still_says_it_had_not_expired_yet():
    """The endpoint relies on this: an expired link says so, a revoked one must
    not pretend to have aged out."""
    token, _expires, revoke_token = share_cache.create_share(_payload(10))
    share_cache.revoke_share(token, revoke_token)
    assert share_cache.expiry_of(token) > time.time()


def test_a_very_long_tail_does_not_reach_the_int_digit_limit():
    # int(text, 36) raises past CPython's digit limit; expiry_of must not raise.
    assert share_cache.expiry_of("abc_" + "1" * 100_000) is None


# ---------------------------------------------------------------------------
# one client cannot evict everyone else's links
# ---------------------------------------------------------------------------
def test_one_client_cannot_push_out_another_clients_link(monkeypatch):
    """The 64MB budget is global and unauthenticated, so without a per-client quota
    a single caller creating links in a loop wiped everybody else's live links."""
    monkeypatch.setattr(share_cache, "MAX_ENTRY_BYTES", 10_000)
    monkeypatch.setattr(share_cache, "MAX_BYTES_PER_CLIENT", 3_000)
    monkeypatch.setattr(share_cache, "MAX_ENTRIES_PER_CLIENT", 100)
    monkeypatch.setattr(share_cache, "MAX_TOTAL_BYTES", 100_000)
    monkeypatch.setattr(share_cache, "MAX_ENTRIES", 500)

    host, _e, _r = share_cache.create_share(_payload(500), quota_key="host")
    flood = [share_cache.create_share(_payload(1_000), quota_key="flood")[0] for _ in range(10)]

    assert share_cache.get_share(host) == _payload(500)          # untouched
    held = [t for t in flood if share_cache.get_share(t) is not None]
    assert len(held) == 2                                       # its own budget, not the whole cache
    assert share_cache._total_bytes <= 100_000


def test_a_clients_number_of_links_is_capped_too(monkeypatch):
    monkeypatch.setattr(share_cache, "MAX_ENTRIES_PER_CLIENT", 2)
    monkeypatch.setattr(share_cache, "MAX_BYTES_PER_CLIENT", 100_000)

    tokens = [share_cache.create_share(_payload(50), quota_key="one")[0] for _ in range(5)]
    assert [share_cache.get_share(t) is not None for t in tokens] == [False, False, False, True, True]


def test_without_a_quota_key_the_global_caps_still_apply(monkeypatch):
    monkeypatch.setattr(share_cache, "MAX_ENTRIES", 2)
    tokens = [share_cache.create_share(_payload(10))[0] for _ in range(3)]
    assert share_cache.get_share(tokens[0]) is None
    assert share_cache.get_share(tokens[-1]) is not None


def test_a_per_client_eviction_gives_its_bytes_back(monkeypatch):
    """A client's own eviction deletes entries directly (not through the global
    evictor), so it has to decrement the shared byte counter itself -- otherwise
    the budget shrinks on every link a busy caller replaces."""
    monkeypatch.setattr(share_cache, "MAX_ENTRIES_PER_CLIENT", 1)
    monkeypatch.setattr(share_cache, "MAX_BYTES_PER_CLIENT", 10_000_000)

    first, _e1, _r1 = share_cache.create_share(_payload(1_000), quota_key="1.2.3.4")
    second, _e2, _r2 = share_cache.create_share(_payload(2_000), quota_key="1.2.3.4")

    assert share_cache.get_share(first) is None
    assert share_cache.get_share(second) is not None
    assert share_cache._total_bytes == share_cache._store[second][2]
