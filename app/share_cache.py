"""
Ephemeral Share Cache.

Lets someone generate a link to their analysis that another person can
open without re-uploading the file -- "here's what I found, take a
look" -- without becoming permanent storage. In-memory, TTL-based,
unguessable token: no accounts, no database, and nothing outlives the
process restart or the expiry window, matching the rest of this app's
"nothing is kept" design as closely as a share-by-link feature can
while still being useful.

In-memory rather than Redis/a database on purpose: this is a portfolio
project's ephemeral cache, not a production multi-instance deployment,
and a single dict with a lock is the simplest thing that's actually
correct for a single-process deployment. The natural upgrade path if
this ever needs to survive process restarts or run across multiple
instances is swapping this module's storage for Redis with the same
three functions' signatures unchanged -- nothing else in the app would
need to change.
"""
import json
import secrets
import threading
import time

TTL_SECONDS = 24 * 60 * 60  # 24 hours -- long enough to actually share with someone, short enough to stay "ephemeral"
MAX_ENTRY_BYTES = 15 * 1024 * 1024  # 15MB -- generous for a full v2+kpis payload, defensive against abuse
MAX_ENTRIES = 500  # defensive cap on total memory use

_store = {}
_lock = threading.Lock()


def _prune_expired_locked():
    now = time.time()
    expired = [k for k, (_, expires_at) in _store.items() if expires_at < now]
    for k in expired:
        del _store[k]


def create_share(payload: dict) -> tuple:
    """Returns (token, expires_at_unix_ts). Raises ValueError if the
    payload is too large -- caller is expected to turn that into a 400,
    not a 500."""
    size = len(json.dumps(payload))
    if size > MAX_ENTRY_BYTES:
        raise ValueError(f"This analysis is too large to share ({size / 1024 / 1024:.1f}MB, limit {MAX_ENTRY_BYTES / 1024 / 1024:.0f}MB).")

    with _lock:
        _prune_expired_locked()
        if len(_store) >= MAX_ENTRIES:
            # Make room by dropping whichever entry is closest to expiring
            # anyway, rather than refusing new shares outright once the
            # cache is full.
            oldest_token = min(_store, key=lambda k: _store[k][1])
            del _store[oldest_token]
        token = secrets.token_urlsafe(16)
        expires_at = time.time() + TTL_SECONDS
        _store[token] = (payload, expires_at)
    return token, expires_at


def get_share(token: str):
    """Returns the stored payload, or None if the token is unknown or
    expired (expired entries are deleted on the read that finds them,
    same lazy-cleanup spirit as the write-time pruning above)."""
    with _lock:
        entry = _store.get(token)
        if entry is None:
            return None
        payload, expires_at = entry
        if expires_at < time.time():
            del _store[token]
            return None
        return payload
