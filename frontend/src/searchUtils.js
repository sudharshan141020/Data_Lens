// Builds a flat, searchable index from the current analysis result and
// provides simple substring matching over it. Entirely client-side --
// this is UI navigation over data already in memory, not a new query.

export function buildSearchIndex(v2) {
  const index = [];

  (v2.findings || []).forEach((f, i) => {
    index.push({
      category: 'Finding',
      text: f.text,
      anchorId: `search-finding-${i}`,
    });
  });

  (v2.weak_points || []).forEach((w, i) => {
    index.push({
      category: 'Weak Point',
      text: `${w.problem} — ${w.impact}`,
      anchorId: `search-weakpoint-${i}`,
    });
  });

  (v2.story || []).forEach((beat, i) => {
    index.push({
      category: 'Story',
      text: `${beat.label}: ${beat.text}`,
      anchorId: `search-story-${i}`,
    });
  });

  (v2.all_analyses || []).forEach((a) => {
    index.push({
      category: 'Chart',
      text: `${a.title}${a.reasoning ? ' — ' + a.reasoning : ''}`,
      anchorId: 'search-explorer-panel',
      analysisId: a.id, // triggers section+selection change, not a plain scroll
    });
  });

  (v2.correlation_center?.pairs || []).forEach((p, i) => {
    index.push({
      category: 'Correlation',
      text: `${p.col1} and ${p.col2} (r=${p.r})${p.caveat ? ' — ' + p.caveat : ''}`,
      anchorId: `search-correlation-${i}`,
    });
  });

  return index;
}

export function searchIndex(index, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored = [];
  for (const entry of index) {
    const lower = entry.text.toLowerCase();
    const pos = lower.indexOf(q);
    if (pos === -1) continue;
    // Earlier matches (and matches at a word boundary) rank higher than a
    // hit buried mid-sentence.
    const atWordStart = pos === 0 || /\s/.test(lower[pos - 1]);
    const score = (atWordStart ? 0 : 50) + pos;
    scored.push({ ...entry, score });
  }
  scored.sort((a, b) => a.score - b.score);
  return scored.slice(0, 12);
}
