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

  describe('Python script item', () => {
    it('only appears when the app can generate one', () => {
      const { rerender } = render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} />);
      openMenu();
      expect(screen.queryByRole('menuitem', { name: /python script/i })).not.toBeInTheDocument();
      rerender(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} onExportCode={async () => {}} />);
      const item = screen.getByRole('menuitem', { name: /python script/i });
      expect(item).toHaveTextContent('.py');
      expect(item).toHaveAttribute('title', expect.stringMatching(/pandas script/));
    });

    it('runs the handler, closes the menu, confirms briefly, then resets', async () => {
      vi.useFakeTimers();
      const onExportCode = vi.fn().mockResolvedValue(undefined);
      render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} onExportCode={onExportCode} />);
      openMenu();
      await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: /python script/i })); });
      expect(onExportCode).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole('menuitem')).not.toBeInTheDocument();
      await act(async () => { vi.advanceTimersByTime(2000); });
      openMenu();
      expect(screen.getByRole('menuitem', { name: /python script/i })).toBeInTheDocument();
    });

    it('a failed download shows "Couldn\'t download" instead of failing silently', async () => {
      vi.useFakeTimers();
      render(<ExportMenu onExportExcel={noop} onExportPdf={noop} onCopyFindings={noop} onExportCode={vi.fn().mockRejectedValue(new Error('x'))} />);
      openMenu();
      await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: /python script/i })); });
      openMenu();
      expect(screen.getByRole('menuitem', { name: /couldn't download/i })).toBeInTheDocument();
    });
  });
});
