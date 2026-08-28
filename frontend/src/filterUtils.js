// Client-side filtering + re-aggregation over the compact `filterable_data`
// row set the backend ships alongside the analysis. Keeps the backend
// fully stateless -- filters never trigger another server round trip.

export function getDistinctValues(rows, column) {
  const set = new Set();
  for (const r of rows) {
    if (r[column] !== null && r[column] !== undefined && r[column] !== '') set.add(r[column]);
  }
  return Array.from(set).sort();
}

export function getDateRange(rows, dateColumn) {
  let min = null, max = null;
  for (const r of rows) {
    const v = r[dateColumn];
    if (!v) continue;
    if (min === null || v < min) min = v;
    if (max === null || v > max) max = v;
  }
  return { min, max };
}

export function applyFilters(rows, filters) {
  if (!filters) return rows;
  const { dateFrom, dateTo, dateColumn, dimensionFilters } = filters;
  return rows.filter((r) => {
    if (dateColumn && (dateFrom || dateTo)) {
      const v = r[dateColumn];
      if (!v) return false;
      if (dateFrom && v < dateFrom) return false;
      if (dateTo && v > dateTo) return false;
    }
    if (dimensionFilters) {
      for (const [col, allowed] of Object.entries(dimensionFilters)) {
        if (allowed && allowed.size > 0 && !allowed.has(r[col])) return false;
      }
    }
    return true;
  });
}

function aggregate(values, aggregation) {
  if (!values.length) return 0;
  const sum = values.reduce((a, b) => a + b, 0);
  return aggregation === 'avg' ? sum / values.length : sum;
}

export function recomputeTrend(rows, dateColumn, metricColumn, aggregation) {
  const buckets = new Map();
  for (const r of rows) {
    const d = r[dateColumn];
    const v = r[metricColumn];
    if (!d || typeof v !== 'number') continue;
    const month = d.slice(0, 7); // 'YYYY-MM'
    if (!buckets.has(month)) buckets.set(month, []);
    buckets.get(month).push(v);
  }
  const labels = Array.from(buckets.keys()).sort();
  return labels.map((label) => ({
    label,
    value: Math.round(aggregate(buckets.get(label), aggregation) * 100) / 100,
    is_forecast: false,
  }));
}

export function recomputeDistributionSum(rows, column, metricColumn, aggregation, topN = 15) {
  const buckets = new Map();
  for (const r of rows) {
    const key = r[column];
    const v = r[metricColumn];
    if (key === null || key === undefined || typeof v !== 'number') continue;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(v);
  }
  const entries = Array.from(buckets.entries())
    .map(([label, values]) => ({ label: String(label), value: Math.round(aggregate(values, aggregation) * 100) / 100 }))
    .sort((a, b) => b.value - a.value);
  return entries.slice(0, topN);
}

export function recomputeDistributionCount(rows, column, topN = 15) {
  const counts = new Map();
  for (const r of rows) {
    const key = r[column];
    if (key === null || key === undefined) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const entries = Array.from(counts.entries())
    .map(([label, value]) => ({ label: String(label), value }))
    .sort((a, b) => b.value - a.value);
  return entries.slice(0, topN);
}

// Recomputes an analysis's `.data` from the filtered rows for the chart
// types this feature covers. Returns the ORIGINAL analysis unchanged for
// any type it doesn't know how to recompute (scatter, heatmap, boxplot,
// correlation matrix) -- those keep showing the full, unfiltered dataset,
// and the UI marks them as such rather than silently pretending they're
// filtered too.
export function recomputeAnalysis(analysis, filteredRows) {
  if (analysis.type === 'trend' && analysis.date_column && analysis.metric_column) {
    return { ...analysis, data: recomputeTrend(filteredRows, analysis.date_column, analysis.metric_column, analysis.aggregation || 'sum') };
  }
  if (analysis.type === 'distribution_sum' && analysis.column && analysis.metric_column) {
    return { ...analysis, data: recomputeDistributionSum(filteredRows, analysis.column, analysis.metric_column, analysis.aggregation || 'sum') };
  }
  if (analysis.type === 'distribution_count' && analysis.column) {
    return { ...analysis, data: recomputeDistributionCount(filteredRows, analysis.column) };
  }
  return analysis;
}

export const FILTER_REACTIVE_TYPES = new Set(['trend', 'distribution_sum', 'distribution_count']);
