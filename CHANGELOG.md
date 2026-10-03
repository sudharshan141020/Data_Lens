# DataLens — Change Log

Plain-language running log of what changed, and why, in the order it
happened — oldest at the top, newest at the bottom. Meant to be
readable on its own: enough to remind you what changed in each update,
and enough detail to explain any of it to an interviewer without
having to re-open the code first. Each entry also lists the files it
touched.

**How this file works going forward:** every time we finish an update,
a new dated entry gets appended to the bottom — never rewritten or
replaced. If you want to know "what did we do on date X," it's a
scroll down, not a git-blame.

**Where the history below comes from:** everything up to and including
the "From an earlier chat, continued (session 3)" section was pulled
directly out of three old chat sessions where this project was
actually built — not reconstructed from general memory of the project,
but assembled by going back through those conversations themselves
(including a second pass over tool-call history to catch anything a
first summary missed). It's grouped the way those chats described
their own work (phases, feature names) rather than by exact calendar
date, since exact dates for that period weren't tracked at the time.
A few bullets note explicitly where a detail is slightly less certain
(early edits described from surrounding context rather than a full
re-read) — flagged inline rather than presented as more precise than
it is.

Everything from "2026-09-25 — Readable chart legends" onward is a real
per-update log written at the time of the change, with exact file
lists — no reconstruction involved.

If more old chats turn up later, their history gets merged in above
this note, in the right chronological spot, the same way.

---

## From an earlier chat (session 1) — the project's actual origin

> Reconstructed from an old chat's own description of itself. The project started as two folders (`sales-insights-backend/`, `sales-insights-frontend/`), got merged into `sales-insights-app/`, and after a sandbox reset mid-chat came back as `datalens/`. File paths below are relative (`app/…`, `frontend/src/…`).

### Phase 0: the original Business Dashboard project (Excel, SQL, Power BI)
- [superstore.csv] — Downloaded the standard Sample Superstore dataset (9,994 rows) from a GitHub mirror — you had no data to build the dashboard on.
- [Superstore_Cleaned.xlsx, clean_data.py] — Converted dates to real Excel dates and added live-formula columns (Order Year, Order Month, Ship Days, Profit Margin %). Also added a "Data Quality Log" sheet — this was the data-cleaning step of the project.
- [clean_data.py] — Fixed an itertuples attribute-name crash on columns with spaces — the script failed on the first run.
- [Superstore_Cleaned.xlsx] — Recalculated formulas with recalc.py (about 40k cells, 0 errors) — so the cached values were populated.
- [Superstore_Cleaned.xlsx / Data Quality Log sheet] — Documented that the file was already clean (no duplicates, nulls or negatives) instead of inventing fixes — a fake cleaning step would look bad to a reviewer.
- [superstore.db, build_db.py] — Loaded the cleaned data into SQLite with indexes — this was the SQL layer.
- [queries.sql] — Added five KPI queries: MoM retention, region×category profitability, Pareto customers, discount bands, YoY by region — to produce real insights instead of bar charts.
- [run_queries.py] — Fixed a bug where every statement was filtered out because each chunk started with a comment — the query runner printed nothing.
- [powerbi_build_guide.md] — Wrote the Power BI data model, DAX measures and 3-page layout — Power BI Desktop is Windows-only, so I couldn't produce a .pbix from the sandbox.

### Phase 1: Pivot to a web tool (backend first)
- [sales-insights-backend/app/column_detector.py] — Added column role detection by name hints plus a dtype fallback — so the tool works on CSVs it has never seen.
- [app/kpi.py] — Added KPI, monthly-trend and breakdown computation driven by the detected mapping — nothing hardcoded to Superstore's column names.
- [app/insights.py] — Added rule-based detectors (trend, segment concentration, margin risk with discount-band analysis, customer concentration), ranked by score — this was the "auto-insight" engine, deliberately free of paid APIs.
- [app/main.py, requirements.txt, README.md] — Added the FastAPI app with /analyze and /health — this is the backend entry point.
- [app/column_detector.py] — Replaced per-column matching with a two-pass exact-then-substring matcher — testing showed "Country" was being chosen as Region over the real "Region" column.
- [requirements.txt] — Loosened the pinned versions (fastapi/pandas/uvicorn/python-multipart) — pandas==2.2.2 tried to compile from source on your Python 3.14 and failed, which also left uvicorn uninstalled.
- [app/main.py] — Added an encoding fallback (utf-8 → utf-8-sig → latin1 → cp1252) — your CSV threw "'utf-8' codec can't decode byte 0xa0".

### Phase 2: Frontend v1 ("Ledger" dark theme)
- [frontend/src/index.css] — Created the dark "ink" design tokens with Space Grotesk, Inter and JetBrains Mono — the look came from the tool's own idea (ranked findings).
- [frontend/src/api.js] — Added the fetch wrapper for the upload endpoint — so the UI could call the backend.
- [components/UploadZone.jsx] — Added a drag-and-drop upload zone — the entry point of the app.
- [components/ColumnMapping.jsx] — Added a "confirm the read" screen — so a bad auto-detection is caught before it produces a misleading dashboard.
- [components/KpiStrip.jsx, TrendChart.jsx, BreakdownChart.jsx] — Added KPI cards, a revenue/profit line chart, and category/region bars that turn red when margin is negative — the first dashboard.
- [components/InsightsPanel.jsx] — Added insight cards with a signal-strength bar sized to each finding's score — makes the ranking visible.
- [App.jsx, App.css, .env, README.md, index.html] — Added the upload → mapping → dashboard flow and the base styles — the full v1 UI.

### Phase 3: One app, Excel support, one-click launch
- [app/main.py] — Made FastAPI serve the built React app from app/static/ and moved the API to /api/analyze and /api/health — so there is one process and no CORS, and one server to launch.
- [app/main.py] — Added _load_dataframe supporting .csv, .tsv, .xlsx and .xls — you asked for Excel and other analyst formats.
- [requirements.txt] — Added openpyxl and xlrd — needed to read Excel files.
- [frontend/src/api.js, components/UploadZone.jsx] — Switched to same-origin /api/... calls and to accepting .csv/.tsv/.xlsx/.xls — matches the merged backend.
- [run.py] — Added a launcher that starts uvicorn and opens the browser automatically — you wanted no manual redirecting.
- [start.bat] — Added a double-click launcher that creates the venv and installs requirements on first run — so there's no PowerShell typing.
- [README.md, frontend/] — Wrote setup and rebuild instructions and copied the frontend source into frontend/ — so future edits could be rebuilt into app/static/.

### Phase 4: Detection bugs, deployment, recommendations
- [app/column_detector.py] — Made quantity detection win before the loose discount heuristic, made percent-step detection stricter, and only assigned Profit from a leftover numeric column if it can go negative — your screenshot showed UnitPrice labelled Profit and ItemsInCart labelled Discount.
- [Procfile, render.yaml, .gitignore] — Added Render deployment config and ignore rules — so friends could open a public link.
- [app/insights.py] — Added a recommendation field to every detector (trend, concentration, margin, discount, customer) using the real numbers — you wanted "where to improve" advice without a paid API or public-abuse risk.
- [components/InsightsPanel.jsx, App.css] — Rendered a "Suggestion —" block under each finding — to show the new recommendations.

### Phase 5: Sessions, pin, combine
- [components/UploadZone.jsx] — Made it accept multiple files at once — you wanted several uploads together.
- [components/Sidebar.jsx] — Added a session list (status dot, revenue preview, remove button) — each file became its own analysis, like separate chats.
- [components/MappingSummary.jsx] — Replaced the blocking mapping screen with a collapsible panel that flags "N inferred — worth a check" — bulk uploads can't wait on a confirmation screen.
- [components/ColumnMapping.jsx] — Deleted it — superseded by MappingSummary.
- [App.jsx] — Rewrote it around a sessions array with per-file loading/error/ready state and independent async analysis — so one bad file doesn't block the others.
- [App.css] — Added the sidebar, session-item and status-dot styles — the sessions UI.
- [app/kpi.py] — Added combine_dataframes, which concatenates rows and renames columns to canonical roles — so combined stats are recomputed on merged rows, not averaged across dashboards (verified: combined revenue equals the sum of both files).
- [app/main.py] — Added POST /api/analyze-combined, with _load_and_detect and _analyze_df helpers — this powers the "combine files" feature.
- [app/main.py] — Fixed a decorator/signature I mangled during that edit — it would have broken the endpoint.
- [frontend/src/api.js] — Added analyzeCombined — the frontend call for that endpoint.
- [components/Sidebar.jsx, App.jsx, App.css] — Added the ▲ pin toggle (pinned sessions sort to the top) and a combine mode with checkboxes and a "Combine selected (N)" button — these were the pin and combine requests.
- [components/MappingSummary.jsx, App.css] — Added a "merged" badge for combined sessions and stopped counting merged roles as "inferred" — so combined results don't show false warnings.

