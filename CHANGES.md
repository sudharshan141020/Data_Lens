# Period-over-Period Comparison — changed files

Item #1 of the "add all" batch. New: `app/period_comparison.py`,
`frontend/src/components/PeriodComparisonPanel.jsx`. Modified:
`app/main.py`, `frontend/src/App.jsx`.

Compares the latest complete month vs. the one before using a Welch's
t-test on the raw row-level values (not just a percent-change on the
aggregated totals) — same scipy pattern as correlation_center.py.
Deliberately NOT gated on significance (unlike seasonality.py): this is
one planned comparison, not 12 simultaneous ones, so it always reports
the number and its p-value rather than hiding an uncertain-but-real
change. Verified against real demo data (down 6.3%, correctly flagged
not significant) and synthetic cases (clear jump → p=0.000; pure noise →
correctly not significant). Full HTTP round-trip + PDF export both
verified 200 OK with the new `period_comparison` key present.
