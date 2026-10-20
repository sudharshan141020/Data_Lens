import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { buildWaterfall, formatChange, shareText, pickComparison, pickDimension } from '../driverUtils';

const KIND_COLOR = { up: 'var(--teal)', down: 'var(--red)', total: 'var(--text-muted)' };

function StepTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label mono">{d.fullName}</p>
      <p className="tooltip-value">{formatChange(d.change)}</p>
    </div>
  );
}

function Header({ tickNum }) {
  return (
    <div className="panel-head">
      {tickNum && <span className="tick">{tickNum}</span>}
      <div>
        <h3>Why Did It Change?</h3>
        <p className="dim-sub">Where the movement landed, split by each category</p>
      </div>
    </div>
  );
}

// Splits a change by dimension so "sales fell" becomes "70% of that is
// Region=West, mostly Furniture". Plain arithmetic from the backend
// (app/drivers.py): the bars add up exactly to the net change. It shows where
// the change landed, not what caused it.
export default function DriversPanel({ drivers, tickNum }) {
  const [compId, setCompId] = useState(null);
  const [dimName, setDimName] = useState(null);

  if (!drivers?.available || !drivers.comparisons?.length) {
    return (
      <div className="panel">
        <Header tickNum={tickNum} />
        <p className="dim-sub" style={{ padding: '4px 0 16px' }}>
          {drivers?.note || 'Needs a date column, a measure and at least one category column to split a change.'}
        </p>
      </div>
    );
  }

  const comparison = pickComparison(drivers, compId);
  const dim = pickDimension(comparison, dimName);
  const steps = buildWaterfall(dim);
  const net = comparison.change;
  const up = net >= 0;
  const isBest = dim.dimension === comparison.best_dimension;

  return (
    <div className="panel">
      <Header tickNum={tickNum} />

      {drivers.comparisons.length > 1 && (
        <div className="explorer-tabs" role="tablist" aria-label="Comparison">
          {drivers.comparisons.map((c) => (
            <button
              key={c.id}
              role="tab"
              aria-selected={c.id === comparison.id}
              className={`explorer-tab ${c.id === comparison.id ? 'active' : ''}`}
              onClick={() => { setCompId(c.id); setDimName(null); }}
            >
              {c.title}
            </button>
          ))}
        </div>
      )}

      <div className="insights-list" style={{ marginTop: 12 }}>
        <div className="insight-card">
          <div className="insight-top">
            <span className="insight-type" style={{ color: up ? 'var(--teal)' : 'var(--red)' }}>
              {up ? '▲' : '▼'} {formatChange(net)}{comparison.change_pct != null ? ` (${comparison.change_pct > 0 ? '+' : ''}${comparison.change_pct}%)` : ''}
            </span>
            <span className="insight-rank mono">{comparison.before.label} → {comparison.after.label}</span>
          </div>
          <p className="insight-text" style={{ marginBottom: 0 }}>{comparison.headline}</p>
        </div>
      </div>

      <div className="explorer-tabs" role="tablist" aria-label="Split by" style={{ marginTop: 14 }}>
        {comparison.dimensions.map((d) => (
          <button
            key={d.dimension}
            role="tab"
            aria-selected={d.dimension === dim.dimension}
            className={`explorer-tab ${d.dimension === dim.dimension ? 'active' : ''}`}
            onClick={() => setDimName(d.dimension)}
          >
            {d.dimension}{d.dimension === comparison.best_dimension ? ' ★' : ''}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 12 }} role="img" aria-label={`Waterfall of the change in ${drivers.metric} split by ${dim.dimension}`}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={steps} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--border-soft)" vertical={false} />
            <XAxis dataKey="name" stroke="var(--text-faint)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} axisLine={{ stroke: 'var(--border)' }} interval={0} />
            <YAxis stroke="var(--text-faint)" fontSize={12} fontFamily="var(--font-mono)" tickLine={false} axisLine={false} tickFormatter={(v) => formatChange(v, { signed: false })} />
            <Tooltip content={<StepTooltip />} cursor={{ fill: 'var(--surface-raised)' }} />
            <ReferenceLine y={0} stroke="var(--border)" />
            <Bar dataKey="range" isAnimationActive={false}>
              {steps.map((s, i) => <Cell key={i} fill={KIND_COLOR[s.kind]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ marginTop: 10, display: 'grid', rowGap: 8 }}>
        {dim.segments.map((s) => (
          <div key={s.segment} className="dq-bar-row" style={{ gridTemplateColumns: '120px 1fr max-content' }}>
            <span className="dq-bar-label mono" title={s.segment}>{s.segment}</span>
            <div className="dq-bar-track">
              <div className="dq-bar-fill" style={{ width: `${Math.min(100, s.share_of_movement_pct)}%`, background: s.change >= 0 ? 'var(--teal)' : 'var(--red)' }} />
            </div>
            <span className="dq-bar-value mono" style={{ whiteSpace: 'nowrap' }}>{formatChange(s.change)} · {shareText(s)}</span>
          </div>
        ))}
        {dim.other && (
          <p className="dim-sub" style={{ marginTop: 6 }}>
            {dim.other.count} smaller {dim.dimension} values together: {formatChange(dim.other.change)}
          </p>
        )}
      </div>

      {dim.offsetting && (
        <p className="dim-sub" style={{ marginTop: 10 }}>
          The net change is small next to the movement underneath it, so shares are shown against the total movement rather than against the net.
        </p>
      )}
      {!isBest && (
        <p className="dim-sub" style={{ marginTop: 10 }}>
          {comparison.best_dimension} (★) is the split that concentrates the change most.
        </p>
      )}
      {comparison.id === 'break' && drivers.seasonally_adjusted_break && (
        <p className="dim-sub" style={{ marginTop: 10 }}>
          The break above was found on a seasonally adjusted series; these figures are raw, so percentages can differ slightly.
        </p>
      )}
      <p className="dim-sub" style={{ marginTop: 10 }}>
        This shows where the change landed, not why it happened. Check what changed in the biggest segment (a price or policy change, one large account, a data issue).
      </p>
    </div>
  );
}
