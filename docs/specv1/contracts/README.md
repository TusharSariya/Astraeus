---
id: SPECV1-CONTRACTS
title: Executable Contract Catalogue
type: contract-index
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
  - RFC-001
  - RFC-004
supersedes: []
---

# Executable contract catalogue

- [`openapi.yaml`](openapi.yaml): dynamic web plan lifecycle and transport.
- [`observation-modules.yaml`](observation-modules.yaml): registered module
  identities, capabilities, contracts, rules, limitations, and lifecycle.
- [`observation-module-registry.schema.json`](schemas/observation-module-registry.schema.json):
  machine validation for the module registry.
- [`evaluation-revision.schema.json`](schemas/evaluation-revision.schema.json):
  immutable evaluation identity.
- [`layer-manifest.schema.json`](schemas/layer-manifest.schema.json): analytic
  and explanatory map assets.
- [`plan-snapshot.schema.json`](schemas/plan-snapshot.schema.json): signed
  controlled-preview/fallback envelope.

These contracts are proposed until their golden examples and generated clients
are reviewed. Once accepted, prose cannot override their wire shapes.
