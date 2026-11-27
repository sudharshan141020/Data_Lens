"""Rate limiting on the share endpoints (app/rate_limit.py).

Sharing is the one thing here that accepts a large caller-supplied payload without
an account, and the read side is a public lookup by token. Neither had a limit: one
client could keep a worker busy re-serialising 15MB results, and probing expired
tokens was free. These tests pin the budget and the 429, and -- just as important --
that the budget belongs to an address the caller cannot simply choose.
"""
import asyncio

import pytest
from starlette.requests import Request

try:
    from httpx import ASGITransport, AsyncClient
except ModuleNotFoundError:                      # this repo's dev requirements install httpx2
    pytest.importorskip("httpx2")
    from httpx2 import ASGITransport, AsyncClient

from app import body_limit
from app import main as main_module
from app import rate_limit
from app.rate_limit import SlidingWindowLimiter

CLEAN_V2 = {
    "profile": {"columns": ["Region", "Sales"]},
    "filterable_data": {"available": True, "rows": [{"Region": "West", "Sales": 10}]},
}


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _request(client=("9.9.9.9", 1234), forwarded=None):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({
        "type": "http", "method": "GET", "path": "/api/share", "headers": headers,
        "client": client, "server": ("testserver", 80), "scheme": "http", "query_string": b"",
    })


def _share(client):
    return client.post("/api/share", json={"file_name": "d.csv", "kpis": {}, "v2": CLEAN_V2})


# ---------------------------------------------------------------------------
# the window itself
# ---------------------------------------------------------------------------
def test_the_budget_is_spent_then_refills_as_the_window_rolls():
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.check("a") == 0.0
    assert limiter.check("a") == 0.0
    assert limiter.check("a") == pytest.approx(60)

    clock.now += 45
    # A refused request records nothing, so the wait only shrinks.
    assert limiter.check("a") == pytest.approx(15)

    clock.now += 16
    assert limiter.check("a") == 0.0


def test_clients_do_not_share_a_budget():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    assert limiter.check("a") == 0.0
    assert limiter.check("b") == 0.0
    assert limiter.check("a") > 0


def test_the_counter_table_stays_bounded():
    """Every client address is a key, and an address is caller-influenced: an
    unbounded dict here would be its own memory leak."""
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, max_keys=2)
    for i in range(100):
        limiter.check(f"client-{i}")
    assert len(limiter._hits) <= 2


# ---------------------------------------------------------------------------
# whose budget it is
# ---------------------------------------------------------------------------
def test_the_budget_belongs_to_the_socket_peer_by_default():
    # The left-most X-Forwarded-For value is the caller's own claim; trusting it
    # would let one client change it every request and never be limited.
    assert rate_limit.client_key(_request(forwarded="1.2.3.4")) == "9.9.9.9"


def test_one_declared_proxy_switches_to_the_address_it_appended(monkeypatch):
    monkeypatch.setattr(rate_limit, "TRUSTED_PROXIES", 1)
    assert rate_limit.client_key(_request(forwarded="203.0.113.9")) == "203.0.113.9"
    assert rate_limit.client_key(_request(forwarded="1.2.3.4, 203.0.113.9")) == "203.0.113.9"


def test_a_request_with_no_peer_still_gets_a_key():
    assert rate_limit.client_key(_request(client=None)) == "unknown"


def test_retry_after_is_never_zero():
    assert rate_limit.retry_after_header(0.2) == 1
    assert rate_limit.retry_after_header(12.3) == 13


# ---------------------------------------------------------------------------
# through the real endpoints
# ---------------------------------------------------------------------------
def test_creating_share_links_is_limited(client, monkeypatch):
    monkeypatch.setattr(main_module, "_SHARE_CREATE_LIMITER", SlidingWindowLimiter(2, 60))

    assert _share(client).status_code == 200
    assert _share(client).status_code == 200

    refused = _share(client)
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1
    assert "Too many requests" in refused.json()["detail"]


def test_reading_share_links_is_limited(client, monkeypatch):
    token = _share(client).json()["token"]
    monkeypatch.setattr(main_module, "_SHARE_READ_LIMITER", SlidingWindowLimiter(1, 60))

    assert client.get(f"/api/share/{token}").status_code == 200
    assert client.get(f"/api/share/{token}").status_code == 429


def test_probing_unknown_tokens_is_not_free(client, monkeypatch):
    monkeypatch.setattr(main_module, "_SHARE_READ_LIMITER", SlidingWindowLimiter(1, 60))
    assert client.get("/api/share/not-a-token").status_code == 404
    assert client.get("/api/share/not-a-token").status_code == 429


