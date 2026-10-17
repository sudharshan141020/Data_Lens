import { describe, it, expect } from 'vitest';
import { KPI_VERDICT, CORR_VERDICT, TONE_COLOR, verdictInfo, formatNum, formatR, sortByMateriality } from './robustnessUtils';

describe('verdict tables', () => {
  // These keys are what app/robustness.py emits; a rename there must break here, not silently show raw ids in the UI.
  it('cover every verdict the backend can produce', () => {
    expect(Object.keys(KPI_VERDICT).sort()).toEqual(['concentrated', 'no_spread', 'sensitive', 'skewed', 'stable']);
    expect(Object.keys(CORR_VERDICT).sort()).toEqual(['flips', 'holds', 'insufficient', 'lost_significance', 'strengthens', 'weakens']);
  });
  it('every verdict has a label and a tone that has a colour', () => {
    [...Object.values(KPI_VERDICT), ...Object.values(CORR_VERDICT)].forEach((v) => {
      expect(v.label).toBeTruthy();
      expect(TONE_COLOR[v.tone]).toBeTruthy();
    });
  });
  it('an unknown verdict degrades to a neutral label instead of crashing', () => {
    expect(verdictInfo(KPI_VERDICT, 'brand_new')).toEqual({ label: 'brand_new', tone: 'info' });
    expect(verdictInfo(KPI_VERDICT, undefined).label).toBe('n/a');
  });
  it('a sign reversal is the only "bad" tone', () => {
    const bad = [...Object.entries(CORR_VERDICT), ...Object.entries(KPI_VERDICT)].filter(([, v]) => v.tone === 'bad').map(([k]) => k);
    expect(bad).toEqual(['flips']);
  });
});

describe('formatNum / formatR', () => {
  it('formats numbers and guards missing values', () => {
    expect(formatNum(1234.567)).toBe('1,234.57');
    expect(formatNum(null)).toBe('n/a');
    expect(formatNum(NaN)).toBe('n/a');
  });
  it('signs correlations with a real minus sign', () => {
    expect(formatR(0.842)).toBe('+0.84');
    expect(formatR(-0.4)).toBe('\u22120.40');
    expect(formatR(null)).toBe('n/a');
  });
});

describe('sortByMateriality', () => {
  it('puts material findings first, keeps the order within each group, and does not mutate', () => {
    const items = [{ id: 'a', material: false }, { id: 'b', material: true }, { id: 'c', material: false }, { id: 'd', material: true }];
    const sorted = sortByMateriality(items);
    expect(sorted.map((i) => i.id)).toEqual(['b', 'd', 'a', 'c']);
    expect(items.map((i) => i.id)).toEqual(['a', 'b', 'c', 'd']);
  });
});
