import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DriftBanner from './DriftBanner';
import { saveSnapshot, findMatchingSnapshot, computeDrift } from '../snapshotUtils';
import { makeSession, makeWeakPoint, salesRows } from '../test/fixtures';
import { expectNoRawEscapes } from '../test/helpers';

// Built with the real snapshot functions, so this exercises the banner
// against exactly the drift shape the app produces, not a hand-rolled one.
function realDriftScenario() {
  saveSnapshot(makeSession({
    fileName: 'jan.csv', rows: salesRows(100),
    weakPoints: [
      makeWeakPoint({ problem: 'Resolved one', priority: 'medium' }),
      makeWeakPoint({ problem: 'Gets worse', priority: 'low' }),
      makeWeakPoint({ problem: 'Gets better', priority: 'high' }),
    ],
  }));
  const feb = makeSession({
    fileName: 'feb.csv', rows: salesRows(120, { base: 200 }), dimensionColumns: ['Category', 'Region'],
    weakPoints: [
      makeWeakPoint({ problem: 'Gets worse', priority: 'high' }),
      makeWeakPoint({ problem: 'Gets better', priority: 'low' }),
      makeWeakPoint({ problem: 'Brand new', priority: 'medium' }),
    ],
  });
  const match = findMatchingSnapshot(feb);
  return { match, drift: computeDrift(match.snapshot, feb) };
}

describe('DriftBanner', () => {
  it('renders nothing without a match or a computed drift', () => {
    const { container, rerender } = render(<DriftBanner match={null} drift={null} onDismiss={() => {}} />);
    expect(container).toBeEmptyDOMElement();
    const { match } = realDriftScenario();
    rerender(<DriftBanner match={match} drift={null} onDismiss={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('is collapsed by default: names the earlier file and hides the diff', () => {
    const { match, drift } = realDriftScenario();
    render(<DriftBanner match={match} drift={drift} onDismiss={() => {}} />);
    expect(screen.getByText('jan.csv')).toBeInTheDocument();
    expect(screen.getByText(/updated version of/)).toBeInTheDocument();
    expect(screen.getByText(/67% of columns match/)).toBeInTheDocument(); // a column was added -> fuzzy match
    expect(screen.queryByText('Measures')).not.toBeInTheDocument();
  });

  it('does not mention a match percentage for an exact column match', () => {
    saveSnapshot(makeSession({ fileName: 'jan.csv', rows: salesRows(10) }));
    const now = makeSession({ fileName: 'feb.csv', rows: salesRows(12) });
    const match = findMatchingSnapshot(now);
    render(<DriftBanner match={match} drift={computeDrift(match.snapshot, now)} onDismiss={() => {}} />);
    expect(screen.queryByText(/of columns match/)).not.toBeInTheDocument();
  });

  it('expands to show measures, rows, every weak-point bucket and added columns', () => {
    const { match, drift } = realDriftScenario();
    const { container } = render(<DriftBanner match={match} drift={drift} onDismiss={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'View what changed' }));

    expect(screen.getByRole('button', { name: 'Hide' })).toBeInTheDocument();
    expect(screen.getByText('Measures')).toBeInTheDocument();
    expect(container.textContent).toMatch(/14[,.\s]?950\s*→\s*31[,.\s]?140\s*\(\+108\.29%\)/);
    expect(container.textContent).toMatch(/Rows:\s*100\s*→\s*120/);
    expect(screen.getByText('Resolved since last time')).toBeInTheDocument();
    expect(screen.getByText('✓ Resolved one')).toBeInTheDocument();
    expect(screen.getByText('Got worse')).toBeInTheDocument();
    expect(screen.getByText('↑ Gets worse (now high priority)')).toBeInTheDocument();
    expect(screen.getByText('Improved')).toBeInTheDocument();
    expect(screen.getByText('↓ Gets better (now low priority)')).toBeInTheDocument();
    expect(screen.getByText('+ Brand new')).toBeInTheDocument();
    expect(screen.getByText('+ Added: Region')).toBeInTheDocument();
  });

  it('renders every glyph as a real symbol, never a literal \\u escape', () => {
    const { match, drift } = realDriftScenario();
    // add a removed column too so the "−" row renders as well
    const withRemoved = { ...drift, removedColumns: ['OldCol'] };
    const { container } = render(<DriftBanner match={match} drift={withRemoved} onDismiss={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'View what changed' }));
    expect(container.textContent).toContain('📊');
    expect(container.textContent).toContain('− Removed: OldCol');
    expect(screen.getByRole('button', { name: 'Dismiss' })).toHaveTextContent('✕');
    expectNoRawEscapes(container);
  });

  it('tells you so when nothing was comparable', () => {
    const { match } = realDriftScenario();
    const empty = { rowCountChangePct: null, measureDeltas: [], resolved: [], worsened: [], improved: [], newIssues: [], addedColumns: [], removedColumns: [] };
    render(<DriftBanner match={match} drift={empty} onDismiss={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'View what changed' }));
    expect(screen.getByText(/No measures or weak points were comparable/)).toBeInTheDocument();
  });

  it('calls onDismiss from the close button', () => {
    const { match, drift } = realDriftScenario();
    const onDismiss = vi.fn();
    render(<DriftBanner match={match} drift={drift} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
