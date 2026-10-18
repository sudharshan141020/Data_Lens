import { describe, it, expect } from 'vitest';
import {
  levelCounts, groupColumnOptions, outcomeOptions, isProportionOutcome, positiveLevelOptions,
  defaultSelection, buildPayload, selectionKey, formatP, formatNumber, formatPercent, signed, intervalGeometry,
} from './hypothesisUtils';

const FD = { available: true, dimension_columns: ['Region', 'Category', 'Constant'], measure_columns: ['Sales', 'Flag'] };
const ROWS = [
  { Region: 'West', Category: 'Tech', Constant: 'x', Sales: 10, Flag: 1 },
  { Region: 'West', Category: 'Tech', Constant: 'x', Sales: 20, Flag: 0 },
  { Region: 'West', Category: 'Furniture', Constant: 'x', Sales: 30, Flag: 1 },
  { Region: 'East', Category: 'Tech', Constant: 'x', Sales: 5, Flag: 0 },
  { Region: 'East', Category: 'Furniture', Constant: 'x', Sales: 15, Flag: 0 },
  { Region: null, Category: '', Constant: 'x', Sales: 99, Flag: 1 },
];

describe('levelCounts', () => {
  it('counts distinct values biggest first, ignoring blanks, ties alphabetical', () => {
    expect(levelCounts(ROWS, 'Region')).toEqual([{ level: 'West', n: 3 }, { level: 'East', n: 2 }]);
    expect(levelCounts([{ a: 'b' }, { a: 'a' }], 'a')).toEqual([{ level: 'a', n: 1 }, { level: 'b', n: 1 }]);
  });
  it('compares as text, the way the server does', () => {
    expect(levelCounts([{ t: 1 }, { t: '1' }, { t: 2 }], 't')).toEqual([{ level: '1', n: 2 }, { level: '2', n: 1 }]);
  });
  it('is safe on empty or missing input', () => {
    expect(levelCounts([], 'x')).toEqual([]);
    expect(levelCounts(undefined, 'x')).toEqual([]);
  });
});

describe('column options', () => {
  it('offers only dimensions with at least two values in the rows being shown', () => {
    expect(groupColumnOptions(FD, ROWS)).toEqual(['Region', 'Category']);
  });
  it('re-evaluates against the filtered rows (a filter that leaves one value removes the column)', () => {
    expect(groupColumnOptions(FD, ROWS.filter((r) => r.Region === 'West'))).toEqual(['Category']);
  });
  it('outcomes are measures first then dimensions, never the group column itself', () => {
    expect(outcomeOptions(FD, 'Region').map((o) => `${o.kind}:${o.column}`)).toEqual(['measure:Sales', 'measure:Flag', 'dimension:Category', 'dimension:Constant']);
  });
});

describe('isProportionOutcome', () => {
  it('a category column is always a rate outcome', () => {
    expect(isProportionOutcome({ column: 'Category', kind: 'dimension' }, ROWS)).toBe(true);
  });
  it('a number column is a rate outcome only when it takes exactly two values (a 0/1 flag)', () => {
    expect(isProportionOutcome({ column: 'Flag', kind: 'measure' }, ROWS)).toBe(true);
    expect(isProportionOutcome({ column: 'Sales', kind: 'measure' }, ROWS)).toBe(false);
    expect(isProportionOutcome({ column: 'Flag', kind: 'measure' }, [{ Flag: 1 }, { Flag: 1 }])).toBe(false);
  });
  it('is false without an outcome', () => {
    expect(isProportionOutcome(null, ROWS)).toBe(false);
  });
});

describe('positiveLevelOptions', () => {
  it('lists the values when there are few enough to pick from, none when there are too many', () => {
    expect(positiveLevelOptions(ROWS, 'Category').map((l) => l.level)).toEqual(['Tech', 'Furniture']);
    const many = Array.from({ length: 11 }, (_, i) => ({ c: `v${i}` }));
    expect(positiveLevelOptions(many, 'c')).toEqual([]);
  });
});

describe('defaultSelection', () => {
  it('picks the first splittable column, its two most common values and the first measure', () => {
    expect(defaultSelection(FD, ROWS)).toEqual({ groupColumn: 'Region', a: 'West', b: 'East', outcomeColumn: 'Sales', positive: '' });
  });
  it('is null when nothing can be compared', () => {
    expect(defaultSelection(FD, ROWS.filter((r) => r.Region === 'West' && r.Category === 'Tech'))).toBeNull();
    expect(defaultSelection({ available: true, dimension_columns: ['Region'], measure_columns: [] }, ROWS.concat([{ Region: 'East' }]))).toBeNull();
  });
});

