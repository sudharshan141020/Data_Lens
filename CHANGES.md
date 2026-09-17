# Chunked File Reads + Memory Reduction — changed files

Sixth item of this round. Modified only: `app/main.py`,
`tests/test_api_endpoints.py`, `tests/test_pipeline_robustness.py`.

## Honest scope note
True end-to-end streaming isn't compatible with how this app works —
every analysis module (clustering, correlations, anomaly detection...)
needs the complete dataframe in memory at once. What's genuinely
achievable and implemented: (1) a `MAX_FILE_SIZE_MB` cap (250MB) with a
clear error instead of an uncontrolled OOM crash, and (2) chunked CSV
parsing with per-chunk numeric downcasting (float64→float32,
int64→smallest int that fits), which measurably shrinks the FINAL
dataframe's memory footprint — the part of "large file" pain that's
actually fixable without restructuring how the app analyzes data.

## Three real bugs caught and fixed while building this — in sequence
This is the most bug-prone single change of the whole session, and the
test suite from two rounds ago caught every one of them before they
shipped:

1. **Categorical-conversion ordering bug.** First version also converted
   low-cardinality string columns to `category` dtype during chunking,
   for a bigger memory win (74MB vs 90MB on the benchmark below). But
   converting *before* `_coerce_mostly_numeric_columns` runs meant a
   "mostly numeric, few stray text values" column could get miscategorized
   as `category` dtype and silently skip that cleanup (category dtype is
   neither plain `object` nor treated as string dtype by the existing
   skip-check). Fixed initially by reordering — categorize only after
   numeric coercion — but then:

2. **Cross-cutting date-column bug.** A date column with relatively few
   distinct months got converted to `category` dtype (low cardinality),
   and unrelated code in `kpi.py` called `.min()`/`.max()` on it expecting
   a datetime — crashes on an unordered Categorical. This is exactly the
   kind of subtle interaction the project's own documented bug history
   warns about. Fixed by **removing categorical conversion entirely**,
   keeping only numeric downcasting (which can't have this class of bug —
   float32/int8 behave identically to float64/int64 for every comparison
   any other code does, just with less precision/range). Reduces the
   memory win from 38% to ~25%, but removes real risk.

3. **JSON serialization bug.** `numpy.float64` happens to subclass
   Python's built-in `float` (so it always serialized fine by accident),
   but `numpy.float32`/`int8` do not subclass anything JSON-aware — every
   endpoint returning one immediately 500'd. Root cause was two layers
   deep: FastAPI's own `jsonable_encoder` runs *before* the app's custom
   `SafeJSONResponse.render()` (which already existed to sanitize NaN/
   Infinity) ever gets a chance, so the existing NaN-sanitizing logic
   silently never ran on the crashing values. Fixed two ways: (a)
   `_sanitize_json` now converts any `numpy.generic` scalar via `.item()`
   before its NaN check, and (b) the three routes that return raw dicts
   (`/api/analyze`, `/api/compare`, `/api/analyze-combined`) now
   explicitly wrap their response in `SafeJSONResponse(...)` before
   returning, which makes FastAPI skip its own encoder and use the
   already-numpy-aware one instead.

## Verified this session
- Benchmarked with `resource.getrusage` (not assumed): 2M rows / 124MB
  CSV — single-shot read: 120.0MB final dataframe. Chunked + numeric
  downcast: 90.0MB (25% smaller).
- Float32 precision loss checked explicitly: relative error ~2.4×10⁻⁸ on
  a 2M-row sum — confirmed as expected, benign float32 behavior (via
  relative, not absolute, comparison), not a correctness bug.
- The exact bug-2 scenario (low-cardinality numeric column with stray
  text, mixed with a real date column) re-tested after the fix: numeric
  column still coerces correctly, no crash on the date column.
- File-size cap tested with a temporarily lowered threshold: rejects
  cleanly with a clear message; normal files unaffected.
- Full pipeline (segments, anomalies, confidence intervals, etc.) run on
  a genuinely downcast dataframe: no crashes, correct results.
- Full real HTTP round-trip on a 300K-row / 12MB upload: 200 OK,
  anomalies and confidence intervals both available, PDF export also
  200 OK.
- Full pytest suite: 59/59 passing (56 existing + 3 new regression
  tests, one per bug above), ~6.6s.
