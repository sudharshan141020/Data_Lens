# Compare Two Files Side-by-Side — changed files

Item #6 of the "add all" batch. New: `app/comparison.py`,
`frontend/src/components/CompareView.jsx`. Modified: `app/main.py`,
`frontend/src/api.js`, `frontend/src/App.jsx`,
`frontend/src/components/Sidebar.jsx`.

Different from the existing `/api/analyze-combined` (which merges two
files' rows into one dataset) — this runs each file through the exact
same pipeline independently, then diffs the two results: KPI deltas
(sorted by size of change), correlation changes (including sign flips),
row count / data quality / domain comparison.

`main.py` refactor: extracted `/api/analyze`'s column-detection logic
into a shared `_full_analyze_from_df()` helper, used by both
`/api/analyze` and the new `/api/compare` — avoids duplicating that
logic a second time, which is exactly the failure mode ("recurring bug
pattern... across ~5 independent code paths") already documented for
this project. Regression-tested: `/api/analyze` still works identically
after the refactor.

Frontend: a new "Compare two files…" mode in the sidebar, mirroring the
existing combine-mode UI pattern exactly but capped at exactly 2
selections. Produces a pseudo-session (`isComparison: true`) that
renders `<CompareView>` instead of the normal dashboard.

## Verified this session
- Full HTTP round-trip on two real months of your actual sales data
  (November vs December): correct KPI deltas (e.g. total_units_sold
  +23.3%, avg_revenue_per_customer -22.6%), correct correlation deltas
  with no false sign-flips.
- Edge case: comparing a file with no usable numeric metric correctly
  returns 400 with a clear message, rather than crashing on a missing
  `kpis` key deeper in the diff logic (caught and fixed during
  testing — the categorical-only fallback response always includes a
  `kpis` key, just a minimal one, so the guard checks the actual
  `no_numeric_metric` flag instead).
- Regression check: `/api/analyze` and `/api/analyze-combined` both
  still return 200 and work identically after the `_full_analyze_from_df`
  refactor.
- `frontend`: `npm run build` succeeds, no new warnings.

## Not yet done
- Not visually verified in a browser — worth checking the sidebar's
  compare-mode checkboxes (capped at 2, so a 3rd click should just do
  nothing rather than deselecting anything) and the CompareView layout.
