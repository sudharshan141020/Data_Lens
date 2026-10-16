import { describe, it, expect } from 'vitest';
import {
  getDistinctValues, getDateRange, applyFilters, aggregate,
  recomputeTrend, recomputeDistributionSum, recomputeDistributionCount,
  recomputeAnalysis, FILTER_REACTIVE_TYPES, runCustomQuery, chooseQueryChartType,
} from './filterUtils';

const ROWS = [
  { Date: '2024-01-10', Category: 'Furniture', Region: 'East', Sales: 100 },
  { Date: '2024-01-20', Category: 'Furniture', Region: 'West', Sales: 150 },
  { Date: '2024-02-05', Category: 'Tech', Region: 'East', Sales: 300 },
  { Date: '2024-02-15', Category: 'Tech', Region: 'West', Sales: 200 },
  { Date: '2024-03-01', Category: 'Office', Region: 'East', Sales: 50 },
];

describe('getDistinctValues', () => {
  it('returns sorted unique values and skips null/undefined/empty', () => {
    const rows = [{ c: 'b' }, { c: 'a' }, { c: 'b' }, { c: null }, { c: undefined }, { c: '' }, {}];
    expect(getDistinctValues(rows, 'c')).toEqual(['a', 'b']);
  });
});

describe('getDateRange', () => {
  it('finds the min and max ISO date, ignoring rows with no date', () => {
    const rows = [{ d: '2024-03-01' }, { d: '2024-01-15' }, { d: null }, { d: '2024-02-01' }, {}];
    expect(getDateRange(rows, 'd')).toEqual({ min: '2024-01-15', max: '2024-03-01' });
  });

  it('returns nulls for an empty set', () => {
    expect(getDateRange([], 'd')).toEqual({ min: null, max: null });
  });
});

describe('applyFilters', () => {
  it('returns the same array when there are no filters', () => {
    expect(applyFilters(ROWS, null)).toBe(ROWS);
  });

  it('treats the date range as inclusive on both ends', () => {
    const out = applyFilters(ROWS, { dateColumn: 'Date', dateFrom: '2024-01-20', dateTo: '2024-02-05' });
    expect(out.map((r) => r.Date)).toEqual(['2024-01-20', '2024-02-05']);
  });

  it('drops rows with no date once a date filter is active', () => {
    const rows = [...ROWS, { Date: null, Category: 'X', Region: 'East', Sales: 1 }];
    const out = applyFilters(rows, { dateColumn: 'Date', dateFrom: '2024-01-01' });
    expect(out).toHaveLength(ROWS.length);
  });

  it('filters on an allowed-values set per dimension, ANDed together', () => {
    const out = applyFilters(ROWS, {
      dimensionFilters: { Category: new Set(['Tech', 'Furniture']), Region: new Set(['East']) },
    });
    expect(out.map((r) => r.Sales)).toEqual([100, 300]);
  });

  it('treats an empty allowed set as "no restriction", not "match nothing"', () => {
    const out = applyFilters(ROWS, { dimensionFilters: { Category: new Set() } });
    expect(out).toHaveLength(ROWS.length);
  });
});

describe('aggregate', () => {
  it('sums by default and averages on request', () => {
    expect(aggregate([1, 2, 3], 'sum')).toBe(6);
    expect(aggregate([1, 2, 3], 'avg')).toBe(2);
  });

  it('returns 0 for no values rather than NaN', () => {
    expect(aggregate([], 'avg')).toBe(0);
    expect(aggregate([], 'sum')).toBe(0);
  });
});

