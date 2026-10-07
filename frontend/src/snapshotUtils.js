// Snapshot / drift comparison across repeat uploads of an evolving
// dataset -- entirely client-side (localStorage), so a recurring
// "upload this month's export" workflow can see what changed since
// last time without the backend ever storing anything, consistent
// with its genuine no-server-storage guarantee.
//
// A snapshot is a lightweight fingerprint of one analysis: column
// list, row count, each measure's sum/avg, and the weak points found
// -- never the raw rows themselves. Saved snapshots are keyed by a
// hash of their (sorted) column list, so saving a newer version of
// the "same" dataset shape simply overwrites the previous snapshot
// for that shape rather than accumulating forever.

const STORAGE_PREFIX = 'datalens_snapshot::';
const MATCH_THRESHOLD = 0.6; // fraction of columns that must overlap (Jaccard) to call two uploads "the same dataset"
const PRIORITY_RANK = { low: 0, medium: 1, high: 2 };

function hashString(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(36);
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

export function fingerprintColumns(columns) {
  return hashString([...columns].sort().join('|'));
}

function keyFor(fingerprint) {
  return `${STORAGE_PREFIX}${fingerprint}`;
}

// Builds the lightweight snapshot object for the CURRENT state of a
// ready session. Needs filterable_data (the same compact row payload
// the client-side filter/query-builder features already use) to
// compute measure totals -- unavailable on very large datasets, same
// limitation those features already have.
export function buildSnapshot(session) {
  const v2 = session?.result?.v2;
  const filterable = v2?.filterable_data;
  if (!v2 || !filterable?.available || !Array.isArray(filterable.rows)) return null;

  const columns = [...(filterable.measure_columns || []), ...(filterable.dimension_columns || [])];
  const measures = {};
  for (const m of filterable.measure_columns || []) {
    const values = filterable.rows.map((r) => r[m]).filter((v) => typeof v === 'number');
    if (!values.length) continue;
    const sum = values.reduce((a, b) => a + b, 0);
    measures[m] = { sum: round2(sum), avg: round2(sum / values.length), count: values.length };
  }

  const weakPoints = (v2.weak_points || []).map((w) => ({
    problem: w.problem, priority: w.priority, category: w.category, significant: w.significant,
  }));

  return {
    savedAt: Date.now(),
    fileName: session.fileName,
    columns: [...columns].sort(),
    rowCount: v2.profile?.row_count ?? null,
    measures,
    weakPoints,
  };
}

export function saveSnapshot(session) {
  const snapshot = buildSnapshot(session);
  if (!snapshot) return false;
  try {
    localStorage.setItem(keyFor(fingerprintColumns(snapshot.columns)), JSON.stringify(snapshot));
    return true;
  } catch {
    return false; // storage full/unavailable -- this is a convenience feature, fail quietly
  }
}

function readAllSnapshots() {
  const out = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key || !key.startsWith(STORAGE_PREFIX)) continue;
    try {
      const parsed = JSON.parse(localStorage.getItem(key));
      if (parsed && Array.isArray(parsed.columns)) out.push({ key, snapshot: parsed });
    } catch {
      // corrupt/foreign entry under our prefix -- skip it
    }
  }
  return out;
}

function overlapRatio(a, b) {
  const setA = new Set(a);
  const setB = new Set(b);
  const inter = [...setA].filter((x) => setB.has(x)).length;
  const union = new Set([...setA, ...setB]).size;
  return union ? inter / union : 0;
}

// Finds the best previously-saved snapshot that looks like an earlier
// version of the CURRENT session's dataset -- exact column-set match
// first, else the closest fuzzy match above MATCH_THRESHOLD (so adding
// or dropping a column or two between exports doesn't break the match).
export function findMatchingSnapshot(session) {
  const current = buildSnapshot(session);
  if (!current) return null;

  const exactKey = keyFor(fingerprintColumns(current.columns));
  let best = null;
  let bestScore = 0;
  for (const { key, snapshot } of readAllSnapshots()) {
    if (key === exactKey) return { snapshot, score: 1, isExact: true };
    const score = overlapRatio(current.columns, snapshot.columns);
    if (score > bestScore) {
      bestScore = score;
      best = snapshot;
    }
  }
  if (best && bestScore >= MATCH_THRESHOLD) return { snapshot: best, score: round2(bestScore), isExact: false };
  return null;
}

// Compares a previously-saved snapshot against the CURRENT session's
// live data -- which measures moved and by how much, which weak points
// got resolved/newly appeared/got worse/got better, and which columns
// were added or dropped.
export function computeDrift(oldSnapshot, session) {
  const current = buildSnapshot(session);
  if (!current) return null;

  const measureDeltas = [];
  const allMeasureNames = new Set([...Object.keys(oldSnapshot.measures || {}), ...Object.keys(current.measures || {})]);
  for (const name of allMeasureNames) {
    const oldM = oldSnapshot.measures?.[name];
    const newM = current.measures?.[name];
    if (!oldM || !newM) continue; // only compare measures present in both snapshots
    const sumChangePct = oldM.sum ? round2(((newM.sum - oldM.sum) / Math.abs(oldM.sum)) * 100) : null;
    measureDeltas.push({ measure: name, oldSum: oldM.sum, newSum: newM.sum, sumChangePct });
  }
  measureDeltas.sort((a, b) => Math.abs(b.sumChangePct || 0) - Math.abs(a.sumChangePct || 0));

  const oldByProblem = new Map((oldSnapshot.weakPoints || []).map((w) => [w.problem, w]));
  const newByProblem = new Map((current.weakPoints || []).map((w) => [w.problem, w]));

  const resolved = [];
  const worsened = [];
  const improved = [];
  const newIssues = [];
  for (const [problem, oldW] of oldByProblem) {
    const newW = newByProblem.get(problem);
    if (!newW) {
      resolved.push(oldW);
      continue;
    }
    const oldRank = PRIORITY_RANK[oldW.priority] ?? 1;
    const newRank = PRIORITY_RANK[newW.priority] ?? 1;
    if (newRank > oldRank) worsened.push(newW);
    else if (newRank < oldRank) improved.push(newW);
  }
  for (const [problem, newW] of newByProblem) {
    if (!oldByProblem.has(problem)) newIssues.push(newW);
  }

  const oldCols = new Set(oldSnapshot.columns);
  const newCols = new Set(current.columns);
  const addedColumns = current.columns.filter((c) => !oldCols.has(c));
  const removedColumns = oldSnapshot.columns.filter((c) => !newCols.has(c));

  const rowCountChangePct = oldSnapshot.rowCount
    ? round2(((current.rowCount - oldSnapshot.rowCount) / oldSnapshot.rowCount) * 100)
    : null;

  return {
    oldFileName: oldSnapshot.fileName,
    oldSavedAt: oldSnapshot.savedAt,
    newFileName: current.fileName,
    rowCountOld: oldSnapshot.rowCount,
    rowCountNew: current.rowCount,
    rowCountChangePct,
    measureDeltas,
    resolved,
    newIssues,
    worsened,
    improved,
    addedColumns,
    removedColumns,
  };
}
