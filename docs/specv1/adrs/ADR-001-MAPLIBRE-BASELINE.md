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

## Context

Web and native clients need a renderer for owned, revisioned map layers without
turning a rendering vendor into the scientific source of truth.

## Decision

Use MapLibre GL JS with deck.gl on web and MapLibre React Native on mobile.
Backend analytic evidence remains renderer-neutral.

## Alternatives considered

- Mapbox Native and GL JS: stronger licensed terrain support, with greater
  vendor and redistribution constraints.
- ArcGIS Maps SDK: capable enterprise GIS tooling, but a heavier licensed
  baseline than V1 requires.
- CesiumJS/Cesium Native: useful for 3-D inspection, but not the operational
  decision surface for V1.

## Consequences

The baseline is open and supports owned layers and offline-oriented formats.
Native true-terrain parity is not assumed. CesiumJS, Mapbox, and ArcGIS remain
optional inspection or licensed adapters and cannot become obstruction truth.
