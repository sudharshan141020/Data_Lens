// Filter-aware reports: helpers for sending the rows the dashboard is showing to
// POST /api/filtered-reports and for deciding when that is possible.
//
// Four reports (Seasonality, Period Comparison, "Why did it change?", Robustness) need real
// statistics and groupbys, so they cannot be re-aggregated in the browser the way the charts are.
// The server recomputes them on the filtered rows with the SAME code the upload ran
// (app/filtered_reports.py); nothing here re-implements any of that.

export const MAX_RECOMPUTE_ROWS = 50_000;     // matches the server's RECOMPUTE_MAX_ROWS

// Which measure and aggregation the reports are about: whatever the upload-time Drivers used (it comes
// from the same trend analysis as Period Comparison), else the last trend analysis in the result.
export function primaryTrendSpec(v2) {
  const dateColumn = v2?.filterable_data?.date_column;
  if (!dateColumn) return null;
  if (v2.drivers?.available && v2.drivers.metric) {
    return { metric_column: v2.drivers.metric, aggregation: v2.drivers.aggregation || 'sum', date_column: dateColumn };
  }
  const trends = (v2.all_analyses || []).filter((a) => a.type === 'trend' && a.metric_column);
  const last = trends[trends.length - 1];
  return last ? { metric_column: last.metric_column, aggregation: last.aggregation || 'sum', date_column: dateColumn } : null;
}

// Why a recompute is not possible, or null when it is. The messages are shown to the person.
export function recomputeBlocker(v2, rowCount) {
  const fd = v2?.filterable_data;
  if (!fd?.available) return 'The row-level data is not available for this dataset, so these reports cannot follow the filters.';
  if (!fd.measure_aggregations) return 'This result was made before filter-aware reports existed. Re-analyse the file to enable them.';
  if (!primaryTrendSpec(v2)) return 'These reports need a date column and a measure, which this dataset does not have.';
  if (rowCount > MAX_RECOMPUTE_ROWS) {
    return `${rowCount.toLocaleString('en-US')} rows is too many to recompute interactively (the limit is ${MAX_RECOMPUTE_ROWS.toLocaleString('en-US')}).`;
  }
  return null;
}

// The request body: the rows column by column (no repeated keys, so it is a fraction of the size).
export function buildFilteredPayload(v2, rows) {
  const fd = v2.filterable_data;
  const spec = primaryTrendSpec(v2);
  const names = [...new Set([fd.date_column, ...fd.dimension_columns, ...fd.measure_columns])];
  const columns = {};
  for (const name of names) columns[name] = rows.map((r) => (r[name] === undefined ? null : r[name]));
  return {
    columns,
    date_column: fd.date_column,
    dimension_columns: fd.dimension_columns,
    measure_columns: fd.measure_columns,
    measure_aggregations: fd.measure_aggregations,
    metric_column: spec.metric_column,
    aggregation: spec.aggregation,
  };
}

// Shape of a report the panels already know how to show as "unavailable, here is why".
export function unavailableReports(note) {
  const off = { available: false, note, comparisons: [] };
  return { seasonality: { available: false, note }, period_comparison: { available: false, note }, drivers: off, robustness: { ...off, kpis: [], correlations: [] } };
}
