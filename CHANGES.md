# Paste-CSV / Sheets Import — changed files

This is backlog item #6. Only **one file changed** — extract into
`frontend/src/components/`.

## Modified files
- `frontend/src/components/UploadZone.jsx` — added a "paste data instead"
  link (shown under both the full and compact upload zones) that reveals
  a textarea. On submit, the pasted text is converted client-side into a
  `File` object and passed through the exact same `onFilesSelected`
  callback the drag-and-drop / browse path already uses.

## Zero backend changes
This reuses the existing upload pipeline end to end, unmodified:
- `app/main.py`'s `_load_dataframe()` already picks its CSV parser purely
  from the file extension (`.tsv` → tab-separated, anything else →
  comma-separated).
- The frontend sniffs the pasted text's first line for tabs vs. commas
  (pasting straight out of Excel/Google Sheets is tab-separated, typing
  or pasting a CSV is comma-separated) and names the synthesized `File`
  `pasted-data.tsv` or `pasted-data.csv` accordingly — so the backend's
  existing dispatch handles it correctly without knowing anything changed.
- Confirmed via `loadSampleFile` in `api.js`, which already does exactly
  this (`fetch` → `blob` → `new File(...)`) for the sample-dataset
  gallery — this feature follows that same established pattern.

## Verified this session
- `npm run build`: clean, no new warnings.
- Delimiter sniffing (tested directly in Node): comma-CSV → `.csv`,
  tab-separated (Sheets-style) paste → `.tsv`; empty, whitespace-only,
  and header-only pastes all correctly rejected with a clear error
  message routed through the existing `error` prop.
- Backend round-trip via FastAPI TestClient, sending raw text bytes
  under both filenames exactly as the frontend would produce them:
  `pasted-data.csv` (comma) and `pasted-data.tsv` (tab) both return
  200 and parse correctly, with **no backend code touched at all**.

## Not yet done
- Not visually verified in a browser (no way to screenshot from this
  sandbox) — worth a look at the textarea's placement/sizing in both the
  full first-run screen and the compact sidebar "+ New analysis" button.
- No delimiter override in the UI if the auto-sniff ever guesses wrong
  (e.g. a single-column paste with no delimiter at all falls back to
  `.csv`, which is harmless but worth knowing).
