import { describe, it, expect, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { render, screen, fireEvent } from '@testing-library/react';
import QueryBuilderPanel from './QueryBuilderPanel';
import { expectNoRawEscapes } from '../test/helpers';

// The chart itself (Recharts) can't lay out in jsdom, and what matters here
// is what the panel *asks* it to draw -- so capture its props instead.
vi.mock('./AnalysisChartV2', () => ({
  default: ({ analysis }) => (
    <div
      data-testid="chart"
      data-type={analysis.type}
      data-chart-type={analysis.chart_type}
      data-column={analysis.column}
      data-column2={analysis.column2 ?? ''}
      data-metric={analysis.metric_column ?? ''}
      data-data={JSON.stringify(analysis.data)}
    />
  ),
}));

const ROWS = [
  { Category: 'Furniture', Region: 'East', Sales: 100, Profit: 10 },
  { Category: 'Furniture', Region: 'West', Sales: 150, Profit: 20 },
  { Category: 'Tech', Region: 'East', Sales: 300, Profit: 90 },
  { Category: 'Tech', Region: 'West', Sales: 200, Profit: 40 },
];
const FILTERABLE = { available: true, dimension_columns: ['Category', 'Region'], measure_columns: ['Sales', 'Profit'] };

const chart = () => screen.getByTestId('chart');
const pick = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('QueryBuilderPanel', () => {
  it('hides itself when there is nothing to build a query from', () => {
    const { container, rerender } = render(<QueryBuilderPanel filterableData={{ available: false }} rows={[]} tickNum="04" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<QueryBuilderPanel filterableData={{ available: true, dimension_columns: [], measure_columns: ['Sales'] }} rows={[]} tickNum="04" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('starts with a useful default instead of an empty state: total of the first measure by the first dimension', () => {
    render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    expect(chart()).toHaveAttribute('data-type', 'distribution_sum');
    expect(chart()).toHaveAttribute('data-column', 'Category');
    expect(chart()).toHaveAttribute('data-metric', 'Sales');
    expect(JSON.parse(chart().dataset.data)[0]).toEqual({ label: 'Tech', value: 500 });
    expect(screen.getByText('Total of Sales, by Category')).toBeInTheDocument();
  });

  it('lets you pick a different measure, aggregation and dimension, and updates instantly', () => {
    render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    pick('Of', 'Profit');
    pick('Aggregation', 'avg');
    pick('Broken down by', 'Region');
    expect(chart()).toHaveAttribute('data-metric', 'Profit');
    expect(screen.getByText('Average of Profit, by Region')).toBeInTheDocument();
    expect(JSON.parse(chart().dataset.data)).toEqual([{ label: 'East', value: 50 }, { label: 'West', value: 30 }]);
  });

  it('"Count of records" drops the measure picker and reads naturally', () => {
    render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    pick('Aggregation', 'count');
    expect(screen.queryByLabelText('Of')).not.toBeInTheDocument();
    expect(chart()).toHaveAttribute('data-type', 'distribution_count');
    expect(chart()).toHaveAttribute('data-chart-type', 'donut'); // 2 categories -> donut, same rule as the auto-picked charts
    expect(screen.getByText('Count of records, by Category')).toBeInTheDocument();
  });

  it('a second dimension turns it into a cross-tab heatmap, and offers every dimension except the first', () => {
    render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    const second = screen.getByLabelText('And by (optional)');
    expect([...second.options].map((o) => o.value)).toEqual(['', 'Region']);
    pick('And by (optional)', 'Region');
    expect(chart()).toHaveAttribute('data-type', 'pivot');
    expect(chart()).toHaveAttribute('data-chart-type', 'heatmap');
    expect(chart()).toHaveAttribute('data-column2', 'Region');
    expect(screen.getByText('Total of Sales, by Category × Region')).toBeInTheDocument();
  });

  it('never ends up cross-tabbing a dimension against itself', () => {
    render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    pick('And by (optional)', 'Region');
    pick('Broken down by', 'Region'); // the first dimension becomes the one already chosen as the second
    expect(chart()).not.toHaveAttribute('data-chart-type', 'heatmap');
    expect(chart()).toHaveAttribute('data-column2', '');
  });

  it('has a real result on its very first paint (no flash of the empty state)', () => {
    // render() flushes effects before returning, so it can't see a first-paint flash.
    // Server-rendering runs no effects at all: it shows exactly what the first commit contains.
    const html = renderToString(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    expect(html).not.toContain('Pick a dimension above to see a result.');
    expect(html).toContain('data-testid="chart"');
  });

  it('re-initialises when a different dataset (different columns) is loaded into the same panel', () => {
    const { rerender } = render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    pick('Broken down by', 'Region');
    pick('And by (optional)', 'Category');

    const OTHER = { available: true, dimension_columns: ['Department'], measure_columns: ['Salary'] };
    const OTHER_ROWS = [{ Department: 'Eng', Salary: 100 }, { Department: 'Ops', Salary: 50 }];
    rerender(<QueryBuilderPanel filterableData={OTHER} rows={OTHER_ROWS} tickNum="04" />);

    expect(screen.getByText('Total of Salary, by Department')).toBeInTheDocument();
    expect(screen.queryByText('No rows match this combination.')).not.toBeInTheDocument();
    expect(chart()).toHaveAttribute('data-column', 'Department');
  });

  it('reflects the rows it is handed (e.g. after the dashboard filters are applied)', () => {
    const { rerender } = render(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS} tickNum="04" />);
    rerender(<QueryBuilderPanel filterableData={FILTERABLE} rows={ROWS.filter((r) => r.Region === 'East')} tickNum="04" />);
    expect(JSON.parse(chart().dataset.data)).toEqual([{ label: 'Tech', value: 300 }, { label: 'Furniture', value: 100 }]);
  });

  it('says so when no rows match instead of drawing an empty chart', () => {
    const { container } = render(<QueryBuilderPanel filterableData={FILTERABLE} rows={[]} tickNum="04" />);
    expect(screen.queryByTestId('chart')).not.toBeInTheDocument();
    expect(screen.getByText('No rows match this combination.')).toBeInTheDocument();
    expectNoRawEscapes(container);
  });
});
