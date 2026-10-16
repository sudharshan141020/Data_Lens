import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SensitiveDataBanner from './SensitiveDataBanner';
import { expectNoRawEscapes } from '../test/helpers';

const col = (column, confidence = 'high', extra = {}) => ({ column, confidence, reason: `${column} looks personal`, ...extra });
const v2With = (columns) => ({ sensitive_data: { columns } });

describe('SensitiveDataBanner', () => {
  it('renders nothing when there is no report or nothing was found', () => {
    const { container, rerender } = render(<SensitiveDataBanner v2={{}} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<SensitiveDataBanner v2={v2With([])} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing once every flagged column has been masked', () => {
    const { container } = render(<SensitiveDataBanner v2={v2With([col('Email', 'high', { masked: true })])} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('counts the columns in plain language, singular and plural', () => {
    const { rerender } = render(<SensitiveDataBanner v2={v2With([col('Email')])} />);
    expect(screen.getByRole('note')).toHaveTextContent('1 column in this file looks like personal information');
    rerender(<SensitiveDataBanner v2={v2With([col('Email'), col('Phone')])} />);
    expect(screen.getByRole('note')).toHaveTextContent('2 columns in this file look like personal information');
  });

  it('keeps the details collapsed until asked, then lists each column with its reason', () => {
    const { container } = render(<SensitiveDataBanner v2={v2With([col('Email'), col('Phone', 'medium')])} />);
    const toggle = screen.getByRole('button', { name: /show details/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Phone looks personal', { exact: false })).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/Phone looks personal/)).toBeInTheDocument();
    expect(screen.getByText(/medium confidence/)).toBeInTheDocument();
    expect(screen.getByText(/pattern-based check/)).toBeInTheDocument();
    expectNoRawEscapes(container);
  });
});
