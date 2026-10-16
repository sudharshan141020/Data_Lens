import { describe, it, expect, vi, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import {
  analyzeFile, analyzeCombined, analyzeJoined, compareFiles, loadSampleFile, SAMPLE_DATASETS,
  createShareLink, fetchSharedAnalysis, exportPdf, exportHtml, downloadCleanedCsv,
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
