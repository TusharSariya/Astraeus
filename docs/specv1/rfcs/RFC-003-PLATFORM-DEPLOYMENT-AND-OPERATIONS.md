---
id: RFC-003
title: Platform Deployment and Operations
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
  - RFC-000
  - RFC-001
supersedes: []
---

# RFC-003 — Platform deployment and operations

## OPS-TOPO-001 — Use the approved managed topology

```text
Cloudflare
  Vite web, DNS/TLS/WAF/CDN, R2, thin API/asset Worker
Google Cloud Run northamerica-northeast1
  FastAPI, task worker, ingestion/batch jobs, TiTiler, Martin
Supabase ca-central-1
  PostgreSQL/PostGIS; Auth disabled until required
GCE Montreal private VM
  Valhalla with persistent disk and versioned graph
```

Cloud Run services are stateless. Durable state belongs in Postgres or R2.
Free tiers are development conveniences, not event-day reliability claims.

## OPS-EDGE-001 — Make Cloudflare the canonical public boundary

`/api/*` routes through a thin Worker that performs bounded normalization,
admission, origin authentication, and asset authorization. Cloud Run rejects
requests without a short-lived audience-bound origin credential. Task workers
accept only same-project Cloud Tasks OIDC with pinned audience. Administrative
and batch endpoints have no public ingress.

The Worker MUST NOT decode scientific formats, score, perform geometry, or
authoritatively mask data.

## OPS-QUEUE-001 — Bound asynchronous work

The Montreal plan queue starts at one dispatch/second, two concurrent
dispatches, a 14-minute per-attempt dispatch deadline, no more than five
attempts, and a 30-minute total retry window. The total retry window is the
governing bound and may stop retries before five attempts. Use exponential
backoff, deterministic task names, and a durable terminal failure state.
Admission returns `429` for quota rejection and `503` only for retryable
platform saturation.

Scheduled ingests use a unique provider/product/run/normalization key, durable
lease, idempotent checkpoints, and compare-and-swap publication. A late job
cannot move `latest` backwards. Publication requires complete manifests,
hashes, and QC.

## OPS-CAP-001 — Enforce initial compute envelopes

| Workload | CPU/RAM | Concurrency | Maximum | Timeout |
|---|---:|---:|---:|---:|
| API | 1 vCPU / 1 GiB | 20 | 10 instances | 60 s |
| Task worker | 2 vCPU / 4 GiB | 1 | 4 instances | 15 min |
| TiTiler | 2 vCPU / 4 GiB | 4 | 4 instances | 120 s |
| Martin | 1 vCPU / 1 GiB | 20 | 4 instances | 60 s |
| Ingestion job | 4 vCPU / 16 GiB | 1 | 1 task | 2 h, one retry |

Limits change only through a load-tested spec revision.

## OPS-DB-001 — Bound cross-cloud database access

Cloud Run uses Direct VPC egress, Cloud NAT, reserved static IPv4 allowlisting,
TLS verification, Supavisor transaction pooling for requests, and a separate
session/direct role for migrations. Production records and tests:

```text
max_instances * pools_per_instance * pool_size
  + jobs + migrations + admin_reserve
  < Supabase connection limit
```

Runtime, migration, backup, and administrative roles remain distinct.

## OPS-OBJ-001 — Treat object identity and delivery as contracts

Production raw and derived artifacts use separate R2 buckets. Keys are content
or revision addressed. Irreplaceable forecast vintages receive retention/lock
policy and independently credentialed cross-provider disaster copies;
reproducible derivatives receive lifecycle expiry.

The Worker authorizes before normalized cache lookup. Immutable responses use
strong ETag, length, content type, byte ranges, and immutable cache control.
Mutable manifests use short revalidation. Tokens do not become cache identity.
Authorization failures are never cached; missing objects are cached briefly
with version-scoped purge controls.

## OPS-REL-001 — Promote immutable builds and fail visibly

Local, staging, and production use isolated databases, buckets, services,
credentials, notification installations, and origins. CI builds immutable
images and one web artifact, deploys to staging, runs migrations separately,
executes golden smoke tests, and promotes identical artifacts. Web environment
selection uses a schema-validated runtime configuration document.

Required recovery includes database backup and restore, off-provider logical
export, replayable immutable ingestion, object/catalogue recovery, credential
expiry, queue redelivery, migration rollback, routing outage, CDN outage, and
cost kill-switch rehearsals.

`v1_web` accepts a single live Montreal region. Regional failure falls back to
the last verified signed snapshot clearly marked stale. It must never render a
fresh-looking dynamic result.

## OPS-SEC-001 — Use workload-scoped credentials

GCP Secret Manager stores runtime secrets. GitHub Actions uses workload
identity federation. R2 tokens are environment/workload/bucket/duty scoped.
Long-lived secrets support overlapping rotation and emergency revocation. No
secret enters a client, fixture, manifest, log, or crash report.

Billing alerts are not caps. Maximum instances, queue limits, request limits,
daily ingestion limits, admission quotas, and an operator kill switch enforce
cost boundaries.
