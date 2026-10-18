// Pure helpers for the "Test a Hypothesis" panel. The statistics themselves
// run on the server (app/hypothesis.py); this only decides what to offer,
// builds the request from the rows the dashboard is already showing, and
// turns numbers into the little interval graphic.

export const MAX_POSITIVE_LEVELS = 10; // matches the backend's MAX_OUTCOME_LEVELS

// Distinct non-empty values of a column with row counts, biggest first
// (ties alphabetical so the order is stable). Values are compared as text,
// the same way the server compares group labels.
export function levelCounts(rows, column) {
  const counts = new Map();
  for (const r of rows || []) {
    const v = r?.[column];
    if (v === null || v === undefined || v === '') continue;
    const k = String(v);
    counts.set(k, (counts.get(k) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([level, n]) => ({ level, n }))
    .sort((a, b) => b.n - a.n || a.level.localeCompare(b.level));
}

// Columns you can split on: dimensions with at least two values in the rows
// currently shown (a column with one value has nothing to compare).
export function groupColumnOptions(filterableData, rows) {
  return (filterableData?.dimension_columns || []).filter((c) => levelCounts(rows, c).length >= 2);
}

// Outcomes: numbers (measures) first, then categories (dimensions).
export function outcomeOptions(filterableData, groupColumn) {
  const measures = (filterableData?.measure_columns || []).map((column) => ({ column, kind: 'measure' }));
  const dims = (filterableData?.dimension_columns || []).map((column) => ({ column, kind: 'dimension' }));
  return [...measures, ...dims].filter((o) => o.column !== groupColumn);
}

// A rate (proportion) outcome is any category column, or a number column that
// only ever takes two values (a 0/1 flag). Mirrors the server's "auto" rule.
export function isProportionOutcome(outcome, rows) {
  if (!outcome) return false;
  if (outcome.kind === 'dimension') return true;
  const numbers = new Set();
  for (const r of rows || []) {
    const v = r?.[outcome.column];
    if (v !== null && v !== undefined && v !== '') {
      numbers.add(v);
      if (numbers.size > 2) return false;
    }
  }
  return numbers.size === 2;
}

export function positiveLevelOptions(rows, column) {
  const levels = levelCounts(rows, column);
  return levels.length <= MAX_POSITIVE_LEVELS ? levels : [];
}

// Sensible first picks so the panel is usable before anything is chosen: the
// first splittable column, its two most common values, the first measure.
export function defaultSelection(filterableData, rows) {
  const groupColumns = groupColumnOptions(filterableData, rows);
  if (!groupColumns.length) return null;
  const groupColumn = groupColumns[0];
  const [a, b] = levelCounts(rows, groupColumn).slice(0, 2).map((l) => l.level);
  const outcomes = outcomeOptions(filterableData, groupColumn);
  if (!outcomes.length) return null;
  return { groupColumn, a, b, outcomeColumn: outcomes[0].column, positive: '' };
}

// Only the two groups' rows, as two parallel arrays -- nothing else leaves the browser.
export function buildPayload(rows, sel, outcome) {
  if (!sel || !outcome || !sel.a || !sel.b) return null;
  const groups = [];
  const outcomes = [];
  for (const r of rows || []) {
    const g = r?.[sel.groupColumn];
    if (g === null || g === undefined || g === '') continue;
    const key = String(g);
    if (key !== sel.a && key !== sel.b) continue;
    const o = r?.[sel.outcomeColumn];
    if (o === null || o === undefined || o === '') continue;
    groups.push(key);
    outcomes.push(o);
  }
  return {
    group_column: sel.groupColumn,
    outcome_column: sel.outcomeColumn,
    group_a: sel.a,
    group_b: sel.b,
    groups,
    outcomes,
    outcome_kind: outcome.kind === 'dimension' ? 'categorical' : 'auto',
    positive_level: sel.positive || null,
  };
}

// A shown result is only valid for the exact question and rows it answered.
export function selectionKey(sel, rowCount) {
  return JSON.stringify([sel?.groupColumn, sel?.a, sel?.b, sel?.outcomeColumn, sel?.positive || '', rowCount]);
}

export function formatP(p) {
  if (p === null || p === undefined || Number.isNaN(p)) return 'n/a';
  return p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`;
}

export function formatNumber(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  const a = Math.abs(v);
  if (a >= 1000) return Math.round(v).toLocaleString('en-US');
  if (a >= 100) return (Math.round(v * 10) / 10).toString();
  if (a >= 1) return (Math.round(v * 100) / 100).toString();
  return Number(v.toPrecision(3)).toString();
}

export function formatPercent(rate) {
  return `${(rate * 100).toFixed(1)}%`;
}

export function signed(v, fmt = formatNumber) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return v >= 0 ? `+${fmt(Math.abs(v))}` : `\u2212${fmt(Math.abs(v))}`;
}

// Where to draw the interval on a 0-100 axis that always includes zero, so
// "does the interval cross zero?" is visible at a glance.
export function intervalGeometry(low, high, estimate) {
  const min = Math.min(low, 0, estimate);
  const max = Math.max(high, 0, estimate);
  const pad = (max - min) * 0.08 || 1;
  const lo = min - pad;
  const span = max + pad - lo;
  const at = (v) => ((v - lo) / span) * 100;
  return { low: at(low), high: at(high), estimate: at(estimate), zero: at(0), crossesZero: low <= 0 && high >= 0 };
}
