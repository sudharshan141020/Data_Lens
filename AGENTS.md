# DataLens — Agent Instructions

## Project rules
- Read this file and `HANDOFF.md` before making changes.
- Read relevant sections of `CHANGELOG.md` before modifying existing features.
- Inspect the actual source code before deciding what needs to be changed.
- Do not assume that older handoff notes describe the current implementation.
- Do not rewrite working modules or replace entire files unnecessarily.
- Preserve existing API contracts, frontend behavior, tests, and security protections unless the task explicitly requires a change.

## Architecture and scalability
- The long-term goal is a reliable dataset-analysis platform that can handle large datasets, including datasets exceeding one million rows.
- Design for asynchronous analysis, persistent job state, controlled worker concurrency, and efficient data storage.
- Do not claim that a feature supports a particular dataset size or concurrency level without measured tests.
- Avoid loading or copying unnecessarily large datasets into memory.
- Prefer incremental, testable changes over a complete rewrite.
- Do not introduce Kubernetes or unnecessary infrastructure without a demonstrated need.

## Security
- Never commit API keys, passwords, tokens, credentials, or private datasets.
- Never weaken `share_guard.py` or other protections for personal or sensitive data without explicit justification and tests.
- Validate uploads, request sizes, file paths, and user-controlled inputs.
- Do not expose private data through public share links or exports.

## Development workflow
1. Inspect `git status` before editing.
2. Identify the relevant modules and existing tests.
3. Explain the intended changes before substantial modifications.
4. Implement the smallest complete solution.
5. Run relevant backend, frontend, and end-to-end tests.
6. Report the exact commands run and their actual results.
7. Do not claim tests passed if they were not executed.
8. Do not discard user changes, force-push, or reset branches to make a task easier.

## Documentation
- Update `HANDOFF.md` when a substantial task changes the project state or the next steps.
- Add chronological entries to `CHANGELOG.md` for meaningful changes.
- Record lasting architecture decisions in `DECISIONS.md`.
- Update `PROJECT_STATUS.md` with verified progress.
- Record confirmed unresolved problems in `KNOWN_ISSUES.md`.
- Do not duplicate the full changelog or handoff history in other files.

## Completion report
At the end of each substantial task, report:
- What changed and why.
- Files created, modified, or deleted.
- Tests executed and their results.
- Known limitations or unresolved issues.
- Recommended next task.
- Git commit hash, if committed.

## Collaboration
- Freebuff is the primary implementation environment.
- Claude.ai is used for planning, reviewing, and identifying risks.
- Avoid having multiple agents edit the same files simultaneously.
- Treat GitHub as the shared source of truth.
- Review incoming changes before merging or pushing.
