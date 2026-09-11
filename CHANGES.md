# Benford's Law Check — changed files

Item #4 of the "add all" batch. New: `app/benford.py`,
`frontend/src/components/BenfordPanel.jsx`. Modified: `app/main.py`,
`frontend/src/App.jsx`.

Chi-square goodness-of-fit test comparing each monetary column's
leading-digit distribution to Benford's Law's expected distribution.
Only runs on columns semantically identified as monetary
(FINANCIAL_METRIC/PROFIT/UNIT_COST roles) — deliberately not applied to
arbitrary numeric columns like ages or IDs, since Benford's Law doesn't
apply to those. Also gates on the values spanning at least 2 orders of
magnitude, since the test isn't meaningful on a narrow range regardless
of column type. Phrasing is deliberately hedged: a deviation is called
"worth a closer look," not proof of anything, since rounding/caps/range
restrictions can also cause it.

Verified in both directions: synthetic log-uniform data spanning 10^1–
10^6 correctly passes (p=0.71); synthetic data with a uniform (non-
Benford) leading-digit distribution across 3 orders of magnitude is
correctly flagged (chi²=721.8, p<0.0001). Edge cases (too few values,
no monetary columns, narrow magnitude span) all handled cleanly. Real
demo data: Sales correctly skipped (too narrow a range), Profit checked
and flagged. Full HTTP round-trip + PDF export both 200 OK.
