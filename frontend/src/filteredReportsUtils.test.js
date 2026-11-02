import { describe, it, expect } from 'vitest';
import { primaryTrendSpec, recomputeBlocker, buildFilteredPayload, unavailableReports, MAX_RECOMPUTE_ROWS } from './filteredReportsUtils';
import fixture from './test/fixtures/analysis.json';

const v2 = () => JSON.parse(JSON.stringify(fixture.v2));

describe('primaryTrendSpec', () => {
  it('takes the measure and aggregation the upload-time Drivers used, and the row data\'s date column', () => {
    const x = v2();
    expect(primaryTrendSpec(x)).toEqual({ metric_column: x.drivers.metric, aggregation: x.drivers.aggregation, date_column: x.filterable_data.date_column });
  });

  it('falls back to the last trend analysis when Drivers was unavailable', () => {
    const x = v2();
    x.drivers = { available: false, comparisons: [] };
    const lastTrend = x.all_analyses.filter((a) => a.type === 'trend').at(-1);
    expect(primaryTrendSpec(x)).toMatchObject({ metric_column: lastTrend.metric_column });
  });

  it('is null without a date column or without any trend', () => {
    const noDate = v2();
    noDate.filterable_data.date_column = null;
    expect(primaryTrendSpec(noDate)).toBeNull();
    const noTrend = v2();
    noTrend.drivers = { available: false };
    noTrend.all_analyses = noTrend.all_analyses.filter((a) => a.type !== 'trend');
    expect(primaryTrendSpec(noTrend)).toBeNull();
    expect(primaryTrendSpec(undefined)).toBeNull();
  });
});

describe('recomputeBlocker', () => {
  it('is null for a normal result', () => {
    expect(recomputeBlocker(v2(), 100)).toBeNull();
  });
  it('explains each reason in words', () => {
    const noRows = v2(); noRows.filterable_data = { available: false };
    expect(recomputeBlocker(noRows, 10)).toMatch(/row-level data is not available/);
    const old = v2(); delete old.filterable_data.measure_aggregations;
    expect(recomputeBlocker(old, 10)).toMatch(/Re-analyse the file/);
    const noDate = v2(); noDate.filterable_data.date_column = null;
    expect(recomputeBlocker(noDate, 10)).toMatch(/date column and a measure/);
    expect(recomputeBlocker(v2(), MAX_RECOMPUTE_ROWS + 1)).toMatch(/too many to recompute/);
  });
  it('allows exactly the limit', () => {
    expect(recomputeBlocker(v2(), MAX_RECOMPUTE_ROWS)).toBeNull();
  });
  it('is safe on a missing result', () => {
    expect(recomputeBlocker(undefined, 0)).toMatch(/not available/);
  });
});

describe('buildFilteredPayload', () => {
  it('sends the rows column by column, aligned, with the dataset\'s own aggregations', () => {
    const x = v2();
    const rows = x.filterable_data.rows.slice(0, 5);
    const p = buildFilteredPayload(x, rows);
    const fd = x.filterable_data;
    expect(Object.keys(p.columns).sort()).toEqual([...new Set([fd.date_column, ...fd.dimension_columns, ...fd.measure_columns])].sort());
    for (const col of Object.keys(p.columns)) {
      expect(p.columns[col]).toHaveLength(5);
      expect(p.columns[col]).toEqual(rows.map((r) => r[col]));
    }
    expect(p.measure_aggregations).toEqual(fd.measure_aggregations);
    expect(p.metric_column).toBe(x.drivers.metric);
    expect(p.date_column).toBe(fd.date_column);
  });

  it('turns an absent value into null (JSON has no undefined)', () => {
    const x = v2();
    const col = x.filterable_data.measure_columns[0];
    const rows = [{ ...x.filterable_data.rows[0] }];
    delete rows[0][col];
    expect(buildFilteredPayload(x, rows).columns[col]).toEqual([null]);
  });

  it('sends nothing but the row data the dashboard already holds: no file name, no other analyses', () => {
    const p = buildFilteredPayload(v2(), v2().filterable_data.rows.slice(0, 3));
    expect(Object.keys(p).sort()).toEqual(['aggregation', 'columns', 'date_column', 'dimension_columns', 'measure_aggregations', 'measure_columns', 'metric_column']);
  });
});

describe('unavailableReports', () => {
  it('gives every panel the same reason, in the shape each panel already renders', () => {
    const u = unavailableReports('Because.');
    expect(u.seasonality).toEqual({ available: false, note: 'Because.' });
    expect(u.period_comparison.available).toBe(false);
    expect(u.drivers).toMatchObject({ available: false, note: 'Because.', comparisons: [] });
    expect(u.robustness).toMatchObject({ available: false, note: 'Because.', kpis: [], correlations: [] });
  });
});
