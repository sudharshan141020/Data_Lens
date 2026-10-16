"""Regenerate the captured /api/analyze response the frontend tests use.

Run from the project root after an intentional change to the API response
shape:   python scripts/regenerate_frontend_fixture.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from scripts.frontend_fixture import CSV_PATH, JSON_PATH, capture_response, make_csv  # noqa: E402


def main():
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_bytes(make_csv())
    body = capture_response(TestClient(app))
    JSON_PATH.write_text(json.dumps(body, separators=(",", ":")))
    print(f"wrote {CSV_PATH.name} ({CSV_PATH.stat().st_size:,} bytes) and {JSON_PATH.name} ({JSON_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
