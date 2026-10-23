import { describe, it, expect, vi, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import {
  analyzeFile, analyzeCombined, analyzeJoined, compareFiles, loadSampleFile, SAMPLE_DATASETS,
  createShareLink, fetchSharedAnalysis, exportPdf, exportHtml, exportCode, serializeFilters, runHypothesisTest, PersonalDataError, downloadCleanedCsv,
} from './api';

function reply({ ok = true, status = 200, body = {}, blob = new Blob(['x']), headers = {} } = {}) {
  return {
    ok, status,
    json: async () => body,
    blob: async () => blob,
    headers: { get: (k) => headers[k.toLowerCase()] ?? null },
  };
}
const stubFetch = (response) => {
  const fn = vi.fn().mockResolvedValue(response);
  vi.stubGlobal('fetch', fn);
  return fn;
};
const csv = (name) => new File(['a,b\n1,2'], name, { type: 'text/csv' });

describe('analyzeFile', () => {
  it('posts the file to /api/analyze and returns the parsed body', async () => {
    const fetchFn = stubFetch(reply({ body: { ok: 1 } }));
    const out = await analyzeFile(csv('a.csv'));
    expect(out).toEqual({ ok: 1 });
    const [url, init] = fetchFn.mock.calls[0];
    expect(url).toBe('/api/analyze');
    expect(init.method).toBe('POST');
    expect(init.body.get('file').name).toBe('a.csv');
    expect(init.body.has('column_overrides')).toBe(false);
  });

  it('sends column overrides as JSON only when there are some', async () => {
    const fetchFn = stubFetch(reply());
    await analyzeFile(csv('a.csv'), { Amount: 'FINANCIAL_METRIC' });
    expect(JSON.parse(fetchFn.mock.calls[0][1].body.get('column_overrides'))).toEqual({ Amount: 'FINANCIAL_METRIC' });
    await analyzeFile(csv('a.csv'), {});
    expect(fetchFn.mock.calls[1][1].body.has('column_overrides')).toBe(false);
  });

  it("surfaces the server's own message when it sends a string detail", async () => {
    stubFetch(reply({ ok: false, status: 400, body: { detail: 'File too large.' } }));
    await expect(analyzeFile(csv('a.csv'))).rejects.toThrow('File too large.');
  });

  it('falls back to a generic message for a FastAPI validation error (detail is a list)', async () => {
    stubFetch(reply({ ok: false, status: 422, body: { detail: [{ loc: ['body', 'file'], msg: 'field required' }] } }));
    await expect(analyzeFile(csv('a.csv'))).rejects.toThrow('The file could not be analyzed. Check that it is a valid file.');
  });
});

describe('multi-file endpoints', () => {
  it('analyzeCombined sends every file under "files"', async () => {
    const fetchFn = stubFetch(reply());
    await analyzeCombined([csv('a.csv'), csv('b.csv'), csv('c.csv')]);
    expect(fetchFn.mock.calls[0][0]).toBe('/api/analyze-combined');
    expect(fetchFn.mock.calls[0][1].body.getAll('files').map((f) => f.name)).toEqual(['a.csv', 'b.csv', 'c.csv']);
  });

  it('analyzeJoined sends exactly two files, in order, to /api/analyze-joined', async () => {
    const fetchFn = stubFetch(reply());
    await analyzeJoined(csv('orders.csv'), csv('customers.csv'));
    expect(fetchFn.mock.calls[0][0]).toBe('/api/analyze-joined');
    expect(fetchFn.mock.calls[0][1].body.getAll('files').map((f) => f.name)).toEqual(['orders.csv', 'customers.csv']);
  });

  it('analyzeJoined passes through the "no shared key" explanation so the user sees why', async () => {
    const detail = "Couldn't find a column shared between these two files that looks like a real join key.";
    stubFetch(reply({ ok: false, status: 400, body: { detail } }));
    await expect(analyzeJoined(csv('a.csv'), csv('b.csv'))).rejects.toThrow(detail);
  });

  it('each falls back to its own generic message', async () => {
    stubFetch(reply({ ok: false, status: 500, body: {} }));
    await expect(analyzeCombined([csv('a.csv')])).rejects.toThrow('The files could not be combined.');
    await expect(analyzeJoined(csv('a.csv'), csv('b.csv'))).rejects.toThrow('The files could not be joined.');
    await expect(compareFiles(csv('a.csv'), csv('b.csv'))).rejects.toThrow('The files could not be compared.');
  });

  it('compareFiles uses file_a / file_b', async () => {
    const fetchFn = stubFetch(reply());
    await compareFiles(csv('jan.csv'), csv('feb.csv'));
    const body = fetchFn.mock.calls[0][1].body;
    expect([body.get('file_a').name, body.get('file_b').name]).toEqual(['jan.csv', 'feb.csv']);
  });
});

describe('sample datasets', () => {
  it('each sample has a unique id and a .csv filename', () => {
    const ids = SAMPLE_DATASETS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    SAMPLE_DATASETS.forEach((s) => expect(s.filename).toMatch(/\.csv$/));
  });

  it.each(SAMPLE_DATASETS.map((s) => [s.filename]))('%s actually ships in public/ (otherwise the gallery button 404s)', (filename) => {
    expect(fs.existsSync(path.join(process.cwd(), 'public', filename))).toBe(true);
  });

  it('loadSampleFile fetches from the site root and returns a CSV File with that name', async () => {
    const fetchFn = stubFetch(reply({ blob: new Blob(['a,b\n1,2']) }));
    const file = await loadSampleFile('demo-sales-data.csv');
    expect(fetchFn).toHaveBeenCalledWith('/demo-sales-data.csv');
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe('demo-sales-data.csv');
    expect(file.type).toBe('text/csv');
  });

  it('loadSampleFile gives a friendly error when the file is missing', async () => {
    stubFetch(reply({ ok: false, status: 404 }));
    await expect(loadSampleFile('nope.csv')).rejects.toThrow('Could not load that sample dataset.');
  });
});

describe('share links', () => {
  beforeEach(() => { vi.stubGlobal('location', { ...window.location, origin: 'https://datalens.example' }); });

  it('builds an absolute URL from the origin and the returned path', async () => {
    const fetchFn = stubFetch(reply({ body: { share_path: '/s/abc123' } }));
    const url = await createShareLink('sales.csv', null, { a: 1 });
    expect(url).toBe('https://datalens.example/s/abc123');
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toMatchObject({ file_name: 'sales.csv', kpis: {} });
  });

  it('surfaces a string detail, and keeps the default message when the error body is not JSON', async () => {
    stubFetch(reply({ ok: false, status: 413, body: { detail: 'Too big to share.' } }));
    await expect(createShareLink('x', {}, {})).rejects.toThrow('Too big to share.');

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => { throw new SyntaxError('not json'); } }));
    await expect(createShareLink('x', {}, {})).rejects.toThrow('The share link could not be created.');
  });

  it('fetchSharedAnalysis explains an expired link by default', async () => {
    stubFetch(reply({ ok: false, status: 404, body: {} }));
    await expect(fetchSharedAnalysis('tok')).rejects.toThrow("This share link has expired or doesn't exist.");
  });
});

