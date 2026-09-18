function formatNum(v) {
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

export default function ConfidenceIntervalsPanel({ confidenceIntervals, tickNum }) {
  if (!confidenceIntervals?.available) {
    return (
      <div className="panel">
        <div className="panel-head">
          {tickNum && <span className="tick">{tickNum}</span>}
          <div>
            <h3>How Precise Are These Numbers?</h3>
            <p className="dim-sub">95% confidence intervals on key metrics</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {confidenceIntervals?.note || 'Needs a numeric measure with enough data to estimate a range.'}
        </p>
      </div>
    );
  }

  const { intervals, note } = confidenceIntervals;

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>How Precise Are These Numbers?</h3>
          <p className="dim-sub">95% confidence intervals — how much each figure might naturally vary</p>
        </div>
      </div>

      <div className="insights-list">
        {intervals.map((i) => (
          <div key={i.measure} className="insight-card">
            <div className="insight-top">
              <span className="insight-type">{i.measure}</span>
              <span className="insight-rank mono">±{i.relative_margin_pct != null ? `${i.relative_margin_pct}%` : 'n/a'}</span>
            </div>
            <p className="insight-text" style={{ marginBottom: 0 }}>
              {formatNum(i.point_estimate)} <span className="dim-sub">(likely between {formatNum(i.ci_low)} and {formatNum(i.ci_high)})</span>
            </p>
          </div>
        ))}
      </div>

      {note && <p className="dim-sub" style={{ marginTop: 10 }}>{note}</p>}
    </div>
  );
}
