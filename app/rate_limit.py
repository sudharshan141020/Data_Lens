"""
In-process rate limiting for the share endpoints.

Sharing is the one feature here that does real work on a caller-supplied
payload without an account: POST /api/share serialises the whole result,
scans every string in it for personal data, and keeps 15MB in memory, and
GET /api/share/{token} is a public lookup anyone can call. Neither had a
limit, so one client could keep a worker busy by posting the same large
payload in a loop, and probing tokens was free.

In-memory and per process for the same reason share_cache.py is: this app
deploys as a single process, and a dict of deques behind a lock is the
simplest thing that is actually correct there. A multi-instance deployment
would need a shared store (Redis) with these same three entry points; the
counters would otherwise be per worker, i.e. N times the intended budget.

The window is sliding, not a fixed bucket: a fixed window lets a caller spend
the whole budget at the end of one window and again at the start of the next,
which is twice the intended rate in a burst.

Which address the budget belongs to is a security decision, not a detail:
`client_key` ignores X-Forwarded-For unless the deployment says a proxy it
controls appends to it, because the left-most value is whatever the caller
typed, and honouring that would let one client mint a fresh budget per request
just by changing the header.

The create endpoint is limited by ShareCreateRateLimitMiddleware, not inside the
handler: FastAPI reads, decodes and validates a model endpoint's body inside the
route handler, after every middleware has run, so a limiter called from the
handler is paid for with the parse it is supposed to prevent.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import deque


def _env_int(name: str, default: int) -> int:
    """A positive integer from the environment, or `default` -- a bad value must
    not stop the app from starting."""
    try:
        value = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


WINDOW_SECONDS = _env_int("DATALENS_RATE_WINDOW_SECONDS", 60)
# Creating a link is the expensive one (serialise + scan + 15MB retained).
SHARE_CREATE_LIMIT = _env_int("DATALENS_SHARE_CREATE_LIMIT", 30)
# Reading is cheap but public, and 120 a minute is far more than a person opening
# a link will ever use while still bounding a loop.
SHARE_READ_LIMIT = _env_int("DATALENS_SHARE_READ_LIMIT", 120)
# How many proxies in front append to X-Forwarded-For. 0 = no proxy trusted.
TRUSTED_PROXIES = _env_int("DATALENS_TRUSTED_PROXIES", 0)
MAX_TRACKED_CLIENTS = 10_000   # the counter table needs a bound of its own


class SlidingWindowLimiter:
    """At most `limit` events per `window_seconds`, per key.

    `check()` is the whole interface: it records an event and returns 0.0 when
    the caller is under its budget, or returns the seconds to wait and records
    nothing when it is not (a refused request must not extend the wait).
    """

    def __init__(self, limit: int, window_seconds: float, max_keys: int = MAX_TRACKED_CLIENTS, clock=time.monotonic):
        self.limit = max(1, int(limit))
        self.window = max(1.0, float(window_seconds))
        self.max_keys = max(1, int(max_keys))
        self._clock = clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _prune(self, hits: deque, now: float) -> None:
        stale_before = now - self.window
        while hits and hits[0] <= stale_before:
            hits.popleft()

    def _make_room(self, now: float) -> None:
        """Keep the table bounded. Only called when a NEW key needs a slot, so the
        cost of the scan is paid on new clients rather than on every request."""
        if len(self._hits) < self.max_keys:
            return
        stale_before = now - self.window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= stale_before]:
            del self._hits[key]
        while len(self._hits) >= self.max_keys:
            oldest = min(self._hits, key=lambda k: self._hits[k][-1])
            del self._hits[oldest]

    def check(self, key: str) -> float:
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                self._make_room(now)
                hits = self._hits[key] = deque()
            self._prune(hits, now)
            if len(hits) >= self.limit:
                return max(0.0, self.window - (now - hits[0]))
            hits.append(now)
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request) -> str:
    """Who the budget is counted against.

    The socket peer by default. Behind a proxy every request arrives from the
    proxy's address, and the real client is in X-Forwarded-For; that header is
    used only when DATALENS_TRUSTED_PROXIES says how many of its entries the
    deployment's own proxies appended, and then from the RIGHT, because that is
    the end the closest trusted proxy wrote. Taking the left-most entry (the
    obvious choice) would hand the caller the key: it is simply the text they
    sent, so changing it every request would give them an unlimited budget.
    """
    return client_key_from_scope(request.scope)


def client_key_from_scope(scope) -> str:
    """`client_key` for a bare ASGI scope.

    The middleware has to answer this before a Request object exists, and the
    two must not drift apart: this is the only implementation, and
    `client_key` is a thin wrapper over it.
    """
    if TRUSTED_PROXIES > 0:
        forwarded = ""
        for name, value in scope.get("headers") or []:
            if name.lower() == b"x-forwarded-for":
                forwarded = value.decode("latin-1")
                break
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= TRUSTED_PROXIES:
            return parts[-TRUSTED_PROXIES]
    client = scope.get("client")
    return (client[0] if client else None) or "unknown"


def retry_after_header(seconds: float) -> int:
    """Retry-After is in whole seconds, and 0 would invite an immediate retry."""
    return max(1, int(math.ceil(seconds)))


def rejection_detail(seconds: int) -> str:
    """The 429 message. Built here so the handler and the middleware cannot
    answer the same refusal with two different sentences."""
    return f"Too many requests. Try again in {seconds} second{'s' if seconds != 1 else ''}."


# The one route whose body is expensive enough to limit before it is read.
SHARE_CREATE_PATH = "/api/share"


def _route_path(scope) -> str:
    """The path as the router sees it, i.e. with any mount prefix removed.
    Starlette's router strips `root_path` the same way; matching on the raw
    `path` would silently stop limiting anything under a mount."""
    path = scope.get("path") or ""
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        return path[len(root):] or "/"
    return path


class ShareCreateRateLimitMiddleware:
    """Spend POST /api/share's budget before FastAPI reads the request body.

    The limiter used to be called from the endpoint, which runs after FastAPI has
    already read, decoded and validated the body (fastapi/routing.py reads it in
    `get_request_handler`). So a malformed body answered 422 and an oversized one
    413 even for a caller whose budget was long gone -- and both paid the parse
    this limit exists to avoid.

    Pure ASGI rather than BaseHTTPMiddleware, because the point is what does NOT
    happen: on refusal the wrapped app is never called, so nothing downstream --
    not the router, not the body-size middleware inside this one -- can touch
    `receive`. A middleware that only inspects the scope could not answer without
    calling the app; this one writes the 429 itself.

    It is registered after BodySizeLimitMiddleware, which makes it the outermost
    of the two (Starlette builds the stack from the last-added inwards), so an
    over-budget caller is refused before the body's declared length is even
    looked at. Being outside the size cap means oversized posts are charged to
    the budget as well, which is intended: otherwise a caller could send
    bodies that are refused only by the size cap and never spend anything.

    A single trailing slash is folded into the create path: POST /api/share/
    is the same request to a caller, and charging it separately would leave the
    budget reachable-but-free through the slashed URL. Exactly one slash is
    folded -- /api/share// is a different path -- and no other path is
    rewritten.

    Only this route and method are affected; every other request passes through
    untouched, and the read endpoint keeps its own limiter in the handler.
    """

    def __init__(self, app, limiter_provider, path: str = SHARE_CREATE_PATH):
        self.app = app
        # A callable, not the limiter itself: the app is installed at import time
        # and its middleware stack is built once, so reading main's module
        # attribute per request keeps the limiter replaceable (tests do this).
        self._limiter_provider = limiter_provider
        self._path = path

    def _applies(self, scope) -> bool:
        if scope.get("type") != "http" or (scope.get("method") or "").upper() != "POST":
            return False
        path = _route_path(scope)
        # One trailing slash is the same create request: Starlette answers
        # /api/share/ with a 405 rather than redirecting to the canonical URL, so
        # without this the slashed form is a free way to reach this route -- the
        # budget would only apply to the spelling a caller may simply not use.
        # Exactly one: /api/share// is not this route, and stays uncharged. The
        # comparison is against this one path, so nothing else is normalised.
        if path == self._path + "/":
            path = self._path
        return path == self._path

    async def __call__(self, scope, receive, send):
        if not self._applies(scope):
            await self.app(scope, receive, send)
            return

        wait = self._limiter_provider().check(client_key_from_scope(scope))
        if wait:
            seconds = retry_after_header(wait)
            body = json.dumps({"detail": rejection_detail(seconds)}).encode("utf-8")
            # Deliberately no receive(): the body is not read, not drained and
            # not validated for a request that is already refused.
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(seconds).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
