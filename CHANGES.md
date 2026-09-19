# Tier 1: Ephemeral Shareable Links — changed files

New: `app/share_cache.py`. Modified: `app/main.py`,
`frontend/src/api.js`, `frontend/src/App.jsx`,
`frontend/src/components/ExportMenu.jsx`, `tests/test_api_endpoints.py`.

## Design
In-memory, TTL-based (24h), unguessable-token cache — no database, no
accounts. "Copy share link" in the Export menu POSTs the current
session's `kpis`+`v2` (filterable_data included, so the recipient gets
full interactive filtering, not a stripped static view) to `/api/share`,
gets back a token, and the URL is copied to the clipboard.
`GET /api/share/{token}` returns the stored snapshot or a 404 if
expired/unknown.

The natural upgrade path if this ever needs to survive process
restarts or run across multiple instances is swapping `share_cache.py`'s
storage for Redis — the three function signatures
(`create_share`/`get_share`/the pruning) wouldn't need to change, and
nothing else in the app touches storage directly.

Defensive limits: 15MB per-entry size cap (rejects with a clear 400,
not a crash), 500-entry total cap with oldest-expiring-first eviction
so the cache can't grow unbounded.

## No new backend routing needed for the link itself
The existing SPA catch-all (`@app.get("/{full_path:path}")`, already
serving `index.html` for any non-API path) already handles
`/share/<token>` with zero changes — confirmed this by fetching it
directly through the real built static files, not assumed. The React
app just reads the token off `window.location.pathname` on mount,
fetches the snapshot, and drops it into the existing session list as a
normal (read-only) session — reuses 100% of the existing dashboard
rendering (every panel, every export option) with no separate view to
keep in sync. A small banner ("You're viewing a shared analysis...")
and hidden sidebar are the only shared-mode-specific UI.

## Verified this session
- share_cache.py tested standalone: create/retrieve round-trip, unknown
  token, expiry (TTL monkeypatched to prove it actually expires), size
  cap, and entry-count eviction all correct.
- One cosmetic bug caught and fixed: the size-limit error message mixed
  binary MB (the actual cap, `1024*1024`) with decimal MB (`1e6`) for
  display, so a 15MB cap displayed as "16MB" — fixed to consistent
  binary-MB units throughout.
- Full HTTP round-trip: create a share of a real analysis, retrieve it
  by token, confirm the data matches; unknown token returns 404.
- Confirmed the SPA catch-all correctly serves `index.html` for
  `/share/<token>` using the actual built static files, not just
  reasoned about.
- Confirmed the sample CSVs (served from the same static directory)
  weren't affected by rebuilding — they live in `frontend/public/` and
  Vite copies them into `dist/` automatically.
- Confirmed the share-detection code is actually present in the
  compiled JS bundle, not just the source.
- Full pytest suite: 67/67 passing (64 existing + 3 new: create/
  retrieve, unknown-token-404, oversized-payload-400).
- `frontend`: `npm run build` succeeds, no new warnings.

## Not yet done
- Not visually verified in a browser — worth actually clicking "Copy
  share link", pasting it in a new tab, and confirming the read-only
  banner + full dashboard render correctly once you pull this down.
- The `/api/share/{token}` GET endpoint isn't rate-limited — fine for a
  portfolio demo, worth knowing if this ever sees real traffic.