### Phase 6: Landing page overhaul
- [components/UploadZone.jsx] — Redesigned it with a cloud icon, "Browse Files" button, a formats line and drag glow/icon-grow animation — the landing-page suggestions (upload area, drag animation).
- [components/WorkflowSteps.jsx] — Added an Upload → Analyze → Insights → Dashboard strip — explains the flow at a glance.
- [components/TopBar.jsx] — Added About (a real popover) and GitHub links, first with a placeholder URL — the suggested top-right links.
- [frontend/public/demo-sales-data.csv, frontend/src/api.js] — Added a bundled 600-row demo dataset with real baked-in findings and loadDemoFile() — so recruiters can try it in one click.
- [frontend/src/api.js] — Rewrote the file after a bad edit broke analyzeCombined's signature — I caught it on reading the file back.
- [App.jsx, App.css] — Added the hero copy, "Try Demo Dataset" button, trust list and tech-stack line — you asked for a stronger value pitch.
- [frontend/src/index.css] — Lowered the grid line opacity — you wanted the upload card to stand out more.

### Phase 7: Making it universal (not just sales)
- [app/insights.py] — Reworded the insights to use the real column names, and added three domain-agnostic detectors: correlation, outlier and missing data — labels like "Revenue" were wrong on non-sales files.
- [app/kpi.py] — Added row_count, column_count and data_completeness_pct to every response — so any dataset gets baseline KPIs.
- [app/main.py] — Added a _categorical_only_analysis fallback instead of a 422 when there's no numeric column — files like a roster shouldn't fail.
- [app/main.py] — Removed count-as-currency chart data from that fallback after finding it picked the Name column and would have shown "$1" — a misleading chart.
- [components/KpiStrip.jsx] — Made the labels dynamic ("Total Fare", "Records", "Data completeness"), showing $ only when the column name looks like currency — Titanic showed "Total Revenue".
- [components/TrendChart.jsx, components/BreakdownChart.jsx] — Made titles, legend and tooltip use the real metric name — same reason.
- [App.jsx, components/InsightsPanel.jsx, components/UploadZone.jsx, components/TopBar.jsx] — Made the copy domain-neutral and added labels for the new insight types — "Drop sales files" was wrong for general data.

### Phase 8: Titanic and healthcare complaints
- [app/column_detector.py] — Added detection of numeric identifier columns (sequential or near-unique) and treated binary 0/1 flags as categorical, not "quantity" — PassengerId was chosen as Revenue purely because its sum was largest.
- [app/kpi.py] — Added breakdown_by_column and all_breakdowns, which scan every meaningful categorical column — only one "category" and one "region" were being analysed, so healthcare's columns were ignored.
- [app/kpi.py] — Removed leftover duplicate lines from the old breakdown_by body — my edit left a syntax hazard.
- [app/insights.py] — Made the concentration and margin detectors scan all categorical columns and pass extra_categoricals to every detector — the same "only category/region" problem.
- [app/main.py] — Returned a dynamic breakdowns list instead of by_category/by_region and passed extra_categoricals through — feeds the new dropdown.
- [components/BreakdownExplorer.jsx, components/BreakdownChart.jsx (hideHeader), App.jsx, App.css] — Added a dropdown built from whatever categorical columns the file has — a friend's "dynamic dropdown" review and your request.
- [app/column_detector.py] — Replaced dtype == object with pd.api.types.is_string_dtype() in two places — pandas 3.x uses a new str dtype, so every string column was silently treated as unmapped.

### Phase 9: Domain-aware rebuild, old plan (Phases 1–4)
- [app/semantic_roles.py] — Added a domain-agnostic column classifier (keyword dictionaries plus a dtype fallback, roles such as CONDITION, HOSPITAL, INSURANCE, SUBJECT, SCORE) — the first layer of your domain-aware architecture.
- [app/domains.py] — Added domain scoring over semantic roles (healthcare, sales, education, hr, finance, traffic, generic) — the second layer.
- [app/domains.py] — Removed CATEGORY, QUANTITY and FINANCIAL_METRIC from the scoring weights and added a minimum threshold — Titanic was falsely detected as "sales".
- [app/planner.py] — Added a planner that produced count-distribution, sum/avg-distribution, trend and histogram analyses per domain — so charts follow the data's entities, not just the money column.
- [app/planner.py] — Added a numeric-dtype check before planning histograms — a "Grade" column of letters was being planned as a histogram.
- [app/planner.py] — Added a fallback list of headline metrics (CANDIDATE_METRIC_ROLES) — traffic data had no analysis for congestion, accidents or speed.
- [app/planner.py] — Added an AGGREGATION_BY_ROLE map (money is summed, scores and speeds are averaged) — a summed test score is meaningless.
- [app/executor.py] — Added an executor that turns specs into chart-ready {label, value} data — one renderer can then draw every analysis type.
- [app/main.py] — Added _semantic_layer, which returns domain, domain_confidence and analyses alongside the old KPI/insight pipeline — additive, to avoid regressing what already worked.
- [components/AnalysisChart.jsx, components/AnalysisExplorer.jsx, App.jsx] — Added a unified chart and dropdown explorer showing "Detected as {domain} data" — front-end for the planner.

### Phase 10: "Universal Analytics Platform" (new plan Phases 1–4)
- [app/understanding.py] — Added understand_dataset() returning a DatasetProfile (domain, entity, measures with aggregation, dimensions with a chartable flag) — one source of truth for everything downstream.
- [app/understanding.py] — Added a domain-based entity fallback (healthcare → Patient, and so on) — healthcare showed "Record" because its identity column was just Name.
- [app/analysis_planner.py] — Added an analysis planner and visualization planner (AnalysisSpec, choose_chart_type, importance ranking, explorer sections, top_n) — picks the most valuable analyses and chart types (line, donut, horizontal bar, treemap, histogram, scatter, heatmap, boxplot).
- [app/analysis_planner.py] — Changed top_n to avoid repeating the same column, not just the same type — sum and count of the same dimension were both winning the top 3.
- [app/insight_engine.py] — Added domain-flavoured positive findings ("X is the most common Y", averages, trend, top segment, correlation) — you wanted findings beyond one numeric aggregation.
- [app/weak_points.py] — Added a detector with Problem / Impact / Priority / Suggested Action for declining trend, missing data, outliers, concentration and underperformance — the weak-point and recommendation engines.
- [app/semantic_roles.py, app/understanding.py] — Added a PROFIT role and put PROFIT and DISCOUNT into the measure list — they were silently dropped, so discount and margin risk were invisible.
- [app/weak_points.py] — Added margin_risk and discount_risk detectors — this restored the -122.6% discount finding and added sub-category losses.
- [app/executor_v2.py] — Added an executor for the new specs including scatter points, correlation matrix cells and boxplot statistics — Phase 2 planned them but nothing computed them.
- [app/main.py] — Added _run_v2_pipeline and returned it under v2 — the new engine ships next to the legacy fields.
- [app/main.py] — Restored _semantic_layer after my edit merged it into another function as dead code — it would have crashed at runtime.
- [components/AnalysisChartV2.jsx] — Added a renderer for line, bar, horizontal bar, donut, scatter, treemap, heatmap and boxplot — the visualization variety you asked for.
- [components/AnalysisChartV2.jsx] — Fixed the heatmap fragment key by using <Fragment key> — shorthand fragments can't take a key.
- [components/ExecutiveSummary.jsx, IntelligentDashboard.jsx, AnalysisExplorerV2.jsx, FindingsPanel.jsx, WeakPointsPanel.jsx, App.jsx, App.css] — Redesigned the dashboard as Executive Summary → top-3 key analyses → sectioned explorer (Trends, Distributions, Relationships, Correlations, Outliers) → findings → weak points — this was the frontend redesign.