describe('exports', () => {
  let click;
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:fake');
    URL.revokeObjectURL = vi.fn();
    click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { click.lastDownload = this.download; });
  });

  const V2 = { findings: [1], weak_points: [2], filterable_data: { rows: new Array(1000).fill({}) } };

  it.each([['pdf', exportPdf, '/api/export/pdf'], ['html', exportHtml, '/api/export/html']])(
    '%s export never uploads the bulky client-only filterable_data, but keeps everything else',
    async (_name, fn, endpoint) => {
      const fetchFn = stubFetch(reply());
      await fn('Q3 Sales.csv', V2);
      expect(fetchFn.mock.calls[0][0]).toBe(endpoint);
      const sent = JSON.parse(fetchFn.mock.calls[0][1].body);
      expect(sent.file_name).toBe('Q3 Sales.csv');
      expect(sent.v2).toEqual({ findings: [1], weak_points: [2] });
    },
  );

  it('names the downloaded files from a sanitised version of the dataset name', async () => {
    stubFetch(reply());
    await exportPdf('Q3 Sales.csv', V2);
    expect(click.lastDownload).toBe('Q3_Sales_report.pdf');
    await exportHtml('Q3 Sales.csv', V2);
    expect(click.lastDownload).toBe('Q3_Sales_report.html');
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
  });

  it('shows the server message when an export fails', async () => {
    stubFetch(reply({ ok: false, status: 500, body: { detail: 'Renderer crashed.' } }));
    await expect(exportPdf('x', V2)).rejects.toThrow('Renderer crashed.');
    stubFetch(reply({ ok: false, status: 500, body: {} }));
    await expect(exportHtml('x', V2)).rejects.toThrow('The HTML report could not be generated.');
  });

  it('downloadCleanedCsv returns the cleaning summary from the response header and names the file', async () => {
    stubFetch(reply({ headers: { 'x-clean-summary': JSON.stringify({ rows_dropped: 3 }) } }));
    const summary = await downloadCleanedCsv(csv('raw.csv'), 'My Data.csv');
    expect(summary).toEqual({ rows_dropped: 3 });
    expect(click.lastDownload).toBe('My_Data_cleaned.csv');
  });

  it('a malformed summary header does not fail the download', async () => {
    stubFetch(reply({ headers: { 'x-clean-summary': '{not json' } }));
    await expect(downloadCleanedCsv(csv('raw.csv'), 'd.csv')).resolves.toBeNull();
  });
});

