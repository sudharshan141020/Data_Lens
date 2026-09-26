import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import ReadableLegend from './ReadableLegend';

const CURRENCY_HINTS = ['sale', 'revenue', 'price', 'cost', 'amount', 'fare', 'profit', 'value', 'income', 'pay', 'earning'];
function looksLikeCurrency(name) {
  if (!name) return false;
  const n = name.toLowerCase();
  return CURRENCY_HINTS.some((k) => n.includes(k));
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label mono">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="mono" style={{ color: p.color }}>
          {p.name}: {looksLikeCurrency(p.name) ? '$' : ''}{p.value.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </p>
      ))}
    </div>
  );
}

export default function TrendChart({ data, mapping = {} }) {
  if (!data?.length) return null;
  const hasProfit = data[0].profit !== undefined;
  const metricName = mapping.revenue || 'Value';
  const profitName = mapping.profit || 'Profit';

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick">03</span>
        <h3>{metricName} over time</h3>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--border-soft)" vertical={false} />
          <XAxis dataKey="month" stroke="var(--text-faint)" fontSize={12} fontFamily="var(--font-mono)" tickLine={false} axisLine={{ stroke: 'var(--border)' }} />
          <YAxis stroke="var(--text-faint)" fontSize={12} fontFamily="var(--font-mono)" tickLine={false} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--border)' }} />
          <Legend content={<ReadableLegend />} />
          <Line type="monotone" dataKey="revenue" name={metricName} stroke="var(--teal)" strokeWidth={2} dot={false} />
          {hasProfit && (
            <Line type="monotone" dataKey="profit" name={profitName} stroke="var(--amber)" strokeWidth={2} dot={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