### Phase 11: DataLens, plugin architecture, Story Mode, Data Quality
- [components/TopBar.jsx, Sidebar.jsx, App.jsx, app/main.py, frontend/index.html, frontend/package.json, README.md] — Renamed the brand and text to "DataLens" — it now analyzes any dataset, not just sales. I did not rename the folder or repo, since that would break your venv and Render link.
- [app/analyzers/base_analyzer.py, registry.py, __init__.py] — Added BaseAnalyzer and a registry mapping domain to plugin — so a new domain is one file plus one line.
- [app/analyzers/healthcare_analyzer.py, sales_analyzer.py, education_analyzer.py, hr_analyzer.py, traffic_analyzer.py, finance_analyzer.py, generic_analyzer.py] — Added one small plugin per domain (headline dimension roles and a KPI list) plus a universal fallback — domain knowledge now lives in plugins, not shared modules.
- [app/analysis_planner.py] — Removed the DOMAIN_HEADLINE_DIMENSIONS dict and made plan_analyses take headline_roles as a parameter — it was scattered domain logic inside a generic module.
- [app/main.py] — Switched _run_v2_pipeline to use get_analyzer(...) and return profile.key_kpis — the architecture change was verified to give identical output.
- [components/ExecutiveSummary.jsx, App.css] — Showed "This domain typically tracks: …" — surfaces the Domain Knowledge Library.
- [app/story_engine.py, app/analyzers/base_analyzer.py] — Added Story Mode, which chains existing findings and weak points into Trend → Breakdown → Driver → Recommendation, with generate_story() implemented on the base analyzer — a narrative built only from computed sentences, with no invented text or LLM.
- [app/main.py] — Returned v2.story — feeds the UI.
- [components/StoryMode.jsx, App.jsx, App.css] — Added the connected-timeline story panel — Story Mode is presented as the flagship feature.
- [app/data_quality.py] — Added a Data Quality report (missing by column, duplicates, constant and high-cardinality columns, outliers per measure, dtype breakdown, 0–100 score) — the Data Quality Center.
- [app/correlation_center.py] — Added strongest positive/negative correlations and a ranked list of notable pairs — the "so what" over the heatmap.
- [app/analysis_planner.py, app/executor_v2.py] — Added a reasoning field ("why this chart") to every spec and passed it through — chart-reasoning captions.
- [app/main.py] — Wired data_quality and correlation_center into v2 — exposes them to the UI.
- [components/DataQualityCenter.jsx, components/CorrelationCenter.jsx, IntelligentDashboard.jsx, AnalysisExplorerV2.jsx, App.jsx, App.css] — Added both panels and reasoning captions under charts — the frontend for those features.

### Phase 12: "Final architecture improvements"
- [app/analysis_planner.py] — Rebalanced importance so entity distributions outrank metric-by-entity breakdowns — 2 of 3 top slots were Billing Amount analyses.
- [app/analysis_planner.py] — Changed top_n so it enforces unique subject only (removing the strict type-diversity block), then added a cap of 2 per type and restored the dropped subject_of helper — the strict rule pushed a weaker trend into the slot, and the loose rule let 3 entity charts crowd out the trend on Superstore.
- [app/main.py] — Sorted top_analyses by importance instead of plan-creation order — the trend was displaying first even though it ranked lower.
- [components/AnalysisChartV2.jsx] — Added a legend and a percentage/value tooltip to the donut — the donut had colours but no labels.
- [app/executor_v2.py, app/analysis_planner.py, components/AnalysisChartV2.jsx] — Coloured scatter points by the domain's headline dimension, with a legend — all points were the same colour.
- [app/executor_v2.py, components/AnalysisChartV2.jsx, App.css] — Added r, an interpretation string ("Weak negative relationship" and so on) and a Relationship block showing X-axis, Y-axis, colour-by and correlation — the "Relationship" titles lacked axis labels and meaning.
- [app/executor_v2.py] — Simplified the interpretation wording so a small |r| reads "No meaningful relationship" — the first version read "Very weak / no clear negative relationship".

### Phase 13: Plain-English weak points
- [app/weak_points.py] — Rewrote every problem, impact and action string without jargon ("margin", "concentration", "IQR") — non-analysts couldn't understand the panel.
- [app/weak_points.py] — Stopped lowercasing column names in fallback labels — it produced "One ship mode" and "One pclass".
- [app/story_engine.py (reads weak points)] — Story Mode's sentences became plain-English automatically — it reuses the same weak-point text.

