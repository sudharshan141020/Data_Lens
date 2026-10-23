import { describe, it, expect } from 'vitest';
import { getSensitiveReport, needsGuard, defaultMaskSelection, maskV2, reportFromServerFindings } from './sensitiveUtils';
import fixture from './test/fixtures/analysis.json';

const report = (columns) => ({ has_sensitive: columns.length > 0, risk: 'high', columns });
const email = { column: 'Email', label: 'email address', kind: 'email', confidence: 'high', numeric: false, reason: 'x' };
const custId = { column: 'Customer ID', label: 'person identifier', kind: 'person_id', confidence: 'medium', numeric: true, reason: 'x' };
const address = { column: 'Address', label: 'street address', kind: 'address', confidence: 'low', numeric: false, reason: 'x' };

function makeV2() {
  return {
    findings: [{ text: 'Top buyer ann.lee@corp.com spent 40 (customer 1033)' }],
    top_analyses: [{ title: 'Sales by Email', data: [{ label: 'ann.lee@corp.com', value: 5 }, { label: 'bo@y.org', value: 7 }] }],
    sensitive_data: report([email, custId, address]),
    filterable_data: {
      available: true,
      dimension_columns: ['Email', 'Region'],
      measure_columns: ['Sales', 'Customer ID'],
      rows: [
        { Email: 'ann.lee@corp.com', 'Customer ID': 1033, Sales: 5, Region: 'East' },
        { Email: 'bo@y.org', 'Customer ID': 1034, Sales: 7, Region: 'West' },
        { Email: 'ann.lee@corp.com', 'Customer ID': 1033, Sales: 9, Region: 'East' },
      ],
    },
  };
}

describe('getSensitiveReport / needsGuard', () => {
  it('is null / false when the backend sent no report (older result, shared view)', () => {
    expect(getSensitiveReport({})).toBeNull();
    expect(getSensitiveReport(undefined)).toBeNull();
    expect(needsGuard({})).toBe(false);
  });
  it('is false when the scan found nothing', () => {
    expect(needsGuard({ sensitive_data: report([]) })).toBe(false);
  });
  it('is true when there are unmasked findings, false once every one is masked', () => {
    expect(needsGuard(makeV2())).toBe(true);
    const done = { sensitive_data: report([{ ...email, masked: true }]) };
    expect(needsGuard(done)).toBe(false);
  });
});

describe('defaultMaskSelection', () => {
  it('pre-ticks medium and high confidence, leaves low unticked', () => {
    expect(defaultMaskSelection(makeV2().sensitive_data)).toEqual(['Email', 'Customer ID']);
  });
  it('skips columns already masked and tolerates a missing report', () => {
    expect(defaultMaskSelection(report([{ ...email, masked: true }, custId]))).toEqual(['Customer ID']);
    expect(defaultMaskSelection(null)).toEqual([]);
  });
});

