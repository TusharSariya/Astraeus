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

- [x] 1.1 Raise the bucket quota to 64 GiB in the worker bootstrap and the
  compose configuration, keep the unit-suffix parse, and reset a quota that
  differs from the configured value at start.
  Verify: `cd api && uv run pytest tests/test_store_quota.py -k "quota and 64"`
  Verify result: 7 passed. Cap is `STORAGE_CAP`/`STORAGE_CAP_BYTES` in `api/weather_api/config.py`; compose, `.env.example` and `infra/minio/bootstrap.sh` default to `64GiB`; the unit-suffix parse is unchanged and `_parse_cap(None)` now returns 64 GiB.
- [x] 1.2 Rewrite `infra/STORAGE.md`: 64 GiB, no cold tier, retention as the
  sliding valid-time window plus the two-run forecast rule, the 24-hour
  observation floor replacing the three-hour floor, and the restart-cache
  purpose. Cite ticket 20 and both size-probe files by path.
  Verify: `grep -n "64GiB\|64 GiB" infra/STORAGE.md && ! grep -n "25GiB\|three hours" infra/STORAGE.md`
  Verify result: 4 matches for 64 GiB, 0 for `25GiB` or `three hours` (grep exit 1 on the negation). Cites ticket 20 and both size-probe files by path.
- [x] 1.3 Refuse a projection that would exceed the cap before any download,
  and never satisfy one by planning to purge an in-window frame.
  Verify: `cd api && uv run pytest tests/test_store_quota.py -k "exceeded or no_evict"`
  Verify result: 3 passed. `assert_room_for` credits only `weather_experiment.reclaimable_bytes` - bytes already outside the window - so a projection is never satisfied by purging an in-window frame, and the refusal path sends no DELETE.

## 2. The single window definition (API owner)

- [x] 2.1 Define the sliding window once in `api/weather_api/config.py` as
  `now-24h .. now+14d` and have `/timeline`, request validation, the
  `FetchWindow` and the QC bounds all read it.
  Verify: `cd api && uv run pytest tests/test_evidence_window.py -k "sliding or single_source"`
  Verify result: 5 passed. `FetchWindow` reads it through `ingest/window.py`, the QC bounds through `ingest/validate.py`, request validation and `/timeline` directly.
- [x] 2.2 `/timeline` returns 361 hourly items with correct
  `America/St_Johns` local times across a DST transition; boundary instants
  are accepted, outside instants are 422.
  Verify: `cd api && uv run pytest tests/test_timeline.py -k "361 or boundary or dst"`
  Verify result: 5 passed. 361 items over 15 days; the DST case opens the window on 2026-10-25 so it straddles the 2026-11-01 transition and carries both NDT and NST.
- [x] 2.3 Live readiness is judged against the sliding window and reports
  aged out where a last valid time exists.
  Verify: `cd api && uv run pytest tests/test_ready.py -k "window or aged_out"`
  Verify result: 6 passed. A frame 20 h old or 10 d ahead now makes the boundary true; a store holding only aged-out frames reports `ready: false` with `aged_out_sources`, and an unreadable record names the failure instead.

## 3. Retention, purge and last valid time (storage owner)

- [x] 3.1 Implement the purge: frames outside the window, the latest plus
  previous complete run per forecast source with a third displacing the
  oldest at publication, and 24 hours of observations and nowcasts. Assert no
  vintage archive accumulates with free space available.
  Verify: `cd api && uv run pytest tests/test_retention.py -k "window or two_runs or no_archive"`
  Verify result: 3 passed here; the rules themselves are proved against a real PostgreSQL by `make test-sql` (21 retention invariants, including the third run displacing the oldest at publication and no archive accumulating with free space available).
- [x] 3.2 Record and keep the last valid time per logical stream after its
  frames are purged; report `unavailable` when it cannot be read.
  Verify: `cd api && uv run pytest tests/test_retention.py -k "last_valid_time"`
  Verify result: 3 passed. `weather_experiment.stream_last_valid_time` is written at publication and again before a purge, never lowered, and survives its frames; an unreadable record raises `StoreUnavailable` and the endpoints report `unavailable`.
- [x] 3.3 Purge safety against an open read: rows before objects, no removal
  behind a current pointer, `StoreUnavailable` or `ArtifactIntegrityError`
  rather than truncated bytes, purged revisions dropped from the dataset
  cache, a missing object does not abort the sweep.
  Verify: `cd api && uv run pytest tests/test_retention.py -k "purge_during_read or cache_drop or missing_object"`
  Verify result: 4 passed. The pointer row is deleted in the same statement as the revision, the last valid time is recorded before anything is removed, a purged revision is dropped from the dataset cache, and a missing object does not abort the sweep.
- [x] 3.4 SQL migration for the retention window, the stream last-valid-time
  record and the purge function; publication and purge stay one transaction.
  Verify: `make test-sql`
  Verify result: `make test-sql` green: 17 publication invariants and 21 retention invariants, all PASS, `all storage invariants hold`. `publish_run` purges before it returns, in its own transaction.

## 4. Idempotent ingestion and restart (ingest owner)

