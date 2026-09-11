export default function AnomaliesPanel({ anomalies, tickNum }) {
  if (!anomalies?.available) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Anomalies</h3>
            <p className="dim-sub">Rows unusual across multiple measures at once</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {anomalies?.note || 'Needs at least two numeric measures to check for unusual combinations.'}
        </p>
      </div>
    );
  }

  const { anomaly_count, anomaly_pct, measures_used, anomalies: rows } = anomalies;

  if (anomaly_count === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Anomalies</h3>
            <p className="dim-sub">Checked {measures_used.join(', ')}</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>No unusual rows found — everything falls within the normal spread.</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Anomalies</h3>
          <p className="dim-sub">{anomaly_count} rows ({anomaly_pct}%) unusual across {measures_used.join(', ')}</p>
        </div>
      </div>

      <div className="insights-list">
        {rows.map((a) => (
          <div key={a.row_index} className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: 'var(--red)' }}>Row {a.row_index}</span>
              <span className="insight-rank mono">distance {a.distance}</span>
            </div>
            <p className="insight-text" style={{ marginBottom: 0 }}>
              Flagged for {a.why}.
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
