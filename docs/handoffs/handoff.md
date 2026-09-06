# Autonomous execution handoff: deliver the working desktop evidence app

Updated September 6, 2026. This is the current non-normative execution record.
It supersedes earlier framework-first queue instructions while preserving their
history and the owner's earlier design selections.

## Destination and map ownership

[Source map #70](https://github.com/TusharSariya/Astraeus/issues/70) owns every
eligible free-access product from provider request through bounded worker,
immutable artifact, real API response, and consumption by the **existing web
application**. A source is complete only when every eligible product field has a
retrieved, missing, unsupported, or deferred disposition and retained evidence
proves the normal path. Catalogue entries, adapter fixtures, isolated captures,
or nonpublishable artifacts alone do not complete a source.

[Application map #38](https://github.com/TusharSariya/Astraeus/issues/38) remains
a separate, linked effort for the later desktop visual rebuild. Do not merge the
maps or create another master map. Source work may make routine changes needed
by the existing UI; new layout, styling, shared-snapshot UX, and desktop design
stay with #38.

The owner's current autonomous product outcome is one working desktop application
that uses every relevant eligible source. #70 owns source truth through the
existing client; #38 owns the subsequent desktop interaction and visual rebuild
on that working data path. Treat these as two linked delivery stages, not two
competing products. Reconcile broad, duplicate, obsolete and deferred children
against this outcome instead of mechanically closing every historical ticket.
A source or app ticket closes only when its evidence is complete or a traceable
replacement, exclusion, external block or owner-approved deferral is recorded.

The owner approved a corrective sequencing change after the September 6 delivery
audit: first make one complete HRDPS vertical slice work through the current
refresh/store/API/web path, then repeat complete source paths. Further fragment,
shared-snapshot, scoped-database-role, and general framework extensions are
paused until a measured source or UI failure demonstrates their need. This
supersedes the earlier framework-first sequence; it does not say those earlier
features were never selected and does not revert merged safety work.

## Measured baseline

Current main is `9a58dccc74d0b6f8b3ca7f6d50eba5286bff5345` after the reviewed HRDPS implementation, exact-memory admission fix and contract backfill.
The registry contains 123 records: 21 are `implemented-unverified`. Seventeen
records intersected ingestible configuration and a registered adapter, but only
`awc-metar-speci` and `noaa-swpc-kp` implemented both finite discovery and
payload resource bounds at that audit point. PR199 subsequently added the first
fully verified HRDPS vertical. Treat these as dated code-configuration counts,
not proof that every registered source is live in the application; each source
still needs the vertical definition of done below.

The current web client still reads `/point`, `/timeline`, `/layers`, `/catalog`,
`/sources/status`, and the existing image/feature routes. It makes no snapshot
request. Before the post-PR157 source queue, the recorded live audit found 35
layers, 118 catalogue records, 54 fields on the one-point response, sparse
timeline coverage, and null profiles. Recent bounded acquisition and safety PRs
improved evidence and failure handling, but many deliberately stopped before
publication or existing-UI integration.

Trace the baseline through [PR157](https://github.com/TusharSariya/Astraeus/pull/157),
the partial-cache refusal in [PR161](https://github.com/TusharSariya/Astraeus/pull/161),
the payload gates in [PR162](https://github.com/TusharSariya/Astraeus/pull/162)
and [PR166](https://github.com/TusharSariya/Astraeus/pull/166), the durable
reservation implementation in [PR173](https://github.com/TusharSariya/Astraeus/pull/173),
and the deferred shared-snapshot contract in
[PR195](https://github.com/TusharSariya/Astraeus/pull/195).

## Completed first slice, next source, and definition of done

[#196](https://github.com/TusharSariya/Astraeus/issues/196) is complete via
[PR199](https://github.com/TusharSariya/Astraeus/pull/199). The reviewed and
merged trees were identical. On preserved PostgreSQL and MinIO volumes, the
bounded HRDPS path published one immutable 48-field, 25-time artifact, served a
consistent 14:00Z revision through `/point`, `/timeline`, `/layers`, `/profile`
and the existing Brief and Workbench, then completed an explicit refresh with
zero provider payload because the retained run was complete. Independent proof
compared 1,200 GRIB field-time inputs and 26,462,400 cells with zero value,
unit, shape or hash mismatches. The source remains experimental and
non-operational; #187 still owns the additional 195 HRDPS vertical catalogue
IDs.

[#201](https://github.com/TusharSariya/Astraeus/issues/201) is the next bounded
vertical slice. It targets the already registered CYYT `awc-taf` source because
the existing client already presents CYYT TAF evidence, while this adapter still
fails closed before provider payload retrieval. It must extend only measured AWC
bounds that the TAF endpoint and body actually support, preserve every eligible
TAF field and change-group disposition, and prove normal refresh through
artifact, real API and the existing Brief/Workbench. Other aviation products
remain with #115; remaining source bounds remain with #159.

Every subsequent source follows the same definition of done:

1. Enumerate all eligible product fields and exact dispositions; do not hide a
   family behind a small selected sample.
2. Bound discovery, network bytes, decode memory/process limits, temporary and
   stored physical allocation, and cleanup before payload retrieval.
3. Preserve source/product/run/revision identity, native units, geometry, masks,
   QC and missingness, and provider publication/valid/retrieval times.
4. Publish only validated complete artifacts atomically and preserve the prior
   readable revision on failure.
5. Prove raw-to-artifact values and actual API values from a retained bounded
   capture, then prove the existing web client consumes those responses.
6. Exercise malformed, unavailable, oversized, quota, restart and stale-cache
   paths. Fixture-only and direct-adapter-only checks are insufficient.
7. Pass relevant API, registry/profile, SQL/storage, strict OpenSpec, specctl and
   CI gates, followed by independent evidence review.

Continue until #97 can verify all relevant eligible source dispositions and
integrations, then execute #38 against those real paths. During the queue, triage
tracker children into four explicit outcomes: required delivery, duplicate or
superseded with a replacement pointer, deferred with a stated product reason, or
blocked by a named owner/external fact. Research completion, a merged contract,
or an adapter that cannot publish does not by itself count as delivered.

## Deferred work and retained safeguards

- #158 missing-only repair and #159 source-bound coverage remain open and remain
  blockers of #97 for their honest residual obligations. They are not blockers
  of #196 unless its measurements demonstrate that full-fetch repair or a shared
  bound is required.
- Unmerged fragment manifests, shared 15-minute snapshots, selection-refresh
  jobs, and scoped database roles are parked. Preserved worktrees are evidence,
  not merged capability. Resume only with a reproduced partial-cache, concurrent
  revision, or privilege-boundary need and an explicitly bounded task.
- PR173's merged durable reservation/fencing safeguards remain in main. Do not
  delete or weaken them. Unsupported adapters continue to fail closed.
- Draft contract PRs #167, #168, #172, #175, and #179 are concrete owner
  decisions, not accepted blanket authority. Present their recommendations as a
  batch when they directly unblock source publication; do not acquire additional
  variants merely to create more contract questions.

## Fixed boundaries

Keep `operational: false`, registry ceilings, the 64 GiB hot quota, two complete
forecast runs, rolling 24-hour observation history, and 14-day forecast horizon.
No cold tier, paid service, rented compute, provider outreach, implicit rights
acceptance, science promotion, or public deployment is authorized. No raw
provider payload belongs in Git. Retain bounded raw bytes, headers, exact HTTP
completion times and artifacts outside Git until independent review; commit only
compact receipts and tiny representative fixtures.

Tracking truth is GitHub. Keep no more than three active implementation tickets.
All detailed work is delegated from the root orchestrator; completed runtime
threads may be reused. A lead does not independently approve its own evidence.
Use an independent reviewer before merge, preserve user worktrees, integrate
current main before final gates, and make conventional commits/PRs with exact
`Spec-Refs` and `Verification`.

## Current worktrees and claims

- Root user checkout contains unrelated work and must not be mutated.
- #196 HRDPS is merged and closed; its bounded evidence remains outside Git for audit.
- #201 CYYT TAF implementation is assigned to the payload/resource lead in a fresh
  isolated current-main worktree, with independent review by the GeoMet lead.
- `/private/tmp/astraeus-live-query-snapshot-api`, branch
  `execution/live-query-snapshot-api`, preserves two local API commits and is
  paused; do not merge it under the corrective sequence.
- `/private/tmp/astraeus-scoped-db-roles`, branch
  `execution/scoped-weather-db-roles`, preserves uncommitted scoped-role work and
  is paused.
- The #158 fragment worktree remains preserved and paused.
- The current product-outcome handoff update is isolated at
  `/private/tmp/astraeus-autonomous-app-goal`.

Research and handoff prose are non-normative. Only the owner changes accepted,
verified, or superseded specification status.

Spec-Impact: none; this records authorized execution order and completion proof.
