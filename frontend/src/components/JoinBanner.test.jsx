import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import JoinBanner from './JoinBanner';
import { expectNoRawEscapes } from '../test/helpers';

const INFO = {
  fact_file: 'orders.csv', dimension_file: 'customers.csv',
  key_in_fact_file: 'Customer_ID', key_in_dimension_file: 'Customer_ID',
  total_rows: 902, matched_rows: 892, unmatched_rows: 10, match_rate_pct: 98.9,
  shared_column_names: ['Region'],
};

describe('JoinBanner', () => {
  it('renders nothing without join info', () => {
    const { container } = render(<JoinBanner info={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('explains what was joined, on which key, and how well it matched', () => {
    const { container } = render(<JoinBanner info={INFO} />);
    const text = container.textContent.replace(/\s+/g, ' ');
    expect(text).toContain('Joined orders.csv to customers.csv on Customer_ID');
    expect(text).toContain('892 of 902 rows matched (98.9%)');
    expect(text).toContain('10 kept with blank fields from the unmatched side');
    expectNoRawEscapes(container);
  });

  it('shows both key names only when the two files call the key different things', () => {
    const { container, rerender } = render(<JoinBanner info={INFO} />);
    expect(container.textContent).not.toContain('/');
    rerender(<JoinBanner info={{ ...INFO, key_in_dimension_file: 'CustID' }} />);
    expect(container.textContent).toContain('Customer_ID / CustID');
  });

  it('says nothing about unmatched rows when every row matched', () => {
    render(<JoinBanner info={{ ...INFO, matched_rows: 902, unmatched_rows: 0, match_rate_pct: 100 }} />);
    expect(screen.queryByText(/kept with blank fields/)).not.toBeInTheDocument();
  });

  it('pluralises the shared-column note and quotes each name', () => {
    const { container, rerender } = render(<JoinBanner info={INFO} />);
    expect(container.textContent).toContain('shared column name "Region" kept as separate');
    rerender(<JoinBanner info={{ ...INFO, shared_column_names: ['Region', 'Status'] }} />);
    expect(container.textContent).toContain('shared column names "Region", "Status" kept as separate');
    rerender(<JoinBanner info={{ ...INFO, shared_column_names: [] }} />);
    expect(container.textContent).not.toContain('shared column');
  });
});
