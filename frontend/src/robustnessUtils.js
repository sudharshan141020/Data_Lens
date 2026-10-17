// Presentation helpers for the "Does this hold without the outliers?" panel.
// The judgement itself (what counts as extreme, what is material) lives in
// app/robustness.py; this only decides how a verdict is worded and coloured.

export const KPI_VERDICT = {
  stable: { label: 'Holds', tone: 'ok' },
  sensitive: { label: 'Moves', tone: 'warn' },
  concentrated: { label: 'Concentrated', tone: 'warn' },
  skewed: { label: 'Skewed', tone: 'info' },
  no_spread: { label: 'No spread', tone: 'info' },
};

export const CORR_VERDICT = {
  holds: { label: 'Holds', tone: 'ok' },
  weakens: { label: 'Weakens', tone: 'warn' },
  strengthens: { label: 'Strengthens', tone: 'warn' },
  lost_significance: { label: 'No longer significant', tone: 'warn' },
  flips: { label: 'Reverses', tone: 'bad' },
  insufficient: { label: 'Unclear', tone: 'info' },
};

export const TONE_COLOR = {
  ok: 'var(--teal)',
  warn: 'var(--amber)',
  bad: 'var(--red)',
  info: 'var(--text-muted)',
};

export function verdictInfo(table, key) {
  return table[key] || { label: String(key || 'n/a'), tone: 'info' };
}

export function formatNum(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

export function formatR(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  const s = Math.abs(v).toFixed(2);
  return v < 0 ? `\u2212${s}` : `+${s}`;
}

// Material findings first, so the problems are not buried under the passes.
export function sortByMateriality(items) {
  return [...items].sort((a, b) => Number(b.material) - Number(a.material));
}