describe('serializeFilters', () => {
  it('turns the dashboard\'s Sets into arrays and keeps the date range', () => {
    expect(serializeFilters({ dateColumn: 'Order Date', dateFrom: '2024-01-01', dateTo: '2024-03-31', dimensionFilters: { Region: new Set(['West', 'East']) } }))
      .toEqual({ dateColumn: 'Order Date', dateFrom: '2024-01-01', dateTo: '2024-03-31', dimensionFilters: { Region: ['West', 'East'] } });
  });
  it('sends null when nothing is actually filtered (empty sets, blank dates, no filters at all)', () => {
    expect(serializeFilters(null)).toBeNull();
    expect(serializeFilters(undefined)).toBeNull();
    expect(serializeFilters({ dateFrom: '', dateTo: '', dimensionFilters: { Region: new Set(), Category: undefined } })).toBeNull();
  });
  it('drops empty dimension filters but keeps the ones with values, and a one-sided date range', () => {
    expect(serializeFilters({ dateColumn: 'D', dateFrom: '2024-05-01', dimensionFilters: { Region: new Set(), Category: new Set(['Tech']) } }))
      .toEqual({ dateColumn: 'D', dateFrom: '2024-05-01', dimensionFilters: { Category: ['Tech'] } });
  });
});

describe('exportCode', () => {
  let click;
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:fake');
    URL.revokeObjectURL = vi.fn();
    click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { click.lastDownload = this.download; });
  });
  const V2 = { findings: [1], filterable_data: { available: true, date_column: 'D', dimension_columns: ['Region'], rows: new Array(1000).fill({ Region: 'West' }) } };

  it('posts the result without the row data, plus the serialised filters', async () => {
    const fetchFn = stubFetch(reply());
    await exportCode('Q3 Sales.csv', V2, { dimensionFilters: { Region: new Set(['West']) } });
    expect(fetchFn.mock.calls[0][0]).toBe('/api/export/code');
    const sent = JSON.parse(fetchFn.mock.calls[0][1].body);
    expect(sent.file_name).toBe('Q3 Sales.csv');
    expect(sent.filters).toEqual({ dimensionFilters: { Region: ['West'] } });
    expect(sent.v2.findings).toEqual([1]);
    expect(sent.v2.filterable_data.rows).toEqual([]);           // rows are not uploaded...
    expect(sent.v2.filterable_data.dimension_columns).toEqual(['Region']);   // ...but the column names the script needs are
  });

  it('does not mutate the live result (the session keeps its rows)', async () => {
    stubFetch(reply());
    await exportCode('x.csv', V2, null);
    expect(V2.filterable_data.rows).toHaveLength(1000);
  });

  it('works when the result has no filterable_data at all', async () => {
    const fetchFn = stubFetch(reply());
    await exportCode('x.csv', { findings: [] }, null);
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toEqual({ file_name: 'x.csv', v2: { findings: [] }, filters: null });
  });

  it('names the file from a sanitised dataset name, ending in .py', async () => {
    stubFetch(reply());
    await exportCode('Q3 Sales (final).csv', V2, null);
    expect(click.lastDownload).toBe('Q3_Sales_final_datalens.py');
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  it('shows the server message when it fails, with a sensible default', async () => {
    stubFetch(reply({ ok: false, status: 500, body: { detail: 'Could not generate the script.' } }));
    await expect(exportCode('x', V2, null)).rejects.toThrow('Could not generate the script.');
    stubFetch(reply({ ok: false, status: 500, body: {} }));
    await expect(exportCode('x', V2, null)).rejects.toThrow('The script could not be generated.');
  });
});

