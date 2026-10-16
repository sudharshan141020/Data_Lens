import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import WeakPointsPanel from './WeakPointsPanel';
import { makeWeakPoint } from '../test/fixtures';
import { expectNoRawEscapes } from '../test/helpers';

describe('WeakPointsPanel', () => {
  it('says so plainly when nothing stood out', () => {
    render(<WeakPointsPanel weakPoints={[]} tickNum="07" />);
    expect(screen.getByText(/Nothing stood out as a problem/)).toBeInTheDocument();
  });

  it('shows the problem, impact and suggested action with its priority', () => {
    render(<WeakPointsPanel tickNum="07" weakPoints={[makeWeakPoint({ priority: 'high' })]} />);
    expect(screen.getByText('Office Supplies is falling behind on Sales')).toBeInTheDocument();
    expect(screen.getByText(/25% lower than average/)).toBeInTheDocument();
    expect(screen.getByText(/Look into what makes Office Supplies different/)).toBeInTheDocument();
    expect(screen.getByText('High priority')).toBeInTheDocument();
  });

  it('tags a statistically-confirmed weak point "checked", an unconfirmed one "unconfirmed", and an ungated one with neither', () => {
    const { container } = render(
      <WeakPointsPanel tickNum="07" weakPoints={[
        makeWeakPoint({ problem: 'Confirmed', significant: true }),
        makeWeakPoint({ problem: 'Doubtful', significant: false }),
        makeWeakPoint({ problem: 'Not tested', significant: null }),
      ]}
      />,
    );
    expect(screen.getAllByText('checked ✓')).toHaveLength(1);
    expect(screen.getAllByText('unconfirmed')).toHaveLength(1);
    expect(container.querySelectorAll('.insight-card')).toHaveLength(3);
    expectNoRawEscapes(container);
  });

  it('gives every card an id the global search can scroll to', () => {
    const { container } = render(<WeakPointsPanel tickNum="07" weakPoints={[makeWeakPoint(), makeWeakPoint({ problem: 'B' })]} />);
    expect(container.querySelector('#search-weakpoint-0')).toBeInTheDocument();
    expect(container.querySelector('#search-weakpoint-1')).toBeInTheDocument();
  });
});
