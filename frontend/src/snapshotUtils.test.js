import { describe, it, expect, vi } from 'vitest';
import {
  fingerprintColumns, buildSnapshot, saveSnapshot, findMatchingSnapshot, computeDrift,
} from './snapshotUtils';
import { makeSession, makeWeakPoint, salesRows } from './test/fixtures';

const KEY_PREFIX = 'datalens_snapshot::';
const storedKeys = () => Object.keys(localStorage).filter((k) => k.startsWith(KEY_PREFIX));

describe('fingerprintColumns', () => {
  it('ignores column order but distinguishes different column sets', () => {
    expect(fingerprintColumns(['a', 'b', 'c'])).toBe(fingerprintColumns(['c', 'a', 'b']));
    expect(fingerprintColumns(['a', 'b'])).not.toBe(fingerprintColumns(['a', 'c']));
  });

  it('does not mutate the array it is given', () => {
    const cols = ['b', 'a'];
    fingerprintColumns(cols);
    expect(cols).toEqual(['b', 'a']);
  });
});

describe('buildSnapshot', () => {
  it('returns null when there is no result, or filterable_data is unavailable', () => {
    expect(buildSnapshot(null)).toBeNull();
    expect(buildSnapshot({ result: {} })).toBeNull();
    expect(buildSnapshot(makeSession({ rows: salesRows(5), filterableAvailable: false }))).toBeNull();
  });

  it('computes per-measure sum, avg and count, ignoring non-numeric values', () => {
    const rows = [{ Sales: 10, Category: 'A' }, { Sales: 20, Category: 'B' }, { Sales: '30', Category: 'A' }, { Sales: null, Category: 'B' }];
    const snap = buildSnapshot(makeSession({ rows }));
    expect(snap.measures.Sales).toEqual({ sum: 30, avg: 15, count: 2 });
  });

  it('records sorted columns, row count and only the weak-point fields it diffs on', () => {
    const snap = buildSnapshot(makeSession({
      rows: salesRows(4), measureColumns: ['Sales'], dimensionColumns: ['Region', 'Category'],
      weakPoints: [makeWeakPoint({ problem: 'P', priority: 'high', category: 'trend', significant: false })],
    }));
    expect(snap.columns).toEqual(['Category', 'Region', 'Sales']);
    expect(snap.rowCount).toBe(4);
    expect(snap.weakPoints).toEqual([{ problem: 'P', priority: 'high', category: 'trend', significant: false }]);
    expect(snap.fileName).toBe('sales.csv');
  });

  it('never stores raw rows', () => {
    const snap = buildSnapshot(makeSession({ rows: salesRows(50) }));
    expect(JSON.stringify(snap)).not.toContain('"rows"');
    expect(JSON.stringify(snap).length).toBeLessThan(1500);
  });
});

describe('saveSnapshot', () => {
  it('stores one entry under the namespaced key and reports success', () => {
    expect(saveSnapshot(makeSession({ rows: salesRows(5) }))).toBe(true);
    expect(storedKeys()).toHaveLength(1);
  });

  it('overwrites rather than accumulates for the same column set', () => {
    saveSnapshot(makeSession({ fileName: 'jan.csv', rows: salesRows(5) }));
    saveSnapshot(makeSession({ fileName: 'feb.csv', rows: salesRows(9) }));
    expect(storedKeys()).toHaveLength(1);
    expect(JSON.parse(localStorage.getItem(storedKeys()[0])).fileName).toBe('feb.csv');
  });

  it('keeps separate entries for different column sets', () => {
    saveSnapshot(makeSession({ rows: salesRows(5) }));
    saveSnapshot(makeSession({ rows: salesRows(5), dimensionColumns: ['Region'] }));
    expect(storedKeys()).toHaveLength(2);
  });

  it('returns false instead of throwing when there is nothing to snapshot', () => {
    expect(saveSnapshot(makeSession({ rows: [], filterableAvailable: false }))).toBe(false);
    expect(storedKeys()).toHaveLength(0);
  });

  it('returns false instead of throwing when storage is full or blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
    expect(saveSnapshot(makeSession({ rows: salesRows(5) }))).toBe(false);
  });
});

