import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import HypothesisTestPanel from './HypothesisTestPanel';
import { expectNoRawEscapes } from '../test/helpers';

vi.mock('../api', () => ({ runHypothesisTest: vi.fn() }));
import { runHypothesisTest } from '../api';

const FD = { available: true, dimension_columns: ['Region', 'Category'], measure_columns: ['Sales'] };
const ROWS = [
  ...Array.from({ length: 6 }, (_, i) => ({ Region: 'West', Category: i % 2 ? 'Tech' : 'Furniture', Sales: 100 + i })),
  ...Array.from({ length: 4 }, (_, i) => ({ Region: 'East', Category: 'Tech', Sales: 80 + i })),
  ...Array.from({ length: 2 }, (_, i) => ({ Region: 'North', Category: 'Tech', Sales: 90 + i })),
];

const NUMERIC_RESULT = {
  available: true, kind: 'numeric', group_a: 'West', group_b: 'East', group_column: 'Region', outcome_column: 'Sales',
  test: { id: 'welch_t', name: "Welch's t-test", why: 'Both groups have at least 30 rows.' },
  statistic_label: 'Difference in means (B \u2212 A)', difference: -21.5, interval: [-30.2, -12.8], interval_method: '95% interval (Welch-Satterthwaite)',
  p_value: 0.0004, significant: true, effect_size: { name: "Cohen's d (Hedges-corrected)", value: -1.4, label: 'large' },
  stats: { West: { n: 6, mean: 102.5, median: 102.5, std: 1.9 }, East: { n: 4, mean: 81.5, median: 81.5, std: 1.3 } },
  cross_check: { test: 'Mann-Whitney U', p_value: 0.01, agrees: true },
  headline: 'West has a higher average Sales than East: 102.5 vs 81.5 (+21, 95% interval +12.8 to +30.2). That gap is unlikely to be chance (p < 0.001), and the effect is large.',
  caveats: ['Assumes each row is an independent observation.', 'A p-value says whether a gap could be chance.'],
};

const run = () => fireEvent.click(screen.getByRole('button', { name: /run test/i }));

beforeEach(() => { runHypothesisTest.mockReset(); runHypothesisTest.mockImplementation(async () => ({ available: false, note: 'unmocked' })); });