- [x] 4.1 Key frames by `(source_id, provider_run_id, valid_time)` in
  nanoseconds; ask the store what is present before fetching; refuse a
  byte-different fetch of a published key as `run_identity_conflict`; fail
  the source when the store cannot be asked.
  Verify: `cd api && uv run pytest tests/test_ingest_idempotency.py`
  Verify result: 10 passed. `ingest/scheduler.py:plan_fetch` asks
  `store.present_keys` and fetches only the missing nanosecond keys;
  `ingest/store.py:assert_run_identity` raises `RunIdentityConflict` naming
  both digests before the run row is touched; a store that raises propagates
  and `worker/runtime.py:run_source` reports the source `failed` without
  fetching.
- [x] 4.2 Restart reconciliation: sweep abandoned staging, purge outside the
  window, then fetch only what is missing. Cover restart mid-publication, a
  full window, a long outage and an unreadable store.
  Verify: `cd api && uv run pytest tests/test_worker_restart.py -k "mid_publication or full_window or long_outage or unreadable"`
  Verify result: 4 passed, 7 deselected; the whole file is 11 passed.
  `ingest/scheduler.py:reconcile_on_start` runs the two steps in order and
  returns unhealthy without purging or fetching when either raises;
  `worker/runtime.py:run` exits 1 rather than scheduling on an unreadable
  store.
- [x] 4.3 Recompute derived artifacts from retained inputs instead of
  re-fetching; a derived artifact with an aged-out or null input is absent
  and reports its worst input's state.
  Verify: `cd api && uv run pytest tests/test_derived_recompute.py`
  Verify result: 12 passed. `ingest/scheduler.py:derived_plan` recomputes when
  every input is retained and is otherwise absent naming the worst input; the
  existing `cloud_motion_cycle` recompute path is asserted to read
  `current_artifacts` and nothing else. `null` outranks `aged_out`; the
  reasoning is in design.md under Deviations.
- [x] 4.4 Move the out-of-window QC bounds to the shared window definition
  and keep the five-flag cap with the `+N_more` remainder; a run with no
  in-window step is refused.
  Verify: `cd api && uv run pytest tests/test_validate_run.py -k "out_of_window"`
  Verify result: 11 passed, 1 deselected; the whole file is 12 passed. The
  gate is `ingest/validate.py:out_of_window_verdict`, reading
  `weather_api.config` through `ingest/window.py`;
  `ingest/manifest.py:validate_run` calls it. The refusal flag is
  `no_step_in_window`, deliberately outside the capped `out_of_window:`
  family - recorded in design.md.
- [x] 4.5 Outcomes: an idempotent no-op is `succeeded` with zero artifacts
  and a stated reason; the quota failure names the 64 GiB cap; a run that
  never completes is `failed` every cycle without accumulating staged bytes.
  Verify: `cd api && uv run pytest tests/test_worker_outcomes.py -k "noop or quota or never_completes"`
  Verify result: 7 passed, 2 deselected; the whole file is 9 passed.
  `LOCAL_STORAGE_CAP_BYTES` is 64 GiB and `QuotaExceeded` formats the cap and
  the projected size from the configured value; three failed cycles each
  discard the previous attempt's staged rows before staging again, and
  `publish_run` is never called for an incomplete run.

## 5. Absence state end to end (API and web owners)

- [x] 5.1 Add `aged_out` with `last_valid_time` to the absence reasons in
  `api/weather_api/models.py` and return it from `/point`, `/profile`,
  `/timeline` and `/layers`, distinct from `null`, `blocked`,
  `retrieval failed` and `available-not-stored`.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k "aged_out"`
  Verify result: 9 passed. `aged_out` rides `quality.flags` with `provenance.last_valid_time` beside it on `/point`, `/profile`, `/timeline` and `/layers`; `Provenance` refuses the flag without the instant. The five states are named once in `weather_api.store.ABSENCE_STATES`.
- [x] 5.2 Web badge and legend naming all five absence states, with the last
  valid time shown on the aged-out badge.
  Verify: `cd web && npm test -- --run aged-out`
  Verify result: passed, 12 tests in `web/src/aged-out.test.tsx`. Full suite
  `npm test -- --run` 330 passed in 15 files (unit and gl projects), and
  `npm run build` succeeded. The badge reads `Aged out at <last valid time>`
  in `America/St_Johns` local time from the zone database, with the ISO
  instant in the text alternative; the legend names all five states. An
  `aged_out` flag arriving with no readable last valid time renders as
  `unavailable`, per the spec's "SHALL NOT be reported without a recorded
  last valid time". Note for the API owner: the wire contract fixed only how
  `aged_out` arrives (`quality.flags`), so the client reads `blocked` and
  `retrieval_failed` from either `quality.flags` or `quality.status`; whichever
  the API settles on will render.

Ownership note added during implementation: sections 1 and 3 turned out to
need `ingest/store.py`, which the header assigns to the ingest owner. The two
were run in sequence, not concurrently: after section 4 landed on
`execution/storage-window`, the storage owner merged it and reconciled the two
purges into one - `ArtifactStore.purge_outside_window` now delegates to
`weather_experiment.purge_outside_window`. Recorded in design.md. Nothing else
under `ingest/` was touched by the storage owner.

## 6. Gate

- [ ] 6.1 `make test`, `openspec validate storage-window-and-restart-cache
  --strict`, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
