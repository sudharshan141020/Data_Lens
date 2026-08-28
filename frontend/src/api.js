// Same-origin by default (the built frontend is served by the same FastAPI
// process as the API). VITE_API_BASE can override this for local dev when
// running `npm run dev` separately from the backend.
const API_BASE = import.meta.env.VITE_API_BASE || '';

export async function analyzeFile(file) {
  const formData = new FormData();
  formData.append('file', file);

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

export async function loadDemoFile() {
  const res = await fetch('/demo-sales-data.csv');
  if (!res.ok) throw new Error('Could not load the demo dataset.');
  const blob = await res.blob();
  return new File([blob], 'demo-sales-data.csv', { type: 'text/csv' });
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
