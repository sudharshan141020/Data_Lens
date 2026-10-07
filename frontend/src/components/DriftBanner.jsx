import { useState } from 'react';

function fmtDate(ts) {
  return new Date(ts).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function fmtPct(p) {
  if (p == null) return '';
  return `${p > 0 ? '+' : ''}${p}%`;
}

function changeColor(p) {
  if (p == null || p === 0) return 'var(--text-faint)';
  return p > 0 ? 'var(--teal)' : 'var(--red)';
}

export default function DriftBanner({ match, drift, onDismiss }) {
  const [expanded, setExpanded] = useState(false);
  if (!match || !drift) return null;

  const { snapshot } = match;
  const hasAnyChange = drift.measureDeltas.length || drift.resolved.length || drift.worsened.length
    || drift.improved.length || drift.newIssues.length || drift.addedColumns.length || drift.removedColumns.length;

  return (
    <div className="panel drift-banner">
      <div className="drift-banner-head">
        <p className="drift-banner-text">
          <span className="drift-banner-icon" aria-hidden="true">📊</span>
          {' '}This looks like an updated version of <strong>{snapshot.fileName}</strong>, saved {fmtDate(snapshot.savedAt)}
          {!match.isExact && ` (${Math.round(match.score * 100)}% of columns match)`}.
        </p>
        <div className="drift-banner-actions">
          <button type="button" className="drift-banner-btn" onClick={() => setExpanded((e) => !e)}>
            {expanded ? 'Hide' : 'View what changed'}
          </button>
          <button type="button" className="drift-banner-dismiss" onClick={onDismiss} aria-label="Dismiss">✕</button>
        </div>
      </div>

      {expanded && (
        <div className="drift-details">
          {drift.rowCountChangePct != null && (
            <p className="dim-sub" style={{ marginBottom: 10 }}>
              Rows: {drift.rowCountOld?.toLocaleString()} → {drift.rowCountNew?.toLocaleString()}
              {' '}<span style={{ color: changeColor(drift.rowCountChangePct) }}>({fmtPct(drift.rowCountChangePct)})</span>
            </p>
          )}

          {drift.measureDeltas.length > 0 && (
            <div className="drift-section">
              <p className="drift-section-title">Measures</p>
              {drift.measureDeltas.map((m) => (
                <div key={m.measure} className="drift-row">
                  <span className="mono">{m.measure}</span>
                  <span className="mono" style={{ color: changeColor(m.sumChangePct) }}>
                    {m.oldSum?.toLocaleString()} → {m.newSum?.toLocaleString()} ({fmtPct(m.sumChangePct)})
                  </span>
                </div>
              ))}
            </div>
          )}

          {drift.resolved.length > 0 && (
            <div className="drift-section">
              <p className="drift-section-title" style={{ color: 'var(--teal)' }}>Resolved since last time</p>
              {drift.resolved.map((w, i) => <p key={i} className="dim-sub">✓ {w.problem}</p>)}
            </div>
          )}

          {drift.improved.length > 0 && (
            <div className="drift-section">
              <p className="drift-section-title" style={{ color: 'var(--teal)' }}>Improved</p>
              {drift.improved.map((w, i) => <p key={i} className="dim-sub">↓ {w.problem} (now {w.priority} priority)</p>)}
            </div>
          )}

          {drift.worsened.length > 0 && (
            <div className="drift-section">
              <p className="drift-section-title" style={{ color: 'var(--red)' }}>Got worse</p>
              {drift.worsened.map((w, i) => <p key={i} className="dim-sub">↑ {w.problem} (now {w.priority} priority)</p>)}
            </div>
          )}

          {drift.newIssues.length > 0 && (
            <div className="drift-section">
              <p className="drift-section-title" style={{ color: 'var(--amber)' }}>New</p>
              {drift.newIssues.map((w, i) => <p key={i} className="dim-sub">+ {w.problem}</p>)}
            </div>
          )}

          {(drift.addedColumns.length > 0 || drift.removedColumns.length > 0) && (
            <div className="drift-section">
              <p className="drift-section-title">Columns</p>
              {drift.addedColumns.length > 0 && <p className="dim-sub">+ Added: {drift.addedColumns.join(', ')}</p>}
              {drift.removedColumns.length > 0 && <p className="dim-sub">− Removed: {drift.removedColumns.join(', ')}</p>}
            </div>
          )}

          {!hasAnyChange && (
            <p className="dim-sub">No measures or weak points were comparable between the two versions.</p>
          )}
        </div>
      )}
    </div>
  );
}
