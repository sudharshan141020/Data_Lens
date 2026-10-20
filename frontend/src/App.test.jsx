import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act, within } from '@testing-library/react';
import App from './App';
import analysis from './test/fixtures/analysis.json';
import { expectNoRawEscapes } from './test/helpers';

// The whole app, rendered from a REAL backend response (captured by
// scripts/regenerate_frontend_fixture.py and kept honest by
// tests/test_frontend_fixture_contract.py). Only the network is faked.

function stubBackend() {
  const fetchFn = vi.fn(async (url) => {
    if (url === '/api/analyze') return { ok: true, status: 200, json: async () => analysis };
    return { ok: false, status: 404, json: async () => ({ detail: `unexpected request in test: ${url}` }) };
  });
  vi.stubGlobal('fetch', fetchFn);
  return fetchFn;
}

const escape = () => fireEvent.keyDown(window, { key: 'Escape' });
const onHeroPage = () => screen.queryByText('Automated Data Intelligence');

async function uploadSalesCsv() {
  const input = document.querySelector('input[type="file"]');
  const file = new File(['Order Date,Sales\n2024-01-01,1'], 'sales.csv', { type: 'text/csv' });
  fireEvent.change(input, { target: { files: [file] } });
  await screen.findByText('Ask Your Own Question', {}, { timeout: 8000 });
}

