export default function BenfordPanel({ benford, tickNum }) {
  const results = (benford?.results || []).filter((r) => r.checked);

  if (!benford?.available || results.length === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Benford's Law Check</h3>
            <p className="dim-sub">Digit-distribution data-integrity check on monetary columns</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {benford?.note || (benford?.results || [])[0]?.note || 'No monetary columns with enough range to check.'}
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Benford's Law Check</h3>
          <p className="dim-sub">Digit-distribution data-integrity check on monetary columns</p>
        </div>
      </div>

      <div className="insights-list">
        {results.map((r) => (
          <div key={r.column} className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: r.deviates ? 'var(--red)' : 'var(--teal)' }}>
                {r.column}
              </span>
              <span className="insight-rank mono">n={r.n}</span>
            </div>
            <p className="insight-text" style={{ marginBottom: 0 }}>{r.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