describe('recomputeTrend', () => {
  it('buckets by YYYY-MM, sorts chronologically, and marks nothing as forecast', () => {
    const out = recomputeTrend([...ROWS].reverse(), 'Date', 'Sales', 'sum');
    expect(out).toEqual([
      { label: '2024-01', value: 250, is_forecast: false },
      { label: '2024-02', value: 500, is_forecast: false },
      { label: '2024-03', value: 50, is_forecast: false },
    ]);
  });

  it('supports averaging and rounds to 2 decimals', () => {
    const rows = [
      { Date: '2024-01-01', v: 1 }, { Date: '2024-01-02', v: 1 }, { Date: '2024-01-03', v: 2 },
    ];
    expect(recomputeTrend(rows, 'Date', 'v', 'avg')[0].value).toBe(1.33);
  });

  it('skips rows whose metric is not a number or whose date is missing', () => {
    const rows = [
      { Date: '2024-01-01', v: 10 }, { Date: '2024-01-02', v: '12' }, { Date: null, v: 5 }, { Date: '2024-01-03', v: null },
    ];
    expect(recomputeTrend(rows, 'Date', 'v', 'sum')).toEqual([{ label: '2024-01', value: 10, is_forecast: false }]);
  });
});

describe('recomputeDistributionSum / Count', () => {
  it('sorts descending, stringifies labels and respects topN', () => {
    const sum = recomputeDistributionSum(ROWS, 'Category', 'Sales', 'sum', 2);
    expect(sum).toEqual([{ label: 'Tech', value: 500 }, { label: 'Furniture', value: 250 }]);
  });

  it('averages per group when asked', () => {
    const avg = recomputeDistributionSum(ROWS, 'Category', 'Sales', 'avg');
    expect(avg.find((d) => d.label === 'Tech').value).toBe(250);
  });

  it('ignores rows with a null key or a non-numeric metric', () => {
    const rows = [{ k: 'a', v: 1 }, { k: null, v: 5 }, { k: 'a', v: 'x' }];
    expect(recomputeDistributionSum(rows, 'k', 'v', 'sum')).toEqual([{ label: 'a', value: 1 }]);
  });

  it('counts rows per category', () => {
    expect(recomputeDistributionCount(ROWS, 'Region')).toEqual([
      { label: 'East', value: 3 }, { label: 'West', value: 2 },
    ]);
  });
});

describe('recomputeAnalysis', () => {
  const base = { id: 'a', title: 't' };

  it('recomputes a trend from filtered rows without mutating the original', () => {
    const original = { ...base, type: 'trend', date_column: 'Date', metric_column: 'Sales', aggregation: 'sum', data: [{ label: 'x', value: 1 }] };
    const out = recomputeAnalysis(original, ROWS.slice(0, 2));
    expect(out.data).toEqual([{ label: '2024-01', value: 250, is_forecast: false }]);
    expect(original.data).toEqual([{ label: 'x', value: 1 }]);
    expect(out).not.toBe(original);
  });

  it('recomputes distribution_sum and distribution_count', () => {
    const sum = recomputeAnalysis({ ...base, type: 'distribution_sum', column: 'Category', metric_column: 'Sales', data: [] }, ROWS);
    expect(sum.data[0]).toEqual({ label: 'Tech', value: 500 });
    const count = recomputeAnalysis({ ...base, type: 'distribution_count', column: 'Category', data: [] }, ROWS);
    expect(count.data.find((d) => d.label === 'Furniture').value).toBe(2);
  });

  it('returns types it cannot recompute (scatter, heatmap...) as the very same object', () => {
    const scatter = { ...base, type: 'correlation', data: [1, 2, 3] };
    expect(recomputeAnalysis(scatter, [])).toBe(scatter);
  });

  it('returns the original when a recomputable type is missing the columns it needs', () => {
    const broken = { ...base, type: 'trend', data: [9] };
    expect(recomputeAnalysis(broken, ROWS)).toBe(broken);
  });

  it('advertises exactly the types it can recompute', () => {
    expect([...FILTER_REACTIVE_TYPES].sort()).toEqual(['distribution_count', 'distribution_sum', 'trend']);
  });
});

