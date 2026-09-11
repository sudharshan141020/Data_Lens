# New Domains: Real Estate + SaaS/Subscription — changed files

Item #5 of the "add all" batch. New: `app/analyzers/real_estate_analyzer.py`,
`app/analyzers/saas_analyzer.py`. Modified: `app/semantic_roles.py`,
`app/understanding.py`, `app/domains.py`, `app/analyzers/registry.py`.

Followed the existing plugin architecture exactly as documented in the
codebase's own comments (registry.py: "the ONLY place that needs to
change... nowhere else branches on domain name"):
- New semantic roles (PROPERTY_TYPE, SQUARE_FOOTAGE, BEDROOMS, SALE_PRICE,
  etc. for real estate; MRR, ARR, SUBSCRIPTION_PLAN, CHURN_STATUS, etc.
  for SaaS) added to `semantic_roles.py`, inserted *before* the generic
  CATEGORY block so specific matches (e.g. "property_type") win over
  CATEGORY's broad "type"/"status" catch-all keywords.
- Aggregation defaults (MEASURE_ROLES) and dimension classification
  (DIMENSION_ROLES) added to `understanding.py`, plus entity-noun
  fallbacks ("Property", "Subscriber") in DOMAIN_DEFAULT_ENTITY.
- Domain scoring weights added to `domains.py`'s DOMAIN_SIGNALS, using
  only genuinely distinctive roles per the lesson already documented
  there (the Titanic/CATEGORY false-positive story) — no FINANCIAL_METRIC
  or generic CATEGORY signal used for either new domain.
- Two new analyzer classes, each just class attributes
  (headline_dimension_roles + key_kpis), no method overrides — same
  pattern every existing domain analyzer already follows.

## Verified this session
- Synthetic real estate dataset: detected at confidence 1.0, zero
  incidental score in any other domain, primary_entity correctly
  resolved to "Property" via the fallback.
- Synthetic SaaS dataset: detected at confidence 0.83, primary_entity
  correctly resolved to "Customer" (a Customer ID column was present,
  so the explicit match took precedence over the "Subscriber" fallback).
- Full HTTP round-trip + PDF export on both: 200 OK, all downstream
  features (segments, seasonality, anomalies, Simpson's paradox,
  Benford's Law, findings, weak points, story) ran without errors.
- Regression check: all 3 existing sample datasets
  (sales/healthcare/manufacturing) still classify correctly at full
  confidence — the new keyword insertions didn't shift any existing
  classification.
