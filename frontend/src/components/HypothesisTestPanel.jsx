import { useId, useMemo, useRef, useState } from 'react';
import { runHypothesisTest } from '../api';
import {
  levelCounts, groupColumnOptions, outcomeOptions, isProportionOutcome, positiveLevelOptions,
  defaultSelection, buildPayload, selectionKey, formatP, formatNumber, formatPercent, signed, intervalGeometry,
} from '../hypothesisUtils';

function IntervalBar({ interval, estimate, label, fmt }) {
  const g = intervalGeometry(interval[0], interval[1], estimate);
  const color = g.crossesZero ? 'var(--text-muted)' : 'var(--teal)';
  const aria = `${label}: ${signed(estimate, fmt)}, interval ${signed(interval[0], fmt)} to ${signed(interval[1], fmt)}${g.crossesZero ? ', includes zero' : ', does not include zero'}`;
  // Plain positioned elements rather than an SVG: a non-uniformly scaled SVG
  // turns the point estimate into an ellipse, and zero has to stay clearly visible.
  return (
    <figure style={{ margin: '14px 0 0' }}>
      <div role="img" aria-label={aria} style={{ position: 'relative', height: 34, margin: '0 10px' }}>
        <div aria-hidden="true" style={{ position: 'absolute', left: `${g.zero}%`, top: 0, bottom: 14, borderLeft: '2px dashed var(--text-muted)' }} />
        <span aria-hidden="true" className="mono" style={{ position: 'absolute', left: `${g.zero}%`, bottom: 0, transform: 'translateX(-50%)', fontSize: 11, color: 'var(--text-muted)' }}>0</span>
        <div aria-hidden="true" style={{ position: 'absolute', left: `${g.low}%`, width: `${Math.max(g.high - g.low, 0.5)}%`, top: 8, height: 6, borderRadius: 3, background: color }} />
        <div aria-hidden="true" style={{ position: 'absolute', left: `${g.estimate}%`, top: 4, width: 14, height: 14, borderRadius: '50%', background: color, border: '2px solid var(--surface)', transform: 'translateX(-50%)' }} />
      </div>
      <figcaption className="dim-sub" style={{ marginTop: 6 }}>
        {label}: <span className="mono">{signed(estimate, fmt)}</span> (95% interval <span className="mono">{signed(interval[0], fmt)}</span> to <span className="mono">{signed(interval[1], fmt)}</span>).
        {' '}{g.crossesZero ? 'The interval includes zero.' : 'The interval does not include zero.'}
      </figcaption>
    </figure>
  );
}

function Result({ result }) {
  const isNumeric = result.kind === 'numeric';
  const fmtDiff = result.rate ? (v) => `${(Math.abs(v) * 100).toFixed(1)} pts` : formatNumber;
  const rows = Object.entries(result.stats);

  return (
    <div style={{ marginTop: 16 }}>
      <div className="insights-list">
        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: result.significant ? 'var(--teal)' : 'var(--text-muted)' }}>
              {result.significant ? 'Likely a real difference' : 'No clear difference'}
            </span>
            <span className="insight-rank mono">{result.test.name}</span>
          </div>
          <p className="insight-text" style={{ marginBottom: 0 }}>{result.headline}</p>
        </div>
      </div>

      {result.interval && (
        <IntervalBar interval={result.interval} estimate={result.difference} label={result.statistic_label} fmt={fmtDiff} />
      )}

      <table className="dim-sub" style={{ width: '100%', marginTop: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th scope="col">Group</th>
            <th scope="col">Rows</th>
            {isNumeric && <th scope="col">Average</th>}
            {isNumeric && <th scope="col">Median</th>}
            {!isNumeric && result.rate && <th scope="col">Rate of {result.positive_level}</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, s]) => (
            <tr key={name}>
              <th scope="row" style={{ textAlign: 'left', fontWeight: 'normal' }}>{name}{name === result.group_a ? ' (A)' : ' (B)'}</th>
              <td className="mono">{s.n.toLocaleString('en-US')}</td>
              {isNumeric && <td className="mono">{formatNumber(s.mean)}</td>}
              {isNumeric && <td className="mono">{formatNumber(s.median)}</td>}
              {!isNumeric && result.rate && <td className="mono">{formatPercent(result.rate[name])}</td>}
            </tr>
          ))}
        </tbody>
      </table>

      <p className="dim-sub" style={{ marginTop: 12 }}>
        <strong>{formatP(result.p_value)}</strong>
        {' · '}{result.effect_size.name}: <span className="mono">{signed(result.effect_size.value, (v) => v.toFixed(2))}</span> ({result.effect_size.label})
        {result.relative_risk != null && <> · relative risk <span className="mono">{result.relative_risk.toFixed(2)}</span></>}
      </p>
      {result.cross_check && (
        <p className="dim-sub" style={{ marginTop: 4 }}>
          Cross-check with {result.cross_check.test}: {formatP(result.cross_check.p_value)}
          {result.cross_check.agrees ? ' — same conclusion.' : ' — a different conclusion.'}
        </p>
      )}
      {result.interval_method && <p className="dim-sub" style={{ marginTop: 4 }}>Interval: {result.interval_method}.</p>}
      <p className="dim-sub" style={{ marginTop: 4 }}><strong>Why this test:</strong> {result.test.why}</p>

      <details style={{ marginTop: 8 }}>
        <summary className="dim-sub" style={{ cursor: 'pointer' }}>Things to keep in mind ({result.caveats.length})</summary>
        <ul className="dim-sub" style={{ margin: '8px 0 0', paddingLeft: 20 }}>
          {result.caveats.map((c) => <li key={c} style={{ marginBottom: 4 }}>{c}</li>)}
        </ul>
      </details>
    </div>
  );
}

