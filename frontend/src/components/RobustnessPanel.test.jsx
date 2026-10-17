import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import RobustnessPanel from './RobustnessPanel';
import { expectNoRawEscapes } from '../test/helpers';

const kpi = (over) => ({ measure: 'Amount', aggregation: 'avg', n: 200, n_flagged: 3, flagged_pct: 1.5, full: 188.5, trimmed: 100, change_pct: -46.9, flagged_share_pct: null, material: true, verdict: 'sensitive', note: 'Without the 3 extreme rows (1.5%), the average falls 46.9%.', ...over });
const corr = (over) => ({ col1: 'X', col2: 'Y', r_full: 0.95, r_trimmed: 0.05, n_full: 61, n_trimmed: 60, n_removed: 1, p_full: 0, p_trimmed: 0.7, delta: -0.9, verdict: 'lost_significance', material: true, note: 'Significant with all rows (r=+0.95), not significant without 1 extreme row (r=+0.05).', ...over });
const REPORT = {
  available: true, method: 'Rows outside the usual outlier fences are set aside and each number is recomputed.',
  overall: { verdict: 'sensitive', headline: 'Sensitive to extreme rows: 1 of 2 headline numbers move materially; 1 of 1 top correlation changes without them.' },
  kpis: [kpi({ measure: 'Calm', material: false, verdict: 'stable', n_flagged: 0, note: 'No extreme values, so nothing to set aside.', full: 50, trimmed: 50 }), kpi()],
  correlations: [corr()],
};

describe('RobustnessPanel', () => {
  it('explains why it is empty instead of rendering nothing', () => {
    render(<RobustnessPanel robustness={{ available: false, note: 'Needs at least 10 non-missing values in a measure.' }} />);
    expect(screen.getByText('Needs at least 10 non-missing values in a measure.')).toBeInTheDocument();
    expect(screen.getByText('Does This Hold Without the Outliers?')).toBeInTheDocument();
  });

  it('has a generic explanation for an older result with no robustness block', () => {
    render(<RobustnessPanel robustness={undefined} />);
    expect(screen.getByText(/Needs a numeric measure with enough data/)).toBeInTheDocument();
  });

  it('leads with the overall verdict and its headline', () => {
    const { container } = render(<RobustnessPanel robustness={REPORT} />);
    expect(screen.getByText(/Sensitive to extreme rows$/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 2 headline numbers move materially/)).toBeInTheDocument();
    expectNoRawEscapes(container);
  });

  it('a robust result says so with a check mark', () => {
    render(<RobustnessPanel robustness={{ ...REPORT, overall: { verdict: 'robust', headline: 'The headline numbers hold.' } }} />);
    expect(screen.getByText('✓ Robust')).toBeInTheDocument();
  });

  it('shows the full number, the trimmed number and how many rows were set aside', () => {
    render(<RobustnessPanel robustness={REPORT} />);
    const card = screen.getByText('Amount').closest('.insight-card');
    expect(card).toHaveTextContent('188.5 → 100');
    expect(card).toHaveTextContent('without 3 extreme rows');
    expect(within(card).getByText('Moves')).toBeInTheDocument();
  });

  it('puts the findings that matter above the ones that pass', () => {
    const { container } = render(<RobustnessPanel robustness={REPORT} />);
    const names = [...container.querySelectorAll('.insight-card .insight-type')].map((n) => n.textContent);
    expect(names.indexOf('Amount (average)')).toBeLessThan(names.indexOf('Calm (average)'));
  });

  it('a measure with nothing set aside shows just its value, not a pointless arrow', () => {
    render(<RobustnessPanel robustness={REPORT} />);
    const card = screen.getByText('Calm').closest('.insight-card');
    expect(card).not.toHaveTextContent('→');
    expect(card).toHaveTextContent('Holds');
  });

  it('labels a total as a total and an average as an average', () => {
    render(<RobustnessPanel robustness={{ ...REPORT, kpis: [kpi({ aggregation: 'sum', verdict: 'concentrated' })] }} />);
    expect(screen.getByText('(total)')).toBeInTheDocument();
    expect(screen.getByText('Concentrated')).toBeInTheDocument();
  });

  it('shows each correlation before and after with a real minus sign and the verdict', () => {
    render(<RobustnessPanel robustness={{ ...REPORT, correlations: [corr({ verdict: 'flips', r_full: 0.4, r_trimmed: -0.3, note: 'The sign reverses.' })] }} />);
    const card = screen.getByText('X × Y').closest('.insight-card');
    expect(card).toHaveTextContent('r +0.40 → \u22120.30');
    expect(card).toHaveTextContent('1 row set aside');
    expect(within(card).getByText('Reverses')).toBeInTheDocument();
  });

  it('a correlation with no extreme rows shows one value and says so', () => {
    render(<RobustnessPanel robustness={{ ...REPORT, correlations: [corr({ n_removed: 0, r_trimmed: 0.95, verdict: 'holds', material: false, note: 'No extreme rows in either column, so nothing changes.' })] }} />);
    const card = screen.getByText('X × Y').closest('.insight-card');
    expect(card).not.toHaveTextContent('→');
    expect(card).toHaveTextContent('no extreme rows');
  });

  it('an "unclear" correlation (too few rows left) renders without a trimmed value', () => {
    render(<RobustnessPanel robustness={{ ...REPORT, correlations: [corr({ verdict: 'insufficient', r_trimmed: null })] }} />);
    const card = screen.getByText('X × Y').closest('.insight-card');
    expect(card).toHaveTextContent('Unclear');
    expect(card).not.toHaveTextContent('→');
  });

  it('hides the correlations section when there are none', () => {
    render(<RobustnessPanel robustness={{ ...REPORT, correlations: [] }} />);
    expect(screen.queryByText('Top correlations')).not.toBeInTheDocument();
  });

  it('states the method and that extreme rows are not errors', () => {
    render(<RobustnessPanel robustness={REPORT} />);
    expect(screen.getByText(/set aside and each number is recomputed/)).toBeInTheDocument();
    expect(screen.getByText(/Extreme rows are not errors/)).toBeInTheDocument();
  });
});
