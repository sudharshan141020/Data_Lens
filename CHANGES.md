# Export Cleaned CSV — changed files

Item #7 of the "add all" batch. New: `app/data_cleaning.py`. Modified:
`app/main.py`, `app/anomaly_detection.py` (bugfix — see below),
`frontend/src/api.js`, `frontend/src/App.jsx`,
`frontend/src/components/ExportMenu.jsx`.

## ⚠️ Supersedes the anomaly-detection-feature.zip's app/anomaly_detection.py
Building this exposed a real bug in the anomaly detection module shipped
earlier: `row_index` in its output referred to a row's position *after*
dropping NaN rows, not its actual position in the original file. Harmless
for the UI panel (just a display label), but useless for mapping
anomalies back onto the original dataframe — which cleaning needs to do.
Fixed by preserving the original index through the dropna step. Also
added a new `all_anomaly_row_indices` field (uncapped — the existing
`anomalies` list is capped at ~50 for UI readability, but a "flag every
unusual row" feature needs all of them, not just the top 50 with a full
explanation). Re-verified against the original synthetic test — anomalies
still correctly mapped, including with NaN gaps interspersed.

## What "cleaned" means here, deliberately conservative
- Removes exact duplicate rows only (unambiguous — no legitimate reason
  two fully-identical rows both belong).
- FLAGS anomalous rows (new `flagged_as_unusual` column) rather than
  deleting them. Auto-deleting statistical outliers would be a real,
  opinionated data-loss decision this app has no business making
  silently — a genuinely large sale isn't "dirty data" just because
  it's unusual.

New `/api/export/cleaned-csv` endpoint: stateless like the other exports
(re-accepts the file, since the raw dataframe isn't kept server-side
between requests), returns the cleaned CSV as a direct file download
with a summary in an `X-Clean-Summary` response header. Wired into the
existing Export dropdown as a 4th option, using the `sourceFile` each
session already keeps in memory — only shown when a single source file
exists (hidden for combined/comparison sessions, which don't have one).

## Verified this session
- Correctness bug caught and fixed during testing: an artificial test
  with 80 "anomalies" that were all set to the identical value looked
  like duplicates were being over-removed (99 vs. the expected 20) —
  turned out to be correct behavior (those rows genuinely were exact
  duplicates of each other), not a bug. Re-tested with distinct
  anomaly values to properly isolate the two effects: 20/20 duplicates
  removed correctly, 87 of ~80 injected anomalies flagged (a few extra
  from expected false positives at the 1% significance threshold).
- Full HTTP round-trip on real demo data: 200 OK, correct
  Content-Disposition/filename, summary header present and accurate,
  downloaded CSV has the right shape and a working `flagged_as_unusual`
  column (22 flagged, matching the anomaly count already shown
  elsewhere in the app for this same file).
- Regression check: `/api/analyze` and `/api/export/pdf` both still
  200 OK after the anomaly_detection.py fix.
- `frontend`: `npm run build` succeeds, no new warnings.
