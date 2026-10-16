import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PartialCorrelationsPanel from './PartialCorrelationsPanel';
import { expectNoRawEscapes } from '../test/helpers';

const ROBUST = { col1: 'Discount', col2: 'Profit', overall_r: -0.62, robust: true, controls_tested: 3, explained_by: [], summary: 'Discount and Profit remain correlated (r=-0.62) after controlling for the other 3 variables.' };
const EXPLAINED = {
  col1: 'Sales', col2: 'Quantity', overall_r: 0.8, robust: false, controls_tested: 2,
  summary: 'Most of the correlation between Sales and Quantity looks explained by Region.',
  explained_by: [
    { control: 'Region', partial_r: -0.02, text: 'Most of the correlation between Sales and Quantity looks explained by Region.', classification: 'mostly_explained' },
    { control: 'Segment', partial_r: 0.31, text: 'Part of the correlation between Sales and Quantity is explained by Segment.', classification: 'partially_explained' },
  ],
};

describe('PartialCorrelationsPanel', () => {
  it('shows the reason when it cannot run', () => {
    render(<PartialCorrelationsPanel partialCorrelations={{ available: false, note: 'Not enough other variables in this dataset to control for.', results: [] }} tickNum="08" />);
    expect(screen.getByText('Not enough other variables in this dataset to control for.')).toBeInTheDocument();
  });

  it('shows a generic explanation when it cannot run and gives no reason', () => {
    render(<PartialCorrelationsPanel partialCorrelations={null} tickNum="08" />);
    expect(screen.getByText(/Not enough correlated pairs or control variables/)).toBeInTheDocument();
  });

  it('a robust pair reads as holding up, with its overall r', () => {
    const { container } = render(<PartialCorrelationsPanel partialCorrelations={{ available: true, results: [ROBUST] }} tickNum="08" />);
    expect(screen.getByText('Discount ↔ Profit')).toBeInTheDocument();
    expect(screen.getByText('overall r=-0.62')).toBeInTheDocument();
    expect(screen.getByText(/remain correlated/)).toBeInTheDocument();
    expect(container.querySelectorAll('.corr-list-row')).toHaveLength(0);
    expectNoRawEscapes(container);
  });

  it('an explained pair leads with the strongest confound and lists the others beneath it', () => {
    const { container } = render(<PartialCorrelationsPanel partialCorrelations={{ available: true, results: [EXPLAINED] }} tickNum="08" />);
    expect(screen.getAllByText(/explained by Region/).length).toBeGreaterThan(0);
    const rest = container.querySelectorAll('.corr-list-row');
    expect(rest).toHaveLength(1); // only the second confound is itemised; the first is the summary
    expect(rest[0]).toHaveTextContent('controlling for Segment');
    expect(rest[0]).toHaveTextContent('0.31');
  });

  it('gives each result an id the global search can jump to', () => {
    const { container } = render(<PartialCorrelationsPanel partialCorrelations={{ available: true, results: [ROBUST, EXPLAINED] }} tickNum="08" />);
    expect(container.querySelector('#search-partial-correlation-0')).toBeInTheDocument();
    expect(container.querySelector('#search-partial-correlation-1')).toBeInTheDocument();
  });
});
