# DataLens case study: making an analytics tool trustworthy

DataLens takes any CSV or Excel file and returns an analytical report: the
domain it detected, the analyses worth looking at, a plain-English story,
statistically-checked correlations. It is rule-based end to end (no LLM calls),
so every output traces back to an explicit rule.

This page covers the second phase of the project. The first phase was
**discovery**: finding what stands out. The second asked a harder question:
*can you trust what it tells you, and what would you do next?*

## What I added, and the question each one answers

| Addition | The question it answers | The decision I'd point to |
|---|---|---|
| **Why did it change?** | "Sales fell 2.7%. Where?" | Contributions add up *exactly* to the total. Offsetting moves (West +100, East −90) are called out instead of printing a meaningless 2000%. |
| **Personal-data guard** | "Is it safe to share this link?" | Detection reports column names and kinds, never values, because the report travels inside the very result being shared. |
| **Robustness check** | "Does this hold without the outliers?" | It tests a different failure from sampling noise: a result that is real but really about a few rows. |
| **Test a Hypothesis** | "Is B different from A?" | The test is chosen *and justified*. The headline is the effect size and interval; the p-value is not. |
| **Show the code** | "How was this computed? Can I continue in a notebook?" | A fixed template per analysis type, verified by running the output. |
| **Frontend tests and CI** | "Will the next change break it?" | One real-browser test drives the whole flow, and any console error fails it. |

## What testing caught

The most useful part of the work was the bugs that the first round of tests
missed. They are the reason the later tests look the way they do.

**A privacy leak in my own guard.** I wrote masking for the share link and its
unit tests passed. Then a browser test inspected the request actually sent and
found real customer IDs still in it: in the at-risk customer list (as raw
numbers) and as `y` values of scatter charts. My masking only matched string
values from the row data, and my tests had built their own rows, so they
never saw it. The fix handles those places structurally, and the regression
tests now run against the real captured analysis, including the case where the
identifier isn't in the row data at all.

**A security check that could freeze the server.** To enforce the guard on the
server I wrote an email scan with the obvious regex, and the existing
"oversized payload" test hung for five minutes. The pattern is quadratic on a
long run of letters with no `@`, so a single hostile request could have stalled
the server: a worse property than having no check. The scan now finds each `@`
in linear time and examines only a bounded window around it, the size limit is
checked before anything is scanned, and there are timing tests on seven
pathological inputs (8 MB of `x`, 5 MB of `@`, and so on). A malformed-payload
test found a second crash: a string where an object was expected raised an
error instead of being ignored.

**A guard that checks the right thing.** The server cannot trust a caller's
report of what is sensitive, because it can simply be omitted, so it re-derives
what it can from the payload itself: real values in the rows (which a false
"masked" claim cannot hide), column names that suggest personal data, and
emails, SSNs and card numbers in the text. Testing it also clarified what it
should protect: a file with 300 unique email addresses shares fine, because
they are too many to become a chart category or a row-level column and so never
reach the payload. The guard looks at what is being *published*, not at what was
uploaded.

**A warning nobody could read.** A screenshot showed the personal-data dialog
as dark text on a dark box in the light theme. I had used CSS variables the
app doesn't define, so the fallbacks applied. No unit test can see that, so I
added a browser test that computes the real WCAG contrast ratio of the painted
text in both themes. To check the test isn't vacuous I put the bug back: the
ratio came out at 1.1 against a required 4.5, and the test failed.

**False alarms that would teach people to ignore the tool.** Reading real
output (not just passing tests) found two. The robustness check called clean
synthetic data "sensitive" because a correlation went from 0.702 to 0.687 and
crossed a label boundary from "strong" to "moderate"; it now judges only the
size of the change. And it flagged a discount column as outlier-driven when
discounts simply come in tiers (0, 0.1, 0.2, 0.7); more than 5% of rows outside
the fences is now reported as "skewed", a different claim. A driver drill-down
that printed "975% of Furniture's change" was arithmetic noise, so it is now
skipped when the segment's own moves cancel.

**Two differences the round-trip test found while I built it.** The exported
script is executed and compared with the dashboard. That immediately showed
the app's trend data includes forecast months (the script is history only) and
that the app rounds its headline estimates to two decimals. Neither would have
been noticed by reading the code.

**A p-value check that catches miswiring.** Unit tests can all pass on a
hypothesis test that is subtly wrong. So there is a calibration test: with no
real difference, about 5% of 600 simulated tests must come out significant;
with a real effect, over 90% must, and none may point the wrong way.

## How it is built

- **Rule-based, auditable, free to run.** No LLM calls anywhere, including the
  code export, which is a template per analysis type.
- **Stateless.** The server stores nothing. The hypothesis test receives only
  the two groups' values; the code export receives names and analysis
  definitions, never row data.
- **Untrusted text never becomes code.** Column names and filter values come
  from the user's file. They enter the exported script only as quoted
  literals, and a test parses the output and asserts the only imports are
  json, sys, pathlib, numpy and pandas.
- **Fails loudly in the browser.** The end-to-end tests fail on any uncaught
  exception or console error, so a feature that "works" but logs a React
  warning cannot pass.

## What it does not do

- The personal-data check is heuristic. It can miss things or flag harmless
  columns, and says so in the interface. Share links are enforced on the server
  (a caller can only proceed by explicitly acknowledging), but that protects
  against accidents, not someone determined to publish data they already hold.
  It cannot verify a claim that an identifier column was masked when that
  column's values appear only as numbers; it can verify that real values in the
  rows are gone. PDF and HTML exports are downloads to the same person, so they
  are guarded by the dialog only.
- The exported script reproduces loading, cleaning and the groupbys. It does
  not reproduce forecasts, k-means segments, anomaly scores, cohorts or
  p-values and bootstrap intervals.
- "Why did it change?" shows where a change landed, not why it happened, and
  says so on the panel. The driver and robustness panels use the full dataset
  and do not re-compute under the filter bar; the hypothesis test does use the
  filtered rows.
- The hypothesis test compares two groups at a time and assumes rows are
  independent (repeated customers make its p-value too optimistic). It does
  no multiple-testing correction and warns about running many tests and
  reporting the best one.
- Row-level features are unavailable on files over 100,000 rows.

## By the numbers

313 backend tests, 407 frontend tests, 11 end-to-end tests in a real browser,
all in CI. Six additions, each with a changelog entry explaining the
decisions and the bugs found along the way (`CHANGELOG.md`).

## Talking about it

Accurate one-liners, in case they help:

- Extended a rule-based analytics app (FastAPI, pandas, React) with driver
  analysis, a personal-data share guard enforced on the server, an
  outlier-robustness check, A/B hypothesis testing and a pandas-script export,
  backed by 313 backend, 407 frontend and 11 real-browser tests.
- Verified the statistics rather than just exercising them: calibration tests
  for false-positive rate, cross-checks against SciPy, and executing the
  exported script to compare it with the dashboard.
- Found and fixed a privacy leak in my own data-masking feature with a
  browser-level test, and a denial-of-service in my own validation code (a
  quadratic regex) with timing tests on hostile input, and added a contrast test (checked by reintroducing the
  bug) after a screenshot showed the warning was unreadable in the light theme.