describe('runCustomQuery', () => {
  it('returns null without a first dimension', () => {
    expect(runCustomQuery(ROWS, { measure: 'Sales', aggregation: 'sum', dim1: '', dim2: null })).toBeNull();
  });

  it('single dimension: sum, avg and count', () => {
    expect(runCustomQuery(ROWS, { measure: 'Sales', aggregation: 'sum', dim1: 'Category' })[0]).toEqual({ label: 'Tech', value: 500 });
    expect(runCustomQuery(ROWS, { measure: 'Sales', aggregation: 'avg', dim1: 'Category' })[0]).toEqual({ label: 'Tech', value: 250 });
    expect(runCustomQuery(ROWS, { aggregation: 'count', dim1: 'Region' })[0]).toEqual({ label: 'East', value: 3 });
  });

  it('needs a measure for sum/avg but not for count', () => {
    expect(runCustomQuery(ROWS, { measure: '', aggregation: 'sum', dim1: 'Category' })).toBeNull();
    expect(runCustomQuery(ROWS, { measure: '', aggregation: 'sum', dim1: 'Category', dim2: 'Region' })).toBeNull();
    expect(runCustomQuery(ROWS, { measure: '', aggregation: 'count', dim1: 'Category', dim2: 'Region' })).not.toBeNull();
  });

  it('two dimensions: builds a full grid of cells and leaves empty combinations null', () => {
    const cells = runCustomQuery(ROWS, { measure: 'Sales', aggregation: 'sum', dim1: 'Category', dim2: 'Region' });
    expect(cells).toHaveLength(3 * 2); // 3 categories x 2 regions
    const get = (y, x) => cells.find((c) => c.y === y && c.x === x).value;
    expect(get('Furniture', 'East')).toBe(100);
    expect(get('Tech', 'West')).toBe(200);
    expect(get('Office', 'West')).toBeNull(); // no such rows -- null, not a misleading 0
  });

  it('two dimensions: counts rows per cell', () => {
    const cells = runCustomQuery(ROWS, { aggregation: 'count', dim1: 'Category', dim2: 'Region' });
    expect(cells.find((c) => c.y === 'Tech' && c.x === 'East').value).toBe(1);
  });

  it('two dimensions: averages per cell', () => {
    const rows = [
      { a: 'x', b: 'p', v: 2 }, { a: 'x', b: 'p', v: 4 }, { a: 'y', b: 'p', v: 10 },
    ];
    const cells = runCustomQuery(rows, { measure: 'v', aggregation: 'avg', dim1: 'a', dim2: 'b' });
    expect(cells.find((c) => c.y === 'x').value).toBe(3);
  });

  it('two dimensions: keeps only the 8 most frequent values per dimension', () => {
    const rows = [];
    for (let i = 0; i < 12; i += 1) {
      // value i appears (12 - i) times, so 0..7 are the most frequent
      for (let n = 0; n < 12 - i; n += 1) rows.push({ a: `a${i}`, b: 'only', v: 1 });
    }
    const cells = runCustomQuery(rows, { measure: 'v', aggregation: 'sum', dim1: 'a', dim2: 'b' });
    const ys = new Set(cells.map((c) => c.y));
    expect(ys.size).toBe(8);
    expect(ys.has('a0')).toBe(true);
    expect(ys.has('a11')).toBe(false);
  });

  it('two dimensions: ignores rows missing either dimension', () => {
    const rows = [{ a: 'x', b: null, v: 1 }, { a: null, b: 'p', v: 1 }, { a: 'x', b: 'p', v: 5 }];
    const cells = runCustomQuery(rows, { measure: 'v', aggregation: 'sum', dim1: 'a', dim2: 'b' });
    expect(cells).toEqual([{ x: 'p', y: 'x', value: 5 }]);
  });
});

describe('chooseQueryChartType', () => {
  it.each([
    [true, 5, 'sum', 'heatmap'],
    [false, 20, 'sum', 'treemap'],
    [false, 16, 'count', 'treemap'],
    [false, 4, 'count', 'donut'],
    [false, 6, 'count', 'donut'],
    [false, 7, 'count', 'horizontal_bar'],
    [false, 4, 'sum', 'horizontal_bar'],
    [false, 15, 'sum', 'horizontal_bar'],
  ])('hasSecondDim=%s cardinality=%s aggregation=%s -> %s', (second, card, agg, expected) => {
    expect(chooseQueryChartType(second, card, agg)).toBe(expected);
  });
});
