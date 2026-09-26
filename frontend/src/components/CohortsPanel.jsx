export default function CohortsPanel({ cohorts, tickNum }) {
  const atRisk = cohorts?.at_risk;
  const hasCurve = cohorts?.available;
  const hasRisk = atRisk?.available;

  if (!hasCurve && !hasRisk) {
    return (
      <div className="panel">
        <div className="panel-head">
          {tickNum && <span className="tick">{tickNum}</span>}
          <div>
            <h3>Retention</h3>
            <p className="dim-sub">Whether the same entities keep coming back</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {cohorts?.note || atRisk?.note || 'Needs an identifiable customer/entity ID and a date column to track repeat activity.'}
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>Retention</h3>
          <p className="dim-sub">
            {hasCurve ? `${cohorts.cohort_count} ${cohorts.entity_noun.toLowerCase()} cohorts tracked` : 'Who\u2019s overdue to return'}
          </p>
        </div>
      </div>

      <div className="insights-list">
        {hasCurve && (
          <div className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: 'var(--teal)' }}>Month 1 Retention</span>
              <span className="insight-rank mono">{cohorts.avg_month1_retention_pct != null ? `${cohorts.avg_month1_retention_pct}%` : 'n/a'}</span>
            </div>
            <p className="insight-text" style={{ marginBottom: 0 }}>{cohorts.summary}</p>
          </div>
        )}

        {hasCurve && cohorts.cohort_sizes.map((c) => (
          <div key={c.cohort} className="dq-bar-row">
            <span className="dq-bar-label mono">{c.cohort}</span>
            <div className="dq-bar-track">
              <div className="dq-bar-fill" style={{ width: '100%', background: 'var(--border-soft)' }} />
            </div>
            <span className="dq-bar-value mono">{c.size} {cohorts.entity_noun.toLowerCase()}s</span>
          </div>
        ))}

        {hasRisk && (
          <div className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: atRisk.at_risk_count > 0 ? 'var(--chart-4)' : 'var(--teal)' }}>
                At Risk of Lapsing
              </span>
              <span className="insight-rank mono">
                {atRisk.at_risk_count} / {atRisk.total_entities}
              </span>
            </div>
            <p className="insight-text" style={{ marginBottom: atRisk.at_risk.length ? 8 : 0 }}>{atRisk.summary}</p>

            {atRisk.at_risk.length > 0 && (
              <div className="corr-list">
                {atRisk.at_risk.slice(0, 8).map((r, i) => (
                  <div key={i} className="corr-list-row">
                    <div className="corr-list-main">
                      <span className="corr-list-pair">{r.entity}</span>
                      <span className="corr-list-caveat">
                        last seen {r.last_seen} — {r.days_since_last_seen} days ago
                        {r.risk_level === 'high' ? ' (likely lost)' : ' (worth a check-in)'}
                      </span>
                    </div>
                    <div className="corr-list-stats">
                      <span
                        className="mono"
                        style={{ fontSize: 11, color: r.risk_level === 'high' ? 'var(--red)' : 'var(--amber)' }}
                      >
                        {r.risk_level}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
