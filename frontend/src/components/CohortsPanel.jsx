export default function CohortsPanel({ cohorts, tickNum }) {
  if (!cohorts?.available) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Retention</h3>
            <p className="dim-sub">Whether the same entities keep coming back</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {cohorts?.note || 'Needs an identifiable customer/entity ID and a date column to track repeat activity.'}
        </p>
      </div>
    );
  }

  const { entity_noun, cohort_count, avg_month1_retention_pct, summary, cohort_sizes } = cohorts;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Retention</h3>
          <p className="dim-sub">{cohort_count} {entity_noun.toLowerCase()} cohorts tracked</p>
        </div>
      </div>

      <div className="insights-list">
        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: 'var(--teal)' }}>Month 1 Retention</span>
            <span className="insight-rank mono">{avg_month1_retention_pct != null ? `${avg_month1_retention_pct}%` : 'n/a'}</span>
          </div>
          <p className="insight-text" style={{ marginBottom: 0 }}>{summary}</p>
        </div>

        {cohort_sizes.map((c) => (
          <div key={c.cohort} className="dq-bar-row">
            <span className="dq-bar-label mono">{c.cohort}</span>
            <div className="dq-bar-track">
              <div className="dq-bar-fill" style={{ width: '100%', background: 'var(--border-soft)' }} />
            </div>
            <span className="dq-bar-value mono">{c.size} {entity_noun.toLowerCase()}s</span>
          </div>
        ))}
      </div>
    </div>
  );
}
