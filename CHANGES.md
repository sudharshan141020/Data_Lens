# Seasonality Decomposition — changed files

Drop these into your local project at matching paths (`app/` and
`frontend/src/`). This is backlog item #5.

## New files
- `app/seasonality.py` — classical additive decomposition (centered 2x12
  moving-average trend, calendar-month seasonal indices, residual), pandas/
  numpy only, no statsmodels. Runs on the same monthly trend data
  `forecast_trend` already consumes.
- `frontend/src/components/SeasonalityPanel.jsx` — summary panel (peak/
  trough month, seasonal/trend strength bars), reuses existing
  `insight-card`/`dq-bar-*` CSS.

## Modified files
- `app/main.py` — imports `decompose_trend`, adds `_serialize_seasonality()`,
  calls it on the trend data *before* `forecast_trend` appends its
  projected points (order matters — decomposition needs real history
  only). Adds a `seasonality` key to the v2 response, and — only when a
  pattern is found — appends a `seasonal_decomposition` chart entry to
  `all_analyses` (section: "Seasonality").
- `frontend/src/components/AnalysisChartV2.jsx` — new `DecompositionView`
  component (3 stacked panels: Trend, Seasonal Pattern, Residual) and a
  new `case 'seasonal_decomposition':` in the render switch.
- `frontend/src/components/AnalysisExplorerV2.jsx` — `'Seasonality'` added
  to `SECTION_ORDER`.
- `frontend/src/App.jsx` — imports and mounts `<SeasonalityPanel>` at
  tick "10", right after `SegmentsPanel`.

## Why this needed a real fix mid-build (not just tuning a threshold)
First pass gated "is this a real pattern" on a strength score alone
(`seasonal_strength > 0.15`). Testing that against **pure noise** exposed
a false positive: with only 2.5 years of data, each calendar month's
seasonal index is estimated from just 1–2 points, so the index ends up
fitting the noise rather than a real pattern — 30 months of pure noise
scored `seasonal_strength: 0.72`, which would've shown up in the app as a
confident, fabricated seasonal claim.

Fixed by adding a proper significance test — one-way ANOVA (`scipy.stats.
f_oneway`) on the detrended values grouped by calendar month, gated at
p < 0.05 — same spirit as `correlation_center.py` gating correlations on
a p-value rather than trusting r alone on a small sample. Also raised the
minimum history from 2 years to **3 full years (36 months)**, since after
the centered moving-average trims ~12 edge points, 2 years left too few
valid observations per calendar month for the test to have any real
degrees of freedom. Re-verified pure noise correctly returns unavailable
at 30, 36, and 60 months after the fix.

## Verified this session
- Synthetic 36-month series with a known injected trend + seasonal
  pattern (peak Dec, trough Feb): recovered correctly, `p=0.000`,
  `seasonal_strength=1.0`.
- Pure noise at 30/36/60 months: correctly `available: False` at every
  length (the bug above is fixed).
- Real sample datasets:
  - `demo-sales-data.csv` (2 years) — correctly declines, "needs 3 years."
  - `sample-healthcare-data.csv` (3 years, no real seasonal pattern in
    this synthetic data) — correctly declines with p=0.32, doesn't force
    a finding just because there's enough history.
  - None of the current sample datasets happen to have 3+ years *and* a
    genuine seasonal pattern, so there's nothing in the gallery today
    that shows the feature's "available: True" path live — worth keeping
    in mind if you want a demo dataset for this specifically.
- Full HTTP round-trip via `/api/analyze` (FastAPI TestClient) on a
  synthetic 3.5-year seasonal dataset: 200 OK, seasonality detected,
  forecast still works independently on the same trend, response
  JSON-serializes.
- `/api/export/pdf` with the new `seasonality` key present: still 200 OK.
- `frontend`: `npm run build` succeeds, no new warnings.

## Not yet done
- Not visually verified in a browser (no way to screenshot from this
  sandbox) — worth a look once you pull it down, especially the 3-panel
  stacked decomposition chart layout on narrower screens.
- No sample dataset currently demonstrates the "pattern found" path —
  consider adding one to the gallery if you want a live demo.
