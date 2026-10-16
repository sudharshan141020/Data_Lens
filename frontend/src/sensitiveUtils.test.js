import { describe, it, expect } from 'vitest';
import { getSensitiveReport, needsGuard, defaultMaskSelection, maskV2 } from './sensitiveUtils';

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
