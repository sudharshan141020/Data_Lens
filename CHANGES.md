# Segmentation / Clustering — changed files

Drop these into your local project at the matching paths (all under
`app/` and `frontend/src/`).

## New files
- `app/clustering.py` — from-scratch numpy k-means (k-means++ init, 5
  restarts, silhouette-based auto-k in 2–5), rule-based plain-English
  segment labels, sample-and-assign for large datasets (fit on ≤5,000
  rows, assign every row).
- `frontend/src/components/SegmentsPanel.jsx` — cluster cards (reuses
  existing `insight-card`/`dq-bar-*` CSS, no new styles needed).

## Modified files
- `app/main.py` — imports `analyze_segments`, adds `_serialize_segments()`,
  calls it inside `_run_v2_pipeline` (covers all 3 entry points: single
  upload, remap, combined files), adds a `segments` key to the v2
  response, and appends a `segments_scatter` entry to `all_analyses`
  (section: "Segments") that reuses `_compute_scatter`'s existing
  `{x, y, group}` shape — zero chart-rendering code changed.
- `frontend/src/components/AnalysisExplorerV2.jsx` — one-line addition:
  `'Segments'` added to `SECTION_ORDER`.
- `frontend/src/App.jsx` — imports and mounts `<SegmentsPanel>` at
  tick "09", right after `CorrelationCenter`.

## Verified this session
- Synthetic 3-blob test: correctly recovers all 3 groups, sensible labels.
- Edge cases: <2 measures, <30 usable rows, constant columns — all
  guarded with plain-English notes, no crashes.
- 150K rows: 0.87s (well inside the existing performance budget).
- Real sample datasets (sales/healthcare/manufacturing): all produce
  distinct, plausible segments.
- Full HTTP round-trip via `/api/analyze` (FastAPI TestClient): 200 OK,
  segments present, response JSON-serializes cleanly.
- `/api/export/pdf` with the new `segments` key in the payload: still
  200 OK (pdf_report.py doesn't touch it, matches the export's
  documented scope).
- `top_analyses` (dashboard top-3) confirmed unaffected — purely additive.
- `frontend`: `npm install && npm run build` succeeds with no new
  warnings/errors.

## Not yet done
- Not visually verified in a browser (no way to screenshot from this
  sandbox) — worth a quick look once you pull it down, especially the
  segment card color-to-scatter-point color matching.
- Segments aren't included in Excel/PDF export content — matches the
  documented export scope, but flag if you want them added.
