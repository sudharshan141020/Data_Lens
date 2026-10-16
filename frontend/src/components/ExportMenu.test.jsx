import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import ExportMenu from './ExportMenu';
import { expectNoRawEscapes } from '../test/helpers';

const noop = () => {};
const openMenu = () => fireEvent.click(screen.getByRole('button', { name: /export/i }));

afterEach(() => { vi.useRealTimers(); });

describe('ExportMenu', () => {
  it('is closed until the Export button is clicked, and reflects that for assistive tech', () => {
    render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} />);
    const trigger = screen.getByRole('button', { name: /export/i });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('menuitem').length).toBeGreaterThan(0);
  });

  it('closes on Escape and on a click outside', () => {
    render(<div><span>outside</span><ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} /></div>);
    openMenu();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
    openMenu();
    fireEvent.mouseDown(screen.getByText('outside'));
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
  });

  it('only offers "Save snapshot" when the app says snapshots are possible', () => {
    const { rerender } = render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} />);
    openMenu();
    expect(screen.queryByRole('menuitem', { name: /save snapshot/i })).not.toBeInTheDocument();
    rerender(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} onSaveSnapshot={() => true} />);
    expect(screen.getByRole('menuitem', { name: /save snapshot/i })).toBeInTheDocument();
  });

  it('Save snapshot calls the handler, closes the menu, then confirms "Saved!" briefly', () => {
    vi.useFakeTimers();
    const onSaveSnapshot = vi.fn(() => true);
    const { container } = render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} onSaveSnapshot={onSaveSnapshot} />);
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: /save snapshot/i }));
    expect(onSaveSnapshot).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument(); // menu closed itself

    openMenu();
    expect(screen.getByRole('menuitem', { name: /saved!/i })).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(1800); });
    expect(screen.getByRole('menuitem', { name: /save snapshot \(for next time\)/i })).toBeInTheDocument();
    expectNoRawEscapes(container);
  });

  it('reports a failed save instead of pretending it worked', () => {
    render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} onSaveSnapshot={() => false} />);
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: /save snapshot/i }));
    openMenu();
    expect(screen.getByRole('menuitem', { name: /couldn't save/i })).toBeInTheDocument();
  });
});
