# Multivariate Anomaly Detection — changed files

Item #2 of the "add all" batch. New: `app/anomaly_detection.py`,
`frontend/src/components/AnomaliesPanel.jsx`. Modified: `app/main.py`,
`frontend/src/App.jsx`, `frontend/src/components/AnalysisExplorerV2.jsx`
(added "Anomalies" to SECTION_ORDER).

Flags rows unusual across several measures *together*, via Mahalanobis
distance with a proper chi-square p-value gate (alpha=0.01) — catches
rows where no single column looks extreme but the combination does
(e.g. a normal order count with abnormally low revenue, breaking the
usual revenue/orders relationship). From-scratch numpy/scipy, same
pattern as clustering.py and correlation_center.py.

Reuses the scatter chart infrastructure directly (zero new chart code) —
same trick segmentation used, colored "Anomaly" vs "Normal" instead of
by cluster. On a large dataset, every flagged anomaly is kept and the
display budget is filled with a random sample of normal points, so
anomalies never get sampled away from the chart.

Caught and fixed during testing: the "why flagged" explanation initially
could describe a measure sitting exactly at the average (z≈0) as
"unusually high" — that happened when a row was the 2nd-most-extreme
of only 2 measures. Added a z-score threshold so only genuinely extreme
individual measures get named; when none qualify (the anomaly is purely
a broken correlation, no single measure extreme), it says so honestly
instead of manufacturing a specific-sounding reason.

Verified: synthetic test with 5 injected multivariate anomalies (each
individually normal-looking) — all 5 correctly caught. Edge cases
(<20 rows, 1 measure, perfectly-correlated/singular-covariance measures)
all handled without crashing. 150K rows: 0.09s. Real demo data: 22 of
600 rows flagged (3.7%), with a sensible top example (deep-discount
order, deeply negative profit). Full HTTP round-trip + PDF export both
200 OK.
