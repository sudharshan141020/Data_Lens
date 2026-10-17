import { KPI_VERDICT, CORR_VERDICT, TONE_COLOR, verdictInfo, formatNum, formatR, sortByMateriality } from '../robustnessUtils';

function Header() {
  return (
    <div className="panel-head">
      <div>
        <h3>Does This Hold Without the Outliers?</h3>
        <p className="dim-sub">The headline numbers and top correlations, re-run with extreme rows set aside</p>
      </div>
    </div>
  );
}

function Badge({ info }) {
  return <span className="insight-type" style={{ color: TONE_COLOR[info.tone] }}>{info.label}</span>;
}

// A different question from "How Precise Are These Numbers?": that one asks
// whether a result could be sampling noise; this asks whether it is really
// about a handful of extreme rows. Resampling the same rows would reproduce
// an outlier-driven result every time, so a confidence interval can't see it.
export default function RobustnessPanel({ robustness, tickNum }) {
  if (!robustness?.available) {
    return (
      <div className="panel">
        <Header />
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {robustness?.note || 'Needs a numeric measure with enough data to test.'}
        </p>
      </div>
    );
  }

  const { overall, kpis, correlations, method } = robustness;
  const sensitive = overall.verdict === 'sensitive';
  const orderedKpis = sortByMateriality(kpis);
  const orderedCorrs = sortByMateriality(correlations);

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>Does This Hold Without the Outliers?</h3>
          <p className="dim-sub">The headline numbers and top correlations, re-run with extreme rows set aside</p>
        </div>
      </div>

      <div className="insights-list">
        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: sensitive ? 'var(--amber)' : 'var(--teal)' }}>
              {sensitive ? '⚠ Sensitive to extreme rows' : '✓ Robust'}
            </span>
          </div>
          <p className="insight-text" style={{ marginBottom: 0 }}>{overall.headline}</p>
        </div>
      </div>

      <h4 style={{ margin: '16px 0 8px' }}>Headline numbers</h4>
      <div className="insights-list">
        {orderedKpis.map((k) => (
          <div key={k.measure} className="insight-card">
            <div className="insight-top">
              <span className="insight-type" style={{ color: 'inherit' }}>{k.measure} <span className="dim-sub">({k.aggregation === 'avg' ? 'average' : 'total'})</span></span>
              <Badge info={verdictInfo(KPI_VERDICT, k.verdict)} />
            </div>
            <p className="insight-text" style={{ marginBottom: 4 }}>
              {formatNum(k.full)}
              {k.n_flagged > 0 && k.verdict !== 'no_spread' && <> → {formatNum(k.trimmed)} <span className="dim-sub">without {k.n_flagged} extreme row{k.n_flagged !== 1 ? 's' : ''}</span></>}
            </p>
            <p className="dim-sub" style={{ margin: 0 }}>{k.note}</p>
          </div>
        ))}
      </div>

      {orderedCorrs.length > 0 && (
        <>
          <h4 style={{ margin: '16px 0 8px' }}>Top correlations</h4>
          <div className="insights-list">
            {orderedCorrs.map((c) => (
              <div key={`${c.col1}|${c.col2}`} className="insight-card">
                <div className="insight-top">
                  <span className="insight-type" style={{ color: 'inherit' }}>{c.col1} × {c.col2}</span>
                  <Badge info={verdictInfo(CORR_VERDICT, c.verdict)} />
                </div>
                <p className="insight-text mono" style={{ marginBottom: 4 }}>
                  r {formatR(c.r_full)}{c.r_trimmed !== null && c.n_removed > 0 && <> → {formatR(c.r_trimmed)}</>}
                  <span className="dim-sub"> ({c.n_removed > 0 ? `${c.n_removed} row${c.n_removed !== 1 ? 's' : ''} set aside` : 'no extreme rows'})</span>
                </p>
                <p className="dim-sub" style={{ margin: 0 }}>{c.note}</p>
              </div>
            ))}
          </div>
        </>
      )}

      <p className="dim-sub" style={{ marginTop: 12 }}>{method}</p>
      <p className="dim-sub" style={{ marginTop: 6 }}>
        Extreme rows are not errors, and they are often the most important rows in the data. This only shows whether the story depends on them.
      </p>
    </div>
  );
}
