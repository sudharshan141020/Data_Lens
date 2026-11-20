# DataLens — Project Handoff Summary

## Status as of 2026-11-06 (READ THIS FIRST)

**`CHANGELOG.md` is the authoritative history** (newest entry at the bottom, each with what, why and the bugs
found). The long "Recently added" section further down predates it; where they disagree, trust the changelog.

**Where things stand.** `main` on GitHub (`sudharshan141020/Data_Lens`) is green in CI: 372 backend tests (pytest),
443 frontend tests (Vitest, 29 files), 13 end-to-end tests (Playwright, real Chromium against the real server). Two
more Playwright specs exist but are opt-in (screenshots, demo GIF), and `live.spec.js` only runs against a deployed URL.

**Added since the sections below were written** (all in the changelog): frontend tests + CI; personal-data detection
with a share/export guard (dialog in the browser, **and enforced on the server** for share links);
"why did it change?" driver analysis; outlier-robustness check; A/B / hypothesis-test mode; "show the code" pandas
export; Period Comparison / Drivers / Robustness / Seasonality that **follow the filter bar**; deployment readiness
(configurable upload cap, health check, `npm run test:live`); MIT license, README header and demo GIF.
New backend modules: `sensitive_data.py`, `share_guard.py`, `drivers.py`, `robustness.py`, `hypothesis.py`,
`code_export.py`, `filtered_reports.py`. New endpoints: `/api/hypothesis-test`, `/api/export/code`,
`/api/filtered-reports`; `/api/share` now returns 409 for personal data unless `acknowledge_personal_data` is sent;
`/api/health` reports `max_file_mb`.

