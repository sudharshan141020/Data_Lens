"""
The built frontend is served from app/static by a catch-all route.

That route takes its path straight from the URL, and ASGI hands the path over
already percent-decoded, so it is the one place where a request can name a
file. These tests pin the containment rule: a path inside the build is served,
a path that escapes it never is.
"""
from pathlib import Path

import pytest

from app import main

STATIC = Path(main.__file__).parent / "static"


def test_serves_a_file_inside_the_build():
    assert main._safe_static_file("favicon.svg") == (STATIC / "favicon.svg").resolve()


def test_unknown_file_inside_the_build_is_not_served():
    assert main._safe_static_file("no-such-file.js") is None


def test_empty_path_is_not_a_file():
    assert main._safe_static_file("") is None


@pytest.mark.parametrize("path", [
    "../requirements.txt",
    "../main.py",
    "assets/../../main.py",
    "/etc/passwd",
    "../../../../etc/passwd",
])
def test_paths_outside_the_build_are_refused(path):
    assert main._safe_static_file(path) is None


def test_traversal_request_gets_the_spa_not_the_file(client):
    """End to end, in the encoded form a real client sends. The body must be
    the SPA shell, never the repository file the path points at."""
    resp = client.get("/..%2f..%2frequirements.txt")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "fastapi>=" not in resp.text


def test_a_client_side_route_still_gets_the_spa(client):
    """The containment check must not turn SPA routes into 404s."""
    resp = client.get("/share/some-token")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
