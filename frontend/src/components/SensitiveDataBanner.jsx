import { useState } from 'react';
import { needsGuard, getSensitiveReport } from '../sensitiveUtils';

// Heads-up shown on the dashboard when the backend's scan found columns that
// look like personal data. It is informational: the actual stop-and-ask
// happens when the user shares or exports (SensitiveExportDialog). Collapsed
// to one line by default so it never pushes the dashboard down.
export default function SensitiveDataBanner({ v2 }) {
  const [open, setOpen] = useState(false);
  const report = getSensitiveReport(v2);
  if (!report || !needsGuard(v2)) return null;
  const cols = report.columns.filter((c) => !c.masked);

  return (
    <div role="note" aria-label="Personal data warning" style={{ background: 'var(--panel-bg, var(--card, #161a23))', border: '1px solid var(--border, rgba(255,255,255,0.15))', borderRadius: 10, marginBottom: 12, padding: '10px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span aria-hidden="true">🔒</span>
        <span style={{ flex: 1, minWidth: 200 }}>
          <strong>Possible personal data:</strong>{' '}
          {cols.length} column{cols.length !== 1 ? 's' : ''} in this file look{cols.length === 1 ? 's' : ''} like personal information.
          You'll be asked before it goes into a share link or export.
        </span>
        <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} style={{ background: 'none', border: 'none', color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}>
          {open ? 'Hide details' : 'Show details'}
        </button>
      </div>
      {open && (
        <ul style={{ margin: '10px 0 0', paddingLeft: 20 }}>
          {cols.map((c) => (
            <li key={c.column}>
              <span className="mono">{c.column}</span> — {c.reason}{' '}
              <span className="dim-sub">({c.confidence} confidence)</span>
            </li>
          ))}
          <li className="dim-sub" style={{ listStyle: 'none', marginLeft: -20, marginTop: 6 }}>
            This is a pattern-based check, so it can miss things or flag harmless columns.
          </li>
        </ul>
      )}
    </div>
  );
}