def test_the_deployed_config_counts_one_trusted_proxy():
    """On Render the socket peer is Render's proxy, so without this setting every
    visitor would share one budget and one share-cache quota -- a failure that
    looks like "the limit is too low" rather than like a missing config line."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
    assert "- key: DATALENS_TRUSTED_PROXIES" in text
    value_block = text.split("DATALENS_TRUSTED_PROXIES", 1)[1].split("- key:", 1)[0]
    assert 'value: "1"' in value_block


# ---------------------------------------------------------------------------
# the budget is spent before the body is read
# ---------------------------------------------------------------------------
# The limiter used to run inside create_share_link, after FastAPI had already
# read, decoded and validated the body: a malformed request therefore answered
# 422 and an oversized one 413 even for a caller whose budget was gone, and both
# paid the parse the limit exists to prevent. It now runs in middleware, outside
# the body-size cap and outside the router. These pin that ordering.
def test_a_malformed_body_is_refused_by_the_budget_not_by_validation(client, monkeypatch):
    monkeypatch.setattr(main_module, "_SHARE_CREATE_LIMITER", SlidingWindowLimiter(2, 60))

    malformed = {"file_name": "d.csv"}                  # `v2` is required, so this is a 422
    assert client.post("/api/share", json=malformed).status_code == 422
    assert _share(client).status_code == 200             # budget spent: two posts, limit two

    refused = client.post("/api/share", json=malformed)
    assert refused.status_code == 429                    # the budget answers, not validation
    assert int(refused.headers["retry-after"]) >= 1
    assert refused.json()["detail"].startswith("Too many requests. Try again in ")


def test_an_oversized_body_is_refused_by_the_budget_before_the_size_cap(client, monkeypatch):
    """The limiter is registered after BodySizeLimitMiddleware, i.e. outside it,
    so the size cap still works while a caller is under budget and stops
    answering at all once the budget is gone."""
    monkeypatch.setattr(body_limit, "MAX_BODY_BYTES", 1024)
    monkeypatch.setattr(main_module, "_SHARE_CREATE_LIMITER", SlidingWindowLimiter(2, 60))

    oversized = {"file_name": "d.csv", "kpis": {}, "v2": {"pad": "x" * 4096}}

    assert client.post("/api/share", json=oversized).status_code == 413     # cap, body unparsed
    assert _share(client).status_code == 200                              # budget now spent
    assert client.post("/api/share", json=oversized).status_code == 429     # budget, not cap


def test_a_refused_request_is_answered_without_reading_its_body(monkeypatch):
    """Drives the real app with a `receive` that fails the test if it is ever
    called: on refusal nothing below the limiter runs, so the body is not read.
    The Content-Length is far above the size cap, so a 429 here also shows the
    limiter runs outside that guard."""
    monkeypatch.setattr(main_module, "_SHARE_CREATE_LIMITER", SlidingWindowLimiter(1, 60))
    main_module._SHARE_CREATE_LIMITER.check("9.9.9.9")   # this caller is already over budget

    sent = []

    async def receive():
        raise AssertionError("a refused request must not read its body")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/share",
        "raw_path": b"/api/share", "root_path": "", "query_string": b"",
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", b"9000000")],
        "client": ("9.9.9.9", 5000), "server": ("testserver", 80),
    }
    asyncio.run(main_module.app(scope, receive, send))

    started = [m for m in sent if m["type"] == "http.response.start"]
    assert [m["status"] for m in started] == [429]
    assert dict(started[0]["headers"])[b"retry-after"] == b"60"
    assert b"Too many requests" in sent[-1]["body"]


def test_a_refused_method_or_path_is_left_to_the_app(client, monkeypatch):
    """Only POST on the one route is limited: a GET, a DELETE and any other
    endpoint keep their own behaviour even when the create budget is gone."""
    monkeypatch.setattr(main_module, "_SHARE_CREATE_LIMITER", SlidingWindowLimiter(1, 60))

    token = _share(client).json()["token"]
    assert _share(client).status_code == 429

    assert client.get("/api/health").status_code == 200
    # The read side has its own budget, untouched by the create limit.
    assert client.get(f"/api/share/{token}").status_code == 200


def test_concurrent_posts_share_one_budget_exactly(monkeypatch):
    """The check runs in the middleware, on the event loop, before any of these
    reaches the threadpool that runs the endpoint -- so simultaneous posts get
    exactly the budget's worth of 200s instead of racing past it."""
    monkeypatch.setattr(main_module, "_SHARE_CREATE_LIMITER", SlidingWindowLimiter(3, 60))

    async def scenario():
        transport = ASGITransport(app=main_module.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            responses = await asyncio.gather(*[
                client.post("/api/share", json={"file_name": "d.csv", "kpis": {}, "v2": CLEAN_V2})
                for _ in range(12)
            ])
        return [r.status_code for r in responses]

    statuses = asyncio.run(scenario())
    assert statuses.count(200) == 3
    assert statuses.count(429) == 9
