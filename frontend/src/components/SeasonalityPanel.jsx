export default function SeasonalityPanel({ seasonality, tickNum }) {
  if (!seasonality?.available) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Seasonality</h3>
            <p className="dim-sub">Repeating yearly patterns</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {seasonality?.note || 'Needs a trend with enough monthly history to check for a repeating yearly pattern.'}
        </p>
      </div>
    );
  }

  const { summary, seasonal_strength, trend_strength, years_covered, peak_month, trough_month } = seasonality;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Seasonality</h3>
          <p className="dim-sub">{years_covered} years of history · statistically significant yearly pattern</p>
        </div>
      </div>

      <div className="insights-list">
        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: 'var(--chart-3)' }}>Yearly Pattern</span>
          </div>
          <p className="insight-text" style={{ marginBottom: 10 }}>{summary}</p>

          <div className="dq-bar-row">
            <span className="dq-bar-label mono">Seasonal strength</span>
            <div className="dq-bar-track">
              <div className="dq-bar-fill" style={{ width: `${seasonal_strength * 100}%`, background: 'var(--chart-3)' }} />
            </div>
            <span className="dq-bar-value mono">{Math.round(seasonal_strength * 100)}%</span>
          </div>
          <div className="dq-bar-row">
            <span className="dq-bar-label mono">Trend strength</span>
            <div className="dq-bar-track">
              <div className="dq-bar-fill" style={{ width: `${trend_strength * 100}%`, background: 'var(--teal)' }} />
            </div>
            <span className="dq-bar-value mono">{Math.round(trend_strength * 100)}%</span>
          </div>
        </div>

        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: 'var(--teal)' }}>Peak: {peak_month.name}</span>
            <span className="insight-rank mono">{peak_month.pct != null ? `+${peak_month.pct}%` : ''}</span>
          </div>
          <div className="insight-top" style={{ marginBottom: 0 }}>
            <span className="insight-type" style={{ color: 'var(--text-muted)' }}>Trough: {trough_month.name}</span>
            <span className="insight-rank mono">{trough_month.pct != null ? `${trough_month.pct}%` : ''}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
