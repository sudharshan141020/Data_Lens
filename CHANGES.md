# Simpson's Paradox Check — changed files

Item #3 of the "add all" batch. New: `app/simpsons_paradox.py`,
`frontend/src/components/SimpsonsParadoxPanel.jsx`. Modified:
`app/main.py`, `frontend/src/App.jsx`.

Reuses the correlation pairs correlation_center.py already computes
(no recomputation) and checks whether each significant pair's sign
reverses within every subgroup of a categorical dimension — the
classic confounding-variable pattern. Strict definition: flags only
when ALL sufficiently-large subgroups reverse the overall sign, not
just most of them — deliberately conservative, since this is a subtle
claim that's easy to overstate.

Verified against a textbook-constructed example (two groups, each with
a real negative within-group slope, offset so the aggregate looks
positive: r=0.88 overall, r≈-0.63 and r≈-0.64 within each group) —
caught correctly. Confirmed zero false positives on a dataset with a
genuine, consistent correlation, and on the real demo sales data (which
doesn't happen to contain a real paradox). Full HTTP round-trip on both
real and synthetic data, plus PDF export with the new
`simpsons_paradox` key present: all 200 OK.
