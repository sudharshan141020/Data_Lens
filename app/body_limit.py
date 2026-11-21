"""
A cap on request bodies, applied before anything parses them.

Every endpoint that takes a body -- JSON, form-encoded, or a plain text body that
Starlette's model handling will happily decode into a Pydantic field -- has it read
into memory and turned into Python objects first. The per-endpoint limits -- a share
payload's 15MB, a recompute's cell count -- are checked *after* that has already
happened, so they bound what is kept, not what is received: a caller could post a
gigabyte to /api/share and the process would die parsing it before any of those
checks ran.

The cap therefore covers every request *except* multipart uploads, which already
have their own streaming cap (`_read_upload` in main.py) and whose whole point is to
carry a large file. Content type must not decide whether the cap applies: FastAPI
still buffers the body for a model endpoint when the caller says `text/plain`, so a
cap that only watched `application/json` could be skipped by changing one header.

It refuses on the declared Content-Length, and enforces the same cap while the body
streams for a caller that uses chunked encoding and sends no length at all.

The cap sits above every legitimate payload this app produces (a share link's own
payload cap is 15MB) and far below what would hurt the 512MB instance it is
deployed on. DATALENS_MAX_BODY_MB overrides it.
"""
from __future__ import annotations

import json
import os
from typing import Optional

DEFAULT_MAX_BODY_MB = 25.0


def _max_body_bytes() -> int:
    """The cap in bytes. A bad or non-positive value falls back to the default
    rather than stopping the app from starting -- same rule as the upload cap."""
    raw = os.environ.get("DATALENS_MAX_BODY_MB", "").strip()
    try:
        mb = float(raw) if raw else DEFAULT_MAX_BODY_MB
    except ValueError:
        mb = DEFAULT_MAX_BODY_MB
    return int((mb if mb > 0 else DEFAULT_MAX_BODY_MB) * 1024 * 1024)


# Read per request, not captured at import, so a deployment can be reasoned about
# (and a test can tighten it) without rebuilding the app.
MAX_BODY_BYTES = _max_body_bytes()


class BodyTooLarge(Exception):
    """Internal signal from the streaming guard. Never escapes the middleware."""


def _header(scope, name: bytes) -> Optional[bytes]:
    for header_name, value in scope.get("headers") or []:
        if header_name == name:
            return value
    return None


def _is_multipart(scope) -> bool:
    """The one kind of request this middleware leaves alone: an upload, whose size
    is bounded by main._read_upload while it is read. Anything else -- JSON,
    text/plain, form-encoded, or no declared type at all -- is guarded, because
    a model endpoint will buffer it too."""
    content_type = _header(scope, b"content-type")
    if not content_type:
        return False
    return content_type.split(b";", 1)[0].strip().lower() == b"multipart/form-data"


def _declared_length(scope) -> Optional[int]:
    raw = _header(scope, b"content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        # A malformed length is not a claim worth trusting either way; the
        # streaming guard still applies.
        return None


async def _reject(send, limit: int) -> None:
    body = json.dumps({
        "detail": (f"This request is over the {limit / 1024 / 1024:g} MB limit for request bodies. "
                   "Send a smaller analysis, or upload the file and let the server compute it."),
    }).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store"),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """Pure ASGI rather than BaseHTTPMiddleware, because the point is to wrap
    `receive`: a middleware that only inspects the scope cannot stop a body that
    arrives without a Content-Length.

    `max_bytes=None` (how the app installs it) means "read the module's cap on
    each request". Passing a number is for tests.
    """

    def __init__(self, app, max_bytes: Optional[int] = None):
        self.app = app
        self._max_bytes = max_bytes

    def _limit(self) -> int:
        return MAX_BODY_BYTES if self._max_bytes is None else self._max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or _is_multipart(scope):
            await self.app(scope, receive, send)
            return

        limit = self._limit()
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _reject(send, limit)
            return

        received = 0
        response_started = False

        async def guarded_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge
            return message

        async def watched_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, guarded_receive, watched_send)
        except BodyTooLarge:
            if response_started:
                # Unreachable in practice -- every endpoint reads its body before
                # it starts answering -- but replacing a half-sent response with
                # a 413 is not possible, so let the failure be visible.
                raise
            await _reject(send, limit)
