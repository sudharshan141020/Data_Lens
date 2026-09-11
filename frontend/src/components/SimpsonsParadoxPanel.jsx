export default function SimpsonsParadoxPanel({ simpsonsParadox, tickNum }) {
  const flags = simpsonsParadox?.flags || [];

  if (!simpsonsParadox?.available || flags.length === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Simpson's Paradox Check</h3>
            <p className="dim-sub">Whether any relationship reverses when split by a category</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {simpsonsParadox?.note || 'No reversed relationships found — the correlations in this dataset hold up within every subgroup checked.'}
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Simpson's Paradox Check</h3>
          <p className="dim-sub">{flags.length} relationship{flags.length > 1 ? 's' : ''} that reverse when split by a category</p>
        </div>
      </div>

      <div className="insights-list">
        {flags.map((f, i) => (
          <div key={i} className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: 'var(--chart-4)' }}>{f.col1} × {f.col2} by {f.dimension}</span>
              <span className="insight-rank mono">overall r={f.overall_r}</span>
            </div>
            <p className="insight-text" style={{ marginBottom: 0 }}>{f.summary}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
