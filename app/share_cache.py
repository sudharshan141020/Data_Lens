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
instances is swapping this module's storage for Redis with these
functions' signatures unchanged -- nothing else in the app would need to
change.

Memory is bounded twice over. A per-entry cap refuses one oversized
payload, and a TOTAL cap keeps the cache inside a fixed budget: the
entry count alone is not a bound, because 500 entries at the 15MB
per-entry limit is 7.5GB, which is far more than the 512MB instance this
app is deployed on. Entries closest to expiring are dropped to make
room, so a busy server degrades by forgetting old links rather than by
being killed for memory.

A link can also be revoked before it expires. Revoking needs a secret, and
the secret cannot be the token in the URL: the URL is exactly the part people
paste into chats and email, so anyone who can open the link would also be able
to delete it. So `create_share` hands the creator a second, separate revoke
token (returned once, stored only as a hash) and `revoke_share` requires it.

Expiry is written into the token itself (`<random>_<expiry in base 36>`). That
is what lets a request tell "this link expired" apart from "this token never
existed": once an entry is gone -- aged out, revoked, evicted, or lost with the
process -- there is nothing left to look the answer up in, and a tombstone per
dead link would be state that grows with every link ever made.
"""
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Optional

TTL_SECONDS = 24 * 60 * 60  # 24 hours -- long enough to actually share with someone, short enough to stay "ephemeral"
MAX_ENTRY_BYTES = 15 * 1024 * 1024  # 15MB -- generous for a full v2+kpis payload, defensive against abuse
MAX_ENTRIES = 500  # defensive cap on the number of links, independent of their size
MAX_TOTAL_BYTES = 64 * 1024 * 1024  # 64MB -- the REAL memory bound; MAX_ENTRIES * MAX_ENTRY_BYTES would be 7.5GB

# token -> (payload, expires_at, size_in_bytes, revoke_hash)
_store = {}
_total_bytes = 0
_lock = threading.Lock()

# Base-36 digits contain no separator, so the LAST "_" in a token is always
# ours even though token_urlsafe's own alphabet includes one.
_EXPIRY_SEPARATOR = "_"
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"
_BASE36_DIGITS = frozenset(_BASE36)
# 36**13 is ~1.7e20, far past any plausible timestamp -- and refusing longer
# tails also keeps int(text, 36) away from CPython's digit-count limit, which
# would otherwise raise on a hostile path parameter rather than return None.
_MAX_EXPIRY_DIGITS = 13


def _encode_expiry(expires_at: float) -> str:
    n, out = int(expires_at), ""
    while n:
        n, rest = divmod(n, 36)
        out = _BASE36[rest] + out
    return out or "0"


def _new_token(expires_at: float) -> str:
    return f"{secrets.token_urlsafe(16)}{_EXPIRY_SEPARATOR}{_encode_expiry(expires_at)}"


def expiry_of(token: str) -> Optional[float]:
    """When a token we issued was due to expire, read back out of the token;
    None when `token` is not one of ours -- an arbitrary string is "unknown",
    not "expired". A revoked, evicted or restart-lost link still parses: its
    expiry is in the future, which is how a caller learns it did not age out."""
    head, separator, tail = str(token).rpartition(_EXPIRY_SEPARATOR)
    if not separator or not head or not 1 <= len(tail) <= _MAX_EXPIRY_DIGITS:
        return None
    if any(c not in _BASE36_DIGITS for c in tail):
        return None
    return float(int(tail, 36))


def _hash_secret(secret: str) -> bytes:
    """Revoke secrets are compared by hash so the plaintext never sits in the
    store, or in anything that dumps it."""
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _prune_expired_locked():
    global _total_bytes
    now = time.time()
    for token in [t for t, (_p, expires_at, _s, _r) in _store.items() if expires_at < now]:
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
    """Returns (token, expires_at_unix_ts, revoke_token). Raises ValueError if
    the payload is too large -- caller is expected to turn that into a 400,
    not a 500.

    `size` is the already-measured serialisation size (check_size's return
    value) when the caller has one. Measuring it again would dump the whole
    payload to JSON a second time, and at the 15MB per-entry limit that is not
    free on the 512MB instance this runs on, so the endpoint measures once and
    passes it through.

    `revoke_token` is the creator's proof of ownership: returned exactly once,
    stored only as a hash, and required by `revoke_share`. It is deliberately
    NOT the token in the URL, which is public by design."""
    global _total_bytes
    if size is None:
        size = check_size(payload)
    if size > MAX_TOTAL_BYTES:
        raise ValueError(
            f"This analysis is too large to keep a share link for "
            f"({size / 1024 / 1024:.1f}MB, cache budget {MAX_TOTAL_BYTES / 1024 / 1024:.0f}MB)."
        )
    revoke_token = secrets.token_urlsafe(24)

    with _lock:
        _prune_expired_locked()
        # Make room -- by count OR by bytes -- rather than refusing new shares
        # once the cache is full. Dropping expires-soonest entries is the least
        # destructive way to stay inside both caps.
        while _store and (len(_store) >= MAX_ENTRIES or _total_bytes + size > MAX_TOTAL_BYTES):
            _evict_one_locked()
        expires_at = time.time() + TTL_SECONDS
        token = _new_token(expires_at)
        _store[token] = (payload, expires_at, size, _hash_secret(revoke_token))
        _total_bytes += size
    return token, expires_at, revoke_token


def get_share(token: str):
    """Returns the stored payload, or None if the token is unknown or
    expired (expired entries are deleted on the read that finds them,
    same lazy-cleanup spirit as the write-time pruning above)."""
    global _total_bytes
    with _lock:
        entry = _store.get(token)
        if entry is None:
            return None
        payload, expires_at, size, _revoke_hash = entry
        if expires_at < time.time():
            _total_bytes -= size
            del _store[token]
            return None
        return payload


def revoke_share(token: str, revoke_token: str) -> str:
    """Delete a link before it expires. Returns "revoked", "not_found" (unknown
    or already expired -- both leave nothing to revoke) or "forbidden" (the
    secret does not match).

    A wrong secret changes nothing, so a guess cannot destroy somebody else's
    link, and the comparison is hmac.compare_digest rather than `==` so the
    answer does not depend on how many leading bytes were right."""
    global _total_bytes
    with _lock:
        entry = _store.get(token)
        if entry is None:
            return "not_found"
        _payload, expires_at, size, revoke_hash = entry
        if expires_at < time.time():
            _total_bytes -= size
            del _store[token]
            return "not_found"
        if not isinstance(revoke_token, str) or not hmac.compare_digest(revoke_hash, _hash_secret(revoke_token)):
            return "forbidden"
        _total_bytes -= size
        del _store[token]
        return "revoked"
