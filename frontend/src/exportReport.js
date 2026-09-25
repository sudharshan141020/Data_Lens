// Builds a multi-sheet .xlsx report from an analysis result and triggers a
// browser download. Runs entirely client-side -- the backend never sees or
// stores this file, consistent with the "nothing is persisted" design.
import * as XLSX from 'xlsx';

function sheetFromRows(rows, headerOrder) {
  const ws = XLSX.utils.json_to_sheet(rows, headerOrder ? { header: headerOrder } : undefined);
  return ws;
}

function autoWidth(ws, rows) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  ws['!cols'] = keys.map((k) => {
    const longest = Math.max(k.length, ...rows.map((r) => String(r[k] ?? '').length));
    return { wch: Math.min(Math.max(longest + 2, 10), 60) };
  });
}

export function exportAnalysisToExcel(session) {
  const result = session.result;
  const v2 = result?.v2;
  if (!v2) return;

  const wb = XLSX.utils.book_new();

  // --- Overview ---
  const profile = v2.profile || {};
  const overviewRows = [
    { Field: 'File', Value: session.fileName },
    { Field: 'Detected domain', Value: profile.domain },
    { Field: 'Domain confidence', Value: profile.domain_confidence },
    { Field: 'Primary entity', Value: profile.primary_entity },
    { Field: 'Row count', Value: profile.row_count },
    { Field: 'Column count', Value: profile.column_count },
    { Field: 'Data completeness %', Value: profile.data_completeness_pct },
    { Field: 'Data quality score', Value: v2.data_quality?.overall_quality_score },
    { Field: 'Generated', Value: new Date().toLocaleString() },
  ];
  const overviewWs = sheetFromRows(overviewRows);
  autoWidth(overviewWs, overviewRows);
  XLSX.utils.book_append_sheet(wb, overviewWs, 'Overview');

  // --- Story ---
  if (v2.story?.length) {
    const rows = v2.story.map((b) => ({ Stage: b.label, Text: b.text }));
    const ws = sheetFromRows(rows);
    autoWidth(ws, rows);
    XLSX.utils.book_append_sheet(wb, ws, 'Story');
  }

  // --- Findings ---
  if (v2.findings?.length) {
    const rows = v2.findings.map((f) => ({ Finding: f.text, Category: f.category, Score: f.score }));
    const ws = sheetFromRows(rows);
    autoWidth(ws, rows);
    XLSX.utils.book_append_sheet(wb, ws, 'Findings');
  }

  // --- Weak Points ---
  if (v2.weak_points?.length) {
    const rows = v2.weak_points.map((w) => ({
      Problem: w.problem,
      Impact: w.impact,
      Priority: w.priority,
      'Suggested Action': w.suggested_action,
      Category: w.category,
    }));
    const ws = sheetFromRows(rows);
    autoWidth(ws, rows);
    XLSX.utils.book_append_sheet(wb, ws, 'Weak Points');
  }

  // --- Data Quality ---
  const dq = v2.data_quality;
  if (dq) {
    const missingRows = (dq.missing_by_column || []).map((m) => ({
      Column: m.column, 'Missing %': m.missing_pct,
    }));
    const summaryRows = [
      { Metric: 'Duplicate rows', Value: dq.duplicate_row_count },
      { Metric: 'Duplicate row %', Value: dq.duplicate_row_pct },
      { Metric: 'Constant columns', Value: (dq.constant_columns || []).join(', ') },
      { Metric: 'High-cardinality columns', Value: (dq.high_cardinality_columns || []).join(', ') },
      { Metric: 'Overall quality score (raw file)', Value: dq.overall_quality_score },
      { Metric: 'Usable data score (analyzed columns)', Value: dq.usable_quality_score },
      { Metric: 'Columns actually analyzed', Value: `${dq.usable_column_count ?? ''} of ${dq.total_column_count ?? ''}` },
    ];
    const rows = [...summaryRows.map((r) => ({ Column: r.Metric, 'Missing %': r.Value })), ...missingRows];
    const ws = sheetFromRows(rows);
    autoWidth(ws, rows);
    XLSX.utils.book_append_sheet(wb, ws, 'Data Quality');
  }

  // --- Correlations ---
  const cc = v2.correlation_center;
  if (cc?.pairs?.length) {
    const rows = cc.pairs.map((p) => ({
      'Column A': p.col1,
      'Column B': p.col2,
      r: p.r,
      n: p.n,
      'p-value': p.p_value,
      Significant: p.significant ? 'Yes' : 'No',
      Strength: p.strength,
      Caveat: p.caveat || '',
    }));
    const ws = sheetFromRows(rows);
    autoWidth(ws, rows);
    XLSX.utils.book_append_sheet(wb, ws, 'Correlations');

    const vifResults = cc.multicollinearity?.results;
    if (vifResults?.length) {
      const vifRows = vifResults.map((v) => ({
        Column: v.column, VIF: v.vif, Severity: v.severity, Note: v.note,
      }));
      const vifWs = sheetFromRows(vifRows);
      autoWidth(vifWs, vifRows);
      XLSX.utils.book_append_sheet(wb, vifWs, 'Multicollinearity');
    }
  }

  // --- Partial Correlations ---
  const pc = v2.partial_correlations;
  if (pc?.results?.length) {
    const rows = [];
    pc.results.forEach((r) => {
      if (r.robust) {
        rows.push({
          'Column A': r.col1, 'Column B': r.col2, 'Overall r': r.overall_r,
          'Controlling for': '', 'Partial r': '', Classification: 'robust', Note: r.summary,
        });
      } else {
        r.explained_by.forEach((e) => {
          rows.push({
            'Column A': r.col1, 'Column B': r.col2, 'Overall r': r.overall_r,
            'Controlling for': e.control, 'Partial r': e.partial_r, Classification: e.classification, Note: e.text,
          });
        });
      }
    });
    const ws = sheetFromRows(rows);
    autoWidth(ws, rows);
    XLSX.utils.book_append_sheet(wb, ws, 'Partial Correlations');
  }

  const safeName = (session.fileName || 'datalens-report').replace(/\.[^/.]+$/, '').replace(/[^\w\-]+/g, '_');
  XLSX.writeFile(wb, `${safeName}_report.xlsx`);
}
