---
id: ADR-002
title: Use Cloudflare and Cloud Run
type: adr
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - v1_web
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-003
supersedes: []
---

# ADR-002 — Use Cloudflare and Cloud Run

## Decision

Use Cloudflare for web/CDN/WAF/R2 and a thin Worker boundary. Use Montreal
Cloud Run for stateless Python services and jobs.

## Consequences

The system gains managed global delivery and suitable Python compute without
raw-cloud orchestration. Cross-provider identity, egress, recovery, and cost
limits are explicit operational responsibilities.
