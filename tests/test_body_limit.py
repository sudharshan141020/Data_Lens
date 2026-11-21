"""app.body_limit -- refusing an oversized body before it is parsed.

Every endpoint had its body read into memory and decoded before any of the app's
own limits could run, so those limits bounded what was kept, not what was received.
These pin the cap in both places it has to apply -- a declared Content-Length and a
streamed body that declares none -- that every non-multipart content type is
covered (a model endpoint buffers text/plain just the same), and that uploads,
which have their own streaming cap, are untouched.
"""
import asyncio

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import body_limit


def _app(limit=None, calls=None):
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        if calls is not None:
            calls.append(1)
        return {"length": len(await request.body())}

    app.add_middleware(body_limit.BodySizeLimitMiddleware, max_bytes=limit)
    return app


def test_a_declared_length_over_the_cap_is_refused_before_the_endpoint_runs():
    calls = []
    resp = TestClient(_app(limit=100, calls=calls)).post("/echo", json={"data": "x" * 500})
    assert resp.status_code == 413
    assert "limit for request bodies" in resp.json()["detail"]
    assert resp.headers["cache-control"] == "no-store"
    assert calls == []                                   # the handler never ran


def test_a_body_under_the_cap_still_reaches_the_endpoint():
    resp = TestClient(_app(limit=10_000)).post("/echo", json={"data": "x" * 100})
    assert resp.status_code == 200
    assert resp.json()["length"] > 0


def test_a_text_plain_body_is_capped_too():
    """The whole point of the widening: FastAPI does not care that the caller said
    text/plain, so the cap must not care either."""
    calls = []
    resp = TestClient(_app(limit=100, calls=calls)).post(
        "/echo",
        content=b"x" * 500,
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 413
    assert calls == []


def test_a_form_encoded_body_is_capped_too():
    resp = TestClient(_app(limit=100)).post(
        "/echo",
        content=b"a=" + b"x" * 500,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 413


def test_a_body_with_no_content_type_is_capped_too():
    resp = TestClient(_app(limit=100)).post("/echo", content=b"x" * 500)
    assert resp.status_code == 413


def test_a_multipart_upload_is_not_affected():
    # A 10KB CSV is far over this cap and must still be accepted: uploads are
    # capped while they are read (main._read_upload), not by this middleware.
    resp = TestClient(_app(limit=10)).post("/echo", files={"file": ("a.csv", b"x" * 10_000, "text/csv")})
    assert resp.status_code == 200


def test_the_cap_is_read_from_the_module_when_the_app_installs_it(monkeypatch):
    monkeypatch.setattr(body_limit, "MAX_BODY_BYTES", 200)
    client = TestClient(_app())                          # max_bytes=None, as main.py installs it
    assert client.post("/echo", json={"data": "x" * 500}).status_code == 413
    assert client.post("/echo", json={"data": "x"}).status_code == 200


def _streaming_app():
    """Reads the body, then answers 200. Only reached when the body is allowed."""
    async def app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    return app


def _run_streamed(chunks, limit, content_type=b"application/json"):
    sent = []
    scope = {
        "type": "http", "method": "POST", "path": "/echo", "scheme": "http",
        "headers": [(b"content-type", content_type)],               # deliberately no content-length
        "client": ("9.9.9.9", 1), "server": ("testserver", 80), "query_string": b"",
    }
    incoming = [{"type": "http.request", "body": c, "more_body": True} for c in chunks]
    incoming.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive():
        return incoming.pop(0)

    async def send(message):
        sent.append(message)

    middleware = body_limit.BodySizeLimitMiddleware(_streaming_app(), max_bytes=limit)
    asyncio.run(middleware(scope, receive, send))
    return [m for m in sent if m["type"] == "http.response.start"]


def test_a_body_with_no_content_length_is_counted_while_it_streams():
    """Chunked encoding is exactly how a caller avoids the declared-length check."""
    started = _run_streamed([b'{"data":"', b"x" * 128, b"x" * 128, b'"}'], limit=100)
    assert [m["status"] for m in started] == [413]


def test_a_small_streamed_body_is_allowed_through():
    started = _run_streamed([b'{"data":"ok"}'], limit=100)
    assert [m["status"] for m in started] == [200]


def test_a_streamed_text_plain_body_is_capped_too():
    started = _run_streamed([b"x" * 128, b"x" * 128], limit=100, content_type=b"text/plain")
    assert [m["status"] for m in started] == [413]


def test_a_streamed_multipart_body_is_left_to_the_upload_cap():
    started = _run_streamed(
        [b"--b\r\n", b"x" * 128, b"x" * 128],
        limit=100,
        content_type=b"multipart/form-data; boundary=b",
    )
    assert [m["status"] for m in started] == [200]