describe('App (integration, real backend response)', () => {
  it('starts on the landing page, and uploading a file produces the full dashboard from the real response', async () => {
    const fetchFn = stubBackend();
    const { container } = render(<App />);

    expect(onHeroPage()).toBeInTheDocument();
    expect(screen.getByText('Drop your data files here')).toBeInTheDocument();

    await uploadSalesCsv();

    expect(fetchFn).toHaveBeenCalledWith('/api/analyze', expect.objectContaining({ method: 'POST' }));
    expect(onHeroPage()).not.toBeInTheDocument();
    expect(screen.getByText('Key Analyses')).toBeInTheDocument();
    expect(screen.getByText('The Story')).toBeInTheDocument();
    expect(screen.getByText('Weak Points')).toBeInTheDocument();

    // real content from the captured response reached the screen
    expect(screen.getByText('Furniture is actually losing money')).toBeInTheDocument();
    expect(within(screen.getByRole('complementary')).getByText('sales.csv')).toBeInTheDocument();

    // and nothing anywhere on the page is a leaked escape sequence
    expectNoRawEscapes(container);
  });

  it('Present opens the walkthrough; Escape closes ONLY the walkthrough; a second Escape then goes home', async () => {
    stubBackend();
    render(<App />);
    await uploadSalesCsv();

    fireEvent.click(screen.getByRole('button', { name: /present/i }));
    expect(screen.getByRole('dialog', { name: /story presentation/i })).toBeInTheDocument();

    escape();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText('Ask Your Own Question')).toBeInTheDocument(); // still on the dashboard
    expect(onHeroPage()).not.toBeInTheDocument();

    escape();
    expect(onHeroPage()).toBeInTheDocument(); // now it navigates home
    expect(screen.queryByText('Ask Your Own Question')).not.toBeInTheDocument();
  });

  it('the DATALENS logo goes home but keeps the analysis in the sidebar, and re-opening it restores the dashboard', async () => {
    stubBackend();
    render(<App />);
    await uploadSalesCsv();

    fireEvent.click(screen.getByRole('button', { name: /datalens/i }));
    expect(onHeroPage()).toBeInTheDocument();
    const sidebar = screen.getByRole('complementary');
    fireEvent.click(within(sidebar).getByText('sales.csv'));
    expect(await screen.findByText('Ask Your Own Question')).toBeInTheDocument();
  });

  it('Escape does nothing while typing in a text field', async () => {
    stubBackend();
    render(<App />);
    await uploadSalesCsv();

    const field = document.createElement('input');
    document.body.appendChild(field);
    field.focus();
    escape();
    expect(onHeroPage()).not.toBeInTheDocument();
    field.remove();
  });

  it('the query builder re-queries the real data and relabels itself', async () => {
    stubBackend();
    render(<App />);
    await uploadSalesCsv();

    // It starts on the first measure by the first dimension the backend listed
    // (read from the response itself, not assumed).
    const { measure_columns: measures, dimension_columns: dims } = analysis.v2.filterable_data;
    expect(screen.getByText(`Total of ${measures[0]}, by ${dims[0]}`)).toBeInTheDocument();

    const other = dims[1];
    fireEvent.change(screen.getByLabelText('Broken down by'), { target: { value: other } });
    expect(screen.getByText(`Total of ${measures[0]}, by ${other}`)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Aggregation'), { target: { value: 'count' } });
    expect(screen.getByText(`Count of records, by ${other}`)).toBeInTheDocument();
  });

  it('save snapshot, then analysing the same data again, offers a "what changed" banner', async () => {
    stubBackend();
    render(<App />);
    await uploadSalesCsv();

    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /save snapshot/i }));
    expect(Object.keys(localStorage).some((k) => k.startsWith('datalens_snapshot::'))).toBe(true);

    escape(); // back to the landing page
    await uploadSalesCsv();
    expect(await screen.findByText(/updated version of/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'View what changed' }));
    expect(screen.getByText('Measures')).toBeInTheDocument();
  });

  it('Export > Python script downloads a script for the uploaded file, sending no row data', async () => {
    const fetchFn = vi.fn(async (url) => {
      if (url === '/api/analyze') return { ok: true, status: 200, json: async () => analysis };
      if (url === '/api/export/code') return { ok: true, status: 200, blob: async () => new Blob(['print(1)']) };
      return { ok: false, status: 404, json: async () => ({ detail: `unexpected request in test: ${url}` }) };
    });
    vi.stubGlobal('fetch', fetchFn);
    URL.createObjectURL = vi.fn(() => 'blob:fake');
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { click.lastDownload = this.download; });

    render(<App />);
    await uploadSalesCsv();

    fireEvent.click(screen.getByRole('button', { name: /export/i }));
    // the click starts an async chain (request, blob, download, state change); act() waits for all of it
    await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: /python script/i })); });
    await vi.waitFor(() => expect(fetchFn).toHaveBeenCalledWith('/api/export/code', expect.anything()));

    const sent = JSON.parse(fetchFn.mock.calls.find((c) => c[0] === '/api/export/code')[1].body);
    expect(sent.file_name).toBe('sales.csv');
    expect(sent.filters).toBeNull();
    expect(sent.v2.filterable_data.rows).toEqual([]);
    expect(sent.v2.top_analyses.length).toBeGreaterThan(0);
    await vi.waitFor(() => expect(click.lastDownload).toBe('sales_datalens.py'));
  });

  it('Test a Hypothesis sends only the two chosen groups\' rows and shows the verdict', async () => {
    const result = {
      available: true, kind: 'numeric', group_a: 'West', group_b: 'East', group_column: 'Region', outcome_column: 'Sales',
      test: { id: 'welch_t', name: "Welch's t-test", why: 'Both groups have at least 30 rows.' },
      statistic_label: 'Difference in means (B \u2212 A)', difference: 1, interval: [-1, 3], interval_method: '95% interval',
      p_value: 0.4, significant: false, effect_size: { name: "Cohen's d", value: 0.1, label: 'negligible' },
      stats: { West: { n: 3, mean: 1, median: 1, std: 1 }, East: { n: 3, mean: 2, median: 2, std: 1 } },
      cross_check: { test: 'Mann-Whitney U', p_value: 0.5, agrees: true },
      headline: 'No clear difference in Sales between West and East.', caveats: ['Assumes independent rows.'],
    };
    const fetchFn = vi.fn(async (url) => {
      if (url === '/api/analyze') return { ok: true, status: 200, json: async () => analysis };
      if (url === '/api/hypothesis-test') return { ok: true, status: 200, json: async () => result };
      return { ok: false, status: 404, json: async () => ({ detail: `unexpected request in test: ${url}` }) };
    });
    vi.stubGlobal('fetch', fetchFn);

    render(<App />);
    await uploadSalesCsv();

    expect(await screen.findByRole('heading', { name: 'Test a Hypothesis' })).toBeInTheDocument();
    expect(fetchFn).not.toHaveBeenCalledWith('/api/hypothesis-test', expect.anything());   // never runs by itself
    fireEvent.click(screen.getByRole('button', { name: /run test/i }));
    expect(await screen.findByText('No clear difference in Sales between West and East.')).toBeInTheDocument();

    const call = fetchFn.mock.calls.find((c) => c[0] === '/api/hypothesis-test');
    const sent = JSON.parse(call[1].body);
    expect(sent.groups.length).toBeGreaterThan(0);
    expect(new Set(sent.groups)).toEqual(new Set([sent.group_a, sent.group_b]));
    expect(sent.groups).toHaveLength(sent.outcomes.length);
    expect(Object.keys(sent)).not.toContain('rows');
  });
});
