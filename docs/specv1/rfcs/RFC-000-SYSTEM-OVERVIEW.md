---
id: RFC-000
title: Astraeus V1 System Overview
type: rfc
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - PRD-001
supersedes: []
---

# RFC-000 — Astraeus V1 system overview

## Summary

Astraeus is a decision and optimization layer over authoritative astronomy,
weather, observation, terrain, access, and routing evidence. Scientific
providers remain independent from scoring and presentation. UTC, explicit
units, immutable revisions, and provenance are system invariants.

## SYS-ARCH-001 — Maintain explicit service boundaries

```text
request
  -> observation-subject and module resolution
  -> subject-specific geometry and critical-window evaluation
  -> reachable candidate generation
  -> normalized forecast and observation evidence
  -> obstruction, access, route, and site-safety evaluation
  -> scenario utility and time-window aggregation
  -> ranked recommendation revision
  -> renderer-neutral manifests and clients
```

Provider formats MUST terminate at adapters. Scoring MUST consume normalized
domain objects, not GRIB, satellite, vendor, or renderer-specific structures.

## SYS-ARCH-002 — Keep authoritative computation server-side

Subject resolution, module-owned geometry, source normalization, scoring,
line-of-sight evaluation, candidate eligibility, safety gates, alerts, and
provenance MUST execute on the backend. Clients are trusted renderers and
caches, not independent scientific pipelines. Exact point probes MUST use
analytic data, never sampled pixels.

## SYS-ARCH-003 — Use one monorepo with bounded sharing

```text
apps/
  web/                 React/Vite client
  mobile/              Expo/React Native client
packages/
  contracts/           generated API and schema types
  api-client/          generated requests and transport behavior
  domain/              pure units, revision, mask, and display semantics
  ui-web/              web-specific UI
  ui-mobile/           native-specific UI
services/
  api/                 FastAPI request and read services
  jobs/                ingestion, evaluation, and precompute entry points
  routing/             Valhalla graph and adapter
infra/
  cloudflare/
  gcp/
  supabase/
  compose/
```

DOM and React Native UI MUST NOT be forced into a universal component layer.
Contracts, pure domain behavior, tokens, icons, and safety copy MAY be shared.

## SYS-ARCH-004 — Standardize the toolchain

- Node.js LTS, pnpm, and Turborepo own JavaScript builds.
- React 19, Vite, TanStack Router, and TanStack Query own the web shell.
- Expo development builds, React Native, and Expo Router own native clients.
- Python 3.12 and `uv` own scientific and backend environments.
- FastAPI/Pydantic define the HTTP API and OpenAPI output.
- PostgreSQL/PostGIS store relational and spatial state.
- R2 stores large immutable source and derived artifacts.
- xarray, cfgrib, ecCodes, Rasterio/GDAL, pyproj, Shapely, and GeoPandas own
  scientific/geospatial processing.

Bun MAY be evaluated as a local accelerator but MUST NOT create a second
lockfile or become a required runtime. Containers are built once, addressed by
digest, and promoted without per-environment rebuilds.

## SYS-ARCH-005 — Make all boundaries versioned

The committed OpenAPI document and JSON Schemas are the interface source of
truth. A backend schema change MUST regenerate clients and fail CI on an
uncommitted diff. Every normalized object, rule set, provider adapter, routing
graph, site catalogue, observation module, and evaluation revision carries a
version.

## Alternatives

- A T3/tRPC monolith was rejected because Python scientific processing and
  renderer-neutral contracts are first-class.
- A React Native Web universal UI was rejected because web and native maps,
  offline storage, accessibility, sensors, and lifecycle semantics differ.
- Raw AWS was rejected as unnecessary operational complexity for V1.
- A distributed microservice architecture was rejected until measured load
  requires it.

## Failure behavior

Missing or stale critical evidence MUST produce an explicit typed degraded or
no-recommendation state. No layer, provider, client, or route service may hide
failure behind a visually plausible fallback.
