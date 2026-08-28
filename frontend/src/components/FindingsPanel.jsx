const CATEGORY_META = {
  summary: { label: 'Summary', color: 'var(--teal)' },
  trend: { label: 'Trend', color: 'var(--teal)' },
  correlation: { label: 'Correlation', color: 'var(--amber)' },
  top_segment: { label: 'Top segment', color: 'var(--amber)' },
};

export default function FindingsPanel({ findings, tickNum }) {
  if (!findings?.length) return null;
  const maxScore = Math.max(...findings.map((f) => f.score), 1);

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Findings</h3>
          <p className="dim-sub">Statistically-grounded observations about this dataset</p>
        </div>
      </div>

      <div className="insights-list">
        {findings.map((f, i) => {
          const meta = CATEGORY_META[f.category] || { label: f.category, color: 'var(--text-muted)' };
          const barWidth = Math.max(8, (f.score / maxScore) * 100);
          return (
            <div key={i} id={`search-finding-${i}`} className="insight-card">
              <div className="insight-top">
                <span className="insight-type" style={{ color: meta.color }}>{meta.label}</span>
              </div>
              <p className="insight-text">{f.text}</p>
              <div className="signal-track">
                <div className="signal-fill" style={{ width: `${barWidth}%`, background: meta.color }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
