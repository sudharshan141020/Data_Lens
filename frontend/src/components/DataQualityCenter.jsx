function ScoreRing({ score }) {
  const color = score >= 85 ? 'var(--teal)' : score >= 60 ? 'var(--amber)' : 'var(--red)';
  return (
    <div className="dq-score">
      <span className="dq-score-value mono" style={{ color }}>{score}</span>
      <span className="dq-score-label">Quality Score</span>
    </div>
  );
}

export default function DataQualityCenter({ dataQuality, tickNum }) {
  const dq = dataQuality;
  const hasIssues = dq.missing_by_column.length || dq.duplicate_row_count > 0
    || dq.constant_columns.length || dq.outlier_summary.length;

  const hasUsableSplit = dq.total_column_count > 0 && dq.usable_column_count < dq.total_column_count;

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>Data Quality</h3>
          <p className="dim-sub">Structural health of this dataset</p>
        </div>
      </div>

      <div className="dq-layout">
        <div className="dq-score-col">
          <ScoreRing score={dq.overall_quality_score} />
          {hasUsableSplit && (
            <p className="dq-usable-note">
              Scored across all {dq.total_column_count} columns in the file. Only{' '}
              {dq.usable_column_count} had enough real data to actually analyze —
              those score <span className="mono" style={{ color: 'var(--text)' }}>{dq.usable_quality_score}</span>.
            </p>
          )}
        </div>

        <div className="dq-details">
          {dq.missing_by_column.length > 0 && (
            <div className="dq-block">
              <span className="dq-block-title">Missing values</span>
              {dq.missing_by_column.map((m) => (
                <div key={m.column} className="dq-bar-row">
                  <span className="dq-bar-label mono">{m.column}</span>
                  <div className="dq-bar-track">
                    <div className="dq-bar-fill" style={{ width: `${m.missing_pct}%`, background: 'var(--red)' }} />
                  </div>
                  <span className="dq-bar-value mono">{m.missing_pct}%</span>
                </div>
              ))}
            </div>
          )}

          {dq.outlier_summary.length > 0 && (
            <div className="dq-block">
              <span className="dq-block-title">Outliers by measure</span>
              {dq.outlier_summary.map((o) => (
                <div key={o.column} className="dq-bar-row">
                  <span className="dq-bar-label mono">{o.column}</span>
                  <div className="dq-bar-track">
                    <div className="dq-bar-fill" style={{ width: `${Math.min(o.outlier_pct * 3, 100)}%`, background: 'var(--amber)' }} />
                  </div>
                  <span className="dq-bar-value mono">{o.outlier_count} ({o.outlier_pct}%)</span>
                </div>
              ))}
            </div>
          )}

          <div className="dq-chips-row">
            {dq.duplicate_row_count > 0 && (
              <span className="dq-chip dq-chip-warn">{dq.duplicate_row_count} duplicate rows ({dq.duplicate_row_pct}%)</span>
            )}
            {dq.constant_columns.map((c) => (
              <span key={c} className="dq-chip">Constant: {c}</span>
            ))}
            {dq.high_cardinality_columns.map((c) => (
              <span key={c} className="dq-chip">High cardinality: {c}</span>
            ))}
          </div>

          <div className="dq-dtype-row">
            <span className="dim-sub">
              {dq.dtype_breakdown.numeric} numeric · {dq.dtype_breakdown.categorical} categorical ·{' '}
              {dq.dtype_breakdown.date} date · {dq.dtype_breakdown.identifier_or_text} identifier/text
            </span>
          </div>

          {!hasIssues && (
            <p className="dim-sub">No structural issues detected — no missing values, duplicates, or constant columns.</p>
          )}
        </div>
      </div>
    </div>
  );
}
