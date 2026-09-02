# Local storage and publication policy

The `weather-artifacts` MinIO bucket is the only supported home for source
artifacts and derived weather payloads. The worker idempotently creates it and
sets a hard `64GiB` bucket quota before entering its loop. MinIO rejects writes
that exceed that quota. PostgreSQL stores metadata and small geometries only;
its volume is not part of the artifact quota.

The cap includes immutable original downloads, normalized Zarr data, COG map
frames, and Parquet observations. Ingestion must reserve enough room for a
complete staged revision before downloading it. A worker must fail a job
instead of deleting a currently visible revision or exceeding the quota.

Owner decision of record: wayfinder ticket 20,
<https://github.com/TusharSariya/Astraeus/issues/20>.

## Why 64 GiB

The store was sized for a candidate field list. The field catalogue decision
(wayfinder ticket 18) widened the scope to every field every admitted source
publishes, and the re-run size probe measured what that costs.

- `docs/research/wayfinder/size-probe-full-fields.md` (branch
  `research/size-probe-full-fields`) measures three scenarios resident: core
  only at 7.5 GB, core plus planning reductions at 11.1 GB, core plus planning
  with subsetted ensemble members at 18.2 GB. With the two-run staging overlap
  this document mandates and about 20 percent container and manifest overhead
  those become roughly 18 GB, 27 GB and 44 GB.
- `docs/research/wayfinder/size-probe.md` (branch `research/size-probe`)
  measured the same evidence box under the candidate field list at 284 to
  505 MB. It is superseded on scope, not on method.

64 GiB is the smallest round quota that holds the widest scenario with real
headroom, so a sizing decision does not have to be revisited every time the
catalogue grows a family. It is **not** chosen to leave room for history:
history is what the sliding window deliberately does not keep. The dominant
consumer is HRDPS at 377 coverages, 5.53 GB, of which 3.02 GB is its 206
pressure-level coverages; if the quota ever binds, that is the first place to
look.

Both research documents are non-normative.

## There is no cold tier

Nothing spills anywhere. There is no cold, archive or overflow tier, and none
is created at runtime. Reaching the quota fails closed: the run fails naming
the cap and the projected size, the previously visible revision keeps
answering, and no visible revision is evicted to make room.

A tier with no reader would be a second failure mode with no benefit -
verification scoring is out of scope (wayfinder ticket 5) and forecast vintages
are explicitly not retained - and it would give the store somewhere to spill to
at the quota, which is exactly the fail-closed behaviour this experiment does
not want weakened.

A field whose source could not be staged because the quota was reached is
reported as `retrieval failed` naming `quota_exceeded`, never as `null` and
never as `aged out`.

## Retention is the sliding window, used as a restart cache

The store retains exactly the frames whose valid time lies inside the current
evidence window, `now-24h` through `now+14d`, and purges a frame once its valid
time falls outside it. The window is defined once, in
`api/weather_api/config.py` (`WINDOW_BACK`, `WINDOW_FORWARD`,
`sliding_window`), and the same numbers are stated in
`infra/postgres/init/003_retention_window.sql` because SQL cannot import
Python; `infra/postgres/tests/retention_invariants.sql` asserts the two agree.

- **Forecast sources**: the latest complete run and the previous complete run,
  and no more. A third complete run displaces the oldest in the same
  transaction that publishes the newest.
- **Observation and nowcast sources**: the full 24 hours of history inside the
  window. This replaces the earlier three-hour high-cadence floor, which no
  longer applies.
- **No vintage archive.** Retaining every run whose valid times still fall
  inside a 14-day window would be dozens of runs per source, and the store
  would become an archive by accident rather than by decision. Runs beyond the
  two-run ceiling are purged however much room the quota leaves: retention is a
  decision, not a consequence of free space.

The retained set is the restart cache, and that is its only purpose: it is what
a restarting worker must not fetch again. Ingestion is idempotent by
`(source_id, provider_run_id, valid_time)`, so a stop and restart re-fetches
only what the window is missing.

A projection made before a download may credit only bytes already outside the
window (`weather_experiment.reclaimable_bytes`). It is never satisfied by
planning to purge a frame that is still inside the window: trading evidence a
request could name for room to fetch more is an eviction of visible data under
another name.

## The last valid time, and the aged-out absence

For every logical stream the store records the latest valid time it has ever
held, in `weather_experiment.stream_last_valid_time`, and keeps that record
after the frames themselves are purged. It is recorded at publication and again
before a purge, and it is never lowered.

An absence caused by purging is reported as `aged_out` carrying that time. A
stream with no such record reports `null`, never `aged_out`: a deployment that
never held a frame must not claim it did. A store that cannot be read reports
`unavailable` rather than guessing which absence applies.

## Atomic visibility boundary

1. Write every object to a unique immutable revision key under `staging/`.
2. Record its byte size and SHA-256 in `artifact_revisions`.
3. Validate completeness, coverage, expected fields/times, and QC.
4. Mark the revision complete and QC-passed.
5. Call `weather_experiment.publish_run(run_id)` in one database transaction.
   This swaps the `current_artifacts` pointers, supersedes the previous visible
   revisions, records each stream's last valid time, and purges what has left
   the retention window - all atomically.

Readers resolve only `current_artifacts`; they never list `staging/`. A restart
may remove abandoned staging objects, but it must preserve the current pointer.

## Purge safety against an open read

The purge deletes metadata rows before objects and never removes an object a
current pointer still references: the pointer row is deleted in the same
transaction, and the freed object keys are queued in
`weather_experiment.purged_objects` for a separate, resumable sweep. The
metadata row is the record of truth, so an object already gone does not abort
the sweep.

A read in flight when a purge runs either completes against the bytes it has
already verified, or fails closed with `StoreUnavailable` or
`ArtifactIntegrityError`. It never returns partially read bytes, and a cached
dataset whose revision the purge removed is dropped from the cache and never
answers again.

## Notes

Changing the quota with MinIO admin tools is outside the supported stack and
invalidates the 64 GiB guarantee. The worker resets a bucket quota that differs
from the configured value at start, and records that it did.
