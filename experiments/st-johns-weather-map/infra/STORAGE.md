# Local storage and publication policy

The `weather-artifacts` MinIO bucket is the only supported home for source
artifacts and derived weather payloads. The worker idempotently creates it and
sets a hard `25GiB` bucket quota before entering its loop. MinIO rejects writes
that exceed that quota. PostgreSQL stores metadata and small geometries only;
its volume is not part of the artifact quota.

The cap includes immutable original downloads, normalized Zarr data, COG map
frames, and Parquet observations. Ingestion must reserve enough room for a
complete staged revision before downloading it. Eviction order is expired
staging, status metadata older than seven days, then model runs older than the
latest and previous complete run. The high-cadence observation floor is three
hours. A worker must fail a job instead of deleting a currently visible
revision or exceeding the quota.

## Atomic visibility boundary

1. Write every object to a unique immutable revision key under `staging/`.
2. Record its byte size and SHA-256 in `artifact_revisions`.
3. Validate completeness, coverage, expected fields/times, and QC.
4. Mark the revision complete and QC-passed.
5. Call `weather_experiment.publish_revision(revision_id)` in one database
   transaction. This swaps the `current_artifacts` pointer and supersedes the
   previous visible revision atomically.

Readers resolve only `current_artifacts`; they never list `staging/`. A restart
may remove abandoned staging objects, but it must preserve the current pointer.
Object deletion happens only after no current pointer references the object.

This POC initializes the enforcement boundary but the fixture worker performs
no downloads, cleanup, or publication yet. Changing the quota with MinIO admin
tools is outside the supported stack and invalidates the 25 GiB guarantee.

