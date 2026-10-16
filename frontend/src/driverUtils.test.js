import { describe, it, expect } from 'vitest';
import { buildWaterfall, formatChange, shareText, pickComparison, pickDimension } from './driverUtils';

const seg = (segment, change, extra = {}) => ({ segment, before: 0, after: 0, change, share_of_change_pct: null, share_of_movement_pct: 10, ...extra });

describe('formatChange', () => {
  it.each([
    [0, '0'], [3.456, '+3.5'], [0.054, '+0.05'], [-70, '\u221270'], [1234.5, '+1,235'],
    [-12500, '\u221212.5K'], [3400000, '+3.4M'], [2e9, '+2.0B'],
  ])('%s -> %s', (v, out) => expect(formatChange(v)).toBe(out));

  it('unsigned form (axis ticks) keeps only the minus', () => {
    expect(formatChange(5, { signed: false })).toBe('5');
    expect(formatChange(-5, { signed: false })).toBe('-5');
  });
  it('is safe on missing values', () => {
    expect(formatChange(null)).toBe('n/a');
    expect(formatChange(undefined)).toBe('n/a');
    expect(formatChange(NaN)).toBe('n/a');
  });
});

describe('shareText', () => {
  it('prefers the share of the net change, falls back to share of movement when offsetting', () => {
    expect(shareText(seg('West', -70, { share_of_change_pct: 87.5 }))).toBe('87.5% of the change');
    expect(shareText(seg('West', -70, { share_of_change_pct: null, share_of_movement_pct: 40 }))).toBe('40% of the movement');
  });
});

describe('buildWaterfall', () => {
  it('returns nothing for a missing or empty dimension', () => {
    expect(buildWaterfall(null)).toEqual([]);
    expect(buildWaterfall({ segments: [] })).toEqual([]);
  });

  it('walks cumulatively from zero and ends in a net-change bar that matches the running total', () => {
    const steps = buildWaterfall({ segments: [seg('West', -70), seg('East', -10), seg('North', 5)], other: null });
    expect(steps.map((s) => s.range)).toEqual([[-70, 0], [-80, -70], [-80, -75], [-75, 0]]);
    expect(steps.map((s) => s.kind)).toEqual(['down', 'down', 'up', 'total']);
    expect(steps.at(-1).change).toBe(-75);
  });

  it('folds "other" in as its own step and keeps the net bar honest', () => {
    const steps = buildWaterfall({ segments: [seg('A', 10)], other: { count: 4, change: -3 } });
    expect(steps.map((s) => s.name)).toEqual(['A', 'Other (4)', 'Net change']);
    expect(steps[1].fullName).toBe('4 other values');
    expect(steps.at(-1).change).toBe(7);
  });

  it('a positive net draws its total bar upward from zero', () => {
    const steps = buildWaterfall({ segments: [seg('A', 6), seg('B', 4)] });
    expect(steps.at(-1).range).toEqual([0, 10]);
  });

  it('truncates long names for the axis but keeps the full name for the tooltip', () => {
    const steps = buildWaterfall({ segments: [seg('A very long segment name', 1)] });
    expect(steps[0].name).toBe('A very long s\u2026');
    expect(steps[0].name).toHaveLength(14);
    expect(steps[0].fullName).toBe('A very long segment name');
  });
});

describe('pickComparison / pickDimension', () => {
  const drivers = { comparisons: [{ id: 'latest_month', dimensions: [{ dimension: 'Region' }, { dimension: 'Category' }] }, { id: 'break', dimensions: [{ dimension: 'Region' }] }] };
  it('picks by id, falling back to the first', () => {
    expect(pickComparison(drivers, 'break').id).toBe('break');
    expect(pickComparison(drivers, 'nope').id).toBe('latest_month');
    expect(pickComparison(drivers, null).id).toBe('latest_month');
    expect(pickComparison(null, null)).toBeNull();
  });
  it('picks a dimension by name, falling back to the first', () => {
    const c = drivers.comparisons[0];
    expect(pickDimension(c, 'Category').dimension).toBe('Category');
    expect(pickDimension(c, 'Gone').dimension).toBe('Region');
    expect(pickDimension(null, null)).toBeNull();
  });
});
