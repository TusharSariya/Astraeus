---
id: SPECV1-RULES
title: Rule Catalogue
type: rule-index
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - ECL26-SCORE-001
  - ECL26-SAFE-003
supersedes: []
---

# Rule catalogue

- [`solar-eclipse-v1.yaml`](solar-eclipse-v1.yaml): proposed deterministic
  planning-score transformations and gates for the `solar-eclipse` module.
- [`site-safety-v1.yaml`](site-safety-v1.yaml): proposed safety-rule structure;
  numeric environmental thresholds remain intentionally unaccepted until
  source and safety review.
- [`rerouting-policy-v1.yaml`](rerouting-policy-v1.yaml): proposed score and
  persistence thresholds for destination changes.

No draft rule file may enter a production evaluation. Observation modules name
their own score and safety rules in the module registry; rules are not silently
shared across unrelated subject families.
