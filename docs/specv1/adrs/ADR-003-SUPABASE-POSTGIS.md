---
id: ADR-003
title: Use Supabase PostgreSQL and PostGIS
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

# ADR-003 — Use Supabase PostgreSQL and PostGIS

## Context

Candidate sites, routes, evaluation metadata, and provenance require spatial
queries and transactional persistence shared by web and native clients through
the API boundary.

## Decision

Use a Canada Central Supabase PostgreSQL/PostGIS project for metadata, spatial
queries, evaluations, and job state. Keep Auth disabled until accounts are a
real requirement.

## Alternatives considered

- Managed PostgreSQL directly on Google Cloud: tighter provider locality, with
  more database operations and product plumbing.
- Cloudflare D1: attractive at the edge, but not a PostGIS replacement for the
  required spatial workload.
- SQLite/DuckDB: appropriate for local prototypes and analysis, but not the
  multi-client production metadata store.

## Consequences

FastAPI remains the trust boundary; clients do not query PostgREST or service
roles directly. Cloud Run needs static egress, TLS, pooling, least-privilege
roles, bounded connections, and tested backup restore.