describe('findMatchingSnapshot', () => {
  it('finds nothing when nothing has been saved', () => {
    expect(findMatchingSnapshot(makeSession({ rows: salesRows(5) }))).toBeNull();
  });

  it('reports an exact match for an identical column set', () => {
    saveSnapshot(makeSession({ fileName: 'jan.csv', rows: salesRows(5) }));
    const match = findMatchingSnapshot(makeSession({ fileName: 'feb.csv', rows: salesRows(8) }));
    expect(match).toMatchObject({ isExact: true, score: 1 });
    expect(match.snapshot.fileName).toBe('jan.csv');
  });

  it('falls back to a fuzzy match when a column was added (Jaccard 2/3 >= 0.6)', () => {
    saveSnapshot(makeSession({ rows: salesRows(5) }));
    const match = findMatchingSnapshot(makeSession({ rows: salesRows(5), dimensionColumns: ['Category', 'Region'] }));
    expect(match.isExact).toBe(false);
    expect(match.score).toBeCloseTo(0.67, 2);
  });

  it('rejects a match below the 0.6 threshold', () => {
    saveSnapshot(makeSession({ rows: salesRows(5), measureColumns: ['Sales'], dimensionColumns: ['Category'] }));
    // overlap: Sales only -> 1 shared of 5 total = 0.2
    const other = makeSession({ rows: salesRows(5), measureColumns: ['Sales'], dimensionColumns: ['X', 'Y', 'Z'] });
    expect(findMatchingSnapshot(other)).toBeNull();
  });

  it('picks the closest of several saved snapshots', () => {
    saveSnapshot(makeSession({ fileName: 'far.csv', rows: salesRows(5), measureColumns: ['Sales', 'Cost', 'Tax'], dimensionColumns: ['Category'] }));
    saveSnapshot(makeSession({ fileName: 'near.csv', rows: salesRows(5), dimensionColumns: ['Category', 'Region'] }));
    const current = makeSession({ rows: salesRows(5), dimensionColumns: ['Category', 'Region', 'Segment'] });
    expect(findMatchingSnapshot(current).snapshot.fileName).toBe('near.csv');
  });

  it('skips corrupt entries and unrelated keys instead of crashing', () => {
    localStorage.setItem(`${KEY_PREFIX}broken`, '{not json');
    localStorage.setItem(`${KEY_PREFIX}wrongshape`, JSON.stringify({ hello: 'world' }));
    localStorage.setItem('some_other_app_key', JSON.stringify({ columns: ['Sales', 'Category'] }));
    expect(() => findMatchingSnapshot(makeSession({ rows: salesRows(5) }))).not.toThrow();
    expect(findMatchingSnapshot(makeSession({ rows: salesRows(5) }))).toBeNull();
  });
});

describe('computeDrift', () => {
  const jan = () => makeSession({
    fileName: 'jan.csv', rows: salesRows(100),
    weakPoints: [
      makeWeakPoint({ problem: 'Resolved one', priority: 'medium' }),
      makeWeakPoint({ problem: 'Gets worse', priority: 'low' }),
      makeWeakPoint({ problem: 'Gets better', priority: 'high' }),
      makeWeakPoint({ problem: 'Unchanged', priority: 'medium' }),
    ],
  });
  const feb = () => makeSession({
    fileName: 'feb.csv', rows: salesRows(120, { base: 200 }), dimensionColumns: ['Category', 'Region'],
    weakPoints: [
      makeWeakPoint({ problem: 'Gets worse', priority: 'high' }),
      makeWeakPoint({ problem: 'Gets better', priority: 'low' }),
      makeWeakPoint({ problem: 'Unchanged', priority: 'medium' }),
      makeWeakPoint({ problem: 'Brand new', priority: 'medium' }),
    ],
  });

  it('classifies every weak point into resolved / worsened / improved / new, and leaves unchanged ones out', () => {
    saveSnapshot(jan());
    const drift = computeDrift(findMatchingSnapshot(feb()).snapshot, feb());
    expect(drift.resolved.map((w) => w.problem)).toEqual(['Resolved one']);
    expect(drift.worsened.map((w) => w.problem)).toEqual(['Gets worse']);
    expect(drift.improved.map((w) => w.problem)).toEqual(['Gets better']);
    expect(drift.newIssues.map((w) => w.problem)).toEqual(['Brand new']);
  });

  it('computes row-count and measure changes as percentages', () => {
    saveSnapshot(jan());
    const drift = computeDrift(findMatchingSnapshot(feb()).snapshot, feb());
    expect(drift.rowCountOld).toBe(100);
    expect(drift.rowCountNew).toBe(120);
    expect(drift.rowCountChangePct).toBe(20);
    const sales = drift.measureDeltas.find((m) => m.measure === 'Sales');
    const oldTotal = (100 + 199) * 100 / 2; // 100 rows: 100..199
    const newTotal = (200 + 319) * 120 / 2; // 120 rows: 200..319
    expect(sales.oldSum).toBe(oldTotal);
    expect(sales.newSum).toBe(newTotal);
    expect(sales.sumChangePct).toBeCloseTo(((newTotal - oldTotal) / oldTotal) * 100, 1);
  });

  it('reports added and removed columns', () => {
    saveSnapshot(jan());
    const drift = computeDrift(findMatchingSnapshot(feb()).snapshot, feb());
    expect(drift.addedColumns).toEqual(['Region']);
    expect(drift.removedColumns).toEqual([]);
  });

  it('only compares measures present in both versions and sorts by size of change', () => {
    const oldS = makeSession({ rows: [{ A: 100, B: 100, Gone: 5, Category: 'x' }], measureColumns: ['A', 'B', 'Gone'] });
    const newS = makeSession({ rows: [{ A: 110, B: 300, New: 5, Category: 'x' }], measureColumns: ['A', 'B', 'New'] });
    const drift = computeDrift(buildSnapshot(oldS), newS);
    expect(drift.measureDeltas.map((m) => m.measure)).toEqual(['B', 'A']); // B moved +200%, A +10%
  });

  it('gives a null change instead of dividing by zero when the old total was 0', () => {
    const oldS = makeSession({ rows: [{ Sales: 0, Category: 'x' }] });
    const newS = makeSession({ rows: [{ Sales: 50, Category: 'x' }] });
    expect(computeDrift(buildSnapshot(oldS), newS).measureDeltas[0].sumChangePct).toBeNull();
  });

  it('returns null when the current session cannot be snapshotted', () => {
    const snap = buildSnapshot(jan());
    expect(computeDrift(snap, makeSession({ rows: [], filterableAvailable: false }))).toBeNull();
  });
});
