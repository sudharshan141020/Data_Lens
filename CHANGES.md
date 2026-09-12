# Pytest Regression Suite — changed files

Item #8, the final item of the "add all" batch. New: `pytest.ini`,
`requirements-dev.txt`, and `tests/` (conftest.py + 5 test files, 44
tests total).

## How to run
```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```
Runs in ~4-5 seconds. `requirements-dev.txt` is separate from
`requirements.txt` on purpose — pytest has no business in the production
install.

## What's covered
- **test_domain_detection.py** — all 11 domains detect correctly;
  specifically guards the exact failure mode `domains.py`'s own
  docstring already documents (an unrelated domain scoring too close to
  the correct one via an overly generic keyword).
- **test_statistical_modules.py** — codifies every correctness check
  done manually while building this session's 6 statistical modules,
  including the two real bugs that were caught and fixed along the way:
  seasonality's false-positive-on-noise bug, and anomaly detection's
  z≈0-described-as-unusual bug and its row-index-after-dropna bug.
- **test_pipeline_robustness.py** — targets the project's own documented
  recurring bug pattern directly: a column named like a real metric but
  whose data doesn't support it (e.g. a "Revenue" column full of text).
  Also covers general edge cases (all-NaN columns, single row/column,
  constant columns) and a 150K-row performance regression guard.
- **test_file_formats.py** — CSV/TSV/JSON (all 3 shapes)/Parquet all
  load correctly and equivalently; malformed files fail cleanly.
- **test_api_endpoints.py** — smoke tests for every endpoint the
  frontend actually calls, including the two new ones added this
  session (`/api/compare`, `/api/export/cleaned-csv`).

## One real assertion fix made while getting this to pass
`test_saas_does_not_leak_into_other_domains` initially failed: the
synthetic SaaS test dataset's `Customer ID` column legitimately also
scores 2 points toward the `sales` domain (which lists `CUSTOMER` as one
of its own signals) — not a bug, since a SaaS dataset genuinely does
have customers. The original assertion ("zero score anywhere else") was
an unrealistic bar for a role that's legitimately shared across similar
domains. Fixed to assert the correct domain wins by a clear margin
(more than double the next-highest score) instead, which is the
actually meaningful thing to guard against.
