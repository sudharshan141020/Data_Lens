import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  localStorage.clear(); // snapshotUtils persists to localStorage -- never let one test see another's
  vi.restoreAllMocks();
  vi.unstubAllGlobals(); // tests stub global fetch; never leak that into the next test
});

// Recharts' ResponsiveContainer needs ResizeObserver, which jsdom doesn't
// provide. A no-op stub is enough: in jsdom every element has zero size, so
// charts render no SVG anyway -- tests that care about a chart's *inputs*
// mock the chart component instead of asserting on pixels.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
