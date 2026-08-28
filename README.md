# DataLens — Universal Data Intelligence

Upload any structured dataset — CSV, TSV, or Excel — and get back a full
analytical report in seconds: automatic domain detection, the 3 most
valuable analyses for that specific dataset, a plain-English narrative
story, statistically-validated correlations, and concrete, prioritized
recommendations. Not a generic BI dashboard — the analysis itself adapts
to whether it's looking at healthcare, sales, retail, education, HR,
traffic, or finance data.

**[Live demo →](#)** &nbsp;·&nbsp; *(add your Render URL here before sharing this repo)*

---

## Why this project is interesting

Most portfolio dashboards plot whatever columns exist. DataLens tries to
behave the way an actual analyst would: it figures out *what kind* of
dataset it's looking at, decides what's worth analyzing for that domain
specifically, and flags when a finding shouldn't be trusted.

- **Domain-aware, not one-size-fits-all.** Every uploaded file is scored
  against 8 domain profiles (healthcare, sales, retail, manufacturing,
  education, HR, traffic, finance) based on which semantic column roles are present, and the
  entire analysis — which KPIs matter, which charts get generated, what
  "weak points" even means — adapts to the result.
- **Statistically honest.** Every correlation is reported with its actual
  p-value and sample size, not just the coefficient. A strong-looking
  relationship on 12 rows gets flagged as unreliable instead of presented
  as a confident finding. Measures are also checked for multicollinearity
  (VIF) so redundant metrics don't get treated as independent signals.
- **100% rule-based — no LLM calls.** Every finding, story beat, and
  recommendation comes from an explicit, auditable scoring engine. This
  was a deliberate constraint: it keeps the tool free to run, safe to
  deploy publicly with no per-user API cost, and every output is
  traceable back to the exact rule that produced it.
- **Extensible by design.** Adding a new domain is one small analyzer
  file plus one registry line — the plugin architecture means domain
  logic never leaks into the shared pipeline.

## Features

- Automatic semantic column detection (works on files it's never seen —
  no fixed schema)
- Domain detection across 8 verticals with a confidence score
- Auto-generated dashboard: the 3 most important analyses, picked and
  chart-typed automatically, with reasoning for each choice
- Narrative "Story" mode — findings chained into a Trend → Breakdown →
  Driver → Recommendation arc
- Ranked findings and weak-point detection (plain-English, no jargon)
- Data quality report: missing values, duplicates, constant columns,
  outliers, overall quality score
- Correlation Center with significance testing (p-values, sample-size
  caveats) and multicollinearity (VIF) detection
- Linear trend forecasting on time-series measures, with a confidence
  check so it stays silent rather than guessing on noisy data
- Interactive filtering — date range and per-dimension filters that
  live-update the trend and breakdown charts client-side, no re-upload
- Global search across findings, charts, weak points, story, and
  correlations, with click-to-jump navigation
- One-click Excel or PDF export of the full report
- Multi-file sessions with pinning and dataset combining

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, pandas, NumPy, SciPy |
| Frontend | React 19, Vite, Recharts, lucide-react |
| Export | SheetJS (client-side .xlsx generation) |
| Deployment | Render (single process serves both API and built frontend) |
| Data & auth | None — everything is processed in memory per request and discarded |

---

## First-time setup (Windows)

Just **double-click `start.bat`**.

The first time you run it, it will:
1. Create a Python virtual environment (`venv`)
2. Install everything in `requirements.txt`
3. Launch the server and open your browser automatically at `http://127.0.0.1:8000`

Every time after that, double-clicking `start.bat` just launches it directly
(skips the setup since `venv` already exists) and opens your browser
automatically — no typing, no manual URLs.

## Manual setup (if you'd rather run it yourself)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Supported file formats
`.csv`, `.tsv`, `.xlsx`, `.xls` — column roles (date, revenue, profit,
category, region, customer, etc.) are auto-detected from the header names or
inferred from the data if the names don't match anything known.

## Project structure

```
Data_Lens/
  app/
    main.py                 — FastAPI app: serves both the API and the frontend
    understanding.py        — produces the DatasetProfile every downstream step consumes
    semantic_roles.py       — classifies each column into a semantic role
    domains.py               — scores which domain (healthcare/sales/etc.) the data belongs to
    analyzers/               — one plugin per domain (registry.py maps domain -> analyzer)
    analysis_planner.py      — decides which analyses to run and picks chart types
    executor_v2.py           — computes chart data for each planned analysis
    insight_engine.py        — positive findings
    weak_points.py           — problems, impact, priority, suggested action
    story_engine.py          — narrative arc over findings/weak points
    data_quality.py          — missing values, duplicates, outliers, quality score
    correlation_center.py    — correlation significance testing + multicollinearity (VIF)
    kpi.py, insights.py, column_detector.py, planner.py, executor.py
                              — original sales-specific pipeline, kept running
                                alongside the domain-aware one (legacy fields in the API response)
    static/                   — the BUILT frontend (do not hand-edit — see below)
  frontend/                   — frontend SOURCE CODE (edit here, then rebuild)
  requirements.txt
  run.py                      — launches the server + opens your browser
  start.bat                   — Windows one-click launcher
```

## If you want to change the frontend design or behavior

Edit files under `frontend/src/`, then rebuild and re-copy into the
backend's static folder:

```powershell
cd frontend
npm install      # first time only
npm run build
cd ..
Remove-Item -Recurse -Force app\static
Copy-Item -Recurse frontend\dist app\static
```

Then just run `start.bat` (or `python run.py`) again — the server will pick
up the newly built files automatically since it serves whatever is in
`app/static`.

For active frontend development with hot-reload instead of rebuilding every
time, run the backend (`python run.py`) and, separately, `npm run dev`
inside `frontend/` — set `VITE_API_BASE=http://127.0.0.1:8000` in a
`frontend/.env` file so the dev server talks to your backend on a different
port.

## Notes
- Nothing is persisted or sent anywhere beyond your own machine — each
  upload is processed in memory and discarded after the response is sent.
- If you ever move or rename this folder, delete `venv` and let `start.bat`
  recreate it — virtual environments hard-code absolute paths and break if
  the folder moves.

## Roadmap
- More domains (Retail, Manufacturing, Agriculture, Sports, Marketing,
  Customer Support)
- Interactive filtering (date/region/category filters live-updating charts)
- Global search across charts/insights/findings
- Trend forecasting on time-series measures
- PDF export
- Auth + persistence — an open product decision, not a default: this app
  is currently pitched as "nothing is stored," and adding accounts
  reverses that. See `HANDOFF.md` for the full reasoning.
