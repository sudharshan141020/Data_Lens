# DataLens — Architecture Decisions

## ADR-001: Hybrid temporary and persistent workspace model

- **Status:** Accepted
- **Date:** 2026-11-25

### Context

DataLens currently follows a privacy-first workflow in which users can
analyze datasets without requiring accounts or permanent storage.

The project needs a path toward saved workspaces, background processing,
and larger datasets without removing the simplicity of the existing
temporary analysis experience.

### Decision

DataLens will use a hybrid model:

1. Temporary analysis is the default.
2. Users do not need an account to use temporary analysis.
3. Users may optionally create an account and use a persistent workspace.
4. Dataset and analysis persistence requires an explicit user action.
5. The existing analysis engine will be preserved and extended
   incrementally rather than replaced.

### Temporary mode

- No account is required.
- Uploaded datasets and analysis results are temporary.
- Temporary data must have a defined expiry and cleanup policy.
- Temporary data must not silently become persistent workspace data.
- Existing share-link protections must remain in place.

### Persistent workspace mode

- Authentication is required.
- Users can explicitly save datasets and analyses.
- Workspace records must be isolated by user ownership.
- Users must be able to delete their saved data.
- Storage and retention behavior must be documented clearly.

### Proposed technical direction

- React: frontend and workspace experience.
- FastAPI: API, authentication, upload validation and job orchestration.
- PostgreSQL: users, workspace metadata and durable job records.
- Redis: background-job queue and short-lived coordination.
- Celery workers: asynchronous dataset processing.
- S3-compatible object storage: persistent datasets and generated artifacts.

Temporary job state should expire. Do not persist temporary uploads
or results merely because the infrastructure supports persistence.

### Implementation principles

- Preserve existing APIs and analysis behavior where practical.
- Preserve share_guard.py and existing privacy protections.
- Introduce authentication and storage incrementally.
- Use explicit retention, deletion and access-control rules.
- Test user isolation and temporary-data cleanup.
- Do not claim scalability without measured load and memory tests.
- Do not introduce Kubernetes without a demonstrated need.

### Rollout order

1. Audit the current implementation and establish a baseline.
2. Define dataset and analysis job lifecycle contracts.
3. Introduce asynchronous processing without breaking temporary mode.
4. Add durable workspace metadata and object storage.
5. Add authentication and strict workspace isolation.
6. Add the optional save and revisit experience.
7. Test cleanup, deletion, security and performance.

### Non-goals

- Making account creation mandatory.
- Persisting every uploaded dataset by default.
- Rewriting the existing analysis engine.
- Running unlimited concurrent analysis jobs.
- Introducing Kubernetes in the initial implementation.
