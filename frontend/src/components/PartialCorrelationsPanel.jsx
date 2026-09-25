export default function PartialCorrelationsPanel({ partialCorrelations, tickNum }) {
  const results = partialCorrelations?.results || [];

  if (!partialCorrelations?.available || results.length === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          {tickNum && <span className="tick">{tickNum}</span>}
          <div>
            <h3>Partial Correlations</h3>
            <p className="dim-sub">Whether the top relationships survive once you control for another variable</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {partialCorrelations?.note || 'Not enough correlated pairs or control variables in this dataset to check.'}
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>Partial Correlations</h3>
          <p className="dim-sub">Whether the top relationships survive once you control for another variable</p>
        </div>
      </div>

      <div className="insights-list">
        {results.map((res, i) => {
          const rest = res.explained_by.slice(1);
          return (
            <div key={i} className="insight-card" id={`search-partial-correlation-${i}`}>
              <div className="insight-top">
                <span className="insight-type" style={{ color: res.robust ? 'var(--teal)' : 'var(--chart-4)' }}>
                  {res.col1} ↔ {res.col2}
                </span>
                <span className="insight-rank mono">overall r={res.overall_r}</span>
              </div>
              <p className="insight-text" style={{ marginBottom: rest.length ? 8 : 0 }}>{res.summary}</p>
              {rest.length > 0 && (
                <div className="corr-list">
                  {rest.map((e, j) => (
                    <div key={j} className="corr-list-row">
                      <div className="corr-list-main">
                        <span className="corr-list-pair">controlling for {e.control}</span>
                        <span className="corr-list-caveat">{e.text}</span>
                      </div>
                      <div className="corr-list-stats">
                        <span className="corr-list-r mono">{e.partial_r}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
