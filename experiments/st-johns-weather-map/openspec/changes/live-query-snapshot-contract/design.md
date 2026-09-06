# Design: one selection, one visible evidence revision set

## Selection and snapshot boundary

The API canonicalizes the existing workbench selection as Focus coordinates,
selected instant, requested product, enabled layer ids and the evidence window.
It rejects out-of-window instants and unknown products/layers before allocating
capacity. The snapshot closure contains the manifest revision for every
relevant stored logical stream, the registry and field-catalogue revisions, the
derivation-registry versions needed by selected fields, and the inventory facts
used to distinguish absent, aged-out, blocked and available-not-stored values.

An opaque snapshot id is the only wire identity. It is supplied to `/timeline`,
`/layers` and `/point`; continuation calls cannot alter its selection. The
database server records `selected_at` and the immutable `expires_at =
selected_at + 15 minutes`. No read, status check or refresh renews either time.

The response envelope adds `snapshot_id`, `selected_at`, `expires_at`,
`snapshot_state`, `operation_id`, `fencing_token`, `reservation_state` and
`reserved_bytes`. `snapshot_state` is `current`, `changed`, `expired` or
`unavailable`. `changed` means relevant current manifests or interpretation
versions differ from the snapshot; it does not mutate the answer. An expired
snapshot returns a restart-required error and is never described as current.

## Cache miss and refresh

Read routes inspect only the selected manifests and stores. They never call
adapter discovery or provider HTTP. A missing fragment remains an explicit
absence and includes a canonical refresh selection when every requested source
is registered and schedulable. Blocked, unavailable-not-stored, unknown-source
and out-of-window selections are not fetchable misses.

The existing `/refresh` job seam gains a selection-scoped request form. The
server canonicalizes `(baseline_snapshot_id, focus, window, product, layers,
field selectors)` and uses its digest as the idempotency key. Concurrent or
repeated requests return the same nonterminal durable job. A terminal job is
immutable; a later explicit request may create a new job against a new
baseline.

The job reports `queued`, `running`, `succeeded`, `partial`, `failed` or
`cancelled`, plus one outcome for every requested source and expected fragment.
`partial` never means published partial evidence: it means at least one source
published a complete atomic manifest and at least one other source did not.
Each source outcome names `cache_hit`, `published`, `nothing_available`,
`blocked`, `retrieval_failed`, `quota_exceeded` or
`upstream_budget_exhausted` and its manifest revision when published.

When the job reaches a terminal state, the current UI continues to show its
labelled snapshot. An explicit replacement action creates a fresh snapshot for
the same selection and swaps timeline, layers and point as one client state
update after all three responses validate the same new snapshot id. A failed
member read aborts the swap and leaves the earlier labelled snapshot visible.

## Fragment and publication seam

Every schedulable adapter registers an expected-shape function before it may
participate in selection refresh. It maps a canonical selection and provider
candidate to a finite set of keys:

```text
(source_id, provider_run_id, logical_artifact,
 valid_time_or_interval, field_group, member_group)
```

Each key declares normalized fields/units, geography, time/level/member scope,
maximum received bytes and maximum staged bytes. A missing declaration fails
the refresh before transfer. Discovery may retrieve bounded metadata but must
not retrieve the data payload.

The worker checks the selected manifest, reuses verified immutable fragments,
and fetches only absent keys. A fragment key can name only one digest; differing
bytes require a new provider-run or fragment identity. After every required
fragment passes decode, manifest and integrity validation, one database
transaction publishes a new immutable manifest that references the complete
fragment set. A crash or any failed fragment leaves the prior manifest visible.

Acquisition and snapshot pins use the durable allocator owned by issue #173:
`weather_experiment.resource_reservations`, keyed by `operation_id uuid` and
monotonic `fencing_token bigint`, with `task`, `ingestion` and `snapshot` kinds
and `active`, `revoking`, `releasable`, `released` states. The store seam is
`ArtifactStore.reserve_resources(...) -> contextmanager[ReservationIdentity]`;
snapshot admission uses `workload_kind="snapshot"`. Staged rows carry
`reservation_operation_id` and `reservation_fencing_token`, and publication
calls `publish_run(run_id, operation_id, fencing_token)`.
The allocator reserves before provider payload, fragment staging or snapshot
admission. Publication verifies the operation UUID and fencing token. Expiry
enters revocation; all global and host-local capacity remains charged until the
fenced cleanup path proves remote staging, local workspace and allocation rows
are reconciled. A stale owner cannot publish, release or overwrite its
successor.

## Live-proxy raster boundary

GeoMet and other declared live-proxy images are not stored artifacts and do not
join the immutable manifest closure. `/layers` uses the snapshot's stored
catalogue and imagery-availability facts, but `/raster` performs its separately
bounded proxy request under the accepted proxy cache/budget contract. The image
response states `live_proxy`, requested instant, actual served valid/reference
times, retrieval completion and upstream cache status. A different served time
is visible and cannot change `/timeline` or `/point` inside the snapshot.

## Time reconciliation

The authoritative evidence window for this change is the owner-selected and
implemented `now-24h .. now+14d` sliding window from
`storage-window-and-restart-cache`. Snapshot creation fixes its two boundary
instants for the snapshot lifetime; all three reads use those boundaries.

For the existing Map, a stored or advertised layer draws the latest published
frame at or before the selected instant only when its age is strictly less than
one hour. A future frame is never chosen. With no qualifying frame, nothing is
drawn and the reason is shown. Provider-rendered imagery still verifies the
actual served time; if it is future or one hour old, it is refused. This
supersedes the stale nearest-frame/per-layer-tolerance base wording for this
workbench contract. Display interpolation remains governed by its separate,
explicit opt-in contract and does not affect data reads.

## Failure behavior

- No capacity: refuse before transfer and keep the visible manifest/snapshot.
- Unreadable selected revision: return unavailable with revision identity; do
  not substitute current bytes.
- Snapshot expiry: require restart; do not renew or silently refresh.
- Worker failure: preserve the prior atomic manifest and report the exact job
  outcomes.
- Client replacement failure: keep the prior labelled snapshot as a unit.
- Provider throttling: bounded worker backoff only; reads remain upstream-free.
