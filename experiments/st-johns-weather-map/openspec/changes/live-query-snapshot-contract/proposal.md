# Live-query snapshot contract for the existing workbench

## Why

The existing weather workbench already queries `/timeline`, `/layers` and
`/point`, but those independent reads can observe different publication
revisions. A cache miss is currently either returned as absence or repaired by
a later whole-source refresh. Aggregate artifacts cannot safely add one missing
field or valid time without replacing bytes that were already published.

The owner selected this contract on 2026-09-06: finish the existing workbench
before the five-view redesign; use cache plus fetch-on-miss; store immutable
fragments behind an atomically replaced manifest; keep API reads upstream-free;
show asynchronous acquisition progress and adopt it only on explicit refresh;
bind Map, timeline and point reads to one revision set; and use fixed,
nonrenewing 15-minute snapshots inside the 64 GiB hot-store quota. Snapshot and
acquisition capacity use the durable reservations selected in issue #173;
expiry keeps capacity charged until fenced cleanup proves it released.

This is a requirement change for the isolated experiment. It records explicit
owner selections as a proposed OpenSpec change. It does not claim acceptance,
implementation, source admission, operational status, or completion of the
later five-view application.

## What changes

- The current client opens one selection snapshot and supplies its opaque id to
  `/timeline`, `/layers` and `/point`. Those reads resolve the same relevant
  manifest, registry, derivation and absence-inventory revisions.
- A snapshot expires exactly 15 minutes after database-server selection time.
  Reads and change checks do not renew it. Expiry requires a new snapshot.
- Read routes never contact a provider. A missing selection is returned with
  its exact absence plus a refresh offer. Only an explicit selection-scoped
  refresh queues worker acquisition.
- Each adapter declares its expected fragment shape. The worker writes new
  immutable fragments, validates the complete selected shape, and atomically
  publishes a manifest referencing the full set. Readers assemble only through
  the selected manifest.
- Refresh jobs are durable and idempotent by canonical selection plus baseline
  snapshot. They report per-source and per-fragment outcomes. Completion does
  not mutate the displayed snapshot; the reader explicitly replaces it.
- Live-proxy rasters remain outside artifact snapshot guarantees. Their
  advertised time and returned served-time provenance stay explicit.
- The evidence window is `now-24h .. now+14d`. The existing workbench's selected
  Map behavior is latest published frame at or before the selected instant,
  less than one hour old; future frames are never substituted.

## Capabilities

### New capability

- `live-query-snapshots`: selection snapshots, selection-scoped acquisition,
  immutable fragment manifests and atomic client replacement.

### Modified capabilities

- `artifact-ingestion`: expected fragment shapes and atomic manifest publish.
- `artifact-storage-integrity`: durable acquisition and snapshot reservations.
- `evidence-window-timeline`: the 24-hour-back, 14-day-ahead window is the
  snapshot and acquisition boundary.
- `web-evidence-interface`: snapshot-bound reads and the selected at-or-before
  Map rule for the existing workbench.

## Scope

This change does not add Series, verdict, site, camera or five-view routes; an
explicit run-browsing UI; band math; new scoring; scientific or operational
source promotion; camera delivery; or server persistence for client layout.
Every response still preserves actual source and run identity, and snapshot
pins preserve the prior readability required by the selected run policy.
Explicitly authorized experimental live integration may proceed after each
source's field, access and publication contracts are satisfied.
`operational: false` remains unchanged.

Spec-Impact: requirement change; proposed experiment contract.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