describe('maskV2', () => {
  it('returns the input untouched when there is nothing to mask', () => {
    const v2 = makeV2();
    expect(maskV2(v2, []).v2).toBe(v2);
  });

  it('never mutates the original (the live session keeps its real data)', () => {
    const v2 = makeV2();
    const before = JSON.stringify(v2);
    maskV2(v2, ['Email', 'Customer ID']);
    expect(JSON.stringify(v2)).toBe(before);
  });

  it('pseudonymizes text columns consistently: same real value -> same placeholder', () => {
    const { v2 } = maskV2(makeV2(), ['Email']);
    const emails = v2.filterable_data.rows.map((r) => r.Email);
    expect(emails[0]).toBe(emails[2]);
    expect(emails[0]).not.toBe(emails[1]);
    expect(emails.join()).not.toMatch(/@/);
  });

  it('removes a masked numeric ID column from the row data and from the column lists', () => {
    const { v2 } = maskV2(makeV2(), ['Customer ID']);
    expect(v2.filterable_data.rows.every((r) => !('Customer ID' in r))).toBe(true);
    expect(v2.filterable_data.measure_columns).toEqual(['Sales']);
    expect(v2.filterable_data.dimension_columns).toEqual(['Email', 'Region']);
  });

  it('scrubs the real values everywhere else in the result: chart labels and sentences', () => {
    const { v2 } = maskV2(makeV2(), ['Email', 'Customer ID']);
    const blob = JSON.stringify(v2);
    expect(blob).not.toContain('ann.lee@corp.com');
    expect(blob).not.toContain('bo@y.org');
    expect(v2.findings[0].text).toMatch(/^Top buyer Email \d+ spent 40/);
  });

  it('only replaces a numeric ID when it is the whole string, never inside other numbers', () => {
    const v2 = makeV2();
    v2.findings = [{ text: 'Total 10330 across 1033 orders' }, { text: '1033' }];
    const out = maskV2(v2, ['Customer ID']).v2;
    expect(out.findings[0].text).toBe('Total 10330 across 1033 orders');
    expect(out.findings[1].text).toMatch(/^Customer ID \d+$/);
  });

  it('leaves unrelated columns and numbers alone', () => {
    const { v2 } = maskV2(makeV2(), ['Email']);
    expect(v2.filterable_data.rows.map((r) => r.Sales)).toEqual([5, 7, 9]);
    expect(v2.filterable_data.rows.map((r) => r.Region)).toEqual(['East', 'West', 'East']);
  });

  it('marks the masked columns in the copy so it does not warn a second time', () => {
    const { v2, summary } = maskV2(makeV2(), ['Email']);
    expect(v2.sensitive_data.columns.find((c) => c.column === 'Email').masked).toBe(true);
    expect(v2.sensitive_data.columns.find((c) => c.column === 'Customer ID').masked).toBeUndefined();
    expect(summary.masked).toEqual(['Email']);
  });

  it('does not let a regex-special value break the scrub', () => {
    const v2 = makeV2();
    v2.filterable_data.rows[0].Email = 'a+b(c)[d]@x.com';
    v2.findings = [{ text: 'contact a+b(c)[d]@x.com today' }];
    const out = maskV2(v2, ['Email']).v2;
    expect(out.findings[0].text).not.toContain('a+b(c)');
  });

  it('prefers the longer value when one real value contains another', () => {
    const v2 = makeV2();
    v2.filterable_data.rows = [{ Email: 'ann@x.com' }, { Email: 'ann@x.com.au' }];
    v2.findings = [{ text: 'see ann@x.com.au' }];
    const out = maskV2(v2, ['Email']).v2;
    expect(out.findings[0].text).not.toMatch(/\.au|@/);
  });

  it('drops free-text results that belong to a masked column', () => {
    const v2 = makeV2();
    v2.text_analysis = { available: true, results: [{ column: 'Email', top_words: ['x'] }, { column: 'Notes', top_words: ['y'] }] };
    const out = maskV2(v2, ['Email']).v2;
    expect(out.text_analysis.results.map((r) => r.column)).toEqual(['Notes']);
  });

  it('works when the result has no row-level data at all', () => {
    const v2 = { findings: [{ text: 'x' }], sensitive_data: report([email]) };
    const out = maskV2(v2, ['Email']).v2;
    expect(out.filterable_data).toBeUndefined();
    expect(out.sensitive_data.columns[0].masked).toBe(true);
  });
});


