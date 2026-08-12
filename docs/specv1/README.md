---
id: SPECV1-INDEX
title: Astraeus V1 Specification Index
type: index
status: accepted
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on: []
supersedes: []
---

# Astraeus V1 specification index

This is the mandatory entry point for Astraeus V1 product and implementation
work. Read [governance](GOVERNANCE.md) before changing behavior or a normative
document.

## Authority

- Accepted specifications in this directory are normative.
- Accepted executable contracts and rule files are normative for their declared
  interface and must agree with their owning specification. Draft or proposed
  artifacts MUST NOT authorize production behavior.
- [Research](../research/README.md) is supporting evidence, not a requirement.
- GitHub Issues and pull requests track work; they do not redefine behavior.
- A contradiction blocks implementation. Do not choose a convenient source.

## Release profiles

| Profile | Meaning | Current status |
|---|---|---|
| `event_day_preview` | Fixed-origin, signed, precomputed controlled preview | Proposed |
| `v1_web` | Dynamic-origin web planner with live data | Draft |
| `v1_native` | Public iOS/Android companion | Draft and gated |

## Normative documents

### Product

- [PRD-001 — Astraeus V1](product/PRD-001-ASTRAEUS-V1.md)

### Cross-cutting RFCs

- [RFC-000 — System overview](rfcs/RFC-000-SYSTEM-OVERVIEW.md)
- [RFC-001 — Evidence revisions and provenance](rfcs/RFC-001-EVIDENCE-REVISIONS-AND-PROVENANCE.md)
- [RFC-002 — Client rendering and offline](rfcs/RFC-002-CLIENT-RENDERING-AND-OFFLINE.md)
- [RFC-003 — Platform deployment and operations](rfcs/RFC-003-PLATFORM-DEPLOYMENT-AND-OPERATIONS.md)
- [RFC-004 — Site selection and routing](rfcs/RFC-004-SITE-SELECTION-AND-ROUTING.md)
- [RFC-005 — Observation subjects and modules](rfcs/RFC-005-OBSERVATION-SUBJECTS-AND-MODULES.md)

### Architecture decisions

- [ADR-001 — MapLibre baseline](adrs/ADR-001-MAPLIBRE-BASELINE.md)
- [ADR-002 — Cloudflare and Cloud Run](adrs/ADR-002-CLOUDFLARE-AND-CLOUD-RUN.md)
- [ADR-003 — Supabase PostGIS](adrs/ADR-003-SUPABASE-POSTGIS.md)
- [ADR-004 — Valhalla](adrs/ADR-004-VALHALLA.md)

### Features

- [August 12, 2026 eclipse planner](features/eclipse-2026-08-12/README.md)

The eclipse is the first fully specified composition of the generic observation-
module protocol. Non-eclipse capability profiles in RFC-005 are planned, not
implemented or callable.

### Executable contracts

- [Contract catalogue](contracts/README.md)
- [Rule catalogue](rules/README.md)

### Cross-cutting verification

- [Observation module verification matrix](verification/OBSERVATION-MODULES.md)

## Dependency order

```text
governance and contract freeze
  -> geometry, provider, site/routing, and layer fixtures
  -> deterministic scoring fixture and golden recommendation
  -> fixture-backed API and evidence viewer
  -> live-provider integration
  -> staging, recovery, security, and load gates
  -> v1_web
  -> native risk spike and v1_native gates
```

An implementation agent MUST cite accepted requirement IDs, use the owning
contract version, add mapped verification, and run `specctl validate` before
preparing a pull request.

## Current release blockers

1. Accept the HTTP and artifact schemas after fixture review.
2. Accept the eclipse scoring and site-safety rule files with hand-calculated
   cases.
3. Approve a current access/safety catalogue for ranked sites.
4. Validate live provider fields, cadence, licences, and eclipse-time behavior.
5. Benchmark routing, candidate recall, and snapshot fallback.
6. Pass staging load, recovery, cost, and regional-failure rehearsals.
7. Complete native renderer and physical-device gates before `v1_native`.
