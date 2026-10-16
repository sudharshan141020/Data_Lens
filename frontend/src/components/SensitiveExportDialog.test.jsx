import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SensitiveExportDialog from './SensitiveExportDialog';
import { expectNoRawEscapes } from '../test/helpers';

const report = {
  columns: [
    { column: 'Email', confidence: 'high', reason: 'looks like an email address' },
    { column: 'Customer ID', confidence: 'medium', reason: 'looks like a person identifier' },
    { column: 'Address', confidence: 'low', reason: 'looks like a street address' },
    { column: 'Phone', confidence: 'high', masked: true, reason: 'already masked' },
  ],
};
const setup = (props = {}) => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const utils = render(<SensitiveExportDialog action="share" report={report} onConfirm={onConfirm} onCancel={onCancel} {...props} />);
  return { onConfirm, onCancel, ...utils };
};

describe('SensitiveExportDialog', () => {
  it('is an accessible modal that says what is about to happen', () => {
    const { container } = setup();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName('Personal data may be included');
    expect(dialog).toHaveTextContent('share link');
    expectNoRawEscapes(container);
  });

  it.each([['pdf', 'PDF report'], ['html', 'HTML report'], ['share', 'share link']])('names the action: %s', (action, text) => {
    setup({ action });
    expect(screen.getByRole('dialog')).toHaveTextContent(text);
  });

  it('lists unmasked columns only, pre-ticking medium and high confidence', () => {
    setup();
    expect(screen.getByRole('checkbox', { name: 'Mask Email' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Mask Customer ID' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Mask Address' })).not.toBeChecked();
    expect(screen.queryByRole('checkbox', { name: 'Mask Phone' })).not.toBeInTheDocument();
  });

  it('confirms with exactly the ticked columns', () => {
    const { onConfirm } = setup();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Mask Customer ID' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Mask Address' }));
    fireEvent.click(screen.getByRole('button', { name: /mask 2 selected/i }));
    expect(onConfirm).toHaveBeenCalledWith({ columns: ['Email', 'Address'] });
  });

  it('"Continue without masking" confirms with no columns', () => {
    const { onConfirm } = setup();
    fireEvent.click(screen.getByRole('button', { name: /continue without masking/i }));
    expect(onConfirm).toHaveBeenCalledWith({ columns: [] });
  });

  it('cannot "mask" with nothing ticked', () => {
    setup();
    ['Email', 'Customer ID'].forEach((n) => fireEvent.click(screen.getByRole('checkbox', { name: `Mask ${n}` })));
    expect(screen.getByRole('button', { name: /mask 0 selected/i })).toBeDisabled();
  });

  it('cancels from the button, Escape, and a click on the backdrop', () => {
    const a = setup();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(a.onCancel).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(a.onCancel).toHaveBeenCalledTimes(2);
    fireEvent.mouseDown(screen.getByRole('dialog').parentElement);
    expect(a.onCancel).toHaveBeenCalledTimes(3);
  });

  it('a click inside the dialog does not cancel it', () => {
    const { onCancel } = setup();
    fireEvent.mouseDown(screen.getByRole('dialog'));
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('moves focus into the dialog, and stops listening for Escape when it closes', () => {
    const { onCancel, unmount } = setup();
    expect(screen.getByRole('button', { name: /mask 2 selected/i })).toHaveFocus();
    unmount();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).not.toHaveBeenCalled();
  });
});
