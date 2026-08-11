---
id: ADR-004
title: Use Self-Hosted Valhalla
type: adr
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-004
supersedes: []
---

# ADR-004 — Use self-hosted Valhalla

## Context

The planner needs reproducible drive-time isochrones and route feasibility, not
straight-line radius estimates, for both web and native recommendations.

## Decision

Use a pinned Newfoundland Valhalla graph on a private persistent Montreal VM.

## Alternatives considered

- OSRM: simpler and fast, but less suitable for the planned costing and
  multimodal expansion.
- GraphHopper: capable, with a different licensing and feature tradeoff.
- Proprietary routing APIs: useful as optional navigation adapters, but their
  caching, reproducibility, and pricing terms make them unsuitable as the
  authoritative planning engine.

## Consequences

Isochrones, costing, and graph versions remain under project control. The
project owns graph promotion, health, capacity, backups, and signed precomputed
fallbacks. Base ETA is traffic-blind unless a live adapter is added.
