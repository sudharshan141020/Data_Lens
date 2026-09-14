# New Domains: E-commerce + Insurance — changed files

Fourth item of this round (13th and 14th domain overall). New:
`app/analyzers/ecommerce_analyzer.py`, `app/analyzers/insurance_analyzer.py`.
Modified: `app/semantic_roles.py`, `app/understanding.py`, `app/domains.py`,
`app/analyzers/registry.py`, plus `tests/conftest.py` and
`tests/test_domain_detection.py` with new fixtures/tests.

Same plugin architecture as real_estate/saas from the previous round —
new semantic roles (CART_VALUE, CART_STATUS, PAGE_VIEWS, PAYMENT_METHOD
for e-commerce; PREMIUM, CLAIM_AMOUNT, CLAIM_STATUS, COVERAGE_TYPE,
DEDUCTIBLE, RISK_SCORE for insurance) inserted before the generic
CATEGORY block, domain scoring weights using only distinctive roles,
two new analyzer classes with just class attributes.

E-commerce is deliberately distinct from the existing sales/retail
domains: it models in-progress cart/session data (abandonment, page
views, payment method) rather than completed transactions.

## Verified this session
- Both domains detected at confidence 1.0 with zero incidental score in
  any other domain.
- Regression check: all 3 existing real sample datasets
  (sales/healthcare/manufacturing) still classify correctly — no shift
  from the new keyword insertions.
- Full HTTP round-trip + PDF export on both: 200 OK.
- Full pytest suite: 54/54 passing (50 existing + 4 new: 2 detection +
  2 no-leakage-margin tests, following the exact pattern the previous
  round's real_estate/saas tests established), ~6.4s.
