// Same-origin by default (the built frontend is served by the same FastAPI
// process as the API). VITE_API_BASE can override this for local dev when
// running `npm run dev` separately from the backend.
const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function analyzeFile(file, columnOverrides) {
  const formData = new FormData();
  formData.append('file', file);
  if (columnOverrides && Object.keys(columnOverrides).length > 0) {
    formData.append('column_overrides', JSON.stringify(columnOverrides));
  }

  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    body: formData,
  });

  const body = await res.json();

  if (!res.ok) {
    const message = typeof body.detail === 'string'
      ? body.detail
      : 'The file could not be analyzed. Check that it is a valid file.';
    throw new Error(message);
  }

  return body;
}

export async function analyzeCombined(files) {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));

  const res = await fetch(`${API_BASE}/api/analyze-combined`, {
    method: 'POST',
    body: formData,
  });

  const body = await res.json();

  if (!res.ok) {
    const message = typeof body.detail === 'string'
      ? body.detail
      : 'The files could not be combined.';
    throw new Error(message);
  }

  return body;
}

export async function analyzeJoined(fileA, fileB) {
  const formData = new FormData();
  formData.append('files', fileA);
  formData.append('files', fileB);

  const res = await fetch(`${API_BASE}/api/analyze-joined`, {
    method: 'POST',
    body: formData,
  });

  const body = await res.json();

  if (!res.ok) {
    const message = typeof body.detail === 'string'
      ? body.detail
      : 'The files could not be joined.';
    throw new Error(message);
  }

  return body;
}

export async function compareFiles(fileA, fileB) {
  const formData = new FormData();
  formData.append('file_a', fileA);
  formData.append('file_b', fileB);

  const res = await fetch(`${API_BASE}/api/compare`, {
    method: 'POST',
    body: formData,
  });

  const body = await res.json();

  if (!res.ok) {
    const message = typeof body.detail === 'string'
      ? body.detail
      : 'The files could not be compared.';
    throw new Error(message);
  }

  return body;
}


export const SAMPLE_DATASETS = [
  {
    id: 'sales',
    label: 'Sales',
    filename: 'demo-sales-data.csv',
    description: '600 orders — regions, categories, profit, and discounts',
  },
  {
    id: 'healthcare',
    label: 'Healthcare',
    filename: 'sample-healthcare-data.csv',
    description: '1,200 patient records — conditions, admissions, and billing',
  },
  {
    id: 'manufacturing',
    label: 'Manufacturing',
    filename: 'sample-manufacturing-data.csv',
    description: '1,500 production records — defect rates, downtime, and output',
  },
];

export async function loadSampleFile(filename) {
  const res = await fetch(`/${filename}`);
  if (!res.ok) throw new Error('Could not load that sample dataset.');
  const blob = await res.blob();
  return new File([blob], filename, { type: 'text/csv' });
}

export async function createShareLink(fileName, kpis, v2) {
  const res = await fetch(`${API_BASE}/api/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, kpis: kpis || {}, v2 }),
  });

  if (!res.ok) {
    let message = 'The share link could not be created.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }

  const data = await res.json();
  return `${window.location.origin}${data.share_path}`;
}

export async function fetchSharedAnalysis(token) {
  const res = await fetch(`${API_BASE}/api/share/${token}`);
  if (!res.ok) {
    let message = 'This share link has expired or doesn\'t exist.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }
  return res.json();
}

export async function downloadCleanedCsv(sourceFile, fileName) {
  const formData = new FormData();
  formData.append('file', sourceFile);

  const res = await fetch(`${API_BASE}/api/export/cleaned-csv`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    let message = 'The cleaned CSV could not be generated.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }

  let summary = null;
  try {
    const raw = res.headers.get('x-clean-summary');
    if (raw) summary = JSON.parse(raw);
  } catch (e) { /* summary is a nice-to-have, not worth failing the download over */ }

  const blob = await res.blob();
  const safeName = (fileName || 'datalens-data').replace(/\.[^/.]+$/, '').replace(/[^\w-]+/g, '_');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safeName}_cleaned.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);

  return summary;
}

export async function exportPdf(fileName, v2) {
  // filterable_data exists purely for client-side chart filtering and can
  // be a large payload on big datasets; the PDF generator never reads it,
  // so there's no reason to upload it on every export.
  const { filterable_data, ...v2ForExport } = v2;

  const res = await fetch(`${API_BASE}/api/export/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, v2: v2ForExport }),
  });

  if (!res.ok) {
    let message = 'The PDF report could not be generated.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }

  const blob = await res.blob();
  const safeName = (fileName || 'datalens-report').replace(/\.[^/.]+$/, '').replace(/[^\w-]+/g, '_');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safeName}_report.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// The dashboard keeps its filters as { dateColumn, dateFrom, dateTo,
// dimensionFilters: { column: Set } }. Sets don't survive JSON, and "no filters"
// should be sent as null so the generated script says so instead of listing
// empty conditions.
export function serializeFilters(filters) {
  if (!filters) return null;
  const dimensionFilters = {};
  for (const [col, allowed] of Object.entries(filters.dimensionFilters || {})) {
    const values = allowed ? Array.from(allowed) : [];
    if (values.length) dimensionFilters[col] = values;
  }
  const hasDate = !!(filters.dateFrom || filters.dateTo);
  if (!hasDate && Object.keys(dimensionFilters).length === 0) return null;
  const out = { dimensionFilters };
  if (hasDate) {
    out.dateColumn = filters.dateColumn;
    if (filters.dateFrom) out.dateFrom = filters.dateFrom;
    if (filters.dateTo) out.dateTo = filters.dateTo;
  }
  return out;
}

// A directed A-vs-B question. The server only gets the two groups' values (the
// rows the dashboard is showing); an unusable question comes back as
// { available: false, note } rather than an error, so the panel can say why.
export async function runHypothesisTest(payload) {
  const res = await fetch(`${API_BASE}/api/hypothesis-test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let message = 'The test could not be run.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }
  return res.json();
}

// "Show the code": a pandas script that reproduces this analysis. The server
// only needs column names and the analysis definitions, never the row data, so
// the rows are dropped here (they can be the largest part of the result).
export async function exportCode(fileName, v2, filters) {
  const v2ForExport = v2.filterable_data ? { ...v2, filterable_data: { ...v2.filterable_data, rows: [] } } : v2;

  const res = await fetch(`${API_BASE}/api/export/code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, v2: v2ForExport, filters: serializeFilters(filters) }),
  });

  if (!res.ok) {
    let message = 'The script could not be generated.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }

  const blob = await res.blob();
  const safeName = (fileName || 'datalens').replace(/\.[^/.]+$/, '').replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '') || 'datalens';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safeName}_datalens.py`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function exportHtml(fileName, v2) {
  const { filterable_data, ...v2ForExport } = v2;

  const res = await fetch(`${API_BASE}/api/export/html`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, v2: v2ForExport }),
  });

  if (!res.ok) {
    let message = 'The HTML report could not be generated.';
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch (e) { /* non-JSON error body -- keep the default message */ }
    throw new Error(message);
  }

  const blob = await res.blob();
  const safeName = (fileName || 'datalens-report').replace(/\.[^/.]+$/, '').replace(/[^\w-]+/g, '_');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safeName}_report.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
