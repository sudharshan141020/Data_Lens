# Property-Based Tests (Hypothesis) — changed files

Seventh item of this round. New: `tests/test_property_based.py`.
Modified: `requirements-dev.txt` (added `hypothesis>=6.100`).

Direct response to how many real, non-obvious bugs turned up in item #6
(chunked file reads) this session — a category-dtype ordering bug, a
cross-cutting date-column crash, a numpy-dtype JSON serialization bug.
The rest of the suite is example-based (specific input, specific
expected output), which can only ever check examples someone thought to
write. This states invariants that must hold for ANY valid input and
lets Hypothesis search for violations:

- **Clustering**: cluster sizes always sum to the row count actually
  used; k always within its documented bounds.
- **Anomaly detection**: never crashes; `anomaly_count` always equals
  the length of the uncapped row-index list; every flagged index is a
  valid row position; percentage always in [0, 100].
- **Confidence intervals**: the interval always contains its own point
  estimate, for any distribution shape Hypothesis generates.
- **Benford's Law**: observed/expected proportions always sum to ~1;
  p-value always in [0, 1].
- **Chunked CSV reading**: row count survives the read exactly, and
  numeric columns stay numeric, for arbitrary generated numeric data —
  not just the hand-picked examples in test_pipeline_robustness.py.

## A real finding — and what it turned out to be
Hypothesis immediately found a failing case for the Benford proportion-
sum property. Investigated rather than just loosening the assertion:
`benford.py` deliberately rounds each of the 9 digit proportions to 4
decimal places before storing them (matching the app's display-rounding
convention throughout). Summing 9 independently-rounded values can
accumulate up to ~9×0.00005 of drift — the original test's `1e-6`
tolerance was checking for raw float64 precision, which was never a
realistic bar given the intentional rounding. Fixed by widening the
tolerance to `1e-3`, with a comment explaining why — this was a
test-quality bug, not a product bug, and Hypothesis earned its keep by
finding the mismatch between what I assumed and what the code actually,
correctly does.

## Verified this session
- All 5 property tests pass after the tolerance fix.
- Full pytest suite (property-based + everything from prior rounds):
  64/64 passing, ~8.4s total — the property tests add real fuzzing
  coverage for about 2 extra seconds of runtime, still fast enough to
  run on every change.
