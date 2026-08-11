---
id: ADR-003
title: Use Supabase PostgreSQL and PostGIS
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

# ADR-003 — Use Supabase PostgreSQL and PostGIS

## Decision

Use a Canada Central Supabase PostgreSQL/PostGIS project for metadata, spatial
queries, evaluations, and job state. Keep Auth disabled until accounts are a
real requirement.

## Consequences

FastAPI remains the trust boundary; clients do not query PostgREST or service
roles directly. Cloud Run needs static egress, TLS, pooling, least-privilege
roles, bounded connections, and tested backup restore.
