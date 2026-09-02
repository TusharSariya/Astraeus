Owned by this change: `openspec/changes/storage-window-and-restart-cache/**`,
`infra/STORAGE.md`, the bucket-quota bootstrap in `infra/` and the worker
start path, `api/weather_api/config.py` (the single window definition),
`api/weather_api/store.py` (window-bounded coverage, purge sweep, last valid
time), `api/weather_api/models.py` (the `aged_out` absence reason only),
`ingest/store.py` and `ingest/scheduler.py` (idempotency key, restart
reconciliation, recompute path), `ingest/validate.py` (out-of-window bounds),
`web/src/` (the aged-out badge and legend entry), and the tests named below.
Not touched: adapter retrieval logic, `registry/source_data.py`, registry
status, `openspec/config.yaml`.

Owners: infra and storage (one owner); ingest and worker (one owner); API
(one owner); web (one owner).

`models.py` is also owned by `evidence-classes-and-derived-here` (the
`evidence_class` field) and by `field-catalogue-and-families` (`family`,
`comparability`, `phase`). This change touches only the absence reason, so
apply it after those two or coordinate the edit; do not run the three owners
on that file concurrently. `artifact-ingestion` deltas here and in
`field-catalogue-and-families` modify different requirements and do not
conflict.

Decision of record: wayfinder ticket 20,
`https://github.com/TusharSariya/Astraeus/issues/20`. Sizing evidence:
`docs/research/wayfinder/size-probe-full-fields.md` (branch
`research/size-probe-full-fields`) and
`docs/research/wayfinder/size-probe.md` (branch `research/size-probe`), both
non-normative.

## 1. Quota and storage policy (infra owner)

- [ ] 1.1 Raise the bucket quota to 64 GiB in the worker bootstrap and the
  compose configuration, keep the unit-suffix parse, and reset a quota that
  differs from the configured value at start.
  Verify: `cd api && uv run pytest tests/test_store_quota.py -k "quota and 64"`
- [ ] 1.2 Rewrite `infra/STORAGE.md`: 64 GiB, no cold tier, retention as the
  sliding valid-time window plus the two-run forecast rule, the 24-hour
  observation floor replacing the three-hour floor, and the restart-cache
  purpose. Cite ticket 20 and both size-probe files by path.
  Verify: `grep -n "64GiB\|64 GiB" infra/STORAGE.md && ! grep -n "25GiB\|three hours" infra/STORAGE.md`
- [ ] 1.3 Refuse a projection that would exceed the cap before any download,
  and never satisfy one by planning to purge an in-window frame.
  Verify: `cd api && uv run pytest tests/test_store_quota.py -k "exceeded or no_evict"`

## 2. The single window definition (API owner)

- [ ] 2.1 Define the sliding window once in `api/weather_api/config.py` as
  `now-24h .. now+14d` and have `/timeline`, request validation, the
  `FetchWindow` and the QC bounds all read it.
  Verify: `cd api && uv run pytest tests/test_evidence_window.py -k "sliding or single_source"`
- [ ] 2.2 `/timeline` returns 361 hourly items with correct
  `America/St_Johns` local times across a DST transition; boundary instants
  are accepted, outside instants are 422.
  Verify: `cd api && uv run pytest tests/test_timeline.py -k "361 or boundary or dst"`
- [ ] 2.3 Live readiness is judged against the sliding window and reports
  aged out where a last valid time exists.
  Verify: `cd api && uv run pytest tests/test_ready.py -k "window or aged_out"`

## 3. Retention, purge and last valid time (storage owner)

- [ ] 3.1 Implement the purge: frames outside the window, the latest plus
  previous complete run per forecast source with a third displacing the
  oldest at publication, and 24 hours of observations and nowcasts. Assert no
  vintage archive accumulates with free space available.
  Verify: `cd api && uv run pytest tests/test_retention.py -k "window or two_runs or no_archive"`
- [ ] 3.2 Record and keep the last valid time per logical stream after its
  frames are purged; report `unavailable` when it cannot be read.
  Verify: `cd api && uv run pytest tests/test_retention.py -k "last_valid_time"`
- [ ] 3.3 Purge safety against an open read: rows before objects, no removal
  behind a current pointer, `StoreUnavailable` or `ArtifactIntegrityError`
  rather than truncated bytes, purged revisions dropped from the dataset
  cache, a missing object does not abort the sweep.
  Verify: `cd api && uv run pytest tests/test_retention.py -k "purge_during_read or cache_drop or missing_object"`
- [ ] 3.4 SQL migration for the retention window, the stream last-valid-time
  record and the purge function; publication and purge stay one transaction.
  Verify: `make test-sql`

## 4. Idempotent ingestion and restart (ingest owner)

- [ ] 4.1 Key frames by `(source_id, provider_run_id, valid_time)` in
  nanoseconds; ask the store what is present before fetching; refuse a
  byte-different fetch of a published key as `run_identity_conflict`; fail
  the source when the store cannot be asked.
  Verify: `cd api && uv run pytest tests/test_ingest_idempotency.py`
- [ ] 4.2 Restart reconciliation: sweep abandoned staging, purge outside the
  window, then fetch only what is missing. Cover restart mid-publication, a
  full window, a long outage and an unreadable store.
  Verify: `cd api && uv run pytest tests/test_worker_restart.py -k "mid_publication or full_window or long_outage or unreadable"`
- [ ] 4.3 Recompute derived artifacts from retained inputs instead of
  re-fetching; a derived artifact with an aged-out or null input is absent
  and reports its worst input's state.
  Verify: `cd api && uv run pytest tests/test_derived_recompute.py`
- [ ] 4.4 Move the out-of-window QC bounds to the shared window definition
  and keep the five-flag cap with the `+N_more` remainder; a run with no
  in-window step is refused.
  Verify: `cd api && uv run pytest tests/test_validate_run.py -k "out_of_window"`
- [ ] 4.5 Outcomes: an idempotent no-op is `succeeded` with zero artifacts
  and a stated reason; the quota failure names the 64 GiB cap; a run that
  never completes is `failed` every cycle without accumulating staged bytes.
  Verify: `cd api && uv run pytest tests/test_worker_outcomes.py -k "noop or quota or never_completes"`

## 5. Absence state end to end (API and web owners)

- [ ] 5.1 Add `aged_out` with `last_valid_time` to the absence reasons in
  `api/weather_api/models.py` and return it from `/point`, `/profile`,
  `/timeline` and `/layers`, distinct from `null`, `blocked`,
  `retrieval failed` and `available-not-stored`.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k "aged_out"`
- [ ] 5.2 Web badge and legend naming all five absence states, with the last
  valid time shown on the aged-out badge.
  Verify: `cd web && npm test -- --run aged-out`

## 6. Gate

- [ ] 6.1 `make test`, `openspec validate storage-window-and-restart-cache
  --strict`, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
