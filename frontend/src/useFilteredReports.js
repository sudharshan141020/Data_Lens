import { useEffect, useRef, useState } from 'react';
import { fetchFilteredReports } from './api';
import { buildFilteredPayload, recomputeBlocker, unavailableReports } from './filteredReportsUtils';

const DEBOUNCE_MS = 350;
const IDLE = { status: 'idle', reports: null, rowsUsed: null, note: null };

// Keeps four reports in step with the filter bar.
//   idle      no filter is on (or nothing can be recomputed): the panels show the upload-time reports
//   loading   a request for the CURRENT filters is in flight
//   ready     `reports` describe exactly the rows in view
//   error     the update failed; the panels fall back to the full-data reports and the person is told
//   blocked   recompute is impossible for this dataset; `note` says why
//
// Two rules keep it honest. A response is used only if it answers the CURRENT filters (a slow earlier
// request can never overwrite a newer one), and while a new request is pending nothing from an older one
// is shown, because numbers for the wrong filter are worse than a short wait.
export function useFilteredReports({ v2, rows, active }) {
  const [state, setState] = useState(IDLE);
  const runId = useRef(0);

  useEffect(() => {
    const id = ++runId.current;            // any earlier request is now stale, whatever happens next
    if (!active || !v2) { setState(IDLE); return undefined; }

    const blocker = recomputeBlocker(v2, rows.length);
    if (blocker) { setState({ ...IDLE, status: 'blocked', note: blocker }); return undefined; }

    setState({ ...IDLE, status: 'loading' });
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const out = await fetchFilteredReports(buildFilteredPayload(v2, rows), { signal: controller.signal });
        if (id !== runId.current) return;
        if (!out.available) setState({ status: 'ready', rowsUsed: rows.length, note: out.note, reports: unavailableReports(out.note) });
        else setState({ status: 'ready', rowsUsed: out.rows_used, note: null, reports: out });
      } catch (err) {
        if (id !== runId.current || err?.name === 'AbortError') return;
        setState({ ...IDLE, status: 'error', note: err.message || 'The reports could not be updated for your filters.' });
      }
    }, DEBOUNCE_MS);

    return () => { clearTimeout(timer); controller.abort(); };
  }, [v2, rows, active]);

  return state;
}
