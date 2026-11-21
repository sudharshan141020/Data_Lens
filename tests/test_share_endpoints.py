"""The share endpoints as an HTTP surface: caching, size accounting, input caps.

A share link is public and lives for 24 hours, so what surrounds the payload
matters as much as the payload itself: a response that a browser or proxy may
store outlives the link, and a refusal lists column names that describe the
caller's data.
"""
from app import body_limit
from app import main as main_module
from app import share_cache

CLEAN_V2 = {
    "profile": {"columns": ["Region", "Sales"]},
    "filterable_data": {"available": True, "rows": [{"Region": "West", "Sales": 10}]},
}


def _share(client, **overrides):
    body = {"file_name": "d.csv", "kpis": {}, "v2": CLEAN_V2}
    body.update(overrides)
    return client.post("/api/share", json=body)


def test_a_share_response_may_not_be_cached(client):
    created = _share(client)
    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    assert created.headers["referrer-policy"] == "no-referrer"

    fetched = client.get(f"/api/share/{created.json()['token']}")
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "no-store"


def test_a_refusal_that_names_columns_is_not_cached_either(client):
    refused = _share(client, v2={**CLEAN_V2, "profile": {"columns": ["Customer ID"]}})
    assert refused.status_code == 409
    assert refused.headers["cache-control"] == "no-store"


def test_the_payload_is_serialised_once_per_request(client, monkeypatch):
    """The handler measures the payload, then stores it. Measuring it again inside
    the cache meant dumping up to 15MB to JSON twice on every share."""
    calls = []
    real = share_cache.check_size

    monkeypatch.setattr(main_module, "check_share_size", lambda payload: calls.append("handler") or real(payload))
    monkeypatch.setattr(share_cache, "check_size", lambda payload: calls.append("cache") or real(payload))

    assert _share(client).status_code == 200
    assert calls == ["handler"]


def test_the_size_that_was_measured_is_the_size_that_is_stored(client):
    token = _share(client).json()["token"]
    stored_size = share_cache._store[token][2]
    assert stored_size == share_cache.check_size({"file_name": "d.csv", "kpis": {}, "v2": CLEAN_V2})


def test_an_overlong_file_name_is_refused(client):
    assert _share(client, file_name="x" * 261).status_code == 422
    assert _share(client, file_name="q3-sales.csv").status_code == 200


def test_a_share_of_nothing_is_refused_like_the_exports_are(client):
    refused = _share(client, v2={})
    assert refused.status_code == 400
    assert "No analysis data" in refused.json()["detail"]


def test_a_json_body_over_the_limit_is_refused_before_the_endpoint_parses_it(client, monkeypatch):
    """The payload cap below only ran after the whole request had been decoded, so it
    bounded what was kept, not what was received (app/body_limit.py)."""
    monkeypatch.setattr(body_limit, "MAX_JSON_BYTES", 2_000)
    refused = _share(client, v2={"data": "x" * 5_000})
    assert refused.status_code == 413
    assert "limit for JSON bodies" in refused.json()["detail"]


def test_a_link_can_be_revoked_with_the_secret_returned_at_creation(client):
    created = _share(client)
    assert created.status_code == 200
    body = created.json()
    token, revoke_token = body["token"], body["revoke_token"]
    assert revoke_token and revoke_token != token

    revoked = client.delete(f"/api/share/{token}", headers={"X-Share-Revoke": revoke_token})
    assert revoked.status_code == 204

    gone = client.get(f"/api/share/{token}")
    assert gone.status_code == 404
    assert "no longer available" in gone.json()["detail"]       # not "expired": it had not aged out
    assert client.delete(f"/api/share/{token}", headers={"X-Share-Revoke": revoke_token}).status_code == 404


def test_revoking_needs_the_matching_secret(client):
    token = _share(client).json()["token"]
    assert client.delete(f"/api/share/{token}").status_code == 403
    assert client.delete(f"/api/share/{token}", headers={"X-Share-Revoke": "guess"}).status_code == 403
    assert client.get(f"/api/share/{token}").status_code == 200     # a wrong guess destroys nothing


def test_each_link_gets_its_own_revoke_secret(client):
    a = _share(client).json()
    b = _share(client).json()
    assert a["revoke_token"] != b["revoke_token"]
    other = client.delete(f"/api/share/{b['token']}", headers={"X-Share-Revoke": a["revoke_token"]})
    assert other.status_code == 403
    assert client.get(f"/api/share/{b['token']}").status_code == 200


def test_an_expired_link_says_it_expired_instead_of_acting_unknown(client, monkeypatch):
    monkeypatch.setattr(share_cache, "TTL_SECONDS", -1)
    token = _share(client).json()["token"]
    expired = client.get(f"/api/share/{token}")
    assert expired.status_code == 410
    assert "expired on" in expired.json()["detail"]


def test_an_unknown_token_is_not_reported_as_expired(client):
    missing = client.get("/api/share/not-a-token")
    assert missing.status_code == 404
    assert "doesn't exist" in missing.json()["detail"]


def test_a_link_lost_from_the_cache_is_not_reported_as_expired(client):
    """A restart, an eviction or a revoke all leave an unexpired token with no
    entry; the message must not claim the link aged out."""
    token = _share(client).json()["token"]
    _payload, _expires_at, size, _revoke, _quota = share_cache._store.pop(token)   # as a restart would
    share_cache._total_bytes -= size

    lost = client.get(f"/api/share/{token}")
    assert lost.status_code == 404
    assert "no longer available" in lost.json()["detail"]