**Deploying.** `npm run build` writes to `frontend/dist`, **not** to `app/static`, which is what the server serves. After
a frontend change: `cd frontend; npm run build; cd ..; Remove-Item -Recurse -Force app\static; Copy-Item -Recurse frontend\dist app\static`,
then commit `app/static`. `render.yaml` sets the free plan, Python 3.12.7, a health check and `DATALENS_MAX_FILE_MB=10`
(measured: a 32 MB CSV peaks at ~620 MB, over the free plan's 512 MB). Check a deployment with
`$env:LIVE_URL = "https://..."; cd frontend; npm run test:live` (it detects a stale frontend and a missing cap setting).

**Open items.**
- Confirm Render redeployed from the latest push and run `npm run test:live` against it.
- README "Live demo" line is still a placeholder: put the Render address in.
- GitHub About box: description and topics (suggested text is in the 2026-11-02 changelog entry).
- Free plan: share links live in server memory, so a spin-down or redeploy ends them; no login or rate limiting.
- Not recomputed under filters (still full data): segments, anomalies, cohorts, correlations, the changepoint marker.

**Starting a new chat.** The sandbox does not persist between chats. Upload the current project zip first (command below),
then ask for changes. Do not start editing from memory of an older version.

```powershell
cd D:\Data_Lens
$out = "$env:USERPROFILE\Desktop\datalens_full.zip"; Remove-Item $out -ErrorAction SilentlyContinue
$skip = '\\(node_modules|venv|\.venv|env|dist|build|\.git|__pycache__|\.pytest_cache|\.hypothesis|test-results|playwright-report)(\\|$)'
$root = (Get-Location).Path
$files = Get-ChildItem -Recurse -File -Force | Where-Object { $_.FullName.Substring($root.Length) -notmatch $skip -and $_.Extension -notin '.pyc','.zip' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($out, 'Create')
foreach ($f in $files) { [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $f.FullName.Substring($root.Length + 1).Replace('\','/'), 'Optimal') }
$zip.Dispose(); "{0} files -> {1}" -f $files.Count, $out
```

## What it is
A universal, rule-based data analytics platform (originally "Sales Insights
Ledger," renamed to **DataLens**). Upload any CSV/Excel file → it detects
the domain (healthcare, sales, retail, education, HR, traffic, finance, or generic),
understands the data's structure, and produces a full analysis: dataset
profile, top-3 key analyses, a narrative "Story," findings, weak
points/recommendations, data quality report, and a correlation center.

**Critically: 100% rule-based, no LLM/AI API calls anywhere.** This was a
deliberate choice from the start — keeps it free to run and safe to deploy
publicly (no per-user API cost, no abuse risk). Do not suggest adding an LLM
call to "improve" insights — that would violate a core design constraint.

## Tech stack
- Backend: Python, FastAPI, pandas
- Frontend: React + Vite, Recharts for charts, lucide-react for icons
- Single process: FastAPI serves both the API and the built React app
  (no separate frontend/backend servers needed)
- Deployment: Render (free tier), auto-deploys from GitHub on push
- No database, no auth — everything processed in-memory per request

## Current visual design
**Light and dark themes**, switched by a toggle in the top bar (the page sets `data-theme="light"|"dark"` on the root
element). The earlier black-and-white-only theme is now just the dark one. All colour comes from CSS variables defined
in `frontend/src/index.css`: `--ink` (page background), `--surface`, `--surface-raised`, `--border`, `--border-soft`,
`--text`, `--text-muted`, `--text-faint`, `--teal` (the accent), `--on-accent` (text on an accent), `--red`, `--amber`,
`--shadow-raised`. **Use only these.** A variable that does not exist silently falls back to whatever default you wrote,
which is how a warning dialog once shipped dark-on-dark in the light theme. Check contrast in BOTH themes whenever UI changes
(`e2e/features.spec.js` has a WCAG contrast test for the personal-data warning).

## Architecture (backend, all in `app/`)
Built in phases, each a separate tested module — this layering matters,
don't collapse it:

1. **`semantic_roles.py`** — classifies every column into a semantic role
   (FINANCIAL_METRIC, PROFIT, DISCOUNT, DATE, CONDITION, HOSPITAL, CATEGORY,
   IDENTIFIER, etc.) via keyword matching + dtype/cardinality fallback.
2. **`domains.py`** — scores which domain (healthcare/sales/education/hr/
   traffic/finance/generic) the dataset belongs to, based on which semantic
   roles are present. Only counts genuinely distinctive roles (learned the
   hard way: generic roles like CATEGORY caused false positives).
3. **`understanding.py`** — `understand_dataset(df)` produces a
   `DatasetProfile`: domain, confidence, primary entity, measures (each
   tagged sum/avg aggregation), dimensions (each tagged chartable/not).
   This is the single source of truth everything downstream consumes.
4. **`analyzers/`** — plugin architecture. `base_analyzer.py` defines the
   interface (`choose_dashboard`, `generate_findings`, `detect_weak_points`,
   `generate_story`, etc.); one file per domain
   (`healthcare_analyzer.py`, `sales_analyzer.py`, etc.) each just sets a
   few class attributes (`headline_dimension_roles`, `key_kpis`) — no
   domain-specific logic scattered elsewhere. `registry.py` maps domain
   name → analyzer class. Adding a new domain = one new small file +
   one registry line.
5. **`analysis_planner.py`** — decides WHICH analyses to run and picks
   chart types (line/donut/horizontal_bar/scatter/heatmap/boxplot/treemap)
   via explicit rules. Also ranks importance and picks the diverse top-3
   for the dashboard. Also generates "chart reasoning" text (why this
   chart was chosen).
6. **`executor_v2.py`** — actually computes the chart data for each
   planned analysis spec.
7. **`insight_engine.py`** — positive findings ("X is the most common Y").
8. **`weak_points.py`** — problems, each with Problem/Impact/Priority/
   Suggested Action, written in **plain English on purpose** (no jargon
   like "margin," "concentration," "IQR" — explicitly requested).
9. **`story_engine.py`** — chains findings/weak points into a narrative
   arc (Trend → Breakdown → Driver → Recommendation). Not a new detection
   engine — pure narrator over existing data.
10. **`data_quality.py`** — missing values, duplicates, constant columns,
    outliers, quality score.
11. **`correlation_center.py`** — strongest positive/negative relationships,
    each with a real p-value (Pearson r + two-sided t-test) and a caveat
    when the sample is too small or the result isn't significant — a
    strong r on 12 rows gets flagged, not presented as a confident
    finding. Also runs a VIF (variance inflation factor) check across all
    measures to catch multicollinearity — redundant metrics that only
    look independent pairwise. Both are additive to the original
    pairwise-correlation logic; nothing about the original ranking/
    pick-strongest behavior changed, these just attach more context to it.
12. **`kpi.py`, `insights.py`, `column_detector.py`, `planner.py`,
    `executor.py`** — the ORIGINAL sales-specific pipeline, kept running
    alongside the newer domain-aware one for zero regression risk. Both
    coexist in `main.py`'s response (legacy fields + a `v2` key with
    everything new). Don't be surprised two systems exist — that was
    intentional, additive-not-destructive engineering.

## Frontend (`frontend/src/`)
Key components: `ExecutiveSummary`, `IntelligentDashboard` (top-3),
`StoryMode`, `AnalysisExplorerV2` (sectioned: Trends/Distributions/
Relationships/Correlations/Outliers), `FindingsPanel`, `WeakPointsPanel`,
`DataQualityCenter`, `CorrelationCenter`, `Sidebar` (multi-file sessions,
pin, combine), `AnalysisChartV2` (renders all 7 chart types).

## Known regression-prone spots (fixed once, could break again if edited)
- **pandas 3.x changed string dtype** away from `object` — always check
  `pd.api.types.is_string_dtype()`, not `dtype == object`.
- **Identifier columns** (sequential IDs like PassengerId) must be excluded
  from becoming "the metric" — a numeric column with near-100% unique
  values isn't a real measure.
- **CSS token semantics**: `--ink` means "page background," not literally
  ink-black — its actual color has flipped between themes (dark→light→
  dark again). Any hardcoded `color: var(--ink)` assuming a specific
  literal color is fragile — check contrast whenever the theme changes.
- **top-3 diversity logic** in `analysis_planner.py`'s `top_n()`: only
  enforces unique *subject* (column), not unique *type* — an earlier
  stricter version blocked legitimate second entity-distribution analyses.

- **CSS variables that do not exist** (see the design section): always use the real tokens.
- **JS unicode escapes in JSX text** (`\\u25B6`) render literally and build clean; a Vitest scan fails on them.
- **Regexes over user-controlled text must be linear.** An email regex that scans a long run of letters with no `@` is quadratic
  and can freeze the server from one request (it hung a test for five minutes). `share_guard.py` finds each `@` and examines a
  bounded window; keep it that way, and keep the timing tests.
- **Test names must be short.** pytest stores the current test name in an environment variable, Windows caps those at 32,767
  characters, Linux does not. A huge `parametrize` value passes in CI and breaks on a Windows machine. `tests/conftest.py` fails
  collection on any name over 1,000 characters; build big inputs inside the test.
- **Masking works by structure, not only by value.** A masked identifier column also appears as raw numbers in the at-risk list
  and in scatter charts; `maskV2` handles those places explicitly. A test on the real captured analysis guards it.
- **The frontend fixture must be regenerated** after any change to the `/api/analyze` response:
  `python scripts/regenerate_frontend_fixture.py`, then `npm test`. A stale fixture makes new features look "blocked".
- **A guard that only checks what was uploaded is the wrong guard.** The share check looks at what is being PUBLISHED.

## Deployment
- Live on Render, auto-deploys from GitHub on push to main
- Workflow: edit local files → test with `start.bat` → `git add . && git
  commit && git push` → Render redeploys automatically (check the Render
  dashboard's "Events" tab to confirm a deploy actually triggered)
- **`venv` breaks if the project folder is moved/renamed** — Windows bakes
  absolute paths into it. Delete and recreate `venv` after any move.

## What's NOT built yet (from the roadmap discussions)
- More domains beyond the current 9 (Agriculture, Sports, Customer Support)
- Auth + persistence + saved workspace — **flagged multiple times as a
  real product-direction decision**, not just a feature: current app is
  pitched as "nothing is stored," adding accounts/persisted uploads
  reverses that and brings real responsibilities (password hashing,
  per-user data isolation). Needs a deliberate yes/no, not a default.
- Performance/caching for very large datasets (100K+ rows) — the two
  actual bottlenecks found there are now fixed (see below); the
  filtering-disables-past-100K ceiling is a deliberate payload-size
  tradeoff, not a performance limitation, and hasn't been revisited.
- Sunburst charts, map visualizations (mentioned as "future" in specs)

## Recently added (worth knowing about if picking this back up)
- **Share links, and the limits around them** (`app/share_cache.py`,
  `app/rate_limit.py`, `app/body_limit.py`, `app/main.py`): `POST /api/share`
  keeps a snapshot in memory for 24 hours; `GET /api/share/{token}` returns it.
  Three things were added on top of the original feature:
  1. **Revocation.** Creation returns a `revoke_token` in addition to the URL
     token -- deliberately separate, because the URL is the part people paste
     around and so cannot be the credential for deleting it (stored only as a
     SHA-256 hash, compared with `hmac.compare_digest`).
     `DELETE /api/share/{token}` with `X-Share-Revoke` deletes the link; a wrong
     secret returns 403 and changes nothing. The frontend keeps that revoke
     token in memory, per session, for the tab that created the link, and the
     Export menu shows a **Revoke share link** item only while one is held --
     so a link can be deleted from the UI rather than only by hand. A reload or
     another device has no revoke token, and therefore no revoke item: the proof
     of creation was never in the URL (or in storage) to begin with.
  2. **Honest expiry.** Every token is `<random>_<expiry in base 36>`, so the
     expiry is readable from the token alone. That is what lets a miss answer
     410 "expired on <date>" (aged out), 404 "no longer available" (revoked, or
     lost with the process), or 404 "doesn't exist" (never ours), instead of one
     generic 404 for all three -- without keeping a tombstone for every dead link.
  3. **Limits.** Both share endpoints are rate-limited per client (sliding
     window, 30 creates / 120 reads a minute); `render.yaml` sets
     `DATALENS_TRUSTED_PROXIES=1` because Render's proxy is the socket peer, and
     without it every visitor would share one budget. Every non-upload request
     body is refused over 25MB *before* anything parses it (`app/body_limit.py`,
     `DATALENS_MAX_BODY_MB`; the endpoints' own size checks ran only after the
     whole body had been decoded). The gate is "not multipart", not "is JSON":
     FastAPI still buffers the body for a model endpoint when the caller declares
     `text/plain`, so a cap that watched only `application/json` could be skipped
     by changing one header. Uploads keep their own streaming cap. One subtlety
     worth keeping: the streamed refusal is raised as an `HTTPException`, because
     FastAPI rewrites any other exception raised while it reads a model body into
     a misleading 400 "There was an error parsing the body" -- a chunked 27MB
     `text/plain` post really did answer 400 before that, and 413 after. The cache
     also gives each address 15MB / 20 links of its own, evicting that address's
     oldest entries first, so one caller looping creates cannot push out everyone
     else's live links.
  What the UI does and does not do: it copies the URL and keeps `revoke_token` in
  memory for the tab, so **Revoke share link** works for a link created in that
  tab; links created elsewhere stay API-only (curl/scripts), which is the
  intended trade -- the key is the only proof of creation and is not persisted.
- **Marketing domain** (`analyzers/marketing_analyzer.py`): 9th domain,
  same additive plugin pattern -- new semantic roles (CAMPAIGN, CHANNEL,
  IMPRESSIONS, CLICKS, CTR, CONVERSION_RATE, CPC, ROAS, AD_SPEND). Verified
  with a synthetic campaign dataset: detects at full confidence, correct
  KPI vocabulary, and CTR/Conversion Rate/ROAS all correctly average
  rather than sum (a rate summed across rows would be meaningless).
- **Manufacturing domain** (`analyzers/manufacturing_analyzer.py`): 8th
  domain, same additive plugin pattern as Retail -- new semantic roles
  (DEFECT_RATE, DOWNTIME, UNITS_PRODUCED, MACHINE, SHIFT,
  PRODUCTION_LINE), one domains.py entry, one analyzer file, one registry
  line. Verified: a synthetic manufacturing dataset (production line,
  machine, shift, defect rate, downtime columns) detects as
  "manufacturing" at full confidence, with Defect Rate correctly averaged
  (not summed) in findings.
- **Bug fix found while building it, affecting Retail too**: `STORE`,
  `SUPPLIER`, and `WAREHOUSE` were referenced in RetailAnalyzer's
  `headline_dimension_roles` but were never actually added to
  `DIMENSION_ROLES` in `understanding.py` -- meaning columns with those
  roles could never become real dimensions, so the "Store Performance"
  breakdown could never have worked for any retail dataset since Retail
  was added. Fixed by adding STORE/SUPPLIER/WAREHOUSE (and the new
  MACHINE/SHIFT/PRODUCTION_LINE) to DIMENSION_ROLES. Also gave
  INVENTORY_LEVEL/REORDER_POINT/UNIT_COST/DEFECT_RATE/DOWNTIME/
  UNITS_PRODUCED explicit entries in MEASURE_ROLES with correct
  aggregations (e.g. UNIT_COST and DEFECT_RATE average rather than sum)
  instead of relying on the generic "sum" fallback default.
- **150K-row performance fix** (`column_detector.py`, `semantic_roles.py`):
  a 150K-row file took 4.59s end-to-end; profiled every pipeline stage
  individually to find out why rather than guessing. Two real causes,
  both in column-role detection, both fixed:
  1. `_is_usable_column()` (the completeness guard added earlier) was
     called inside nested role x hint x column loops with no memoization
     -- the same column's non-null count got redundantly recomputed
     potentially hundreds of times. Fixed by computing it once per column
     up front.
  2. The bigger one: `_dtype_fallback()`'s date-detection heuristic ran
     `pd.to_datetime()` over the *entire* column for every unmatched text
     column (e.g. Order ID, Customer ID), and dateutil's lenient parser is
     slow at scale even when it correctly concludes "not a date." Fixed
     by sampling up to 1000 values instead of scanning the full column --
     statistically just as reliable for a yes/no classification, ~30x
     faster in isolation (3.09s -> 0.10s for `detect_columns` alone).
  Net result: 4.59s -> ~2.5-2.8s end-to-end on the same 150K-row file,
  with identical output (verified the column mapping was byte-for-byte
  unchanged before/after). Smaller datasets improved too as a side
  benefit -- the ~10.5K stress-test dataset went from ~1.2s to ~0.8s.
- **Global search** (`frontend/src/searchUtils.js`,
  `frontend/src/components/SearchBar.jsx`): a single search box over
  findings, weak points, story beats, chart titles+reasoning, and
  correlation pairs, built as a flat client-side index from the same v2
  result already in memory -- no backend involvement. Simple substring
  matching, word-boundary matches ranked above mid-text ones. Clicking a
  result scrolls to and briefly highlights it; chart results are a special
  case since the Explorer only renders one analysis at a time (behind a
  section tab + dropdown) -- search drives that selection via a
  `jumpTarget` prop on `AnalysisExplorerV2` rather than a plain scroll.
  Verified against a real analysis result: 34 indexed entries across 5
  categories on the sales demo, spot-checked several queries by hand to
  confirm every match was genuine (including a few that looked surprising
  at a glance, e.g. a "region" search surfacing a Sales-vs-Profit scatter
  chart because its reasoning text mentions being grouped by Region).
- **Interactive filtering** (`app/filtering.py`, `frontend/src/filterUtils.js`,
  `frontend/src/components/FilterBar.jsx`): date range + per-dimension
  multi-select filters that live-update charts. Deliberately kept the
  backend fully stateless -- rather than a `/api/filter` endpoint with
  server-side session state, `/api/analyze` now also returns
  `filterable_data`, a compact row-level slice (date + measure + dimension
  columns only, never the whole raw file) that the frontend filters and
  re-aggregates entirely client-side, no further server round trips.
  Covers `trend` and `distribution_sum`/`distribution_count` chart types
  (the three most common); scatter/heatmap/boxplot/correlation-matrix
  aren't recomputed client-side and the UI says so explicitly rather than
  silently leaving them stale. Disables itself above 100K rows (see
  roadmap note above) and above 40 distinct values for a given dimension
  (not meaningfully filterable at that cardinality). Verified the
  client-side aggregation produces byte-for-byte identical numbers to the
  backend's own computation when no filter is applied, and reruns in
  ~14ms end-to-end on a 10.5K-row dataset with a two-dimension filter
  applied.
- **PDF export** (`app/pdf_report.py`, new `/api/export/pdf` endpoint):
  stateless by the same logic as filtering -- the frontend sends back the
  analysis JSON it already has, the backend just formats it into a PDF.
  Mirrors the Excel export's content (Overview, Story, Findings, Weak
  Points, Data Quality, Correlations, Multicollinearity). The frontend
  strips `filterable_data` before sending, since the PDF generator never
  reads it and it can be a substantial payload on large datasets.
- **Retail domain** (`analyzers/retail_analyzer.py`): 7th domain, added purely
  additively per the plugin architecture -- new semantic roles
  (INVENTORY_LEVEL, REORDER_POINT, SUPPLIER, STORE, WAREHOUSE, UNIT_COST) in
  `semantic_roles.py`, one new entry in `domains.py`'s DOMAIN_SIGNALS, one
  new analyzer file, one registry line. Deliberately kept distinct from
  "sales" (inventory/supply-chain signals vs. transaction/discount signals)
  so datasets with both sets of columns resolve to whichever has the
  stronger weighted signal rather than colliding. Verified: a synthetic
  retail dataset (stock level, reorder point, supplier, store columns)
  detects as "retail" at full confidence; the existing sales demo dataset
  still detects as "sales" -- no regression.
- **Correlation significance + multicollinearity** (`correlation_center.py`):
  every correlation now carries `n`, `p_value`, `significant`, `strength`,
  and a plain-English `caveat`. New `analyze_multicollinearity()` function
  computes VIF per measure via plain least-squares (no sklearn needed).
  Added `scipy` and explicit `numpy` to `requirements.txt`.
- **Excel export** (`frontend/src/exportReport.js`): entirely client-side
  via SheetJS (`xlsx` npm package) — multi-sheet workbook (Overview,
  Story, Findings, Weak Points, Data Quality, Correlations,
  Multicollinearity), triggered from a button in `App.jsx`. No backend
  endpoint involved, consistent with the no-persistence design. Note:
  `npm audit` flags `xlsx` with a known prototype-pollution/ReDoS
  advisory with no patch available — low risk here since it's only used
  to *write* files from our own data, never to parse untrusted uploads,
  but worth knowing if `npm audit` output looks alarming later.

## Working style established in this project (worth carrying forward)
- Big feature requests get built in explicit phases, tested end-to-end
  after each one, with real datasets (not just the happy path) — several
  real bugs were only caught this way (pandas dtype bug, PassengerId
  picked as "revenue," top-3 diversity bug, contrast bugs after theme
  changes). Keep testing thoroughly before declaring something done.
- Changes are additive when possible — old working pipelines aren't torn
  out until a replacement is proven solid.
- **Commit messages name the problem being solved, not just the change.** The
  subject says what was wrong (or what was possible that shouldn't have been),
  and the body says why this change closes it — "Cap every non-upload body ..."
  rather than "Update body_limit.py". Someone reading the GitHub history should
  be able to tell which problem a commit solved, and what would have happened
  without it, without opening the diff.
- This sandbox's filesystem does NOT persist between conversation
  sessions — if starting a new chat, you'll need to **re-upload your
  current project zip** (exclude `venv/` and `frontend/node_modules/`,
  those are huge and regenerate automatically) before any further backend
  or frontend edits can be made, same as had to happen this session.
- **Every change gets a `CHANGELOG.md` entry**, appended at the bottom: what, why, decisions, the bugs found along the way, limits,
  files. Date it from the system clock (`date +%F`), never an estimate. (Nine headings were once guessed and had to be corrected.)
- **Deliver one zip per change, containing only the files that changed**, extracted over the project root, and say how to verify
  it (the expected test counts). The user works in Windows PowerShell and pastes terminal output back; ask for it.
- **"Verified" means run.** Run all three suites before delivering. For any guard or check, also switch the protection OFF and
  confirm the test fails (a test that passes either way tests nothing; one such test was caught this way). Look at screenshots of
  UI work: tests did not catch unreadable text or a distorted chart.
- **Drive the real thing.** A real Chromium against the real server found bugs unit tests missed (a privacy leak in masking,
  unreadable text). If the sandbox cannot download Playwright's browser, an npm-packaged Chromium
  (`@sparticuz/chromium`) works with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`.
- **Reuse, don't re-implement.** Filter-aware reports call the same Python functions the upload does, and are tested against
  running the whole pipeline on a pre-filtered file.
- **Be honest about limits** in the docs and the UI (what the guard cannot catch, which panels do not follow filters).
- If the sandbox resets mid-task, rebuild from the original upload plus the delivered zips (in order) and check the test counts
  match the last reported ones before continuing.

