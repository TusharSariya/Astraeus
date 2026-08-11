---
id: ECL26-INDEX
title: August 12 2026 Eclipse Planner
type: feature-index
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - PRD-001
  - RFC-001
  - RFC-004
supersedes: []
---

# August 12, 2026 eclipse planner

Recommend the strongest safe, lawful, reachable observation opportunity for
the August 12, 2026 partial solar eclipse from the user's Avalon Peninsula
origin.

## Feature specifications

- [Product behavior](PRODUCT_SPEC.md)
- [Scientific model](SCIENCE_SPEC.md)
- [Provider and normalization contract](DATA_SPEC.md)
- [Safety](SAFETY_SPEC.md)
- [UX and visualization](UX_SPEC.md)
- [Delivery and rollout](DELIVERY_SPEC.md)
- [Verification and traceability](VERIFICATION.md)

## Fixed planning case

- Seed origin: `47.609032, -52.692213`, near St. John's.
- Internal time: UTC; display zone: `America/St_Johns`.
- Availability: noon–7:00 p.m. NDT.
- Maximum one-way travel: 90 minutes, subject to full round-trip feasibility.
- Mode: certified-filter visual observation and front-filtered photography.
- Ranking interval: local maximum ±30 minutes, emphasizing ±10 minutes.
- Geographic package: Avalon Peninsula.

Approximate St. John's validation values are C1 2:28:44 p.m. NDT, maximum
3:34:55 p.m., C4 4:36:55 p.m., magnitude 0.617, and obscuration 53.1%. These
are regression controls, not values to reuse for another site.

## Release readiness

The controlled preview may ship only as a signed, manually supervised fixed-
origin snapshot. Dynamic planning remains blocked on accepted contracts/rules,
approved site evidence, live-provider validation, routing benchmarks, and
staging recovery/load gates. Native public release additionally requires every
native gate in the delivery spec.
