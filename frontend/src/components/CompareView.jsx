function formatValue(v) {
  if (typeof v !== 'number') return String(v);
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function humanizeMetric(key) {
  return key.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(' ');
}

export default function CompareView({ data }) {
  const { diff } = data;
  const {
    name_a, name_b, domain_a, domain_b, domain_mismatch,
    row_count_a, row_count_b, data_quality_a, data_quality_b,
    kpi_deltas, correlation_diff,
  } = diff;

  return (
    <div className="dashboard">
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Comparing Two Files</h3>
            <p className="dim-sub mono">{name_a} vs. {name_b}</p>
          </div>
        </div>

        {domain_mismatch && (
          <p className="upload-error" style={{ marginTop: 0 }}>
            These look like different kinds of data ({domain_a} vs. {domain_b}) — the comparison below may not be apples-to-apples.
          </p>
        )}

        <div className="dq-bar-row" style={{ gridTemplateColumns: '140px 1fr 1fr' }}>
          <span className="dq-bar-label mono">Rows</span>
          <span className="mono">{row_count_a.toLocaleString()}</span>
          <span className="mono">{row_count_b.toLocaleString()}</span>
        </div>
        <div className="dq-bar-row" style={{ gridTemplateColumns: '140px 1fr 1fr' }}>
          <span className="dq-bar-label mono">Data quality</span>
          <span className="mono">{Math.round(data_quality_a)}/100</span>
          <span className="mono">{Math.round(data_quality_b)}/100</span>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Key Metric Changes</h3>
            <p className="dim-sub">Sorted by size of change</p>
          </div>
        </div>
        <div className="insights-list">
          {kpi_deltas.length === 0 && <p className="dim-sub">No shared numeric KPIs to compare.</p>}
          {kpi_deltas.map((k) => {
            const up = k.pct_change != null && k.pct_change >= 0;
            return (
              <div key={k.metric} className="insight-card">
                <div className="insight-top">
                  <span className="insight-type">{humanizeMetric(k.metric)}</span>
                  <span className="insight-rank mono" style={{ color: up ? 'var(--teal)' : 'var(--red)' }}>
                    {k.pct_change != null ? `${up ? '▲' : '▼'} ${Math.abs(k.pct_change)}%` : ''}
                  </span>
                </div>
                <p className="insight-text" style={{ marginBottom: 0 }}>
                  {formatValue(k.value_a)} → {formatValue(k.value_b)}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {(correlation_diff.changed.length > 0 || correlation_diff.only_in_a.length > 0 || correlation_diff.only_in_b.length > 0) && (
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Relationship Changes</h3>
              <p className="dim-sub">How correlations between measures shifted</p>
            </div>
          </div>
          <div className="insights-list">
            {correlation_diff.changed.map((c, i) => (
              <div key={i} className="insight-card">
                <div className="insight-top">
                  <span className="insight-type" style={{ color: c.sign_flipped ? 'var(--red)' : 'var(--text-muted)' }}>
                    {c.col1} × {c.col2}
                  </span>
                  <span className="insight-rank mono">r: {c.r_a} → {c.r_b}</span>
                </div>
                {c.sign_flipped && <p className="insight-text" style={{ marginBottom: 0 }}>Relationship reversed direction.</p>}
              </div>
            ))}
            {correlation_diff.only_in_a.map((c, i) => (
              <div key={`a${i}`} className="insight-card">
                <p className="insight-text" style={{ marginBottom: 0 }}>{c.col1} × {c.col2} (r={c.r}) — no longer significant in {name_b}.</p>
              </div>
            ))}
            {correlation_diff.only_in_b.map((c, i) => (
              <div key={`b${i}`} className="insight-card">
                <p className="insight-text" style={{ marginBottom: 0 }}>{c.col1} × {c.col2} (r={c.r}) — new in {name_b}, wasn't significant in {name_a}.</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
