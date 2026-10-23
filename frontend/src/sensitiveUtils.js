// Share / export guard for personal data.
//
// The backend scans the uploaded file and stores a column-level report in
// v2.sensitive_data (names, kinds, confidence -- never a raw value). This
// file decides what to do with that report right before data leaves the
// app: which columns to offer masking for, and how to produce a masked copy
// of the result.
//
// Masking is done here, on the client, deliberately: the share and export
// calls all go through api.js with a v2 object, so a masked v2 flows through
// all three paths (share link, HTML, PDF) with no backend change and no
// second masking implementation to keep in sync.
//
// What masking does to a flagged column:
//   * text values are replaced by stable pseudonyms ("Customer Name 7"):
//     the same real value always gets the same pseudonym, so filters,
//     groupings and counts in the shared copy still behave.
//   * the pseudonym replacement is applied to EVERY string in the result
//     (chart labels, findings text, free-text top words), not only to the
//     filterable rows -- otherwise "Top customers" would still name them.
//   * numeric ID columns are removed from the row-level data (they would
//     have to become strings, and a string in a measure column breaks the
//     shared view's maths); exact-match numeric labels in chart text are
//     still pseudonymized.
//
// Not a compliance tool: detection is heuristic and masking covers the
// columns the report found. The dialog says so.

export const CONFIDENCE_RANK = { low: 1, medium: 2, high: 3 };

export function getSensitiveReport(v2) {
  const r = v2?.sensitive_data;
  return r && Array.isArray(r.columns) ? r : null;
}

// True when there is something worth interrupting the user about. Columns
// the user already masked in this copy don't count again.
export function needsGuard(v2) {
  const r = getSensitiveReport(v2);
  return !!r && r.columns.some((c) => !c.masked);
}

// What the SERVER's own check found in the payload, shaped like the upload-time report so the
// same dialog can show it. Findings with no column (an email address sitting in the text of the
// result) cannot be masked by column; they are listed, and the choice is to continue or cancel.
export function reportFromServerFindings(findings) {
  const reasonFor = (f) => {
    if (f.source === 'text') return `${f.label} found in the text of the result`;
    if (f.source === 'values') return `the values look like a ${f.label}`;
    return `column name looks like a ${f.label}`;
  };
  return {
    has_sensitive: (findings || []).length > 0,
    from_server: true,
    columns: (findings || []).map((f) => ({
      column: f.column || `${f.label} in the result text`,
      kind: f.kind,
      label: f.label,
      confidence: f.confidence,
      numeric: false,
      maskable: Boolean(f.column) && f.maskable !== false,
      reason: reasonFor(f),
    })),
  };
}

// Columns pre-ticked in the dialog: medium and high confidence. "low"
// findings (a bare "Address" header, say) are listed but not pre-ticked,
// so the default doesn't wreck charts over a maybe.
export function defaultMaskSelection(report) {
  return (report?.columns || [])
    .filter((c) => !c.masked && c.maskable !== false && CONFIDENCE_RANK[c.confidence] >= CONFIDENCE_RANK.medium)
    .map((c) => c.column);
}

const MIN_SUBSTRING_LEN = 4; // shorter text values are replaced only when they are the whole string

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Distinct non-empty values of a column from the row-level data, as strings.
function distinctValues(rows, column) {
  const seen = new Set();
  for (const row of rows) {
    const v = row?.[column];
    if (v === null || v === undefined || v === '') continue;
    seen.add(String(v));
  }
  return [...seen];
}

