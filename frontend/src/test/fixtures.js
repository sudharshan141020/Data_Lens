// Small builders shared by the frontend tests. They produce objects shaped
// like what the real backend returns (see src/test/fixtures/analysis.json
// for a captured real response) but keep every value explicit so a test
// reads without a lookup.

export function makeWeakPoint(overrides = {}) {
  return {
    problem: 'Office Supplies is falling behind on Sales',
    impact: 'Office Supplies averages 40 for Sales, which is 25% lower than average.',
    priority: 'medium',
    suggested_action: 'Look into what makes Office Supplies different.',
    category: 'underperformance',
    significant: true,
    ci_low: null,
    ci_high: null,
    ...overrides,
  };
}

// A "ready" session as App.jsx holds it: result.v2 carries the compact
// row payload (filterable_data) plus the weak points snapshotUtils reads.
export function makeSession({
  fileName = 'sales.csv',
  rows = [],
  measureColumns = ['Sales'],
  dimensionColumns = ['Category'],
  weakPoints = [],
  rowCount = rows.length,
  filterableAvailable = true,
} = {}) {
  return {
    id: 's1',
    fileName,
    status: 'ready',
    sourceFile: new File(['x'], fileName),
    result: {
      v2: {
        profile: { row_count: rowCount },
        weak_points: weakPoints,
        filterable_data: filterableAvailable
          ? { available: true, rows, measure_columns: measureColumns, dimension_columns: dimensionColumns }
          : { available: false, reason: 'dataset_too_large' },
      },
    },
  };
}

export function salesRows(n, { base = 100, categories = ['A', 'B'] } = {}) {
  return Array.from({ length: n }, (_, i) => ({
    Sales: base + i,
    Category: categories[i % categories.length],
  }));
}
