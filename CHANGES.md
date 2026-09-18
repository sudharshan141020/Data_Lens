# Dashboard Reorganization + Pydantic Response Models — changed files

Two items from the follow-up round, combined since both are polish
work rather than new analysis capability.

## Part 1: Dashboard reorganization
New: `frontend/src/components/DeepDivePanel.jsx`. Modified:
`frontend/src/App.jsx`, `frontend/src/App.css`, plus 11 existing panel
components (small conditional-render fix, see below).

The dashboard had grown to 13 stacked panels in one long scroll as
features piled on session after session. `DeepDivePanel` groups the 10
"secondary" panels (everything past Findings/Weak Points) into 4
browsable tabs, reusing `AnalysisExplorerV2`'s existing tab CSS classes
(`explorer-tabs`/`explorer-tab`) so it reads as the same UI pattern
already established, not a second one:
- **Quality & Relationships** — Data Quality, Correlation Center
- **Patterns** — Segments, Seasonality, Period Comparison, Retention
- **Anomalies & Integrity** — Anomalies, Simpson's Paradox, Benford's Law
- **Precision & Text** — Confidence Intervals, Text Fields

Each panel still renders its own "not available" state internally, so
a tab always shows even if everything in it happens to be unavailable
for a given dataset — no group-level availability logic needed.

Small fix applied to all 11 sub-panels: each has a numbered "tick"
badge in its header, which looked like an empty bordered box when
nested inside a tab with no `tickNum` passed. Fixed by conditionally
rendering the badge (`{tickNum && <span className="tick">...}`)
instead of always rendering it — applied via a single `sed` pass across
all 11 files rather than 13 individual edits, since the markup was
identical everywhere.

`DeepDivePanel` spans the full dashboard grid width (new
`.deep-dive-panel` CSS rule), same treatment already given to
`AnalysisExplorerV2`, since it holds noticeably more content per tab
than a typical half-width grid panel.

## Part 2: Pydantic response models
Modified: `app/main.py` only.

Added `AnalyzeResponse`, `CompareResponse`, `HealthResponse` models and
wired them via `response_model=` on `/api/analyze`, `/api/compare`,
`/api/analyze-combined`, `/api/health`. Deliberately top-level-only —
`v2` and `analyses` hold 17+ analysis modules with their own evolving,
domain-dependent nested shapes; modeling those exhaustively would go
stale the next time any one of them changes. The field NAMES and
top-level TYPES are still real, accurate documentation, which is the
actual gap this closes (previously every endpoint showed no response
schema at all in `/docs`).

Also added explicit `responses={200: {"content": {...}}}` OpenAPI
metadata to the three file-download endpoints (cleaned-csv, PDF, HTML
export), so `/docs` shows their real content types instead of nothing.

### The one thing that had to be verified, not assumed
`/api/analyze`, `/api/compare`, and `/api/analyze-combined` all
currently return `SafeJSONResponse` objects directly rather than plain
dicts — a change from earlier this session specifically to bypass
FastAPI's own `jsonable_encoder`, which crashes on `numpy.float32`/
`int8` (the chunked-CSV-reading bug chain). Adding `response_model=`
could theoretically reintroduce that exact crash if FastAPI re-applied
model validation/serialization to the response. Verified empirically
rather than trusted from memory: ran the full pytest suite — including
the specific regression test for that exact bug
(`test_analyze_endpoint_handles_downcast_numpy_dtypes`) — after adding
the response models, confirmed all 64 still pass. Then separately
confirmed the actual value shows up: fetched `/openapi.json` directly
and checked the generated schema has the right field names and the
file-download endpoints show their real content types
(`application/pdf`, `text/html`, `text/csv`).

## Verified this session
- Full pytest suite: 64/64 passing after both changes.
- `frontend`: `npm run build` succeeds, no new warnings.
- `/openapi.json` fetched directly and inspected: `AnalyzeResponse`,
  `CompareResponse`, `HealthResponse` schemas all present with correct
  field names; file-download endpoints show correct content types.
- `/docs` (Swagger UI) loads successfully (200).

## Not yet done
- Not visually verified in a browser — worth opening `/docs` once you
  pull this down to see the generated Swagger UI, and clicking through
  the dashboard's new tabs to confirm the visual grouping reads well.
- The file-download endpoints' OpenAPI response still lists a leftover
  generic `application/json` content-type entry alongside the real one
  (FastAPI's default, not fully overridden) — cosmetic, not functional;
  worth a closer look if you want the docs fully clean.
