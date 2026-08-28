function formatPValue(p) {
  if (p === null || p === undefined) return null;
  return p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`;
}

function PairCard({ pair, label, tone }) {
  if (!pair) return null;
  return (
    <div className="corr-callout" style={{ borderColor: tone === 'positive' ? 'var(--teal-dim)' : 'var(--red-dim)' }}>
      <span className="corr-callout-label" style={{ color: tone === 'positive' ? 'var(--teal)' : 'var(--red)' }}>
        {label}
      </span>
      <p className="corr-callout-text">{pair.col1} ↔ {pair.col2}</p>
      <div className="corr-callout-stats">
        <span className="corr-callout-r mono">r = {pair.r.toFixed(2)}</span>
        {pair.p_value !== null && pair.p_value !== undefined && (
          <span className="corr-callout-r mono">{formatPValue(pair.p_value)}</span>
        )}
        <span className="corr-callout-r mono">n = {pair.n}</span>
      </div>
      {pair.caveat && <p className="corr-caveat">{pair.caveat}</p>}
    </div>
  );
}

export default function CorrelationCenter({ correlationCenter, tickNum }) {
  const { pairs, strongest_positive, strongest_negative, multicollinearity } = correlationCenter;
  const vifResults = multicollinearity?.results || [];
  const flaggedVif = vifResults.filter((v) => v.severity !== 'ok');

  if (!pairs?.length) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <h3>Correlation Center</h3>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          Not enough numeric measures in this dataset to check for relationships between them.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Correlation Center</h3>
          <p className="dim-sub">Which measures actually move together</p>
        </div>
      </div>

      <div className="corr-callouts">
        <PairCard pair={strongest_positive} label="Strongest positive" tone="positive" />
        <PairCard pair={strongest_negative} label="Strongest negative" tone="negative" />
      </div>

      {pairs.length > 1 && (
        <div className="corr-list">
          <span className="dq-block-title">All notable relationships</span>
          {pairs.map((p, i) => (
            <div key={i} id={`search-correlation-${i}`} className="corr-list-row">
              <div className="corr-list-main">
                <span className="corr-list-pair">{p.col1} ↔ {p.col2}</span>
                {p.caveat && <span className="corr-list-caveat">{p.caveat}</span>}
              </div>
              <div className="corr-list-stats">
                <span className="corr-list-n mono">n={p.n}</span>
                <span className="corr-list-r mono" style={{ color: p.r > 0 ? 'var(--teal)' : 'var(--red)' }}>
                  {p.r.toFixed(2)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {vifResults.length > 0 && (
        <div className="corr-vif">
          <span className="dq-block-title">Redundancy check (multicollinearity)</span>
          <p className="dim-sub" style={{ margin: '2px 0 12px' }}>
            {flaggedVif.length > 0
              ? 'Some measures overlap heavily with the others combined, not just in pairs.'
              : 'Each measure adds independent information — no redundancy detected.'}
          </p>
          {vifResults.map((v, i) => (
            <div key={i} className="corr-vif-row">
              <span className="corr-vif-col">{v.column}</span>
              <span
                className="corr-vif-badge"
                style={{
                  color: v.severity === 'severe' ? 'var(--red)' : v.severity === 'moderate' ? 'var(--amber)' : 'var(--text-faint)',
                  borderColor: v.severity === 'severe' ? 'var(--red-dim)' : v.severity === 'moderate' ? 'var(--amber-dim)' : 'var(--border-soft)',
                }}
              >
                VIF {v.vif.toFixed(1)}
              </span>
              <span className="corr-vif-note">{v.note}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