describe('runHypothesisTest', () => {
  const PAYLOAD = { group_column: 'Region', outcome_column: 'Sales', group_a: 'West', group_b: 'East', groups: ['West', 'East'], outcomes: [1, 2], outcome_kind: 'auto', positive_level: null };

  it('posts the payload as JSON to the hypothesis endpoint and returns the result', async () => {
    const fetchFn = stubFetch(reply({ body: { available: true, significant: false } }));
    const out = await runHypothesisTest(PAYLOAD);
    expect(fetchFn.mock.calls[0][0]).toBe('/api/hypothesis-test');
    expect(fetchFn.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toEqual(PAYLOAD);
    expect(out).toEqual({ available: true, significant: false });
  });

  it('passes an "unusable question" answer through untouched (available:false is not an error)', async () => {
    stubFetch(reply({ body: { available: false, note: 'Needs at least 5 rows with a value in each group; East has 3.' } }));
    expect(await runHypothesisTest(PAYLOAD)).toEqual({ available: false, note: 'Needs at least 5 rows with a value in each group; East has 3.' });
  });

  it('turns a failed request into an Error with the server message, or a default', async () => {
    stubFetch(reply({ ok: false, status: 413, body: { detail: 'Too many rows for an interactive test.' } }));
    await expect(runHypothesisTest(PAYLOAD)).rejects.toThrow('Too many rows for an interactive test.');
    stubFetch(reply({ ok: false, status: 500, body: {} }));
    await expect(runHypothesisTest(PAYLOAD)).rejects.toThrow('The test could not be run.');
  });
});

describe('createShareLink and the server-side personal-data check', () => {
  it('sends exactly what it always did when nothing is acknowledged (no extra key)', async () => {
    const fetchFn = stubFetch(reply({ body: { share_path: '/share/abc' } }));
    await createShareLink('d.csv', { a: 1 }, { x: 1 });
    expect(JSON.parse(fetchFn.mock.calls[0][1].body)).toEqual({ file_name: 'd.csv', kpis: { a: 1 }, v2: { x: 1 } });
  });

  it('sends acknowledge_personal_data only when the person deliberately chose to share as is', async () => {
    const fetchFn = stubFetch(reply({ body: { share_path: '/share/abc' } }));
    await createShareLink('d.csv', {}, { x: 1 }, { acknowledge: true });
    expect(JSON.parse(fetchFn.mock.calls[0][1].body).acknowledge_personal_data).toBe(true);
    await createShareLink('d.csv', {}, { x: 1 }, { acknowledge: false });
    expect(JSON.parse(fetchFn.mock.calls[1][1].body)).not.toHaveProperty('acknowledge_personal_data');
  });

  it('turns the server\'s 409 into a PersonalDataError carrying the findings', async () => {
    const findings = [{ column: 'Customer ID', kind: 'person_id', label: 'person identifier', confidence: 'medium', source: 'header', maskable: true }];
    stubFetch(reply({ ok: false, status: 409, body: { detail: 'This result appears to contain personal data.', code: 'personal_data', findings } }));
    const err = await createShareLink('d.csv', {}, { x: 1 }).catch((e) => e);
    expect(err).toBeInstanceOf(PersonalDataError);
    expect(err.message).toBe('This result appears to contain personal data.');
    expect(err.findings).toEqual(findings);
  });

  it('any other failure, including a 409 that is not about personal data, stays an ordinary Error', async () => {
    stubFetch(reply({ ok: false, status: 409, body: { detail: 'Conflict of some other kind', code: 'other' } }));
    const err = await createShareLink('d.csv', {}, { x: 1 }).catch((e) => e);
    expect(err).not.toBeInstanceOf(PersonalDataError);
    expect(err.message).toBe('Conflict of some other kind');
    stubFetch(reply({ ok: false, status: 400, body: { detail: 'This analysis is too large to share (20.0MB, limit 15MB).' } }));
    await expect(createShareLink('d.csv', {}, { x: 1 })).rejects.toThrow('too large to share');
  });

  it('a malformed findings field does not break the error', () => {
    expect(new PersonalDataError('x', 'nope').findings).toEqual([]);
    expect(new PersonalDataError('x', undefined).findings).toEqual([]);
  });
});
