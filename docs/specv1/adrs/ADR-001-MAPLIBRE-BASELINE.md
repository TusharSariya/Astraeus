---
id: ADR-001
title: Use MapLibre as the Operational Map Baseline
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
  - RFC-002
supersedes: []
---

# ADR-001 — Use MapLibre as the operational map baseline

## Decision

Use MapLibre GL JS with deck.gl on web and MapLibre React Native on mobile.
Backend analytic evidence remains renderer-neutral.

## Consequences

The baseline is open and supports owned layers and offline-oriented formats.
Native true-terrain parity is not assumed. CesiumJS, Mapbox, and ArcGIS remain
optional inspection or licensed adapters and cannot become obstruction truth.
