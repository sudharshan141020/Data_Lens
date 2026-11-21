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

Memory is bounded twice over. A per-entry cap refuses one oversized
payload, and a TOTAL cap keeps the cache inside a fixed budget: the
entry count alone is not a bound, because 500 entries at the 15MB
per-entry limit is 7.5GB, which is far more than the 512MB instance this
app is deployed on. Entries closest to expiring are dropped to make
room, so a busy server degrades by forgetting old links rather than by
being killed for memory.
"""
import json
import secrets
import threading
import time
from typing import Optional

TTL_SECONDS = 24 * 60 * 60  # 24 hours -- long enough to actually share with someone, short enough to stay "ephemeral"
MAX_ENTRY_BYTES = 15 * 1024 * 1024  # 15MB -- generous for a full v2+kpis payload, defensive against abuse
MAX_ENTRIES = 500  # defensive cap on the number of links, independent of their size
MAX_TOTAL_BYTES = 64 * 1024 * 1024  # 64MB -- the REAL memory bound; MAX_ENTRIES * MAX_ENTRY_BYTES would be 7.5GB

# token -> (payload, expires_at, size_in_bytes)
_store = {}
_total_bytes = 0
_lock = threading.Lock()


def _prune_expired_locked():
    global _total_bytes
    now = time.time()
    for token in [t for t, (_p, expires_at, _s) in _store.items() if expires_at < now]:
        _total_bytes -= _store[token][2]
        del _store[token]


def _evict_one_locked():
    """Drop whichever entry is closest to expiring anyway."""
    global _total_bytes
    oldest_token = min(_store, key=lambda t: _store[t][1])
    _total_bytes -= _store[oldest_token][2]
    del _store[oldest_token]


def check_size(payload: dict) -> int:
    """Raises ValueError if the single payload is too large, and returns its
    size in bytes so the caller doesn't have to serialise it a second time.
    Cheap enough to run BEFORE anything scans the payload, so an oversized
    request is refused without being inspected."""
    size = len(json.dumps(payload))
    if size > MAX_ENTRY_BYTES:
        raise ValueError(f"This analysis is too large to share ({size / 1024 / 1024:.1f}MB, limit {MAX_ENTRY_BYTES / 1024 / 1024:.0f}MB).")
    return size


def create_share(payload: dict, size: Optional[int] = None) -> tuple:
    """Returns (token, expires_at_unix_ts). Raises ValueError if the
    payload is too large -- caller is expected to turn that into a 400,
    not a 500.

    `size` is the already-measured serialisation size (check_size's return
    value) when the caller has one. Measuring it again would dump the whole
    payload to JSON a second time, and at the 15MB per-entry limit that is not
    free on the 512MB instance this runs on, so the endpoint measures once and
    passes it through."""
    global _total_bytes
    if size is None:
        size = check_size(payload)
    if size > MAX_TOTAL_BYTES:
        raise ValueError(
            f"This analysis is too large to keep a share link for "
            f"({size / 1024 / 1024:.1f}MB, cache budget {MAX_TOTAL_BYTES / 1024 / 1024:.0f}MB)."
        )

    with _lock:
        _prune_expired_locked()
        # Make room -- by count OR by bytes -- rather than refusing new shares
        # once the cache is full. Dropping expires-soonest entries is the least
        # destructive way to stay inside both caps.
        while _store and (len(_store) >= MAX_ENTRIES or _total_bytes + size > MAX_TOTAL_BYTES):
            _evict_one_locked()
        token = secrets.token_urlsafe(16)
        expires_at = time.time() + TTL_SECONDS
        _store[token] = (payload, expires_at, size)
        _total_bytes += size
    return token, expires_at


def get_share(token: str):
    """Returns the stored payload, or None if the token is unknown or
    expired (expired entries are deleted on the read that finds them,
    same lazy-cleanup spirit as the write-time pruning above)."""
    global _total_bytes
    with _lock:
        entry = _store.get(token)
        if entry is None:
            return None
        payload, expires_at, size = entry
        if expires_at < time.time():
            _total_bytes -= size
            del _store[token]
            return None
        return payload
