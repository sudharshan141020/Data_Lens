# DataLens — Project Status

Last reviewed: 2026-11-27

## 1. Project overview

DataLens is a universal dataset intelligence platform built with React
and FastAPI. It analyzes datasets across multiple domains and produces
KPIs, visualizations, findings, weak points, data-quality assessments,
statistical relationships and narrative explanations.

## 2. Current verified architecture

### Backend
- FastAPI application.
- Python-based dataset analysis pipeline.
- Semantic column-role detection and dataset understanding.
- Domain-specific analyzer architecture.
- Analysis planning and chart execution.
- Findings, weak-point detection and story generation.
- Data quality and correlation analysis.
- Existing share-link, rate-limit and request-body protection modules.

### Frontend
- React application.
- Dashboard and multi-session analysis experience.
- Interactive charts, findings, weak points and data-quality panels.
- Share-link and export functionality documented in the handoff.

### Deployment
- Render deployment configuration exists.
- GitHub main branch is the shared source of truth.
- Repository: https://github.com/sudharshan141020/Data_Lens

## 3. Infrastructure audit

Audited on 2026-11-25 using dependency and Python-source searches.

| Capability | Audit result |
|---|---|
| FastAPI | Present |
| PostgreSQL / SQLAlchemy | No implementation found in audit |
| Redis | No implementation found in audit |
| Celery | No implementation found in audit |
| S3-compatible storage | No implementation found in audit |
| Authentication / JWT | No implementation found in audit |
| Persistent workspaces | No implementation found in audit |
| Dedicated background job APIs | No implementation found in audit |

These results describe the searches performed, not an exhaustive
proof that no related code exists.

## 4. Product direction

Accepted architecture decision: ADR-001 in DECISIONS.md.

DataLens will follow a hybrid model:

- Temporary analysis is the default.
- Account creation is optional.
- Users can explicitly save datasets and analyses in persistent
  workspaces.
- Temporary data must not silently become permanent.
- Persistent workspace data must be isolated by user ownership.
- Existing privacy and share-link protections must be preserved.

## 5. Existing capabilities

The existing handoff documents the following capabilities:

- Multi-domain dataset understanding and analysis.
- Domain-specific analyzers.
- Dynamic analysis planning and chart selection.
- Findings and weak-point recommendations.
- Narrative story generation.
- Data-quality analysis.
- Correlation significance and multicollinearity analysis.
- Share links with expiry, revocation and rate limits.
- Request-body limits and upload protections.
- Global dashboard search and export features.

These are documented existing capabilities. Their complete current
test status has not yet been revalidated in this audit.

## 6. Historical test baseline — requires revalidation

HANDOFF.md records the following results as of 2026-11-06:

- Backend: 372 pytest tests.
- Frontend: 443 Vitest tests.
- End-to-end: 13 Playwright tests.
- Additional opt-in tests.

Do not treat these as current test counts until the suites are run
again on the current main branch.

## 7. Scalability direction

Long-term goal: support large datasets, including datasets exceeding
one million rows, through measured and controlled processing.

Proposed infrastructure:

- PostgreSQL for users, workspace metadata and durable job records.
- Redis for job queueing and coordination.
- Celery workers for asynchronous analysis.
- S3-compatible object storage for persistent datasets and artifacts.
- FastAPI for job lifecycle and workspace APIs.

No dataset-size or concurrency target is considered achieved until
validated through repeatable load, memory and correctness tests.

## 8. Prioritized roadmap

### Phase 1 — Baseline and design
- [ ] Re-run backend, frontend and end-to-end tests.
- [ ] Measure current upload and analysis memory usage.
- [ ] Audit upload lifecycle and temporary data cleanup.
- [ ] Define dataset and analysis job lifecycle contracts.
- [ ] Define temporary versus persistent data boundaries.

### Phase 2 — Asynchronous processing
- [ ] Introduce job submission and status APIs.
- [ ] Add controlled background worker execution.
- [ ] Preserve existing temporary analysis behavior.
- [ ] Add cancellation and failure handling.
- [ ] Test concurrent submissions and resource limits.

### Phase 3 — Optional persistence
- [ ] Introduce PostgreSQL metadata models.
- [ ] Add S3-compatible object storage.
- [ ] Implement explicit save and delete operations.
- [ ] Define retention and cleanup policies.

### Phase 4 — Accounts and workspaces
- [ ] Implement authentication.
- [ ] Enforce workspace ownership and data isolation.
- [ ] Add saved datasets and analyses.
- [ ] Add the optional workspace experience to the frontend.

### Phase 5 — Scale and reliability
- [ ] Benchmark representative large datasets.
- [ ] Test worker failure and job recovery.
- [ ] Test storage cleanup and deletion.
- [ ] Test authorization and share-link security.
- [ ] Document measured limits and operational costs.

## 9. Working rules

- Read AGENTS.md before implementation.
- Read HANDOFF.md and relevant CHANGELOG.md sections.
- Preserve working features and API contracts.
- Make incremental, testable changes.
- Update this document when project status changes.
- Record architecture decisions in DECISIONS.md.
- Record confirmed unresolved issues in KNOWN_ISSUES.md.
- Never claim tests or benchmarks passed without running them.

## 10. Phase work — 2026-11-27

### Completed: Phase 1 test cleanup (merged)

`develop` is at `575ec68a`, the merge commit for PR #1 from `freebuff/phase1`. Phase 1 removed two obsolete
tests (the "four uploads run four analyses at once" concurrency test and the "body is parsed and validated
before the budget is spent" test), kept the rest of the rate-limit suite, added a share-cache regression
test, and ignored the test runner's `.logs/` directory. No application code changed.

### In review: Phase 2 share-create rate limiting

Branch `phase/2-rate-limit`, based on `develop`'s `575ec68a`. Implementation commit `67c87ed`
("Spend the share-create budget before FastAPI reads the body"), plus a documentation commit.

- New `ShareCreateRateLimitMiddleware` (`app/rate_limit.py`), pure ASGI and registered after
  `BodySizeLimitMiddleware`, so it is the outermost of the two: an over-budget `POST /api/share` is answered
  429 without its body being read — not by the router, not by the size cap.
- Expected order of refusals: 429 (budget) before 422 (validation) and before 413 (size cap).
- `create_share_link` no longer calls the limiter; `GET /api/share/{token}` keeps its handler-level limiter.
- The 429 body, `Retry-After` and the client key are unchanged.

**Verification (2026-11-27).** Focused rate-limit, body-limit and share-cache tests: 46 passed. Full backend
suite: 489 passed, 11 pre-existing pandas/`dateutil` warnings, no failures. Real uvicorn 0.54.0 over TCP
(httpx2, `curl`, raw socket; budget 3 per 5 s, 1 MB body cap) returned 200 and 413 under budget and
`429` with `retry-after: 5` over budget for normal, malformed, oversized, 6 MB `Content-Length` and 6 MB
chunked posts. No connection reset, EPIPE or hang, including a client that kept uploading 8 MB after the
429; the window refilled to 200, the read endpoint stayed unaffected, and 10 simultaneous posts gave
exactly 3 × 200 and 7 × 429.

**Status:** pull request into `develop` from `phase/2-rate-limit`; not merged, nothing deployed.

### Remaining tasks

- Review and merge (or return) the Phase 2 pull request.
- Decide whether the budget should be shared across workers; it is currently per process, in memory.
- Keep the create-side budget and the read-side limiter in step if either limit is tuned.
- Add a CORS or auth middleware only with the knowledge that it would sit outside the limiter.