// Regression for a leak the end-to-end test found: an identifier column like
// "Customer ID" is usually NOT in the row-level data, so masking by value did
// nothing, yet its real values were in the at-risk list and in scatter charts.
// These run against the real captured analysis, not a hand-built one.
describe('maskV2 on the real analysis: identifier columns that are not in the row data', () => {
  const v2 = fixture.v2;
  const masked = () => maskV2(v2, ['Customer ID']).v2;
  const realIds = new Set(v2.cohorts.at_risk.at_risk.map((r) => r.entity));

  it('the premise holds: real ids appear as raw NUMBERS in places the old string-matching never touched', () => {
    expect(v2.sensitive_data.columns.some((c) => c.column === 'Customer ID' && c.numeric)).toBe(true);
    expect(realIds.size).toBeGreaterThan(0);
    expect(typeof v2.cohorts.at_risk.at_risk[0].entity).toBe('number');                       // not a string: never matched
    const scatter = v2.all_analyses.find((a) => a.id === 'corr_sales_customer_id');
    expect(scatter.data.some((p) => realIds.has(p.y) || (p.y >= 1000 && p.y <= 1039))).toBe(true);   // plotted as raw y values
  });

  it('no real id survives in the at-risk list: each is replaced by a stable placeholder', () => {
    const list = masked().cohorts.at_risk.at_risk;
    expect(list).toHaveLength(v2.cohorts.at_risk.at_risk.length);
    expect(list.every((r) => /^Customer ID \d+$/.test(r.entity))).toBe(true);
    expect(new Set(list.map((r) => r.entity)).size).toBe(realIds.size);       // distinct stays distinct
    expect(list[0].days_since_last_seen).toBe(v2.cohorts.at_risk.at_risk[0].days_since_last_seen);   // the useful fields are kept
  });

  it('charts that plot the identifier (scatter points, histogram) are left out of the copy', () => {
    const out = masked();
    for (const list of [out.top_analyses, out.all_analyses]) {
      expect(list.some((a) => [a.metric_column, a.column, a.column2, a.x_label, a.y_label].includes('Customer ID'))).toBe(false);
    }
    expect(out.all_analyses.find((a) => a.id === 'hist_customer_id')).toBeUndefined();
    expect(out.all_analyses.find((a) => a.id === 'corr_sales_customer_id')).toBeUndefined();
  });

  it('aggregates that would reveal the id range are dropped too (cluster averages, interval, robustness fences)', () => {
    const out = masked();
    expect(out.segments.clusters.every((c) => !('Customer ID' in c.averages))).toBe(true);
    expect(out.confidence_intervals.intervals.some((i) => i.measure === 'Customer ID')).toBe(false);
    expect(out.robustness.kpis.some((k) => k.measure === 'Customer ID')).toBe(false);
  });

  it('nothing in the whole copy looks like a customer id value any more', () => {
    const body = JSON.stringify(masked());
    expect(body).not.toMatch(/"(entity|x|y)":10[0-3]\d(?=[,}])/);
    for (const id of realIds) expect(body).not.toContain(`"entity":${id}`);
  });

  it('leaves everything unrelated to the masked column exactly as it was', () => {
    const out = masked();
    const same = (id) => JSON.stringify(out.all_analyses.find((a) => a.id === id)) === JSON.stringify(v2.all_analyses.find((a) => a.id === id));
    expect(same('sum_region')).toBe(true);
    expect(same('trend_sales')).toBe(true);
    expect(same('pivot_region_category')).toBe(true);
    expect(out.findings).toEqual(v2.findings);
    const withoutId = v2.filterable_data.rows.map(({ ['Customer ID']: _id, ...rest }) => rest);   // the masked numeric column is removed from the rows, nothing else
    expect(out.filterable_data.rows).toEqual(withoutId);
  });

  it('the same holds when the identifier is NOT in the row data at all (the common case for real files)', () => {
    const noRows = JSON.parse(JSON.stringify(v2));
    noRows.filterable_data.rows = noRows.filterable_data.rows.map(({ ['Customer ID']: _id, ...rest }) => rest);
    noRows.filterable_data.measure_columns = noRows.filterable_data.measure_columns.filter((c) => c !== 'Customer ID');
    const out = maskV2(noRows, ['Customer ID']).v2;
    expect(JSON.stringify(out)).not.toMatch(/"(entity|x|y)":10[0-3]\d(?=[,}])/);
    expect(out.cohorts.at_risk.at_risk.every((r) => /^Customer ID \d+$/.test(r.entity))).toBe(true);
    expect(out.all_analyses.some((a) => a.id === 'corr_sales_customer_id')).toBe(false);
  });

  it('does not mutate the live result', () => {
    const before = JSON.stringify(v2);
    masked();
    expect(JSON.stringify(v2)).toBe(before);
  });

  it('a driver split BY a masked column is dropped rather than shown with its real values', () => {
    const synthetic = {
      sensitive_data: { columns: [{ column: 'Region', label: 'x', confidence: 'high', numeric: false }] },
      filterable_data: { rows: [{ Region: 'West' }, { Region: 'East' }], dimension_columns: ['Region'], measure_columns: [] },
      drivers: { available: true, comparisons: [
        { id: 'a', best_dimension: 'Region', headline: 'Sales fell: 80% of the drop is Region=West.', dimensions: [{ dimension: 'Region' }] },
        { id: 'b', best_dimension: 'Category', headline: 'ok', dimensions: [{ dimension: 'Category' }, { dimension: 'Region', segments: [{ segment: 'West' }] }] },
      ] },
    };
    const out = maskV2(synthetic, ['Region']).v2;
    expect(out.drivers.comparisons.map((c) => c.id)).toEqual(['b']);
    expect(out.drivers.comparisons[0].dimensions.map((d) => d.dimension)).toEqual(['Category']);
    expect(JSON.stringify(out)).not.toContain('West');
  });

  it('when nothing is left of the drivers, says why instead of showing an empty panel', () => {
    const synthetic = {
      sensitive_data: { columns: [{ column: 'Region', label: 'x', confidence: 'high', numeric: false }] },
      drivers: { available: true, comparisons: [{ id: 'a', best_dimension: 'Region', headline: 'x', dimensions: [{ dimension: 'Region' }] }] },
    };
    const out = maskV2(synthetic, ['Region']).v2;
    expect(out.drivers.available).toBe(false);
    expect(out.drivers.note).toMatch(/masked column/);
  });

  it('a text column whose values ARE known keeps its charts, with pseudonymized labels', () => {
    const synthetic = {
      sensitive_data: { columns: [{ column: 'Email', label: 'email address', confidence: 'high', numeric: false }] },
      filterable_data: { rows: [{ Email: 'ann.lee@corp.com', Sales: 1 }], dimension_columns: ['Email'], measure_columns: ['Sales'] },
      top_analyses: [{ id: 'sum_email', column: 'Email', metric_column: 'Sales', data: [{ label: 'ann.lee@corp.com', value: 1 }] }],
      all_analyses: [{ id: 'sum_email', column: 'Email', metric_column: 'Sales', data: [{ label: 'ann.lee@corp.com', value: 1 }] }],
    };
    const out = maskV2(synthetic, ['Email']).v2;
    expect(out.all_analyses).toHaveLength(1);
    expect(out.all_analyses[0].data[0].label).toMatch(/^Email \d+$/);
    expect(JSON.stringify(out)).not.toContain('ann.lee');
  });

  it('a chart by a text column whose values are NOT in the rows cannot be pseudonymized, so it is left out', () => {
    const synthetic = {
      sensitive_data: { columns: [{ column: 'Full Name', label: 'person name', confidence: 'medium', numeric: false }] },
      filterable_data: { rows: [{ Region: 'West' }], dimension_columns: ['Region'], measure_columns: [] },
      all_analyses: [{ id: 'count_name', column: 'Full Name', data: [{ label: 'Asha Rao', value: 3 }] }, { id: 'count_region', column: 'Region', data: [] }],
    };
    const out = maskV2(synthetic, ['Full Name']).v2;
    expect(out.all_analyses.map((a) => a.id)).toEqual(['count_region']);
    expect(JSON.stringify(out)).not.toContain('Asha');
  });
});


