# Cohort / Retention Analysis — changed files

First item of the new round. New: `app/cohort_analysis.py`,
`frontend/src/components/CohortsPanel.jsx`. Modified: `app/main.py`,
`frontend/src/components/AnalysisChartV2.jsx`,
`frontend/src/components/AnalysisExplorerV2.jsx`, plus the two test
files updated with cohort coverage.

Groups each entity (customer/patient/student/etc.) by the month of
their FIRST appearance, then tracks what fraction of that cohort is
still active in each subsequent month — the classic retention-curve
view. Distinct from period_comparison.py (aggregate totals between two
periods) and seasonality.py (repeating calendar pattern): this is
specifically about whether the SAME entities keep coming back.

Reuses the existing heatmap chart component directly — a small,
backward-compatible addition (`value_suffix` field, defaults to empty
string) lets it show "65.0%" instead of a bare number, and setting
`type: "pivot"` gets the correct single-color intensity scale instead
of the diverging red/green one meant for signed values like
correlations.

## Two real bugs caught and fixed while building this
1. Assumed `profile.semantic_roles` was `{column: {"role": ..., ...}}`
   (matching a shape used internally, transiently, in understanding.py)
   when it's actually stored as the flattened `{column: role_string}`.
   Caused an immediate `TypeError`.
2. A variable-ordering bug: `cohort_report = analyze_cohorts(...)` was
   placed after the code that already referenced it, causing an
   `UnboundLocalError`. Caught immediately by the very API smoke tests
   `pytest-suite-feature.zip` added last round — direct evidence that
   suite is already paying for itself.

## Verified this session
- Real demo sales data: correctly finds 5 cohorts, "26.1% average
  month-1 retention" (this dataset has no real repeat-customer pattern
  baked in, so a modest/noisy retention rate is the honest answer).
- Synthetic dataset with a known, injected 60% month-over-month
  retention probability: recovered exactly 60.0%.
- Edge cases (no entity column, single cohort month) both correctly
  decline with a clear note.
- Full HTTP round-trip + PDF export: 200 OK.
- Full pytest suite: 46/46 passing (44 existing + 2 new for this
  feature), ~4.9s.
