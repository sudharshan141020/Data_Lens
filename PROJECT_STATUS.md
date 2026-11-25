# DataLens — Project Status

Last reviewed: 2026-11-25

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
