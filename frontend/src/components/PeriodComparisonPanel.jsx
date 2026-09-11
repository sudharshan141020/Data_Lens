export default function PeriodComparisonPanel({ periodComparison, tickNum }) {
  if (!periodComparison?.available) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Period Comparison</h3>
            <p className="dim-sub">Latest month vs. the one before</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {periodComparison?.note || 'Needs at least two calendar months of data to compare.'}
        </p>
      </div>
    );
  }

  const { period_a, period_b, pct_change, significant, summary } = periodComparison;
  const up = pct_change != null && pct_change >= 0;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Period Comparison</h3>
          <p className="dim-sub">{period_a.label} vs. {period_b.label}</p>
        </div>
      </div>

      <div className="insights-list">
        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: up ? 'var(--teal)' : 'var(--red)' }}>
              {up ? '▲' : '▼'} {pct_change != null ? `${Math.abs(pct_change)}%` : 'n/a'}
            </span>
            <span className="insight-rank mono">{significant ? 'significant' : 'within normal variation'}</span>
          </div>
          <p className="insight-text" style={{ marginBottom: 0 }}>{summary}</p>
        </div>
      </div>
    </div>
  );
}
