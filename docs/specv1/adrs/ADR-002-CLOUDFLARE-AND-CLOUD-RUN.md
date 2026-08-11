---
id: ADR-002
title: Use Cloudflare and Cloud Run
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
  - RFC-003
supersedes: []
---

# ADR-002 — Use Cloudflare and Cloud Run

## Context

Both clients need a stable public API and evidence-delivery boundary, while the
scientific pipeline needs managed Python compute and geospatial dependencies.

## Decision

Use Cloudflare for web/CDN/WAF/R2 and a thin Worker boundary. Use Montreal
Cloud Run for stateless Python services and jobs.

## Alternatives considered

- Vercel/Next.js: excellent application hosting, but not the preferred home for
  the Python scientific and long-running ingestion workloads.
- Railway: simple deployment, with less explicit edge, WAF, object-storage, and
  regional-control architecture for the event-day workload.
- Raw AWS: capable, but intentionally excluded because of operational surface
  area and cost complexity.

## Consequences

The system gains managed global delivery and suitable Python compute without
raw-cloud orchestration. Cross-provider identity, egress, recovery, and cost
limits are explicit operational responsibilities.