// A directed question: "is B different from A on this outcome?". Everything
// else in the dashboard is discovery; this answers the question someone
// actually walks in with. It runs only when asked (never as you change a
// dropdown), on exactly the rows the dashboard is showing, so the filters
// apply, and it shows an answer only while that answer still matches the
// question on screen.
export default function HypothesisTestPanel({ filterableData, rows, tickNum }) {
  const uid = useId();
  const [picked, setPicked] = useState({});
  const [state, setState] = useState({ status: 'idle', key: null, result: null, error: null });
  const runId = useRef(0);

  const defaults = useMemo(() => defaultSelection(filterableData, rows), [filterableData, rows]);
  const groupColumns = useMemo(() => groupColumnOptions(filterableData, rows), [filterableData, rows]);

  // State holds only what was explicitly picked; what is used is derived and
  // validated against the data in front of us, so switching datasets or
  // filters can never leave a stale or impossible selection behind.
  const groupColumn = groupColumns.includes(picked.groupColumn) ? picked.groupColumn : defaults?.groupColumn;
  const levels = useMemo(() => (groupColumn ? levelCounts(rows, groupColumn) : []), [rows, groupColumn]);
  const levelNames = levels.map((l) => l.level);
  const sameGroupPick = picked.groupColumn === groupColumn;
  const a = sameGroupPick && levelNames.includes(picked.a) ? picked.a : levelNames[0];
  const bCandidate = sameGroupPick && levelNames.includes(picked.b) ? picked.b : levelNames.find((l) => l !== a);
  const b = bCandidate && bCandidate !== a ? bCandidate : levelNames.find((l) => l !== a);

  const outcomes = useMemo(() => outcomeOptions(filterableData, groupColumn), [filterableData, groupColumn]);
  const outcome = outcomes.find((o) => o.column === picked.outcomeColumn) || outcomes[0];
  const proportion = useMemo(() => isProportionOutcome(outcome, rows), [outcome, rows]);
  const positives = useMemo(() => (proportion && outcome ? positiveLevelOptions(rows, outcome.column) : []), [proportion, outcome, rows]);
  const positive = positives.some((p) => p.level === picked.positive) ? picked.positive : '';

  if (!filterableData?.available || !defaults || !groupColumn || !outcome || !a || !b) return null;

  const sel = { groupColumn, a, b, outcomeColumn: outcome.column, positive };
  const key = selectionKey(sel, rows.length);
  const isCurrent = state.key === key;

  const set = (patch) => setPicked((prev) => ({ ...prev, ...patch }));

  const run = async () => {
    const payload = buildPayload(rows, sel, outcome);
    const id = ++runId.current;
    setState({ status: 'running', key, result: null, error: null });
    try {
      const result = await runHypothesisTest(payload);
      if (id === runId.current) setState({ status: 'done', key, result, error: null });
    } catch (err) {
      if (id === runId.current) setState({ status: 'error', key, result: null, error: err.message || 'The test could not be run.' });
    }
  };

  const level = (name) => levels.find((l) => l.level === name);

  return (
    <div className="panel">
      <div className="panel-head">
        {tickNum && <span className="tick">{tickNum}</span>}
        <div>
          <h3>Test a Hypothesis</h3>
          <p className="dim-sub">Ask a direct question: is one group different from another? Picks the right test and explains the result</p>
        </div>
      </div>

      <div className="query-builder-controls">
        <div className="query-builder-field">
          <label htmlFor={`${uid}-group`}>Compare groups in</label>
          <select id={`${uid}-group`} className="query-builder-select" value={groupColumn} onChange={(e) => set({ groupColumn: e.target.value, a: undefined, b: undefined, outcomeColumn: undefined, positive: '' })}>
            {groupColumns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="query-builder-field">
          <label htmlFor={`${uid}-a`}>Group A (baseline)</label>
          <select id={`${uid}-a`} className="query-builder-select" value={a} onChange={(e) => set({ groupColumn, a: e.target.value, b })}>
            {levels.filter((l) => l.level !== b).map((l) => <option key={l.level} value={l.level}>{l.level} ({l.n.toLocaleString('en-US')})</option>)}
          </select>
        </div>
        <div className="query-builder-field">
          <label htmlFor={`${uid}-b`}>Group B (compared with A)</label>
          <select id={`${uid}-b`} className="query-builder-select" value={b} onChange={(e) => set({ groupColumn, a, b: e.target.value })}>
            {levels.filter((l) => l.level !== a).map((l) => <option key={l.level} value={l.level}>{l.level} ({l.n.toLocaleString('en-US')})</option>)}
          </select>
        </div>
        <div className="query-builder-field">
          <label htmlFor={`${uid}-outcome`}>On the outcome</label>
          <select id={`${uid}-outcome`} className="query-builder-select" value={outcome.column} onChange={(e) => set({ outcomeColumn: e.target.value, positive: '' })}>
            {outcomes.map((o) => <option key={o.column} value={o.column}>{o.column}</option>)}
          </select>
        </div>
        {positives.length > 0 && (
          <div className="query-builder-field">
            <label htmlFor={`${uid}-positive`}>Rate of</label>
            <select id={`${uid}-positive`} className="query-builder-select" value={positive} onChange={(e) => set({ positive: e.target.value })}>
              <option value="">{positives.length === 2 ? `${positives[positives.length - 1].level} (default)` : 'compare the whole mix'}</option>
              {positives.map((p) => <option key={p.level} value={p.level}>{p.level}</option>)}
            </select>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={run}
          disabled={state.status === 'running' && isCurrent}
          style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: 'var(--teal)', color: 'var(--on-accent)', cursor: 'pointer' }}
        >
          {state.status === 'running' && isCurrent ? 'Testing…' : 'Run test'}
        </button>
        <span className="dim-sub">
          Uses {rows.length.toLocaleString('en-US')} row{rows.length !== 1 ? 's' : ''}{' '}
          ({level(a)?.n.toLocaleString('en-US')} in {a}, {level(b)?.n.toLocaleString('en-US')} in {b})
        </span>
      </div>

      <div aria-live="polite">
        {isCurrent && state.status === 'error' && <p className="dim-sub" role="alert" style={{ marginTop: 12 }}>{state.error}</p>}
        {isCurrent && state.status === 'done' && state.result && !state.result.available && (
          <p className="dim-sub" style={{ marginTop: 12 }}>{state.result.note}</p>
        )}
        {isCurrent && state.status === 'done' && state.result?.available && <Result result={state.result} />}
        {!isCurrent && state.status !== 'idle' && state.status !== 'running' && (
          <p className="dim-sub" style={{ marginTop: 12 }}>You changed the question or the filters — run the test again for an answer that matches.</p>
        )}
      </div>
    </div>
  );
}
