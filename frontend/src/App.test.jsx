import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
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
});
