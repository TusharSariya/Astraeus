---
id: RFC-001
title: Evidence Revisions and Provenance
type: rfc
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-000
supersedes: []
---

# RFC-001 — Evidence revisions and provenance

## EVD-REV-001 — Freeze every recommendation revision

An `EvaluationRevision` MUST freeze:

- request and normalized origin;
- observation subject, occurrence where applicable, module ID/version, and
  observation profile;
- candidate/site catalogue revision;
- valid-time interval and frame cadence;
- source objects, model runs/members, observations, and retrieval times;
- ephemeris, Earth-orientation, and leap-second inputs;
- normalization, geometry, scoring, safety, and routing versions;
- layer, scene, mask, and provenance manifests.

A `FrameKey` selects one valid time within a revision. Timeline scrubbing MUST
change only `FrameKey`. Comparing providers or runs uses explicit comparison
slots containing separate revisions; no implicit source substitution is
allowed.

## EVD-PROV-001 — Preserve issued-source identity

Every evidence item MUST record provider, product/version, source URI, model
initialization or observation time, lead and valid time, ingest time, checksum,
native units/grid/projection, normalization version, QC, and licence. Issued
runs and mutable upstream responses MUST NOT be overwritten.

## EVD-MASK-001 — Use explicit mask semantics

Masks are one of:

- `coverage`;
- `nodata`;
- `quality`;
- `geographic`;
- `access`;
- `obstruction`;
- `selection`.

`coverage`, `nodata`, `quality`, `geographic`, `access`, and `obstruction`
affect server-side analysis. `selection` is visual only.
Missing, failed-QC, or outside-coverage cells MUST NOT render or score as zero,
clear sky, open horizon, clean air, or lawful access.

## EVD-QUAL-001 — Keep uncertainty concepts separate

Clients and APIs MUST expose evidence quality, scenario spread, and source
disagreement separately. Ensemble-member fractions describe the supplied
ensemble only. None may be labelled success probability without empirical
calibration.

## EVD-API-001 — Use asynchronous capability-protected plans

For dynamic profiles, `POST /v1/plans` accepts a closed module-discriminated
request union and returns `202 PlanAccepted` with an opaque plan ID and bearer
capability. Status, result, SSE progress, and deletion require that capability.
Plans expire after 24 hours and precise origins MUST NOT enter application logs
or analytics.

Required behavior:

- `Idempotency-Key` produces one logical plan for the same capability scope.
- SSE events carry durable monotonically ordered event IDs and support replay.
- Errors use RFC 9457 `ProblemDetails` with a stable Astraeus error code.
- Expired or deleted plans return an explicit terminal response.
- Asset manifests contain immutable IDs and hashes, not expiring URLs.
- `/v1/assets/resolve` authorizes and returns short-lived transport locations.

Exact wire shapes live in `contracts/openapi.yaml`.

Only `active` entries in `contracts/observation-modules.yaml` may execute in a
production profile. A proposed schema variant may be validated during contract
development but MUST NOT be treated as callable production behavior.

## EVD-SNAP-001 — Sign controlled snapshots

`PlanSnapshot` uses canonical JSON (RFC 8785), SHA-256, and a detached Ed25519
signature. The envelope includes schema version, snapshot ID, issue/stale/
expiry times, key ID, digest, and signature. Clients reject unknown, revoked,
expired, or mismatched snapshots and retain the previous verified revision
during a failed update. CDN possession of a file is not approval evidence.

## EVD-LAYER-001 — Keep analytic assets renderer-neutral

`LayerManifest` and `SceneLayerManifest` MUST declare evidence class, data kind,
immutable asset identity, provider/licence, CRS and vertical datum, bounds and
native resolution, units and nodata, run/valid/retrieval time, resampling,
masks, renderer capabilities, evaluation revision, and provenance. An asset is
exactly one of analytic, explanatory, or decorative.

Commercial or photorealistic content MUST NOT become analytic input unless its
licence and source characteristics explicitly permit that declared use.

## Security and privacy

Capabilities are high-entropy, revocable, transmitted in authorization headers,
and never included in analytics. Clients receive no database service role,
provider secret, object-store write key, cloud service-account key, or routing
administrative credential.
