const PRIORITY_META = {
  high: { label: 'High', color: 'var(--red)' },
  medium: { label: 'Medium', color: 'var(--amber)' },
  low: { label: 'Low', color: 'var(--text-faint)' },
};

export default function WeakPointsPanel({ weakPoints, tickNum }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Weak Points</h3>
          <p className="dim-sub">Issues worth a closer look, ranked by severity</p>
        </div>
      </div>

      {!weakPoints?.length ? (
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          Nothing stood out as a problem — data looks clean and evenly distributed.
        </p>
      ) : (
        <div className="insights-list">
          {weakPoints.map((w, i) => {
            const meta = PRIORITY_META[w.priority] || PRIORITY_META.low;
            return (
              <div key={i} id={`search-weakpoint-${i}`} className="insight-card">
                <div className="insight-top">
                  <span className="insight-type" style={{ color: meta.color }}>{meta.label} priority</span>
                </div>
                <p className="insight-text" style={{ fontWeight: 600 }}>{w.problem}</p>
                <p className="insight-text" style={{ marginTop: -6 }}>{w.impact}</p>
                <p className="insight-recommendation">
                  <span className="rec-label">Suggested action —</span> {w.suggested_action}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
