// Pure helpers for the "Why did it change?" panel (DriversPanel.jsx).
// Kept out of the component so the waterfall arithmetic is unit-tested
// without rendering a chart (recharts draws nothing in jsdom anyway).

export function formatChange(v, { signed = true } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  const a = Math.abs(v);
  let body;
  if (a >= 1e9) body = `${(a / 1e9).toFixed(1)}B`;
  else if (a >= 1e6) body = `${(a / 1e6).toFixed(1)}M`;
  else if (a >= 1e4) body = `${(a / 1e3).toFixed(1)}K`;
  else if (a >= 100) body = Math.round(a).toLocaleString('en-US');
  else if (a >= 1) body = (Math.round(a * 10) / 10).toString();
  else body = (Math.round(a * 100) / 100).toString();
  if (!signed) return v < 0 ? `-${body}` : body;
  if (v > 0) return `+${body}`;
  if (v < 0) return `\u2212${body}`;
  return body;
}

export function shareText(seg) {
  if (seg.share_of_change_pct !== null && seg.share_of_change_pct !== undefined) {
    return `${seg.share_of_change_pct}% of the change`;
  }
  return `${seg.share_of_movement_pct}% of the movement`;
}

// Floating-bar steps that start at 0 and walk through each segment's change,
// ending in a "Net change" bar from 0. Plotting changes (not before/after
// totals) keeps the steps visible even when the total is huge next to the
// change -- a 40-unit move on a 12,000 base would be an invisible sliver.
export function buildWaterfall(dim) {
  if (!dim?.segments?.length) return [];
  const steps = [];
  let running = 0;
  const push = (name, fullName, change) => {
    const next = running + change;
    steps.push({
      name: name.length > 14 ? `${name.slice(0, 13)}\u2026` : name,
      fullName,
      change,
      range: [Math.min(running, next), Math.max(running, next)],
      kind: change >= 0 ? 'up' : 'down',
    });
    running = next;
  };
  dim.segments.forEach((s) => push(s.segment, s.segment, s.change));
  if (dim.other) push(`Other (${dim.other.count})`, `${dim.other.count} other values`, dim.other.change);
  steps.push({
    name: 'Net change',
    fullName: 'Net change',
    change: running,
    range: [Math.min(0, running), Math.max(0, running)],
    kind: 'total',
  });
  return steps;
}

export function pickComparison(drivers, id) {
  const list = drivers?.comparisons || [];
  return list.find((c) => c.id === id) || list[0] || null;
}

export function pickDimension(comparison, name) {
  const list = comparison?.dimensions || [];
  return list.find((d) => d.dimension === name) || list[0] || null;
}
