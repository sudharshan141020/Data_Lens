import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFilteredReports } from './useFilteredReports';
import fixture from './test/fixtures/analysis.json';

vi.mock('./api', () => ({ fetchFilteredReports: vi.fn() }));
import { fetchFilteredReports } from './api';

const v2 = JSON.parse(JSON.stringify(fixture.v2));
const ROWS_A = v2.filterable_data.rows.slice(0, 40);
const ROWS_B = v2.filterable_data.rows.slice(40, 80);
const REPORTS = (n) => ({ available: true, rows_used: n, seasonality: { available: true }, period_comparison: { available: true, tag: n }, drivers: { available: true, comparisons: [] }, robustness: { available: true } });
const settle = () => act(async () => { await vi.advanceTimersByTimeAsync(400); });

beforeEach(() => { vi.useFakeTimers(); fetchFilteredReports.mockReset(); fetchFilteredReports.mockImplementation(async () => REPORTS(0)); });
afterEach(() => { vi.useRealTimers(); });

describe('useFilteredReports', () => {
  it('does nothing while no filter is on', async () => {
    const { result } = renderHook(() => useFilteredReports({ v2, rows: ROWS_A, active: false }));
    await settle();
    expect(result.current.status).toBe('idle');
    expect(fetchFilteredReports).not.toHaveBeenCalled();
  });

  it('shows "loading" immediately, asks after a short pause, then holds the reports for exactly those rows', async () => {
    fetchFilteredReports.mockImplementation(async () => REPORTS(40));
    const { result } = renderHook(() => useFilteredReports({ v2, rows: ROWS_A, active: true }));
    expect(result.current.status).toBe('loading');
    expect(result.current.reports).toBeNull();
    expect(fetchFilteredReports).not.toHaveBeenCalled();               // debounced
    await settle();
    expect(fetchFilteredReports).toHaveBeenCalledTimes(1);
    expect(result.current).toMatchObject({ status: 'ready', rowsUsed: 40 });
    expect(result.current.reports.period_comparison.tag).toBe(40);
  });

  it('sends the rows column by column', async () => {
    fetchFilteredReports.mockImplementation(async () => REPORTS(40));
    renderHook(() => useFilteredReports({ v2, rows: ROWS_A, active: true }));
    await settle();
    const payload = fetchFilteredReports.mock.calls[0][0];
    expect(payload.columns[v2.filterable_data.date_column]).toHaveLength(40);
    expect(payload).not.toHaveProperty('rows');
  });

  it('a burst of filter changes makes one request, for the last of them', async () => {
    fetchFilteredReports.mockImplementation(async () => REPORTS(10));
    const { rerender } = renderHook((p) => useFilteredReports(p), { initialProps: { v2, rows: ROWS_A, active: true } });
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    rerender({ v2, rows: ROWS_B, active: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    rerender({ v2, rows: ROWS_A.slice(0, 10), active: true });
    await settle();
    expect(fetchFilteredReports).toHaveBeenCalledTimes(1);
    expect(Object.values(fetchFilteredReports.mock.calls[0][0].columns)[0]).toHaveLength(10);
  });

  it('a slow answer for an OLD filter can never replace the answer for the current one', async () => {
    let resolveOld;
    fetchFilteredReports.mockReturnValueOnce(new Promise((r) => { resolveOld = r; }));
    fetchFilteredReports.mockImplementationOnce(async () => REPORTS(2222));
    const { result, rerender } = renderHook((p) => useFilteredReports(p), { initialProps: { v2, rows: ROWS_A, active: true } });
    await settle();                                                     // request 1 is in flight and never answers
    rerender({ v2, rows: ROWS_B, active: true });
    await settle();                                                     // request 2 for the new filter
    expect(result.current.rowsUsed).toBe(2222);
    await act(async () => { resolveOld(REPORTS(1111)); await Promise.resolve(); });   // the old one finally arrives
    expect(result.current.rowsUsed).toBe(2222);
    expect(result.current.reports.period_comparison.tag).not.toBe(1111);
  });

  it('shows nothing from an older filter while a new one is pending', async () => {
    fetchFilteredReports.mockImplementationOnce(async () => REPORTS(40));
    fetchFilteredReports.mockReturnValueOnce(new Promise(() => {}));
    const { result, rerender } = renderHook((p) => useFilteredReports(p), { initialProps: { v2, rows: ROWS_A, active: true } });
    await settle();
    expect(result.current.status).toBe('ready');
    rerender({ v2, rows: ROWS_B, active: true });
    expect(result.current.status).toBe('loading');
    expect(result.current.reports).toBeNull();
  });

  it('turning the filters off clears everything', async () => {
    fetchFilteredReports.mockImplementation(async () => REPORTS(40));
    const { result, rerender } = renderHook((p) => useFilteredReports(p), { initialProps: { v2, rows: ROWS_A, active: true } });
    await settle();
    rerender({ v2, rows: v2.filterable_data.rows, active: false });
    expect(result.current).toMatchObject({ status: 'idle', reports: null });
  });

  it('a failed request becomes an "error" with the message, so the panels can fall back', async () => {
    fetchFilteredReports.mockImplementation(async () => { throw new Error('The reports could not be updated for your filters.'); });
    const { result } = renderHook(() => useFilteredReports({ v2, rows: ROWS_A, active: true }));
    await settle();
    expect(result.current).toMatchObject({ status: 'error', reports: null, note: 'The reports could not be updated for your filters.' });
  });

  it('"nothing usable" from the server becomes per-panel notes, not an error', async () => {
    fetchFilteredReports.mockImplementation(async () => ({ available: false, note: 'No rows match the current filters.' }));
    const { result } = renderHook(() => useFilteredReports({ v2, rows: ROWS_A, active: true }));
    await settle();
    expect(result.current.status).toBe('ready');
    expect(result.current.reports.drivers).toMatchObject({ available: false, note: 'No rows match the current filters.' });
  });

  it('does not call the server at all when recompute is impossible, and says why', async () => {
    const old = JSON.parse(JSON.stringify(v2));
    delete old.filterable_data.measure_aggregations;
    const { result } = renderHook(() => useFilteredReports({ v2: old, rows: ROWS_A, active: true }));
    await settle();
    expect(result.current.status).toBe('blocked');
    expect(result.current.note).toMatch(/Re-analyse/);
    expect(fetchFilteredReports).not.toHaveBeenCalled();
  });

  it('too many rows is blocked without a request', async () => {
    const many = Array.from({ length: 50_001 }, () => ROWS_A[0]);
    const { result } = renderHook(() => useFilteredReports({ v2, rows: many, active: true }));
    await settle();
    expect(result.current.status).toBe('blocked');
    expect(fetchFilteredReports).not.toHaveBeenCalled();
  });

  it('is inert without a result', async () => {
    const { result } = renderHook(() => useFilteredReports({ v2: undefined, rows: [], active: true }));
    await settle();
    expect(result.current.status).toBe('idle');
  });
});
