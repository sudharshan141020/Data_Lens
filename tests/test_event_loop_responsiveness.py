"""
The async upload endpoints must not run pandas work on the event loop.

/api/analyze and friends are `async def` only because reading an upload has to
be awaited. While the analysis itself ran inline, the event loop was blocked for
its whole duration, so /api/health stopped answering -- and a host that restarts
the service when that endpoint fails would kill the app mid-analysis. The fix
hands the CPU-bound part to Starlette's threadpool; this test stands a slow
analysis in for the pandas work and requires a second request to be served while
it is still running.
"""
import asyncio
import time

import pytest

try:
    from httpx import ASGITransport, AsyncClient
except ModuleNotFoundError:                      # this repo's dev requirements install httpx2
    pytest.importorskip("httpx2")
    from httpx2 import ASGITransport, AsyncClient

from app import main as app_main  # noqa: E402


def _csv(rows: int = 5) -> bytes:
    lines = ["Order Date,Sales"] + [f"2024-01-0{i + 1},{(i + 1) * 10}.0" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def _minimal_result() -> dict:
    """A payload AnalyzeResponse accepts, so the test is about scheduling, not analysis."""
    return {
        "detected_columns": {}, "detection_confidence": {}, "unmapped_columns": [],
        "kpis": {}, "monthly_trend": [], "breakdowns": [], "insights": [],
        "domain": "generic", "domain_confidence": 0.5,
        "semantic_roles": {}, "analyses": [], "v2": {},
    }


def test_health_is_served_while_an_analysis_is_running(monkeypatch):
    def slow_analysis(df, column_overrides=None):
        time.sleep(0.5)            # stands in for the CPU-bound analysis
        return _minimal_result()

    monkeypatch.setattr(app_main, "_full_analyze_from_df", slow_analysis)

    async def scenario():
        transport = ASGITransport(app=app_main.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            analysis = asyncio.create_task(
                client.post("/api/analyze", files={"file": ("d.csv", _csv(), "text/csv")})
            )
            await asyncio.sleep(0.1)          # let the analysis start

            started = time.perf_counter()
            health = await client.get("/api/health")
            elapsed = time.perf_counter() - started

            assert not analysis.done(), "the analysis finished first; nothing was tested"
            assert health.status_code == 200
            assert elapsed < 0.2, f"/api/health took {elapsed:.2f}s while an analysis was in flight"
            await analysis

    asyncio.run(scenario())
