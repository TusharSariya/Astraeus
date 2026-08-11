---
id: ADR-004
title: Use Self-Hosted Valhalla
type: adr
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - v1_web
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-004
supersedes: []
---

# ADR-004 — Use self-hosted Valhalla

## Decision

Use a pinned Newfoundland Valhalla graph on a private persistent Montreal VM.

## Consequences

Isochrones, costing, and graph versions remain under project control. The
project owns graph promotion, health, capacity, backups, and signed precomputed
fallbacks. Base ETA is traffic-blind unless a live adapter is added.