describe('findings reported by the server', () => {
  const FINDINGS = [
    { column: 'Contact', kind: 'email', label: 'email address', confidence: 'high', source: 'values', maskable: true },
    { column: 'Patient ID', kind: 'person_id', label: 'person identifier', confidence: 'medium', source: 'header', maskable: true },
    { column: null, kind: 'email', label: 'email address', confidence: 'high', source: 'text', maskable: false },
  ];

  it('become a report the same dialog can show, with a plain reason for each source of evidence', () => {
    const r = reportFromServerFindings(FINDINGS);
    expect(r.from_server).toBe(true);
    expect(r.columns.map((c) => c.reason)).toEqual([
      'the values look like a email address', 'column name looks like a person identifier', 'email address found in the text of the result',
    ]);
  });

  it('a finding with no column cannot be masked and is labelled by what it is', () => {
    const [, , text] = reportFromServerFindings(FINDINGS).columns;
    expect(text.column).toBe('email address in the result text');
    expect(text.maskable).toBe(false);
  });

  it('only maskable, medium-or-high findings are pre-ticked', () => {
    expect(defaultMaskSelection(reportFromServerFindings(FINDINGS))).toEqual(['Contact', 'Patient ID']);
  });

  it('copes with nothing at all', () => {
    expect(reportFromServerFindings(undefined)).toMatchObject({ has_sensitive: false, columns: [] });
  });

  it('masking a column the first scan never reported records it as masked in the copy', () => {
    const v2 = { sensitive_data: { columns: [{ column: 'Customer ID', label: 'x', confidence: 'medium', numeric: true }] },
      filterable_data: { rows: [{ Contact: 'ann@x.org' }, { Contact: 'bo@y.org' }], dimension_columns: ['Contact'], measure_columns: [] } };
    const out = maskV2(v2, ['Contact']).v2;
    const entry = out.sensitive_data.columns.find((c) => c.column === 'Contact');
    expect(entry).toMatchObject({ masked: true, reason: 'reported by the server' });
    expect(out.sensitive_data.columns.find((c) => c.column === 'Customer ID').masked).toBeUndefined();   // untouched
    expect(JSON.stringify(out)).not.toContain('ann@x.org');
  });

  it('masking works even when the result had no report at all', () => {
    const v2 = { filterable_data: { rows: [{ Contact: 'ann@x.org' }], dimension_columns: ['Contact'], measure_columns: [] } };
    const out = maskV2(v2, ['Contact']).v2;
    expect(out.sensitive_data.columns).toHaveLength(1);
    expect(needsGuard(out)).toBe(false);                      // everything reported is masked, so no second warning
  });
});
