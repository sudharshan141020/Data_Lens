import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import DriversPanel from './DriversPanel';
import { expectNoRawEscapes } from '../test/helpers';

// Recharts draws nothing in jsdom (zero-size container), so a test that
// wants to know what the chart was GIVEN has to capture its inputs instead.
let lastBarData = null;
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Pass, CartesianGrid: () => null, XAxis: () => null, YAxis: () => null,
    Tooltip: () => null, ReferenceLine: () => null, Cell: () => null, Bar: () => null,
    BarChart: ({ data, children }) => { lastBarData = data; return <div data-testid="waterfall">{children}</div>; },
  };
});

const seg = (segment, change, share, move = 50) => ({ segment, before: 100, after: 100 + change, change, share_of_change_pct: share, share_of_movement_pct: move });
const DRIVERS = {
  available: true, metric: 'Sales', aggregation: 'sum', seasonally_adjusted_break: true,
  comparisons: [
    {
      id: 'latest_month', title: 'Latest month vs. the one before', best_dimension: 'Category',
      before: { label: '2024-05', months: 1, rows: 30, value: 400 }, after: { label: '2024-06', months: 1, rows: 30, value: 320 },
      change: -80, change_pct: -20,
      headline: 'Sales fell 20% from 2024-05 to 2024-06: 100% of the drop is Category=Furniture, mostly Region=West (88% of Furniture\'s change).',
      dimensions: [
        { dimension: 'Category', offsetting: false, other: null, segment_count: 2, concentration: 50, drill: null, segments: [seg('Furniture', -80, 100, 100), seg('Technology', 0, 0, 0)] },
        { dimension: 'Region', offsetting: false, other: { count: 3, change: -5 }, segment_count: 5, concentration: 30, drill: null, segments: [seg('West', -70, 87.5, 87.5), seg('East', -5, 6.2, 6.2)] },
      ],
    },
    {
      id: 'break', title: 'Before vs. after the detected break', best_dimension: 'Region',
      before: { label: '2023-01 \u2013 2023-06', months: 6, rows: 100, value: 200 }, after: { label: '2023-07 \u2013 2023-12', months: 6, rows: 100, value: 140 },
      change: -60, change_pct: -30, headline: 'Sales fell 30% between the two periods.',
      dimensions: [{ dimension: 'Region', offsetting: true, other: null, segment_count: 2, concentration: 40, drill: null, segments: [seg('West', -60, null, 90), seg('East', 0, null, 10)] }],
    },
  ],
};

describe('DriversPanel', () => {
  it('explains why it is empty instead of rendering nothing', () => {
    render(<DriversPanel drivers={{ available: false, note: 'Needs at least two calendar months of data.', comparisons: [] }} tickNum="05" />);
    expect(screen.getByText('Needs at least two calendar months of data.')).toBeInTheDocument();
    expect(screen.getByText('Why Did It Change?')).toBeInTheDocument();
  });

  it('has a generic explanation when the backend sent nothing at all (an older result)', () => {
    render(<DriversPanel drivers={undefined} />);
    expect(screen.getByText(/Needs a date column, a measure and at least one category column/)).toBeInTheDocument();
  });

  it('leads with the headline and the signed net change, before and after labels', () => {
    const { container } = render(<DriversPanel drivers={DRIVERS} />);
    expect(screen.getByText(/100% of the drop is Category=Furniture/)).toBeInTheDocument();
    expect(screen.getByText(/\u221280 \(-20%\)/)).toBeInTheDocument();
    expect(screen.getByText('2024-05 → 2024-06')).toBeInTheDocument();
    expectNoRawEscapes(container);
  });

  it('opens on the best dimension (starred) and feeds the chart the waterfall for it', () => {
    render(<DriversPanel drivers={DRIVERS} />);
    expect(screen.getByRole('tab', { name: /Category ★/ })).toHaveAttribute('aria-selected', 'true');
    expect(lastBarData.map((d) => d.name)).toEqual(['Furniture', 'Technology', 'Net change']);
    expect(lastBarData.at(-1).change).toBe(-80);
  });

  it('switching dimension re-draws the chart, shows folded-in values, and points back to the best split', () => {
    render(<DriversPanel drivers={DRIVERS} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Region' }));
    expect(lastBarData.map((d) => d.name)).toEqual(['West', 'East', 'Other (3)', 'Net change']);
    expect(screen.getByText(/3 smaller Region values together/)).toBeInTheDocument();
    expect(screen.getByText(/Category \(★\) is the split that concentrates the change most/)).toBeInTheDocument();
  });

  it('switching comparison resets to that comparison\'s own dimensions and shows the seasonal caveat only for the break', () => {
    render(<DriversPanel drivers={DRIVERS} />);
    expect(screen.queryByText(/seasonally adjusted series/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Before vs. after the detected break' }));
    expect(screen.getByText('Sales fell 30% between the two periods.')).toBeInTheDocument();
    expect(screen.getByText(/seasonally adjusted series/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Region ★/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('a single comparison shows no comparison switcher', () => {
    render(<DriversPanel drivers={{ ...DRIVERS, comparisons: [DRIVERS.comparisons[0]] }} />);
    expect(screen.queryByRole('tablist', { name: 'Comparison' })).not.toBeInTheDocument();
  });

  it('offsetting dimensions say shares are against the movement, and rows use that wording', () => {
    render(<DriversPanel drivers={DRIVERS} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Before vs. after the detected break' }));
    expect(screen.getByText(/shown against the total movement rather than against the net/)).toBeInTheDocument();
    expect(screen.getByText(/90% of the movement/)).toBeInTheDocument();
  });

  it('always states what it does not claim', () => {
    render(<DriversPanel drivers={DRIVERS} />);
    expect(screen.getByText(/where the change landed, not why it happened/)).toBeInTheDocument();
  });

  it('lists each segment with its signed change and share', () => {
    const { container } = render(<DriversPanel drivers={DRIVERS} />);
    const rows = container.querySelectorAll('.dq-bar-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Furniture')).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent('\u221280 · 100% of the change');
  });
});
