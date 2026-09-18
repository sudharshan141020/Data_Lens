# CI Workflow — changed files

Eighth and final item of this round. New:
`.github/workflows/tests.yml`.

Runs the full pytest suite (64 tests: unit, statistical-module,
pipeline-robustness, file-format, API-endpoint, and property-based)
automatically on every push and pull request, using GitHub Actions'
free Ubuntu runner. Matches your actual local Python version (3.12,
from your earlier terminal output) rather than an arbitrary default.

Small correctness fix along the way: PyYAML parses a bare `on:` key as
the boolean `True` rather than the string `"on"` (the well-known YAML
1.1 "Norway problem" — `on`/`off`/`yes`/`no` are boolean literals in
that spec). GitHub's own workflow parser handles this correctly
regardless, so it wasn't going to break anything, but quoting it as
`"on":` removes the ambiguity outright rather than relying on that.

## Verified this session
- YAML validated for correct structure (parsed with PyYAML, confirmed
  the `on` key is unambiguously a string after the fix).
- The exact commands the workflow runs — `python -m pip install
  --no-cache-dir -r requirements-dev.txt` then `python -m pytest` —
  run for real in this session: 64/64 passing, ~7.9s.

## One thing only you can do
GitHub Actions needs the repo actually pushed to GitHub to run this —
nothing to configure beyond having the file in `.github/workflows/`
once it's there. If you want a status badge in your README, it's:
`![Tests](https://github.com/<you>/<repo>/actions/workflows/tests.yml/badge.svg)`