describe('HypothesisTestPanel', () => {
  it('renders nothing when the dataset has no row-level data or nothing to compare', () => {
    const { container, rerender } = render(<HypothesisTestPanel filterableData={{ available: false }} rows={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<HypothesisTestPanel filterableData={FD} rows={ROWS.filter((r) => r.Region === 'West' && r.Category === 'Tech')} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('opens with usable defaults: the two biggest groups and the first measure, with row counts', () => {
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    expect(screen.getByLabelText('Compare groups in')).toHaveValue('Region');
    expect(screen.getByLabelText(/Group A/)).toHaveValue('West');
    expect(screen.getByLabelText(/Group B/)).toHaveValue('East');
    expect(screen.getByLabelText('On the outcome')).toHaveValue('Sales');
    expect(screen.getByText(/Uses 12 rows/)).toBeInTheDocument();
    expect(runHypothesisTest).not.toHaveBeenCalled();   // never runs on its own
  });

  it('A and B cannot be the same value: each dropdown hides the other\'s pick', () => {
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    const optionsOfA = within(screen.getByLabelText(/Group A/)).getAllByRole('option').map((o) => o.value);
    const optionsOfB = within(screen.getByLabelText(/Group B/)).getAllByRole('option').map((o) => o.value);
    expect(optionsOfA).not.toContain('East');
    expect(optionsOfB).not.toContain('West');
    expect(optionsOfB).toContain('North');
  });

  it('sends only the two groups\' values when the test is run, then shows the verdict first', async () => {
    runHypothesisTest.mockResolvedValue(NUMERIC_RESULT);
    const { container } = render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    expect(await screen.findByText('Likely a real difference')).toBeInTheDocument();

    const sent = runHypothesisTest.mock.calls[0][0];
    expect(sent).toMatchObject({ group_column: 'Region', outcome_column: 'Sales', group_a: 'West', group_b: 'East', outcome_kind: 'auto' });
    expect(sent.groups).toHaveLength(10);                       // North's 2 rows are not sent
    expect(sent.groups).not.toContain('North');
    expect(screen.getByText(/West has a higher average Sales than East/)).toBeInTheDocument();
    expectNoRawEscapes(container);
  });

  it('shows the test, why it was chosen, effect size, p-value, cross-check and an accessible interval graphic', async () => {
    runHypothesisTest.mockResolvedValue(NUMERIC_RESULT);
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    await screen.findByText('Likely a real difference');
    expect(screen.getByText("Welch's t-test")).toBeInTheDocument();
    expect(screen.getByText(/Why this test:/).parentElement).toHaveTextContent('Both groups have at least 30 rows.');
    expect(screen.getByText('p < 0.001')).toBeInTheDocument();
    expect(screen.getByText(/Cohen's d \(Hedges-corrected\)/).parentElement).toHaveTextContent('\u22121.40 (large)');
    expect(screen.getByText(/Cross-check with Mann-Whitney U/)).toHaveTextContent('same conclusion');
    const graphic = screen.getByRole('img');
    expect(graphic).toHaveAccessibleName(/does not include zero/);
    expect(graphic.closest('figure')).toHaveTextContent('The interval does not include zero.');
  });

  it('a non-significant result is labelled "No clear difference" and an interval across zero says so', async () => {
    runHypothesisTest.mockResolvedValue({ ...NUMERIC_RESULT, significant: false, p_value: 0.4, interval: [-8, 11], difference: 1.5, headline: 'No clear difference in Sales between West and East.' });
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    expect(await screen.findByText('No clear difference')).toBeInTheDocument();
    expect(screen.getByRole('img').closest('figure')).toHaveTextContent('The interval includes zero.');
  });

  it('a disagreeing cross-check is shown as a different conclusion', async () => {
    runHypothesisTest.mockResolvedValue({ ...NUMERIC_RESULT, cross_check: { test: 'Mann-Whitney U', p_value: 0.3, agrees: false } });
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    await screen.findByText('Likely a real difference');
    expect(screen.getByText(/Cross-check with Mann-Whitney U/)).toHaveTextContent('a different conclusion');
  });

  it('lists the group statistics and the caveats (collapsed until opened)', async () => {
    runHypothesisTest.mockResolvedValue(NUMERIC_RESULT);
    const { container } = render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    await screen.findByText('Likely a real difference');
    const table = container.querySelector('table');
    expect(within(table).getByText('West (A)')).toBeInTheDocument();
    expect(within(table).getByText('East (B)')).toBeInTheDocument();
    expect(within(table).getAllByText('102.5')).toHaveLength(2);   // mean and median
    expect(screen.getByText(/Things to keep in mind \(2\)/)).toBeInTheDocument();
    expect(container.querySelector('details')).not.toHaveAttribute('open');
  });

  it('a categorical result shows the rate per group and the relative risk', async () => {
    runHypothesisTest.mockResolvedValue({
      available: true, kind: 'categorical', group_a: 'West', group_b: 'East', positive_level: 'Tech',
      test: { id: 'chi_square', name: 'Chi-square test of independence', why: 'Every expected count is at least 5.' },
      statistic_label: 'Difference in rate of "Tech" (B \u2212 A)', difference: 0.1, interval: [0.02, 0.18], interval_method: '95% Newcombe-Wilson interval',
      p_value: 0.02, significant: true, effect_size: { name: 'Cramer\'s V (phi)', value: 0.2, label: 'small' },
      rate: { West: 0.2, East: 0.3 }, relative_risk: 1.5, stats: { West: { n: 400 }, East: { n: 400 } },
      headline: 'East has a higher rate of Category = Tech than West.', caveats: ['x'],
    });
    const { container } = render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    fireEvent.change(screen.getByLabelText('On the outcome'), { target: { value: 'Category' } });
    run();
    await screen.findByText('Likely a real difference');
    expect(runHypothesisTest.mock.calls[0][0].outcome_kind).toBe('categorical');
    const table = container.querySelector('table');
    expect(within(table).getByText('20.0%')).toBeInTheDocument();
    expect(within(table).getByText('30.0%')).toBeInTheDocument();
    expect(screen.getByText(/relative risk/)).toHaveTextContent('1.50');
    expect(screen.getByText(/Difference in rate of "Tech"/, { exact: false })).toBeInTheDocument();
  });

  it('a "rate of" picker appears for a category outcome and its choice is sent', async () => {
    runHypothesisTest.mockResolvedValue({ available: false, note: 'x' });
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    expect(screen.queryByLabelText('Rate of')).not.toBeInTheDocument();      // a plain number outcome has no such choice
    fireEvent.change(screen.getByLabelText('On the outcome'), { target: { value: 'Category' } });
    fireEvent.change(screen.getByLabelText('Rate of'), { target: { value: 'Furniture' } });
    run();
    await waitFor(() => expect(runHypothesisTest).toHaveBeenCalled());
    expect(runHypothesisTest.mock.calls[0][0].positive_level).toBe('Furniture');
  });

  it('an unusable question shows the server\'s plain-language reason, not an error', async () => {
    runHypothesisTest.mockResolvedValue({ available: false, note: 'Needs at least 5 rows with a value in each group; East has 3.' });
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    expect(await screen.findByText(/Needs at least 5 rows/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('a network/server failure is announced as an alert', async () => {
    runHypothesisTest.mockImplementation(async () => { throw new Error('The test could not be run.'); });
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    expect(await screen.findByRole('alert')).toHaveTextContent('The test could not be run.');
  });

  it('shows "Testing…" and disables the button while a test is running', async () => {
    let resolve;
    runHypothesisTest.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    expect(screen.getByRole('button', { name: 'Testing…' })).toBeDisabled();
    resolve(NUMERIC_RESULT);
    expect(await screen.findByText('Likely a real difference')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run test/i })).toBeEnabled();
  });

  it('never leaves an old answer on screen under a changed question', async () => {
    runHypothesisTest.mockResolvedValue(NUMERIC_RESULT);
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    await screen.findByText('Likely a real difference');

    fireEvent.change(screen.getByLabelText(/Group B/), { target: { value: 'North' } });
    expect(screen.queryByText('Likely a real difference')).not.toBeInTheDocument();
    expect(screen.getByText(/run the test again for an answer that matches/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Group B/), { target: { value: 'East' } });   // back to the answered question
    expect(screen.getByText('Likely a real difference')).toBeInTheDocument();
  });

  it('an answer is dropped when the filters change the rows underneath it', async () => {
    runHypothesisTest.mockResolvedValue(NUMERIC_RESULT);
    const { rerender } = render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    run();
    await screen.findByText('Likely a real difference');
    rerender(<HypothesisTestPanel filterableData={FD} rows={ROWS.slice(0, 11)} />);
    expect(screen.queryByText('Likely a real difference')).not.toBeInTheDocument();
    expect(screen.getByText(/You changed the question or the filters/)).toBeInTheDocument();
  });

  it('a slow earlier answer cannot overwrite a newer one', async () => {
    let resolveFirst;
    runHypothesisTest.mockReturnValueOnce(new Promise((r) => { resolveFirst = r; }));
    runHypothesisTest.mockResolvedValueOnce({ ...NUMERIC_RESULT, headline: 'SECOND ANSWER (West vs North)' });
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);

    run();                                                                       // request 1: West vs East, still pending
    fireEvent.change(screen.getByLabelText(/Group B/), { target: { value: 'North' } });
    run();                                                                       // request 2: West vs North
    expect(await screen.findByText(/SECOND ANSWER/)).toBeInTheDocument();

    resolveFirst({ ...NUMERIC_RESULT, headline: 'FIRST ANSWER (West vs East)' });  // the old one finally arrives
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText(/FIRST ANSWER/)).not.toBeInTheDocument();
    expect(screen.getByText(/SECOND ANSWER/)).toBeInTheDocument();
  });

  it('switching the group column resets A, B and the outcome to valid choices', () => {
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    fireEvent.change(screen.getByLabelText('Compare groups in'), { target: { value: 'Category' } });
    expect(screen.getByLabelText(/Group A/)).toHaveValue('Tech');
    expect(screen.getByLabelText(/Group B/)).toHaveValue('Furniture');
    expect(within(screen.getByLabelText('On the outcome')).queryByRole('option', { name: 'Category' })).not.toBeInTheDocument();
  });

  it('every dropdown has an accessible name', () => {
    render(<HypothesisTestPanel filterableData={FD} rows={ROWS} />);
    screen.getAllByRole('combobox').forEach((c) => expect(c).toHaveAccessibleName());
  });
});
