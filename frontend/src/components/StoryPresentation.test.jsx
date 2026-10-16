import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StoryPresentation from './StoryPresentation';
import { expectNoRawEscapes } from '../test/helpers';

const STORY = [
  { label: 'One', text: 'First beat.', tone: 'neutral' },
  { label: 'Two', text: 'Second beat.', tone: 'warning' },
  { label: 'Three', text: 'Third beat.', tone: 'action' },
];
const key = (k) => fireEvent.keyDown(window, { key: k });

function setup() {
  const onClose = vi.fn();
  const utils = render(<StoryPresentation story={STORY} onClose={onClose} />);
  return { onClose, ...utils };
}

describe('StoryPresentation', () => {
  it('opens as a modal dialog on the first beat, with Back disabled', () => {
    const { container } = setup();
    expect(screen.getByRole('dialog', { name: /story presentation/i })).toBeInTheDocument();
    expect(screen.getByText('First beat.')).toBeInTheDocument();
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /back/i })).toBeDisabled();
    expectNoRawEscapes(container);
  });

  it('Next and Back move through the beats', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText('Second beat.')).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /back/i }));
    expect(screen.getByText('First beat.')).toBeInTheDocument();
  });

  it.each([['ArrowRight'], [' '], ['Enter']])('%j advances', (k) => {
    setup();
    key(k);
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
  });

  it('ArrowLeft goes back, and neither end overshoots', () => {
    setup();
    key('ArrowLeft');
    expect(screen.getByText('1 / 3')).toBeInTheDocument(); // clamped at the start
    key('ArrowRight'); key('ArrowRight'); key('ArrowRight'); key('ArrowRight');
    expect(screen.getByText('3 / 3')).toBeInTheDocument(); // clamped at the end
    key('ArrowLeft');
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
  });

  it('on the last beat, Next becomes Done and closes the presentation', () => {
    const { onClose } = setup();
    key('ArrowRight'); key('ArrowRight');
    expect(screen.queryByRole('button', { name: /next/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /done/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('Escape and the close button both close it', () => {
    const { onClose } = setup();
    key('Escape');
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: /close presentation/i }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('clicking the slide advances (except on the last beat), and the dots jump directly', () => {
    setup();
    fireEvent.click(screen.getByText('First beat.'));
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Go to slide 3' }));
    expect(screen.getByText('Third beat.')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Third beat.'));
    expect(screen.getByText('3 / 3')).toBeInTheDocument(); // still on the last slide
  });

  it('stops listening to the keyboard once it is closed (unmounted)', () => {
    const { onClose, unmount } = setup();
    unmount();
    key('Escape');
    expect(onClose).not.toHaveBeenCalled();
  });
});
