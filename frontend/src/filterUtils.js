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

export function aggregate(values, aggregation) {
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

// ---------------------------------------------------------------------
// Ad-hoc query builder ("ask your own question" instead of only the
// auto-picked Key Analyses). Runs entirely against the same compact
// `filterable_data` row set everything above already uses -- no new
// server endpoint, no round trip, same stateless-backend guarantee.
// Mirrors app/executor_v2.py's _compute_pivot (two dimensions -- same
// "cap to the top N most frequent values per dimension, by row count"
// rule, so a 20x20 grid doesn't happen) and _compute_distribution_sum /
// _compute_distribution_count (one dimension).
// ---------------------------------------------------------------------
const QUERY_TOP_N_SINGLE = 15;
const QUERY_TOP_N_PIVOT = 8;

export function runCustomQuery(rows, { measure, aggregation, dim1, dim2 }) {
  if (!dim1) return null;

  if (!dim2) {
    if (aggregation === 'count') return recomputeDistributionCount(rows, dim1, QUERY_TOP_N_SINGLE);
    if (!measure) return null;
    return recomputeDistributionSum(rows, dim1, measure, aggregation, QUERY_TOP_N_SINGLE);
  }

  if (aggregation !== 'count' && !measure) return null;

  const sub = rows.filter((r) => r[dim1] != null && r[dim2] != null);
  const countOccurrences = (col) => {
    const c = new Map();
    for (const r of sub) c.set(r[col], (c.get(r[col]) || 0) + 1);
    return c;
  };
  const topByFrequency = (col) =>
    Array.from(countOccurrences(col).entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, QUERY_TOP_N_PIVOT)
      .map(([k]) => k);

  const top1 = topByFrequency(dim1);
  const top2 = topByFrequency(dim2);
  const set1 = new Set(top1);
  const set2 = new Set(top2);

  const buckets = new Map(); // `${d1}||${d2}` -> { count, values }
  for (const r of sub) {
    const d1 = r[dim1], d2 = r[dim2];
    if (!set1.has(d1) || !set2.has(d2)) continue;
    const key = `${d1}||${d2}`;
    if (!buckets.has(key)) buckets.set(key, { count: 0, values: [] });
    const b = buckets.get(key);
    b.count += 1;
    if (typeof r[measure] === 'number') b.values.push(r[measure]);
  }

  const cells = [];
  for (const d1 of top1) {
    for (const d2 of top2) {
      const b = buckets.get(`${d1}||${d2}`);
      let value = null;
      if (b) value = aggregation === 'count' ? b.count : (b.values.length ? aggregate(b.values, aggregation) : null);
      cells.push({ x: String(d2), y: String(d1), value });
    }
  }
  return cells;
}

// Same rule app/analysis_planner.py's choose_chart_type uses for
// distribution_count/distribution_sum, so a custom query looks exactly
// like an auto-picked one of the same shape: a small category count
// reads better as a donut, a large one as a treemap, otherwise a bar.
export function chooseQueryChartType(hasSecondDim, cardinality, aggregation) {
  if (hasSecondDim) return 'heatmap';
  if (cardinality > 15) return 'treemap';
  if (aggregation === 'count' && cardinality <= 6) return 'donut';
  return 'horizontal_bar';
}
