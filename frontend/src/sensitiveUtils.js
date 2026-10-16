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

// Columns pre-ticked in the dialog: medium and high confidence. "low"
// findings (a bare "Address" header, say) are listed but not pre-ticked,
// so the default doesn't wreck charts over a maybe.
export function defaultMaskSelection(report) {
  return (report?.columns || [])
    .filter((c) => !c.masked && CONFIDENCE_RANK[c.confidence] >= CONFIDENCE_RANK.medium)
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

  // 5) record what was masked (names only) so the copy is honest about itself
  out.sensitive_data = report
    ? { ...report, columns: report.columns.map((c) => (wanted.has(c.column) ? { ...c, masked: true } : c)) }
    : undefined;

  return { v2: out, summary: { masked: maskedNow, pseudonyms: counter } };
}
