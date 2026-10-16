"""
Contract between the real backend and the captured response the frontend's
integration tests run against (frontend/src/test/fixtures/analysis.json).

Those frontend tests render the whole app from that capture. If the backend
later renames or drops a field, they would keep passing against a response
shape that no longer exists -- the classic failure of mocked tests. This
fails instead, naming exactly what moved.

Deliberately tolerant in one direction: fields the backend ADDS don't fail
it (extending the API shouldn't cost a fixture regeneration every time);
fields it REMOVES or changes the TYPE of do, because that is what breaks the
frontend. Regenerate with:  python scripts/regenerate_frontend_fixture.py
"""
import json

from scripts.frontend_fixture import CSV_PATH, JSON_PATH, capture_response

REGEN = "python scripts/regenerate_frontend_fixture.py"


def shape(value):
    """Reduce a JSON value to its structure. Dicts keep their keys; a list
    becomes the merged shape of its elements (so list LENGTH is irrelevant);
    scalars become a type name, with ints/floats unified as 'number'."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        merged = None
        for item in value:
            merged = _merge(merged, shape(item))
        return [merged] if merged is not None else []
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _merge(a, b):
    if a is None:
        return b
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _merge(out.get(k), v)
        return out
    if isinstance(a, list) and isinstance(b, list):
        return [_merge(a[0] if a else None, b[0] if b else None)] if (a or b) else []
    if a == "null":
        return b
    if b == "null" or a == b:
        return a
    return "|".join(sorted(set(str(a).split("|")) | set(str(b).split("|"))))


def problems(expected, actual, path="response"):
    """What the fixture relies on that the live backend no longer provides."""
    out = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: was an object, now {actual!r}"]
        for key, exp in expected.items():
            if key not in actual:
                out.append(f"{path}.{key}: REMOVED")
            else:
                out += problems(exp, actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: was a list, now {actual!r}"]
        if expected and actual:
            out += problems(expected[0], actual[0], f"{path}[]")
    elif expected != "null" and actual != "null" and expected != actual:
        # null on either side is "no value this time", not a type change
        if not (set(str(actual).split("|")) <= set(str(expected).split("|"))):
            out.append(f"{path}: type changed {expected} -> {actual}")
    return out


def test_fixture_files_are_present():
    assert JSON_PATH.exists(), f"missing {JSON_PATH.name} -- run: {REGEN}"
    assert CSV_PATH.exists(), f"missing {CSV_PATH.name} -- run: {REGEN}"
    header = CSV_PATH.read_text().splitlines()[0]
    assert header == "Order Date,Customer ID,Category,Region,Sales,Profit,Discount,Quantity"


def test_live_backend_still_provides_everything_the_frontend_fixture_relies_on(client):
    captured = json.loads(JSON_PATH.read_text())
    live = capture_response(client)
    issues = problems(shape(captured), shape(live))
    assert not issues, (
        "The /api/analyze response no longer matches the capture the frontend tests use:\n  "
        + "\n  ".join(issues[:25])
        + f"\n\nIf this change is intentional, regenerate with: {REGEN}\n"
        "then re-run the frontend tests (cd frontend && npm test)."
    )


def test_the_contract_check_itself_detects_drift():
    """Guards the guard: a removed field and a type change must be reported,
    an added field must not."""
    base = shape({"a": 1, "b": {"c": "x", "d": [1, 2]}, "e": None})
    assert problems(base, shape({"a": 1, "b": {"c": "x", "d": [3]}, "e": 5})) == []
    assert problems(base, shape({"a": 1, "b": {"c": "x", "d": [3]}, "e": None, "new": 1})) == []
    assert any("b.c: REMOVED" in p for p in problems(base, shape({"a": 1, "b": {"d": [1]}, "e": None})))
    assert any("type changed" in p for p in problems(base, shape({"a": "now text", "b": {"c": "x", "d": [1]}, "e": None})))
