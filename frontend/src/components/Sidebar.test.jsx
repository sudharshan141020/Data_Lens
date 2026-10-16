import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Sidebar from './Sidebar';

const session = (id, over = {}) => ({
  id, fileName: `${id}.csv`, status: 'ready', pinned: false, result: {}, sourceFile: new File(['x'], `${id}.csv`), ...over,
});

function setup(props = {}) {
  const handlers = {
    onSelect: vi.fn(), onRemove: vi.fn(), onFilesSelected: vi.fn(), onTogglePin: vi.fn(),
    onToggleCombineMode: vi.fn(), onToggleSelect: vi.fn(), onCombine: vi.fn(),
    onToggleCompareMode: vi.fn(), onToggleSelectForCompare: vi.fn(), onCompare: vi.fn(),
    onToggleJoinMode: vi.fn(), onToggleSelectForJoin: vi.fn(), onJoin: vi.fn(), onLogoClick: vi.fn(),
  };
  const merged = {
    sessions: [session('orders'), session('customers')], activeId: 'orders', uploadError: null,
    combineMode: false, selectedForCombine: [], compareMode: false, selectedForCompare: [],
    joinMode: false, selectedForJoin: [], ...handlers, ...props,
  };
  const utils = render(<Sidebar {...merged} />);
  return { ...handlers, ...utils };
}

describe('Sidebar: logo', () => {
  it('the DATALENS mark is a button that takes you home', () => {
    const { onLogoClick } = setup();
    fireEvent.click(screen.getByRole('button', { name: /datalens/i }));
    expect(onLogoClick).toHaveBeenCalledTimes(1);
  });
});

describe('Sidebar: join mode', () => {
  it('offers "Join two files…" only once there are two analysed files', () => {
    setup({ sessions: [session('only')] });
    expect(screen.queryByRole('button', { name: /join two files/i })).not.toBeInTheDocument();
  });

  it('shows the join toggle with two ready files and calls the handler', () => {
    const { onToggleJoinMode } = setup();
    fireEvent.click(screen.getByRole('button', { name: /join two files/i }));
    expect(onToggleJoinMode).toHaveBeenCalledTimes(1);
  });

  it('ignores files that are still loading or failed', () => {
    setup({ sessions: [session('a'), session('b', { status: 'loading', sourceFile: null })] });
    expect(screen.queryByRole('button', { name: /join two files/i })).not.toBeInTheDocument();
  });

  it('while joining: offers Cancel, hides Combine/Compare, and keeps Join disabled until exactly two are picked', () => {
    const { onJoin, rerender } = setup({ joinMode: true, selectedForJoin: ['orders'] });
    expect(screen.getByRole('button', { name: /cancel join/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /combine files/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /compare two files/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /join selected \(1\/2\)/i })).toBeDisabled();
    expect(onJoin).not.toHaveBeenCalled();
    expect(rerender).toBeTypeOf('function');
  });

  it('runs the join once two files are selected', () => {
    const { onJoin } = setup({ joinMode: true, selectedForJoin: ['orders', 'customers'] });
    const run = screen.getByRole('button', { name: /join selected \(2\/2\)/i });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    expect(onJoin).toHaveBeenCalledTimes(1);
  });

  it('caps the selection at two: a third file cannot be ticked, but the chosen two can be unticked', () => {
    setup({
      sessions: [session('a'), session('b'), session('c')], activeId: 'a', joinMode: true, selectedForJoin: ['a', 'b'],
    });
    const boxes = screen.getAllByRole('checkbox');
    expect(boxes).toHaveLength(3);
    expect(boxes[0]).toBeChecked(); expect(boxes[0]).toBeEnabled();
    expect(boxes[1]).toBeChecked(); expect(boxes[1]).toBeEnabled();
    expect(boxes[2]).not.toBeChecked(); expect(boxes[2]).toBeDisabled();
  });

  it('clicking a file row toggles it for the join instead of opening it', () => {
    const { onToggleSelectForJoin, onSelect } = setup({ joinMode: true });
    fireEvent.click(screen.getByText('customers.csv'));
    expect(onToggleSelectForJoin).toHaveBeenCalledWith('customers');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('outside any mode, clicking a file just opens it', () => {
    const { onSelect } = setup();
    fireEvent.click(screen.getByText('customers.csv'));
    expect(onSelect).toHaveBeenCalledWith('customers');
  });
});
