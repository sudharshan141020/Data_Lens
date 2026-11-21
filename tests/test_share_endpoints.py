"""The share endpoints as an HTTP surface: caching, size accounting, input caps.

A share link is public and lives for 24 hours, so what surrounds the payload
matters as much as the payload itself: a response that a browser or proxy may
store outlives the link, and a refusal lists column names that describe the
caller's data.
"""
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
