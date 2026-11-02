import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DeepDivePanel from './DeepDivePanel';
import fixture from '../test/fixtures/analysis.json';

const v2 = fixture.v2;
const FULL_HEADLINE = v2.drivers.comparisons[0].headline;
const FILTERED_HEADLINE = 'FILTERED HEADLINE: Sales fell 9% among the rows in view.';

const filteredReports = () => ({
  seasonality: { available: false, note: 'filtered seasonality note' },
  period_comparison: { available: false, note: 'filtered period note' },
  drivers: { ...v2.drivers, comparisons: [{ ...v2.drivers.comparisons[0], headline: FILTERED_HEADLINE }] },
  robustness: { available: false, note: 'filtered robustness note' },
});
const ready = { status: 'ready', rowsUsed: 54, reports: filteredReports(), note: null };
const open = (tab) => fireEvent.click(screen.getByText(tab));

describe('DeepDivePanel and the filter bar', () => {
  it('without filters it shows the upload-time reports and says nothing about filters', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={null} />);
    open('Patterns');
    expect(screen.getByText(FULL_HEADLINE)).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('with filters it shows the filtered reports instead, and says exactly which panels follow the filters', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={ready} totalRows={162} />);
    open('Patterns');
    expect(screen.getByText(FILTERED_HEADLINE)).toBeInTheDocument();
    expect(screen.queryByText(FULL_HEADLINE)).not.toBeInTheDocument();
    expect(screen.getByText('filtered period note')).toBeInTheDocument();
    expect(screen.getByText('filtered seasonality note')).toBeInTheDocument();
    const note = screen.getByRole('status');
    expect(note).toHaveTextContent('Filters are on.');
    expect(note).toHaveTextContent('Seasonality, Period Comparison, Why Did It Change? and Robustness describe the 54 of 162 rows you are looking at');
    expect(note).toHaveTextContent('The other panels here still describe the full dataset.');
  });

  it('the Robustness panel follows the filters too, with the same note on its tab', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={ready} totalRows={162} />);
    open('Precision & Text');
    expect(screen.getByText('filtered robustness note')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('54 of 162 rows');
  });

  it('panels that do not follow the filters are unchanged, and carry no note', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={ready} totalRows={162} />);
    open('Anomalies & Integrity');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('while an update is pending it shows a placeholder, never numbers for the previous filter', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={{ status: 'loading', reports: null, rowsUsed: null, note: null }} totalRows={162} />);
    open('Patterns');
    expect(screen.queryByText(FULL_HEADLINE)).not.toBeInTheDocument();
    expect(screen.queryByText(FILTERED_HEADLINE)).not.toBeInTheDocument();
    expect(screen.getAllByText('Updating for your filters…').length).toBeGreaterThanOrEqual(4);   // the note and one placeholder per panel
    expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(3);                       // seasonality, period comparison, drivers
  });

  it('if the update fails it falls back to the full-data reports and says so', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={{ status: 'error', reports: null, rowsUsed: null, note: 'The reports could not be updated for your filters.' }} totalRows={162} />);
    open('Patterns');
    expect(screen.getByText(FULL_HEADLINE)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('The reports could not be updated for your filters. Those four panels show the full dataset instead.');
  });

  it('if recompute is impossible it keeps the full-data reports and explains why', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={{ status: 'blocked', reports: null, rowsUsed: null, note: 'Re-analyse the file to enable them.' }} totalRows={162} />);
    open('Patterns');
    expect(screen.getByText(FULL_HEADLINE)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Re-analyse the file to enable them. Those four panels describe the full dataset.');
  });

  it('an idle state (filters just cleared) shows the upload-time reports again with no note', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={{ status: 'idle', reports: null, rowsUsed: null, note: null }} totalRows={162} />);
    open('Patterns');
    expect(screen.getByText(FULL_HEADLINE)).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('formats large row counts with separators', () => {
    render(<DeepDivePanel v2={v2} tickNum="08" filtered={{ ...ready, rowsUsed: 12345 }} totalRows={98765} />);
    open('Patterns');
    expect(screen.getByRole('status')).toHaveTextContent('12,345 of 98,765 rows');
  });
});
