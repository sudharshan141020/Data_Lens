# Confidence Intervals on KPIs — changed files

Second item of this round. New: `app/confidence_intervals.py`,
`frontend/src/components/ConfidenceIntervalsPanel.jsx`. Modified:
`app/main.py`, plus two test files updated with coverage.

Bootstrap resampling (not the classic mean ± 1.96×SE formula — makes no
distributional assumption about the data) on each numeric measure,
reporting a 95% interval alongside the point estimate. Same
performance-conscious sampling pattern as clustering.py/
anomaly_detection.py for very large datasets, with the same honest
disclosure when it kicks in.

## A real bug caught and fixed mid-build
First version sampled down to 20,000 rows for speed on large datasets,
then computed BOTH the point estimate and the CI from that same sample
— meaning a "sum" KPI would report a sampled subset's total, not the
real total. Fixed by decoupling the two: the point estimate is always
computed from the complete data (cheap, exact, O(n) regardless of
size), and only the bootstrap's job — estimating how wide the interval
should be — uses the sampled subset when the dataset is huge, correctly
rescaled by the TRUE row count rather than the sample size. Added a
dedicated regression test for exactly this (`test_confidence_interval_
point_estimate_matches_true_value_even_when_sampled`).

## Verified this session
- 150K rows: 0.22s, point estimate exactly matches the true full sum
  (74,989,965.04 both ways).
- Real demo sales data: Sales point estimate ($106,276.56) matches the
  actual total shown elsewhere in the app throughout this whole session
  — confirms the fix is correct, not just internally consistent.
- Both `avg` and `sum` aggregations verified against their true values.
- Edge cases (too few rows, no numeric measures) handled cleanly.
- Full HTTP round-trip + PDF export: 200 OK.
- Full pytest suite: 48/48 passing (46 existing + 2 new), ~7s.
