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
"""
from __future__ import annotations

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
    if TRUSTED_PROXIES > 0:
        forwarded = request.headers.get("x-forwarded-for", "") or ""
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= TRUSTED_PROXIES:
            return parts[-TRUSTED_PROXIES]
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def retry_after_header(seconds: float) -> int:
    """Retry-After is in whole seconds, and 0 would invite an immediate retry."""
    return max(1, int(math.ceil(seconds)))
