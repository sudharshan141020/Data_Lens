import { describe, it, expect } from 'vitest';
import { buildSearchIndex, searchIndex } from './searchUtils';

const V2 = {
  findings: [{ text: 'Revenue is concentrated in the West region' }],
  weak_points: [{ problem: 'Office Supplies is falling behind', impact: 'It is 25% below average.' }],
  story: [{ label: 'The headline', text: 'Sales grew steadily through 2024.' }],
  all_analyses: [
    { id: 'trend-1', title: 'Sales Trend', reasoning: 'Time dimension detected.' },
    { id: 'dist-1', title: 'Category Mix' },
  ],
  correlation_center: { pairs: [{ col1: 'Discount', col2: 'Profit', r: -0.42, caveat: 'Moderate' }, { col1: 'A', col2: 'B', r: 0.9 }] },
  partial_correlations: { results: [{ col1: 'Discount', col2: 'Profit', summary: 'Most of it is explained by Region.' }] },
};

describe('buildSearchIndex', () => {
  it('returns an empty index for an empty result', () => {
    expect(buildSearchIndex({})).toEqual([]);
  });

  it('indexes every section with the category and anchor the UI scrolls to', () => {
    const idx = buildSearchIndex(V2);
    const byCat = (c) => idx.filter((e) => e.category === c);

    expect(byCat('Finding')[0]).toEqual({ category: 'Finding', text: 'Revenue is concentrated in the West region', anchorId: 'search-finding-0' });
    expect(byCat('Weak Point')[0]).toMatchObject({ anchorId: 'search-weakpoint-0', text: 'Office Supplies is falling behind — It is 25% below average.' });
    expect(byCat('Story')[0]).toMatchObject({ anchorId: 'search-story-0', text: 'The headline: Sales grew steadily through 2024.' });
    expect(byCat('Correlation')).toHaveLength(2);
    expect(byCat('Partial Correlation')[0]).toMatchObject({ anchorId: 'search-partial-correlation-0' });
  });

  it('points chart entries at the explorer and carries the analysis id, with reasoning only when present', () => {
    const charts = buildSearchIndex(V2).filter((e) => e.category === 'Chart');
    expect(charts[0]).toMatchObject({ anchorId: 'search-explorer-panel', analysisId: 'trend-1', text: 'Sales Trend — Time dimension detected.' });
    expect(charts[1].text).toBe('Category Mix');
  });

  it('appends a correlation caveat only when there is one', () => {
    const corr = buildSearchIndex(V2).filter((e) => e.category === 'Correlation');
    expect(corr[0].text).toBe('Discount and Profit (r=-0.42) — Moderate');
    expect(corr[1].text).toBe('A and B (r=0.9)');
  });
});

describe('searchIndex', () => {
  const idx = [
    { text: 'the profit margin fell', anchorId: 'a' },
    { text: 'xprofit is a substring hit', anchorId: 'b' },
    { text: 'profit first', anchorId: 'c' },
    { text: 'nothing relevant', anchorId: 'd' },
  ];

  it('returns nothing for an empty or whitespace query', () => {
    expect(searchIndex(idx, '')).toEqual([]);
    expect(searchIndex(idx, '   ')).toEqual([]);
  });

  it('is case-insensitive and drops non-matches', () => {
    const out = searchIndex(idx, 'PROFIT');
    expect(out.map((e) => e.anchorId).sort()).toEqual(['a', 'b', 'c']);
  });

  it('ranks earlier matches first, and a word-start match above a mid-word one even if the mid-word hit is earlier', () => {
    // 'xprofit...' matches at position 1 but mid-word (score 51); 'the profit' matches at 4 on a word start (score 4)
    expect(searchIndex(idx, 'profit').map((e) => e.anchorId)).toEqual(['c', 'a', 'b']);
  });

  it('caps results at 12 and does not mutate the index entries', () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ text: `profit ${i}`, anchorId: String(i) }));
    expect(searchIndex(many, 'profit')).toHaveLength(12);
    expect(many[0]).not.toHaveProperty('score');
  });
});
