// Recharts' built-in <Legend> colors each item's label text to match that
// item's own swatch color (entry.color) — great for a chart with a couple
// of bright accent lines, unusable for anything using the muted multi-hue
// PALETTE (a pie/donut with 6+ slices, grouped scatter colors, etc.): half
// those colors are too low-contrast against a dark background to read as
// text, even though they work fine as a small swatch square. This renders
// the swatch in the segment's own color but keeps the label text itself in
// the theme's regular readable color, in both light and dark mode.
export default function ReadableLegend({ payload }) {
  if (!payload?.length) return null;
  return (
    <ul
      style={{
        display: 'flex', flexWrap: 'wrap', justifyContent: 'center',
        gap: '6px 16px', listStyle: 'none', margin: 0, padding: 0,
        fontSize: 12, fontFamily: 'var(--font-body)',
      }}
    >
      {payload.map((entry, i) => (
        <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: entry.color, display: 'inline-block', flexShrink: 0 }} />
          <span style={{ color: 'var(--text)' }}>{entry.value}</span>
        </li>
      ))}
    </ul>
  );
}
