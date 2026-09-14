export default function TextAnalysisPanel({ textAnalysis, tickNum }) {
  const checked = (textAnalysis?.results || []).filter((r) => r.checked);

  if (!textAnalysis?.available || checked.length === 0) {
    return (
      <div className="panel">
        <div className="panel-head">
          <span className="tick">{tickNum}</span>
          <div>
            <h3>Text Fields</h3>
            <p className="dim-sub">What shows up most in free-text columns</p>
          </div>
        </div>
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {textAnalysis?.note || (textAnalysis?.results || [])[0]?.note || 'No free-text columns found.'}
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">{tickNum}</span>
        <div>
          <h3>Text Fields</h3>
          <p className="dim-sub">What shows up most in free-text columns</p>
        </div>
      </div>

      {checked.map((r) => {
        const maxCount = r.top_words[0]?.count || 1;
        return (
          <div key={r.column} style={{ marginBottom: 18 }}>
            <p className="dim-sub mono" style={{ marginBottom: 8 }}>
              {r.column} — {r.entry_count} entries, ~{r.avg_word_count} words each
            </p>
            {r.top_words.map((w) => (
              <div key={w.word} className="dq-bar-row">
                <span className="dq-bar-label mono">{w.word}</span>
                <div className="dq-bar-track">
                  <div className="dq-bar-fill" style={{ width: `${100 * w.count / maxCount}%`, background: 'var(--chart-2)' }} />
                </div>
                <span className="dq-bar-value mono">{w.pct_of_entries}%</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