describe('buildPayload', () => {
  const sel = { groupColumn: 'Region', a: 'West', b: 'East', outcomeColumn: 'Sales', positive: '' };
  it('sends only the two groups, as parallel arrays, and nothing else about the rows', () => {
    const p = buildPayload(ROWS, sel, { column: 'Sales', kind: 'measure' });
    expect(p.groups).toEqual(['West', 'West', 'West', 'East', 'East']);
    expect(p.outcomes).toEqual([10, 20, 30, 5, 15]);
    expect(Object.keys(p).sort()).toEqual(['group_a', 'group_b', 'group_column', 'groups', 'outcome_column', 'outcome_kind', 'outcomes', 'positive_level']);
  });
  it('drops rows with a blank group or a blank outcome', () => {
    const rows = [{ Region: 'West', Sales: null }, { Region: 'West', Sales: '' }, { Region: 'West', Sales: 1 }, { Region: '', Sales: 2 }];
    expect(buildPayload(rows, sel, { column: 'Sales', kind: 'measure' }).outcomes).toEqual([1]);
  });
  it('asks the server to treat a category outcome as categorical, and lets it decide for a number', () => {
    expect(buildPayload(ROWS, { ...sel, outcomeColumn: 'Category' }, { column: 'Category', kind: 'dimension' }).outcome_kind).toBe('categorical');
    expect(buildPayload(ROWS, sel, { column: 'Sales', kind: 'measure' }).outcome_kind).toBe('auto');
  });
  it('passes the chosen rate level through, or null', () => {
    expect(buildPayload(ROWS, { ...sel, positive: 'Tech' }, { column: 'Category', kind: 'dimension' }).positive_level).toBe('Tech');
    expect(buildPayload(ROWS, sel, { column: 'Sales', kind: 'measure' }).positive_level).toBeNull();
  });
  it('refuses to build without both groups or an outcome', () => {
    expect(buildPayload(ROWS, { ...sel, b: undefined }, { column: 'Sales', kind: 'measure' })).toBeNull();
    expect(buildPayload(ROWS, sel, null)).toBeNull();
  });
});

describe('selectionKey', () => {
  const sel = { groupColumn: 'Region', a: 'West', b: 'East', outcomeColumn: 'Sales', positive: '' };
  it('changes with every part of the question and with the row count (filters)', () => {
    const base = selectionKey(sel, 100);
    expect(selectionKey({ ...sel, a: 'North' }, 100)).not.toBe(base);
    expect(selectionKey({ ...sel, outcomeColumn: 'Profit' }, 100)).not.toBe(base);
    expect(selectionKey({ ...sel, positive: 'Yes' }, 100)).not.toBe(base);
    expect(selectionKey(sel, 99)).not.toBe(base);
    expect(selectionKey({ ...sel }, 100)).toBe(base);
  });
});

describe('formatting', () => {
  it('formats p-values with a floor', () => {
    expect(formatP(0.0004)).toBe('p < 0.001');
    expect(formatP(0.0321)).toBe('p = 0.032');
    expect(formatP(null)).toBe('n/a');
  });
  it('formats numbers, percentages and signed values with a real minus', () => {
    expect(formatNumber(12345.6)).toBe('12,346');
    expect(formatNumber(3.14159)).toBe('3.14');
    expect(formatNumber(0.012345)).toBe('0.0123');
    expect(formatPercent(0.1234)).toBe('12.3%');
    expect(signed(4.2)).toBe('+4.2');
    expect(signed(-4.2)).toBe('\u22124.2');
    expect(signed(null)).toBe('n/a');
  });
});

describe('intervalGeometry', () => {
  it('always includes zero on the axis and flags an interval that crosses it', () => {
    const g = intervalGeometry(-2, 6, 2);
    expect(g.crossesZero).toBe(true);
    expect(g.low).toBeLessThan(g.zero);
    expect(g.zero).toBeLessThan(g.high);
    expect(g.low).toBeGreaterThanOrEqual(0);
    expect(g.high).toBeLessThanOrEqual(100);
  });
  it('an interval entirely on one side keeps zero on the axis but does not cross it', () => {
    const g = intervalGeometry(3, 9, 6);
    expect(g.crossesZero).toBe(false);
    expect(g.zero).toBeLessThan(g.low);
  });
  it('does not divide by zero when everything is zero', () => {
    const g = intervalGeometry(0, 0, 0);
    expect([g.low, g.high, g.estimate, g.zero].every(Number.isFinite)).toBe(true);
  });
});
