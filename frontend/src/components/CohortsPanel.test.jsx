import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CohortsPanel from './CohortsPanel';
import { expectNoRawEscapes } from '../test/helpers';

const AT_RISK = {
  available: true, total_entities: 60, at_risk_count: 2, typical_return_days: 30,
  summary: '2 of 60 customers (3.3%) haven\'t returned in longer than usual.',
  at_risk: [
    { entity: 'C51', last_seen: '2024-02-01', days_since_last_seen: 120, overdue_ratio: 4, risk_level: 'high' },
    { entity: 'C52', last_seen: '2024-04-10', days_since_last_seen: 50, overdue_ratio: 1.7, risk_level: 'medium' },
  ],
};
const CURVE = {
  available: true, entity_noun: 'Customer', cohort_count: 3, avg_month1_retention_pct: 42.5,
  summary: 'About 43% come back the next month.', cohort_sizes: [{ cohort: '2024-01', size: 40 }, { cohort: '2024-02', size: 35 }],
};

describe('CohortsPanel', () => {
  it('explains what is missing when neither the curve nor the risk list can be built', () => {
    render(<CohortsPanel cohorts={{ available: false, note: 'Needs a customer ID and a date column.', at_risk: { available: false } }} tickNum="08" />);
    expect(screen.getByText('Needs a customer ID and a date column.')).toBeInTheDocument();
  });

  it('shows the retention curve and the at-risk list together', () => {
    const { container } = render(<CohortsPanel cohorts={{ ...CURVE, at_risk: AT_RISK }} tickNum="08" />);
    expect(screen.getByText('Month 1 Retention')).toBeInTheDocument();
    expect(screen.getByText('42.5%')).toBeInTheDocument();
    expect(screen.getByText('At Risk of Lapsing')).toBeInTheDocument();
    expect(screen.getByText('2 / 60')).toBeInTheDocument();
    expectNoRawEscapes(container);
  });

  it('still works when only the risk list is available (no cohort curve)', () => {
    render(<CohortsPanel cohorts={{ available: false, note: 'n/a', at_risk: AT_RISK }} tickNum="08" />);
    expect(screen.getByText(/overdue to return/i)).toBeInTheDocument();
    expect(screen.queryByText('Month 1 Retention')).not.toBeInTheDocument();
    expect(screen.getByText('At Risk of Lapsing')).toBeInTheDocument();
  });

  it('describes each overdue entity and tells a "likely lost" one apart from a "worth a check-in"', () => {
    const { container } = render(<CohortsPanel cohorts={{ available: false, at_risk: AT_RISK }} tickNum="08" />);
    const rows = container.querySelectorAll('.corr-list-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('C51');
    expect(rows[0]).toHaveTextContent('120 days ago (likely lost)');
    expect(rows[0]).toHaveTextContent('high');
    expect(rows[1]).toHaveTextContent('50 days ago (worth a check-in)');
  });

  it('lists no individuals when nobody is overdue', () => {
    const { container } = render(<CohortsPanel cohorts={{ available: false, at_risk: { ...AT_RISK, at_risk_count: 0, at_risk: [], summary: 'Everyone is within their usual window.' } }} tickNum="08" />);
    expect(screen.getByText('Everyone is within their usual window.')).toBeInTheDocument();
    expect(container.querySelectorAll('.corr-list-row')).toHaveLength(0);
  });
});