### Phase 14: Light theme, reset, black-and-white theme
- [frontend/src/index.css] — Rewrote the tokens as a light SaaS palette (soft gray page, white cards, blue accent, Inter everywhere, removed the grid background) — you shared a light dashboard reference.
- [frontend/src/App.css] — Gave .panel a 16px radius and soft shadow, and fixed hardcoded shadows and a teal glow — cards needed depth on a light background.
- [frontend/src/App.css] — Changed three buttons from `color: var(--ink)` to `#FFFFFF` — the --ink token had flipped from near-black to near-white and the text would have vanished.
- [components/ExecutiveSummary.jsx, frontend/src/App.css] — Rebuilt the stats as icon-badge cards with lucide-react icons (StatCard) — matches the reference KPI cards.
- [frontend/package.json] — Added lucide-react (latest, after 0.383.0 hit a React 19 peer conflict and the first npm install -s didn't save it) — the build failed until it was properly saved.
- [components/AnalysisChartV2.jsx] — Changed the palette to vivid blue/purple/green/orange — the old muted colours would look washed out on white.
- [frontend/src/App.css] — Darkened the dashed upload-zone border — it was nearly invisible on white.
- [frontend/package.json, frontend/vite.config.js, frontend/index.html, frontend/public/*] — Reconstructed the scaffolding after the environment reset, using the built output; the rebuilt CSS hash matched your deployed one — the sandbox lost my files and only src/ was re-uploaded.
- [frontend/src/index.css] — Replaced the light theme with near-black `#0A0A0B` tokens, with red as the only real colour, reserved for warnings — you asked for a true black-and-white minimalist look.
- [frontend/src/App.css] — Changed button text from `#FFFFFF` to `#0A0A0B` — the accent had become white, so white text would be invisible.
- [frontend/src/App.css] — Changed the dashed border to `#3A3A40`, the popover shadow to a dark shadow, and the drag glow from blue to a light gray — light-theme values were invisible or off-theme on black.
- [components/AnalysisChartV2.jsx] — Changed the chart palette to a grayscale ramp — matches the monochrome reference charts.
- [components/ExecutiveSummary.jsx] — Replaced the hardcoded purple "Columns" icon colours with theme tokens — it was the last non-monochrome element.
- [frontend/src/App.css (.mapping-flag)] — Changed the "1 inferred — worth a check" pill to a solid light-gray background with dark text — light-gray-on-dark-gray was barely readable in your screenshot.
- [HANDOFF.md] — Wrote a project handoff (architecture, regression-prone spots, deployment steps, unbuilt items) — so you can start a fresh chat.

### Notes on this reconstruction (from the old chat itself)
- Superseded frontend files sitting unused in `frontend/src/components/`: KpiStrip.jsx, TrendChart.jsx, BreakdownChart.jsx, BreakdownExplorer.jsx, AnalysisExplorer.jsx, AnalysisChart.jsx, InsightsPanel.jsx — no longer rendered, left in place rather than deleted at the time.
- The legacy backend modules (column_detector.py, kpi.py, insights.py, planner.py, executor.py) ran alongside the newer v2 pipeline rather than replacing it outright.
- Pure machine troubleshooting that changed no project file (venv activation, moving folders, installing Node, PowerShell execution policy) is intentionally left out of this log.
- Ideas discussed but never shipped: LLM-generated suggestions (rule-based was chosen instead), a count/sum toggle in the breakdown explorer, auth/persistence, exports, global search and filtering (most of these were in fact built later — see below).

**A second pass over the same chat** turned up a few more changes that were missing or under-specified the first time around:
- [frontend/.gitignore] — Added a node_modules/dist/.env.local ignore file scoped to the frontend folder, before the project had a root-level .gitignore — so the packaged zip wouldn't balloon with node_modules.
- [app/main.py] — Removed the CORSMiddleware once the frontend and backend merged into one same-origin process — it was dead config at that point, no cross-origin requests left to allow.
- [app/main.py] — Wired _run_v2_pipeline into all three response builders — _analyze_df, _categorical_only_analysis, and analyze_combined — not just the main path, so a combined-files session or a no-numeric-column file also gets the full v2 payload (Story Mode, Data Quality, Correlation Center included), not a partial one.
- [app/analysis_planner.py] — Made the reasoning text for distribution analyses name the actual chart type chosen ("a donut chart reads composition clearly at that size" vs "too many for a pie/bar, so a treemap groups them by size") — ties the explanation to what's literally on screen instead of a generic sentence.
- [healthcare_test.csv, education_test.csv, hr_test.csv, traffic_test.csv, no_numeric_test.csv, generic_test.csv] — Synthetic datasets I created purely to test the domain detector, planner, and weak-point engine across every domain before trusting them on your real files. Not part of your shipped project — just how I verified things before handing them to you.

---

## From an earlier chat, continued (session 2)

### Segmentation / Clustering (backlog item 1)
- app/clustering.py (new) — from-scratch k-means (k-means++ init, multiple restarts, silhouette-based auto-k, sampling for large datasets) — to auto-discover natural groups in uploaded data
- app/main.py — wired analyze_segments into the pipeline, added a scatter-shaped chart entry to all_analyses, added segments key to the response — reused the existing scatter chart rendering instead of building a new chart type
- frontend/src/components/AnalysisExplorerV2.jsx — added "Segments" to SECTION_ORDER — so the cluster scatter chart shows up as an explorer tab
- frontend/src/components/SegmentsPanel.jsx (new) — cluster summary cards — gives a plain-English readout of what each cluster looks like

### Seasonality Decomposition (backlog item 2)
- app/seasonality.py (new) — additive decomposition (centered moving average trend, calendar-month seasonal indices, residual) — to separate trend from repeating seasonal pattern
- app/seasonality.py — added a one-way ANOVA significance gate and raised the minimum history to 3 years — first version falsely reported a strong seasonal pattern on 2.5 years of pure random noise; the gate stops that
- app/main.py — wired decompose_trend in before forecast_trend mutates the trend data, added a seasonal_decomposition chart entry, added seasonality key — ordering matters so the forecast's synthetic future points don't get fed into the decomposition
- frontend/src/components/AnalysisChartV2.jsx — added DecompositionView (3 stacked Trend/Seasonal/Residual panels) and the seasonal_decomposition case
- frontend/src/components/AnalysisExplorerV2.jsx — added "Seasonality" to SECTION_ORDER
- frontend/src/components/SeasonalityPanel.jsx (new) — peak/trough month and strength summary

### Paste-CSV/Sheets Import (backlog item 3)
- frontend/src/components/UploadZone.jsx — added a "paste data instead" link revealing a textarea, with tab-vs-comma delimiter sniffing so the synthesized file gets the right extension — lets someone test quickly without saving a file first; needed zero backend changes since it reuses the existing upload path

### JSON/Parquet Support (backlog item 4)
- app/main.py — extended ALLOWED_EXTENSIONS, added _json_records_to_dataframe (handles flat-records, columns-dict, and wrapped-API-export JSON shapes), added .json/.parquet branches to _load_dataframe — to accept more real-world export formats
- requirements.txt — added pyarrow>=16.0 — required Parquet engine
- frontend/src/components/UploadZone.jsx — updated accepted extensions, accept attribute, and displayed format list
- frontend/src/App.jsx — updated hero copy to mention JSON/Parquet

### "Copy Findings as Text" (backlog item 5)
- frontend/src/findingsText.js (new) — builds a plain-text summary (KPIs, story, findings, segments, seasonality, weak points) entirely client-side — for pasting into Slack/email without a server round-trip
- frontend/src/components/ExportMenu.jsx — added the menu item with a transient "Copied!" state
- frontend/src/App.jsx — added handleCopyFindings, wired into ExportMenu

### Period-over-Period Comparison
- app/period_comparison.py (new) — Welch's t-test on the raw row-level values of the last two complete months (not just a percent-change on totals) — a raw percentage can look dramatic from a handful of large orders and mean nothing; the t-test tests whether the difference is bigger than normal variation
- app/period_comparison.py — fixed a display bug where a decrease showed as "down -6.3%" (double negative) — corrected to "down 6.3%"
- app/main.py — wired compare_periods using the trend spec's date/metric/aggregation, added period_comparison key

- frontend/src/components/PeriodComparisonPanel.jsx (new)

### Multivariate Anomaly Detection
- app/anomaly_detection.py (new) — Mahalanobis distance with a chi-square p-value gate (α=0.01) — flags rows unusual across several measures together, which per-column outlier checks miss entirely
- app/anomaly_detection.py — added a z-score threshold before naming a measure in the "why" explanation — first version could describe a value sitting at the average (z≈0) as "unusually high" just because it was the larger of only two measures
- app/main.py — wired detect_anomalies, added an anomalies_scatter chart entry (colored Anomaly vs Normal, reusing the scatter chart), added anomalies key
- frontend/src/components/AnalysisExplorerV2.jsx — added "Anomalies" to SECTION_ORDER

- frontend/src/components/AnomaliesPanel.jsx (new)

### Simpson's Paradox Check
- app/simpsons_paradox.py (new) — reuses the correlation pairs correlation_center.py already computed, flags when a correlation's sign reverses in every subgroup of a categorical dimension — catches a confounding-variable pattern a plain correlation would miss; deliberately strict (all subgroups, not just most) to avoid overclaiming
- app/main.py — wired check_simpsons_paradox, added simpsons_paradox key

- frontend/src/components/SimpsonsParadoxPanel.jsx (new)

### Benford's Law Check
- app/benford.py (new) — chi-square test comparing a monetary column's leading-digit distribution to Benford's Law, only run on FINANCIAL_METRIC/PROFIT/UNIT_COST-role columns with enough magnitude span — a well-known data-integrity signal, scoped so it's never applied to columns (ages, IDs) where it wouldn't be meaningful
- app/main.py — wired check_benfords_law, added benford key

- frontend/src/components/BenfordPanel.jsx (new)

### Real Estate + SaaS Domains
- app/semantic_roles.py — added PROPERTY_TYPE, PROPERTY_STATUS, LISTING_PRICE, SALE_PRICE, SQUARE_FOOTAGE, BEDROOMS, BATHROOMS, DAYS_ON_MARKET, MRR, ARR, SUBSCRIPTION_PLAN, CHURN_STATUS, CHURN_RATE, TRIAL_STATUS, SEATS, NPS_SCORE roles, inserted before the generic CATEGORY fallback — so domain-specific column names don't get swallowed by the generic "type"/"status" keywords
- app/understanding.py — added aggregation defaults, dimension-role entries, and DOMAIN_DEFAULT_ENTITY ("Property", "Subscriber")
- app/domains.py — added real_estate/saas domain scoring signals
- app/analyzers/real_estate_analyzer.py (new), app/analyzers/saas_analyzer.py (new) — domain-specific KPIs and headline dimensions
- app/analyzers/registry.py — registered both

### Compare Two Files Side-by-Side
- app/comparison.py (new) — diffs two independently-run analyses (KPI deltas, correlation sign flips, row count/quality/domain differences) — distinct from the existing row-merging "combine" feature; this is an A/B comparison of two separate snapshots
- app/main.py — refactored /api/analyze's column-detection logic into a shared _full_analyze_from_df() helper so the new /api/compare endpoint doesn't duplicate it — avoids the exact "same logic fixed in multiple places" bug pattern the project had already hit before
- app/main.py — fixed a guard that checked for a missing kpis key (always present, even on the no-metric fallback) — corrected to check the real no_numeric_metric flag
- frontend/src/api.js — added compareFiles()
- frontend/src/components/CompareView.jsx (new) — renders the KPI/correlation diff
- frontend/src/App.jsx — added compare-mode state and the read-only comparison session rendering path
- frontend/src/components/Sidebar.jsx — added compare-mode selection (capped at exactly two files) and a compare button

### Export Cleaned CSV
- app/anomaly_detection.py — fixed row_index to reflect the original file's row number rather than its position after dropna(); added an uncapped all_anomaly_row_indices field — the existing anomalies list is capped at ~50 for UI display, but a downloadable cleaned file needs every flagged row, not just the top 50
- app/data_cleaning.py (new) — removes exact duplicate rows, flags (never deletes) anomalous rows via a flagged_as_unusual column — deliberately conservative, since auto-deleting a real business anomaly would be real data loss the app has no business deciding on its own
- app/main.py — new /api/export/cleaned-csv endpoint (stateless, re-accepts the file)
- frontend/src/api.js — added downloadCleanedCsv()
- frontend/src/App.jsx — added handleDownloadCleanedCsv
- frontend/src/components/ExportMenu.jsx — added the menu item

### Pytest Regression Suite
- pytest.ini (new), requirements-dev.txt (new) — test config and pytest dependency, kept separate from requirements.txt since pytest has no place in production
- tests/conftest.py (new) — shared dataset fixtures
- tests/test_domain_detection.py (new) — per-domain detection + no-cross-domain-leakage tests
- tests/test_statistical_modules.py (new) — correctness tests for clustering/seasonality/anomaly/Simpson's/Benford, codifying the specific bugs already found and fixed
- tests/test_pipeline_robustness.py (new) — edge cases targeting the project's own documented recurring bug pattern (name-based column classification with no data-quality check)
- tests/test_file_formats.py (new) — CSV/TSV/JSON/Parquet load-equivalence tests
- tests/test_api_endpoints.py (new) — smoke tests for every endpoint
- tests/test_domain_detection.py — loosened an over-strict assertion that required zero incidental score in unrelated domains — a SaaS dataset's Customer ID column legitimately scores a little toward the sales domain too (CUSTOMER is a real shared signal), so the fix checks that the correct domain wins by a clear margin instead of demanding literal zero overlap

### Cohort / Retention Analysis
- app/cohort_analysis.py (new) — groups entities by the month of first appearance, tracks what fraction return in each subsequent month
- app/cohort_analysis.py — fixed a wrong assumption about profile.semantic_roles's shape (assumed {col: {"role": ...}}, it's actually the flattened {col: role_string}) — caused an immediate crash, fixed
- app/main.py — wired analyze_cohorts, added a cohort_retention heatmap chart entry (reusing the existing heatmap component, set to type: "pivot" for the correct single-color scale), added cohorts key
- app/main.py — fixed a variable-ordering bug where cohort_report was computed after code that already referenced it (UnboundLocalError) — caught immediately by the pytest suite added the round before
- frontend/src/components/AnalysisChartV2.jsx — added an optional value_suffix field to the heatmap's pivot cell formatter (backward-compatible) — lets the retention heatmap show "65.0%" instead of a bare number
- frontend/src/components/AnalysisExplorerV2.jsx — added "Retention" to SECTION_ORDER

- frontend/src/components/CohortsPanel.jsx (new)
- tests/test_statistical_modules.py, tests/test_pipeline_robustness.py — added cohort tests

### Confidence Intervals on KPIs
- app/confidence_intervals.py (new) — bootstrap resampling for a 95% interval on each numeric measure — makes no distributional assumption, unlike the classic mean±1.96·SE formula
- app/confidence_intervals.py — fixed a real bug: when sampling down for speed on large datasets, the point estimate itself was also being computed from only the sample, not the true total — fixed so the point estimate always comes from the complete data, and only the interval's width uses the sample, correctly rescaled by the true row count
- app/main.py — wired compute_kpi_confidence_intervals, added confidence_intervals key

- frontend/src/components/ConfidenceIntervalsPanel.jsx (new)
- tests/test_statistical_modules.py, tests/test_pipeline_robustness.py — added CI tests

### Text Field Analysis
- app/text_analysis.py (new) — keyword-frequency analysis (stopword-filtered word counts) on free-text columns — no NLP library, no sentiment model, consistent with the app's no-LLM design
- app/main.py — wired analyze_text_fields, added text_analysis key

- frontend/src/components/TextAnalysisPanel.jsx (new)
- tests/test_statistical_modules.py, tests/test_pipeline_robustness.py — added text-analysis tests

### E-commerce + Insurance Domains
- app/semantic_roles.py — added CART_VALUE, CART_STATUS, CONVERSION_STATUS, PAGE_VIEWS, PAYMENT_METHOD (e-commerce) and PREMIUM, CLAIM_AMOUNT, CLAIM_STATUS, COVERAGE_TYPE, DEDUCTIBLE, RISK_SCORE (insurance) roles
- app/understanding.py — added aggregation defaults, dimension roles, DOMAIN_DEFAULT_ENTITY ("Shopper", "Policyholder")
- app/domains.py — added ecommerce/insurance scoring signals

- app/analyzers/ecommerce_analyzer.py (new), app/analyzers/insurance_analyzer.py (new)
- app/analyzers/registry.py — registered both
- tests/conftest.py, tests/test_domain_detection.py — added fixtures and tests for both

### Self-Contained Static HTML Report
- app/html_report.py (new) — single-file HTML export with everything inlined (no CDN, no external scripts), covering every analysis section including all the newer modules, with all user-controlled values HTML-escaped
- app/main.py — new /api/export/html endpoint, reusing the existing PdfExportRequest model
- frontend/src/api.js — added exportHtml()
- frontend/src/App.jsx — added handleExportHtml
- frontend/src/components/ExportMenu.jsx — added the menu item
- tests/test_api_endpoints.py — added HTML export tests; corrected a first-attempt test that picked data which never actually surfaced the escaping-test payload anywhere in the report (a test-construction issue, not a product bug)

### Chunked File Reads / Memory Reduction
- app/main.py — added a MAX_FILE_SIZE_MB cap and chunked CSV parsing with per-chunk numeric downcasting (float64→float32, int64→smallest fit) — reduces the final in-memory dataframe size on large uploads, since true streaming isn't compatible with how every analysis module needs the complete dataframe
- app/main.py — fixed a category-dtype ordering bug (converting low-cardinality string columns to category before the existing numeric-coercion cleanup ran, causing a "mostly numeric with stray text" column to be skipped)
- app/main.py — fixed a second, deeper bug from the same feature: a date column with few distinct months also got converted to category, and unrelated code in kpi.py called .min()/.max() on it expecting a datetime, crashing — fixed by removing categorical conversion entirely and keeping only the (safe) numeric downcasting
- app/main.py — fixed a JSON-serialization bug: numpy.float64 happens to subclass Python's float (so it always worked by accident) but float32/int8 don't, so every endpoint returning one crashed — fixed by making _sanitize_json convert any numpy.generic via .item(), and by having /api/analyze, /api/compare, /api/analyze-combined return SafeJSONResponse(...) directly so FastAPI's own encoder is skipped
- tests/test_api_endpoints.py, tests/test_pipeline_robustness.py — added regression tests for all three bugs and the file-size cap

### Property-Based Tests (Hypothesis)
- tests/test_property_based.py (new) — invariant-based fuzz tests for clustering, anomaly detection, confidence intervals, Benford's Law, and chunked CSV reading
- requirements-dev.txt — added hypothesis>=6.100
- tests/test_property_based.py — fixed an overly strict tolerance on the Benford proportion-sum check (1e-6) — the module rounds each of 9 values to 4 decimals for display before storing them, so summing them can drift by up to ~0.00045; widened to 1e-3 to reflect that correctly (a test bug, not a product bug)

### CI Workflow
- .github/workflows/tests.yml (new) — GitHub Actions workflow running the full pytest suite on every push/PR against Python 3.12
- .github/workflows/tests.yml — quoted the on: key as "on": to avoid PyYAML's boolean-parsing ambiguity (the "Norway problem") — cosmetic, since GitHub's own parser already handles it correctly either way

### Dashboard Reorganization
- frontend/src/components/DeepDivePanel.jsx (new) — groups the 10 secondary panels (Data Quality, Correlations, Segments, Seasonality, Period Comparison, Anomalies, Simpson's Paradox, Benford, Cohorts, Confidence Intervals, Text Fields) into 4 tabs — the dashboard had grown to 13 stacked panels and become hard to browse
- frontend/src/App.jsx — replaced the 10 individual panel renders with the single DeepDivePanel
- frontend/src/App.css — added a .deep-dive-panel full-width grid rule

- 11 panel components — bulk-fixed to only render their numbered "tick" badge when a tickNum is actually passed, so nesting them inside a tab doesn't show an empty bordered box

### Pydantic Response Models
- app/main.py — added AnalyzeResponse, CompareResponse, HealthResponse models with response_model= on /api/analyze, /api/compare, /api/analyze-combined, /api/health — top-level shape only, since exhaustively modeling the 17+ nested analysis modules would go stale immediately; gives /docs a real, accurate schema where it previously showed nothing
- app/main.py — added explicit responses={200: {"content": {...}}} metadata to the three file-download endpoints so /docs shows their real content types

- Verified (didn't just assume) that adding response_model= doesn't reintroduce the earlier numpy-serialization bug, since those three routes return SafeJSONResponse objects directly and FastAPI skips model validation for routes that already return a Response instance

### Tier 1: Ephemeral Share Links
- app/share_cache.py (new) — in-memory, TTL-based (24h) cache keyed by an unguessable token, with a 15MB per-entry size cap and a 500-entry cap (oldest-expiring evicted first) — lets someone share a link to their analysis without becoming permanent storage
- app/share_cache.py — fixed a cosmetic unit-mismatch bug in the size-limit error message (binary MB cap displayed using decimal-MB math, showing "16MB" for a 15MB cap)
- app/main.py — added ShareRequest/ShareCreateResponse models and the /api/share (POST) / /api/share/{token} (GET) endpoints
- frontend/src/api.js — added createShareLink(), fetchSharedAnalysis()
- frontend/src/App.jsx — added on-mount share-token detection, a synthetic read-only session for the shared view, and a "viewing a shared analysis" banner with the sidebar hidden in that mode
- frontend/src/components/ExportMenu.jsx — added "Copy share link"
- tests/test_api_endpoints.py — added create/retrieve, unknown-token-404, and oversized-payload tests

### Hero Banner Graphic
- Produced hero-banner.svg/.png — a data-cluster/anomaly art motif matching DataLens's actual dark theme (near-monochrome, one red accent reserved for the anomaly point, echoing the app's own real design language), with the real wordmark/tagline baked in, for use as a README banner

- Revised once after self-review: the first pass had a stark empty gap in the middle and the anomaly point crowded against the top edge; added ambient background texture, softened the cluster connector lines, and repositioned the anomaly

### Hero Background on the Landing Page + Fix
- frontend/public/hero-bg.svg (new) — a text-free variant of the hero art (no baked-in wordmark, since the app's real hero text already exists in the DOM)
- frontend/src/App.css — added it as the background of .app-main-area.centered
- frontend/public/hero-bg.svg — regenerated after the background turned out invisible in practice: background-size: cover was cropping unpredictably because the original art concentrated everything in the right third of a 3:1 canvas; rebuilt denser, spread across the full width, with the anomaly point moved toward center so it survives cropping at any viewport aspect ratio

### Glassy / Frosted Card Styling
- frontend/src/index.css — added theme-aware --glass-bg/--glass-border/--glass-highlight and --ambient-glow-1/2/3 tokens (dark theme: neutral white tint; light theme: its own sky-blue/sun-gold tint instead of a leftover dark-mode value), and gave body three soft, fixed-position radial gradients using those tokens
- frontend/src/App.css — updated .panel, .kpi-card, .stat-card to a translucent background, backdrop-filter: blur(16px) saturate(160%) (with the -webkit- prefix), a low-alpha border, and an inset top highlight — the fixed ambient gradients were added specifically because a frosted effect needs real visual variation behind it; blurring a flat solid color is invisible

---

## From an earlier chat, continued (session 3)

### Column mapping badge contrast + chart axis labels
- frontend/src/App.css — Fixed .mapping-flag badge (added font-weight: 600, border: 1px solid var(--amber)) — thin default-weight light-gray text on near-black background was nearly invisible after an earlier B&W theme pivot stripped its definition
- frontend/src/components/AnalysisChartV2.jsx — Added a Y-axis label to scatter charts (previously only X had one) and repositioned the X-axis label outside the plot area — chart had no Y-axis label at all, and the X-axis label overlapped the tick numbers

### Statistical significance on correlations
- app/correlation_center.py — Added p-value, sample size (n), significance flag, strength label, and caveat text per correlation pair via scipy.stats.pearsonr with a manual t-distribution fallback — a raw r-value alone doesn't show whether a relationship is statistically reliable or could be noise from a small sample
- app/main.py — Added _serialize_correlation_pair helper, wired the new fields into the API response
- requirements.txt — Added scipy>=1.11
- frontend/src/components/CorrelationCenter.jsx — Display p-value/n in callouts and list rows, show caveat badges

### Multicollinearity (VIF)
- app/correlation_center.py — Added analyze_multicollinearity() using least-squares-based VIF — two measures can look independent pairwise but still be redundant once every other measure is accounted for
- app/main.py — Wired VIF results into the response
- frontend/src/components/CorrelationCenter.jsx, frontend/src/App.css — VIF display with severity badges

### Excel export
- frontend/src/exportReport.js (new) — Client-side multi-sheet .xlsx generation via SheetJS — no backend involvement needed, consistent with the app's stateless design
- frontend/src/App.jsx, frontend/src/App.css — Export button

### PDF export
- app/pdf_report.py (new) — Server-side PDF generation via reportlab; caught and fixed a real bug during the build (long text overflowing into adjacent table columns, since reportlab tables don't auto-wrap plain strings — fixed by wrapping cell text in Paragraph objects)
- app/main.py — New /api/export/pdf endpoint, stateless (frontend sends back the analysis JSON it already has)
- frontend/src/api.js — exportPdf function

### Export dropdown menu
- frontend/src/components/ExportMenu.jsx (new) — Single "Export ▾" button replacing two separate buttons, opens a dropdown with Excel/PDF options — requested directly by user for cleaner UI

- frontend/src/App.jsx, frontend/src/App.css

### Light/dark theme toggle
- frontend/src/components/ThemeToggle.jsx (new) — Animated sun/moon switch matching a reference image the user provided
- frontend/src/index.css — Full light theme CSS variable block
- frontend/src/components/AnalysisChartV2.jsx — Chart color palette switched to CSS variables so charts also re-theme

- frontend/src/components/TopBar.jsx, frontend/src/App.css

### Scatter chart legend collision fix (regression from the earlier axis-label fix)
- frontend/src/components/AnalysisChartV2.jsx — Moved the scatter chart legend to top-right — the X-axis label (moved outside the plot earlier) was overlapping Recharts' legend, garbling text like "South"/"Sales"

### Export button / theme toggle click-overlap fix
- frontend/src/App.css — Increased .app-main-area top padding (40px → 80px) — the Export button rendered underneath the fixed topbar, and since the topbar had a higher z-index, clicks meant for Export were being captured by the theme toggle instead

### Messy-CSV crash fix
- app/main.py — Added SafeJSONResponse/_sanitize_json to convert stray NaN/Infinity floats to null globally — a real uploaded file (Retail_Sales_Data_Set.csv) with mostly-empty columns produced NaN values that crashed JSON serialization entirely, returning an unparseable "Internal Server Error" to the frontend

### missing_by_column shape bug fix
- app/pdf_report.py, frontend/src/exportReport.js — Fixed both exports to treat missing_by_column as a list of {column, missing_pct} objects, not a dict — wrong assumption made when originally building the exports, only surfaced once tested against a file with actual missing values

### Usable data quality score
- app/data_quality.py — Added usable_quality_score/usable_column_count/total_column_count, computed only over columns actually used in analysis — a file can carry many empty/junk columns that tank the raw score without meaning the real data is unreliable
- app/main.py — Wired into response

- frontend/src/components/DataQualityCenter.jsx, frontend/src/App.css
- app/pdf_report.py, frontend/src/exportReport.js — Added the new score to both exports

### Junk-column-as-measure bug, instance 1 (v2 pipeline)
- app/understanding.py — Added _is_usable_column() completeness guard to the measure/dimension selection loops — a column matched by name but 99%+ empty was still being selected as a real measure

### Junk-column-as-measure bug, instance 2 (legacy pipeline)
- app/column_detector.py — Added the same completeness guard to _exact_and_substring_matches() and the dtype-fallback loop — this pipeline feeds the sidebar's "$X revenue" figure, which was showing a wrong number computed from a near-empty column

### Junk-column-as-measure bug, instance 3 (domain detection)
- app/understanding.py — Filtered domain_scoring_roles to usable columns only before calling detect_domain() — a column that was 97% empty but named e.g. "diagnosis" could swing the entire dataset's domain classification to "healthcare" at full confidence

### Trend forecasting
- app/forecasting.py (new) — Linear regression forecast over monthly trend data, gated behind an R² ≥ 0.3 threshold and a minimum 6 months of history; includes detection and exclusion of a likely-incomplete final period (caught via testing — a partial last month was producing a misleading downward spike before the forecast projection)
- app/main.py — Forecast attachment loop after analysis execution
- app/executor_v2.py — Exposed column/date_column fields needed by forecasting and later filtering
- frontend/src/components/AnalysisChartV2.jsx — Dashed line rendering for forecasted points, "projected" tooltip label
- frontend/src/components/AnalysisExplorerV2.jsx, frontend/src/components/IntelligentDashboard.jsx — Forecast caveat note display

- frontend/src/App.css

### Weak-points junk-column bug (junk-column bug, instance 4)
- app/weak_points.py — Filtered missing_data() to only flag columns in profile.measures/dimensions — found via a real generated stress-test dataset's PDF report, where "The Driver" (a key narrative slot) was showing a notice about an empty junk column instead of the genuinely interesting discount-loss finding

### Tooltip contrast fix, round 2
- frontend/src/App.css — .tooltip-label color changed from var(--text-muted) to var(--text) — an earlier fix only corrected the tooltip's value line, missed that the label line was still low-contrast; also increased .app-main-area padding-top further (80px → 100px) for more breathing room

### Requirements.txt hardening
- requirements.txt — Added explicit pydantic>=2.0 and starlette>=0.35 — both were imported directly but only present transitively via FastAPI; verified in a clean venv that this wasn't an active bug, added anyway as good practice

### Measure-role fallback fix
- app/understanding.py — Added a fallback pass so any numeric column with real, usable data becomes a measure even if its semantic role isn't in the hardcoded MEASURE_ROLES list — found via a synthetic 82-column stress test where 25 legitimate numeric columns had zero measures; also revealed Quantity had never been usable as a measure in the user's own clean sales demo the whole time

### Date misclassification fix
- app/semantic_roles.py — Added a minimum-average-length guard before attempting date parsing in _dtype_fallback() — a column of short codes like "M1"/"M2"/"M3" was being misclassified as a DATE column because dateutil's lenient parser is too permissive on short strings

### 150K-row performance fix
- app/column_detector.py — Memoized _is_usable_column() (computed once per column via a usable_cols set instead of redundantly inside nested role×hint×column loops); replaced full-column pd.to_datetime() date-detection scans with a 1000-row sample in both column_detector.py and app/semantic_roles.py — a 150K-row file took 4.59s end-to-end, traced to the date-detection heuristic scanning every value in every unmatched text column; fixed to ~2.5–2.8s with identical output verified

### Manufacturing domain
- app/semantic_roles.py — New roles: DEFECT_RATE, DOWNTIME, UNITS_PRODUCED, MACHINE, SHIFT, PRODUCTION_LINE
- app/understanding.py — Added these to MEASURE_ROLES/DIMENSION_ROLES with correct aggregations; also fixed a bug found while building this — STORE/SUPPLIER/WAREHOUSE had been referenced in RetailAnalyzer but never actually added to DIMENSION_ROLES, meaning the Retail domain's store-level breakdown could never have worked since Retail was added
- app/domains.py — Manufacturing signal weights

- app/analyzers/manufacturing_analyzer.py (new), app/analyzers/registry.py

### Marketing domain
- app/semantic_roles.py — New roles: CAMPAIGN, CHANNEL, IMPRESSIONS, CLICKS, CTR, CONVERSION_RATE, CPC, ROAS, AD_SPEND
- app/understanding.py — Added to MEASURE_ROLES/DIMENSION_ROLES
- app/domains.py — Marketing signal weights

- app/analyzers/marketing_analyzer.py (new), app/analyzers/registry.py

### README screenshots
- README.md — Added a Screenshots section using real app screenshots the user shared, fixed a stale domain list in the intro paragraph
- docs/screenshots/*.png (new) — 4 curated images

### Numeric coercion fix
- app/main.py — Added _coerce_mostly_numeric_columns(), applied at file load — a column with 90%+ real numeric values but a few stray placeholder strings (e.g. "F") was being read entirely as text, silently excluding it from every measure/correlation/VIF check; found via a real uploaded YouTube dataset (train.csv) where views/likes/dislikes/comment were all invisible to analysis

### Revenue "guessed" confidence fix
- app/column_detector.py — Tagged the blind "pick the biggest numeric column" revenue fallback with a distinct "guessed" confidence level, separate from genuine "inferred" matches
- frontend/src/components/MappingSummary.jsx — "BEST GUESS" badge, counted in the low-confidence flag
- frontend/src/components/Sidebar.jsx — Suppressed the "$X revenue" sidebar stat when confidence is "guessed" — the numeric coercion fix had changed which column got picked for this blind guess, causing the sidebar to show a wildly wrong ($10.7 billion) figure for a dataset with no real revenue concept at all

### Interactive filtering
- app/filtering.py (new) — Builds a compact row-level payload (date + dimension + measure columns only) shipped once alongside analysis results, capped at 100K rows
- app/main.py, app/executor_v2.py — Wiring, exposed column/date_column per analysis
- frontend/src/filterUtils.js (new) — Client-side filter and re-aggregation logic, verified to produce identical output to the backend's own computation
- frontend/src/components/FilterBar.jsx (new) — Date range + per-dimension multi-select filters

- frontend/src/App.jsx, frontend/src/App.css
- frontend/src/api.js — exportPdf updated to strip filterable_data before sending — the PDF generator never reads it, and it could be a multi-megabyte payload on large datasets

### Global search
- frontend/src/searchUtils.js (new) — Flat searchable index over findings, weak points, story beats, chart titles/reasoning, and correlations
- frontend/src/components/SearchBar.jsx (new) — Live search dropdown with click-to-jump
- frontend/src/components/AnalysisExplorerV2.jsx — Added jumpTarget prop to drive section/analysis selection since the Explorer only renders one chart at a time
- frontend/src/components/FindingsPanel.jsx, WeakPointsPanel.jsx, StoryMode.jsx, CorrelationCenter.jsx — Added stable anchor IDs for scroll-to-and-highlight

- frontend/src/App.jsx, frontend/src/App.css

### Manual column remapping
- app/main.py — Added column_overrides form field to /api/analyze, LEGACY_ROLE_TO_V2_ROLE translation table so one correction propagates to both the legacy and v2 pipelines consistently; kept the "Not used in analysis" list consistent with overrides
- app/understanding.py — Added role_overrides parameter to understand_dataset()
- frontend/src/api.js — analyzeFile accepts columnOverrides
- frontend/src/App.jsx — handleRemapColumn, persisted per-session
- frontend/src/components/MappingSummary.jsx — Rewritten with an inline "change" dropdown per row, new "SET BY YOU" badge

- frontend/src/App.css

### Sample dataset gallery
- frontend/public/sample-healthcare-data.csv, sample-manufacturing-data.csv (new) — Synthetic datasets, verified to detect their domains at full confidence
- frontend/src/api.js — SAMPLE_DATASETS, loadSampleFile
- frontend/src/components/SampleGallery.jsx (new) — 3-card gallery replacing the single "Try Demo" button

- frontend/src/App.jsx, frontend/src/App.css

### Sample gallery deployment bug fix
- Moved the two new sample CSVs from app/static/ into frontend/public/ — they were placed in a folder meant to be wiped and rebuilt on every deploy, following bad instructions given for the copy step; frontend/public/ (where demo-sales-data.csv already lived) is auto-bundled by Vite on every build, verified by replicating the user's exact PowerShell deploy sequence

### Pivot / cross-tab explorer
- app/analysis_planner.py — Added column2 field to AnalysisSpec, "pivot" entries in IMPORTANCE_BASE/TYPE_TO_SECTION, and planning logic crossing the two best chartable dimensions with the primary measure
- app/executor_v2.py — Added _compute_pivot(), capped to top-8 values per dimension, missing combinations return null rather than a misleading zero
- frontend/src/components/AnalysisChartV2.jsx — Generalized the existing correlation-matrix HeatmapView to also handle rectangular pivot grids with an independent row/column derivation and a sequential (vs. diverging) color scale

- frontend/src/App.css

- Not shipped in this chat: Segmentation/clustering (#4 on the feature menu) was being investigated when the sandbox reset mid-build; no code was written before the conversation ended. (It did get built later — see the Clustering entry above, from a different chat.)

---

## 2026-09-24 — Sophistication round: deepening 5 existing features
Five ideas, picked because they made existing modules smarter rather
than adding new standalone ones — the brief was "the feature breadth
is already substantial, so sophisticate what's already there."

**1. Seasonality-adjusted forecasting** — `forecasting.py` used to fit
a plain straight line through the data even when there was an obvious
yearly wobble in it, while `seasonality.py` ran completely separately
and never fed into it. Now `forecast_trend` deseasonalizes first (using
`seasonality.py`'s own decomposition), fits the trend on the clean
signal, and adds the right seasonal offset back onto each projected
month. Falls back to the original plain-linear behavior unchanged when
no significant seasonal pattern is available.
**Files:** `app/forecasting.py`, `app/seasonality.py`, `app/main.py`,
`tests/test_forecasting.py`.

**2. Confidence bands on the forecast** — the bootstrap machinery
already existed in `confidence_intervals.py` for KPIs but was never
extended to the forecast's own projected points. Each projected point
now carries a rough 95% plausible range (residual bootstrap — resample
residuals and refit for parameter uncertainty, plus a fresh residual
draw per point for prediction uncertainty), shown as a shaded band
behind the dashed forecast line instead of a single bare line that
invites more confidence than a linear extrapolation deserves.
**Files:** `app/forecasting.py`, `tests/test_forecasting.py`,
`frontend/src/components/AnalysisChartV2.jsx`.

**3. Partial correlations** — new `app/partial_correlation.py`.
Answers "is X still correlated with Y once you control for Z?" for
both numeric controls (linear residualization) and categorical
controls (within-group demeaning/ANCOVA-style) — catches confounds
that `simpsons_paradox.py` alone doesn't, since that module only ever
checks categorical splits and only flags a full sign reversal in every
subgroup; this one also handles numeric controls and reports a
gradient (robust / partially explained / mostly explained / reverses)
rather than requiring an all-or-nothing flip.
**Files:** `app/partial_correlation.py` (new), `app/main.py`,
`tests/test_partial_correlation.py`,
`frontend/src/components/PartialCorrelationsPanel.jsx` (new),
`frontend/src/components/DeepDivePanel.jsx`, `frontend/src/searchUtils.js`,
`frontend/src/exportReport.js`.

**4. Statistically-gated weak points** — every weak point in
`weak_points.py` that makes a comparison or percentage claim (6 of 7
detectors — `missing_data` is a fact about the whole dataset, not a
sample estimate, so it's deliberately left alone) now re-checks itself
by resampling the same rows it came from, via a new general-purpose
`bootstrap_metric_significance()` added to `confidence_intervals.py`.
A finding that doesn't reliably clear its own flagging threshold gets
its priority knocked down a notch (and its score cut) plus a
plain-language caveat; one that does holds up gets a confirmation
note. No jargon ("confidence interval", "bootstrap", "p-value") leaks
into the user-facing text — "checked this by reshuffling the data
thousands of times" says the same thing in plain terms.
**Files:** `app/confidence_intervals.py`, `app/weak_points.py`,
`app/main.py`, `tests/test_weak_points_significance.py`,
`frontend/src/components/WeakPointsPanel.jsx`.

**5. Risk-scored retention** — new `assess_retention_risk()` in
`cohort_analysis.py`, alongside the existing cohort-curve function
rather than replacing it. Learns each dataset's own typical return gap
(median time between consecutive visits, not a hardcoded "30 days")
and flags any entity overdue by 1.5x (medium risk) or 3x (high risk)
— "who's about to churn," which the aggregate retention curve alone
can't show. Verified against synthetic data with 50 regular customers
and 10 deliberately lapsed ones: it recovered the right typical window
and flagged exactly the 10 lapsed customers, no false positives among
the regulars.
**Files:** `app/cohort_analysis.py`, `app/main.py`,
`tests/test_retention_risk.py`, `frontend/src/components/CohortsPanel.jsx`.

## 2026-09-25 — Readable chart legends
Recharts colors each legend label's text to match that item's own
swatch color by default — fine for a couple of bright accent lines,
unreadable once you're pulling from the app's muted multi-hue palette
(a 6-slice donut had some labels nearly invisible against the dark
background). Fixed with a new shared `ReadableLegend.jsx`: swatch stays
colored per segment, but the label text itself always uses the theme's
normal readable color. Wired into the donut/pie chart, the grouped
scatter plot, and the trend line chart — the three places a Recharts
legend was used.

**Files:** `frontend/src/components/ReadableLegend.jsx` (new),
`frontend/src/components/AnalysisChartV2.jsx`,
`frontend/src/components/TrendChart.jsx`.

## 2026-09-27 — Navigation: Escape and logo now go home, GitHub link fixed
Pressing Escape didn't do anything useful inside the app before,
and there was no way to get back to the landing/upload screen once
you'd opened a file except removing every session. Added a global
Escape listener (skipped while typing in a text field, so it doesn't
clobber an in-progress filter) and made the sidebar's DATALENS mark a
real clickable button — both now return to the landing view. That
required one real fix, not just a new button: the landing hero
previously only rendered when there were zero uploaded sessions at
all, so "go home" while you still had files open had nowhere to go.
Changed the condition to key off "no active session" instead, so the
landing view shows correctly with your previous uploads still sitting
in the sidebar. Also pointed the top bar's GitHub link at the actual
developer's profile instead of the leftover placeholder URL.

**Files:** `frontend/src/App.jsx`, `frontend/src/App.css`,
`frontend/src/components/Sidebar.jsx`,
`frontend/src/components/TopBar.jsx`.

## 2026-09-27 — Started this change log
Set up this file. From here on, every update gets a short entry
appended below — what changed and why, in plain language, plus the
files touched — instead of having to reconstruct project history from
memory after the fact.

**Files:** `CHANGELOG.md` (new).

## 2026-09-27 — Change log entries now list files touched
Added a "Files:" line to every entry above (retroactive ones marked as
reconstructed-not-guaranteed-complete; everything from here on is
exact, straight from the actual edits made).

**Files:** `CHANGELOG.md`.

## 2026-10-01 — Merged real history from 3 old chat sessions
Replaced the thin, memory-based "Phase 1 / Phase 2 / Phase 3 / Polish
round" placeholder with real history pulled directly out of three old
chat sessions where the project was actually built — covering
everything from the original Excel/SQL/Power BI dashboard through the
DataLens rename, the domain-aware rebuild, and most of the later
feature rounds (clustering, seasonality, anomaly detection, Simpson's
paradox, Benford's Law, cohorts, confidence intervals, correlation
significance/VIF, filtering, search, the sample gallery, the pivot
explorer, and a long list of real bugs found and fixed along the way).
Cleaned up some line-wrap formatting artifacts from the raw dump by
hand rather than trusting a blind find-and-replace.

**Files:** `CHANGELOG.md`.

## 2026-10-02 — Custom pivot / ad-hoc query builder ("Ask Your Own Question")
First of the "new territory" batch (ideas that don't overlap anything
already in `app/`, as opposed to the earlier round that only
sophisticated existing modules). Until now the only way to see a
measure-by-dimension breakdown was whichever ones `analysis_planner.py`
auto-picked for "Key Analyses" — if you wanted "average Profit by
Region" and the planner hadn't already picked that exact combination,
there was no way to get it. New panel lets you pick any measure, any
aggregation (sum/average/count), and up to two dimensions (a cross-tab)
and see the result instantly.

The nice part: no new backend endpoint at all. `app/filtering.py`
already ships a compact row-level `filterable_data` payload (every
measure + every chartable dimension) alongside the analysis, originally
built for the client-side filter feature — this just reuses the exact
same data, computing the aggregation in the browser
(`runCustomQuery()` in `filterUtils.js`, mirroring
`executor_v2.py`'s `_compute_pivot`/`_compute_distribution_sum` logic
including the same "cap to the top 8 most frequent values per
dimension, by row count" rule for cross-tabs). It also respects
whatever filters are currently active on the dashboard, same as every
other filter-reactive panel. Results render through the existing
`AnalysisChartV2` component by building a synthetic analysis object
client-side — a custom query looks exactly like an auto-picked one of
the same shape, right down to using the same chart-type rules
(`chooseQueryChartType()` mirrors `analysis_planner.py`'s
`choose_chart_type`: donut for a handful of categories, treemap past
15, bar otherwise, heatmap for two dimensions).

Sanity-checked the aggregation logic directly in Node against a small
synthetic table (sum/avg/count, one dimension and two, including a
cross-tab cell with no matching rows correctly coming back `null`
rather than a misleading 0) before wiring it into the UI.

**Files:** `frontend/src/filterUtils.js`,
`frontend/src/components/QueryBuilderPanel.jsx` (new),
`frontend/src/App.jsx`, `frontend/src/App.css`.

## 2026-10-01 — Fixed: the old-chat merge had deleted this chat's own "Sophistication round" entry
The merge above replaced an entire block of the file in one shot,
which — on top of the intended placeholder content — also wiped out
the real "Sophistication round" entry documenting the 5-feature round
from earlier in this same chat (seasonality-adjusted forecasting,
confidence bands, partial correlations, statistically-gated weak
points, risk-scored retention). That was never old-chat history to
begin with, so it should never have been touched. Restored it as its
own dated entry in the right chronological spot, ahead of "Readable
chart legends."

**Files:** `CHANGELOG.md`.
