import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StoryMode from './StoryMode';
import { expectNoRawEscapes } from '../test/helpers';

const STORY = [
  { label: 'The headline', text: 'Sales grew 12% year on year.', tone: 'neutral' },
  { label: 'Watch out', text: 'Office Supplies is losing money.', tone: 'warning' },
  { label: 'Next step', text: 'Cap discounts at 20%.', tone: 'action' },
];

describe('StoryMode', () => {
  it('renders nothing for an empty story', () => {
    const { container } = render(<StoryMode story={[]} tickNum="03" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders every beat with its label and text', () => {
    render(<StoryMode story={STORY} tickNum="03" />);
    STORY.forEach((b) => {
      expect(screen.getByText(b.label)).toBeInTheDocument();
      expect(screen.getByText(b.text)).toBeInTheDocument();
    });
  });

  it('shows the Present button as a real play symbol, not a raw escape sequence', () => {
    const { container } = render(<StoryMode story={STORY} tickNum="03" onPresent={() => {}} />);
    const btn = screen.getByRole('button', { name: /present/i });
    expect(btn).toHaveTextContent('▶ Present');
    expectNoRawEscapes(container);
  });

  it('calls onPresent when clicked, and offers no button when there is no handler', () => {
    const onPresent = vi.fn();
    const { rerender } = render(<StoryMode story={STORY} tickNum="03" onPresent={onPresent} />);
    fireEvent.click(screen.getByRole('button', { name: /present/i }));
    expect(onPresent).toHaveBeenCalledTimes(1);

    rerender(<StoryMode story={STORY} tickNum="03" />);
    expect(screen.queryByRole('button', { name: /present/i })).not.toBeInTheDocument();
  });
});