// Returns a masked deep-enough copy of v2 plus a small summary. Never
// mutates the input (the live session keeps its real data).
export function maskV2(v2, columns) {
  const wanted = new Set(columns || []);
  if (!v2 || wanted.size === 0) return { v2, summary: { masked: [], pseudonyms: 0 } };

  const report = getSensitiveReport(v2);
  const fd = v2.filterable_data;
  const rows = Array.isArray(fd?.rows) ? fd.rows : [];

  // 1) one pseudonym map per masked column, from the real row-level values
  const exact = new Map();      // real value -> pseudonym (whole-string matches)
  const substrings = [];        // [realValue, pseudonym] for text values safe to replace inside sentences
  let counter = 0;
  const maskedNow = [];
  for (const column of wanted) {
    const finding = report?.columns.find((c) => c.column === column);
    const isNumeric = finding?.numeric === true;
    const label = String(column).trim();
    const values = distinctValues(rows, column);
    values.forEach((val, i) => {
      if (exact.has(val)) return;
      const pseudonym = `${label} ${i + 1}`;
      exact.set(val, pseudonym);
      counter += 1;
      if (!isNumeric && val.length >= MIN_SUBSTRING_LEN) substrings.push([val, pseudonym]);
    });
    maskedNow.push(column);
  }

  substrings.sort((a, b) => b[0].length - a[0].length); // longest first so "ann.lee@x.com" beats "ann"
  const capped = substrings.slice(0, 2000);
  const pattern = capped.length ? new RegExp(capped.map(([val]) => escapeRegExp(val)).join('|'), 'g') : null;
  const bySub = new Map(capped);

  const scrubString = (s) => {
    if (exact.has(s)) return exact.get(s);
    return pattern ? s.replace(pattern, (m) => bySub.get(m) ?? m) : s;
  };
  const scrub = (node) => {
    if (typeof node === 'string') return scrubString(node);
    if (Array.isArray(node)) return node.map(scrub);
    if (node && typeof node === 'object') {
      const out = {};
      for (const [k, val] of Object.entries(node)) out[k] = scrub(val);
      return out;
    }
    return node;
  };

  // 2) the row-level data: pseudonymize text columns, drop numeric ones
  const numericMasked = new Set(
    maskedNow.filter((c) => report?.columns.find((f) => f.column === c)?.numeric === true),
  );
  const maskedFd = fd
    ? {
        ...fd,
        rows: rows.map((row) => {
          const next = {};
          for (const [k, val] of Object.entries(row)) {
            if (numericMasked.has(k)) continue;
            if (wanted.has(k) && val !== null && val !== undefined && val !== '') next[k] = exact.get(String(val)) ?? val;
            else next[k] = val;
          }
          return next;
        }),
        dimension_columns: (fd.dimension_columns || []).filter((c) => !numericMasked.has(c)),
        measure_columns: (fd.measure_columns || []).filter((c) => !numericMasked.has(c)),
      }
    : fd;

  // 3) everything else in the result: string scrub (filterable_data handled above)
  const { filterable_data: _fd, sensitive_data: _sd, ...rest } = v2;
  const out = { ...scrub(rest) };
  if (fd !== undefined) out.filterable_data = maskedFd;

  // 4) free-text top words from a masked text column are dropped outright:
  //    word counts of free text can't be pseudonymized meaningfully
  if (Array.isArray(out.text_analysis?.results)) {
    out.text_analysis = {
      ...out.text_analysis,
      results: out.text_analysis.results.filter((r) => {
        const col = r?.column ?? r?.field ?? r?.name;
        return !(col && wanted.has(col));
      }),
    };
  }

  // 5) Places that carry real values of a masked column but that the row data
  //    can't help with. Learned the hard way: an identifier column such as
  //    "Customer ID" usually is NOT in the row-level data at all, so the
  //    pseudonym map above is empty for it -- yet its real values appear in
  //    the at-risk customer list, in scatter charts that plot it, in histogram
  //    labels, and in aggregates that reveal its range. These are handled by
  //    structure, not by matching values.
  const analysisTouches = (a) => [a?.metric_column, a?.column, a?.column2, a?.x_label, a?.y_label, a?.color_by]
    .some((c) => c && wanted.has(c));
  const keepAnalysis = (a) => {
    if (!analysisTouches(a)) return true;
    // A chart BY a text column whose real values we know stays (its labels were
    // pseudonymized above). Anything else that touches a masked column would
    // show raw values or ranges, so it is left out of the copy.
    const dims = [a.column, a.column2].filter((c) => c && wanted.has(c));
    const onlyKnownTextDims = dims.length > 0
      && ![a.metric_column, a.x_label, a.y_label, a.color_by].some((c) => c && wanted.has(c))
      && dims.every((c) => !numericMasked.has(c) && distinctValues(rows, c).length > 0);
    return onlyKnownTextDims;
  };
  for (const key of ['top_analyses', 'all_analyses']) {
    if (Array.isArray(out[key])) out[key] = out[key].filter(keepAnalysis);
  }

  const atRisk = out.cohorts?.at_risk;
  if (atRisk?.entity_column && wanted.has(atRisk.entity_column) && Array.isArray(atRisk.at_risk)) {
    const names = new Map();
    out.cohorts = {
      ...out.cohorts,
      at_risk: {
        ...atRisk,
        at_risk: atRisk.at_risk.map((r) => {
          const k = String(r.entity);
          if (!names.has(k)) names.set(k, `${atRisk.entity_column} ${names.size + 1}`);
          return { ...r, entity: names.get(k) };
        }),
      },
    };
  }

  if (Array.isArray(out.segments?.clusters)) {
    out.segments = {
      ...out.segments,
      clusters: out.segments.clusters.map((c) => ({
        ...c,
        averages: Object.fromEntries(Object.entries(c.averages || {}).filter(([k]) => !wanted.has(k))),
      })),
    };
  }
  if (Array.isArray(out.confidence_intervals?.intervals)) {
    out.confidence_intervals = {
      ...out.confidence_intervals,
      intervals: out.confidence_intervals.intervals.filter((i) => !wanted.has(i.measure)),
    };
  }
  if (Array.isArray(out.robustness?.kpis)) {
    out.robustness = { ...out.robustness, kpis: out.robustness.kpis.filter((k) => !wanted.has(k.measure)) };
  }
  if (Array.isArray(out.drivers?.comparisons)) {
    out.drivers = {
      ...out.drivers,
      comparisons: out.drivers.comparisons
        .filter((c) => !wanted.has(c.best_dimension))   // its headline would name real values
        .map((c) => ({ ...c, dimensions: c.dimensions.filter((d) => !wanted.has(d.dimension)) }))
        .filter((c) => c.dimensions.length > 0),
    };
    if (out.drivers.comparisons.length === 0) out.drivers = { available: false, note: 'Hidden because the result was split by a masked column.', comparisons: [] };
  }
  if (Array.isArray(out.data_quality?.outlier_summary)) {
    out.data_quality = { ...out.data_quality, outlier_summary: out.data_quality.outlier_summary.filter((o) => !wanted.has(o.column)) };
  }

  // 6) record what was masked (names only) so the copy is honest about itself
  // A column the first scan never reported (the server found it) is recorded too, so the copy
  // declares everything that was masked.
  const known = new Set((report?.columns || []).map((c) => c.column));
  const extra = maskedNow.filter((c) => !known.has(c)).map((column) => (
    { column, label: column, kind: 'unknown', confidence: 'medium', numeric: false, masked: true, reason: 'reported by the server' }));
  out.sensitive_data = {
    ...(report || { has_sensitive: true }),
    columns: [...(report?.columns || []).map((c) => (wanted.has(c.column) ? { ...c, masked: true } : c)), ...extra],
  };

  return { v2: out, summary: { masked: maskedNow, pseudonyms: counter } };
}
