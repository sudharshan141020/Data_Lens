// Same PALETTE array as AnalysisChartV2.jsx's ScatterView -- kept local
// rather than shared since neither file currently imports from the other,
// but the order must match so a segment's card color and its scatter-point
// color are the same swatch.
const PALETTE = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)', 'var(--chart-7)', 'var(--chart-8)'];

export default function SegmentsPanel({ segments, tickNum }) {
  if (!segments?.available) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Segments</h3>
            <p className="dim-sub">Natural groups found in the data</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {segments?.note || 'Not enough numeric measures to look for natural groups in this dataset.'}
        </p>
      </div>
    );
  }

  const { clusters, measures_used, k, note } = segments;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Segments</h3>
          <p className="dim-sub">
            {k} natural groups found across {measures_used.join(', ')}
          </p>
        </div>
      </div>

      <div className="insights-list">
        {clusters.map((c, i) => (
          <div key={c.id} id={`search-segment-${i}`} className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: PALETTE[i % PALETTE.length] }}>
                {c.label}
              </span>
              <span className="insight-rank mono">{c.size} rows</span>
            </div>
            <p className="insight-text" style={{ marginBottom: 10 }}>{c.description}</p>
            <div className="dq-bar-row">
              <span className="dq-bar-label mono">Share</span>
              <div className="dq-bar-track">
                <div className="dq-bar-fill" style={{ width: `${c.pct}%`, background: PALETTE[i % PALETTE.length] }} />
              </div>
              <span className="dq-bar-value mono">{c.pct}%</span>
            </div>
          </div>
        ))}
      </div>

      {note && <p className="dim-sub" style={{ marginTop: 10 }}>{note}</p>}
    </div>
  );
}
