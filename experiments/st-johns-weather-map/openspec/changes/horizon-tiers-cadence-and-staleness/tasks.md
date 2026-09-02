Owned by this change:
`openspec/changes/horizon-tiers-cadence-and-staleness/**`,
`registry/source_data.py` (reach, run cadence and measured latency fields only),
`registry/audit.py` (reach and cadence checks),
`worker/scheduler.py` and `worker/heartbeat.py` (schedule computation, bounded
poll, ECCC dated fallback, latency re-measurement),
`api/weather_api/timeline.py` and `api/weather_api/layers.py` (tier ranges,
coverage from reach, `run_time` and `run_stale`),
`web/src/components/Timeline*` and `web/src/components/Coverage*` (boundary,
per-instant coverage, run labels), and the tests named below.

Not touched: window bounds and retention, which belong to the parallel
`storage-window-and-restart-cache` change and are edited by its owner only;
`openspec/config.yaml`; registry status values; adapter retrieval logic;
`registry/fields.py` (owned by `field-catalogue-and-families`).

Owners: registry and worker (one owner); API (one owner); web (one owner).
Task 1 must land before tasks 2 and 3, since both read the new registry fields.
Task 3.1 edits `layers.py`, which `field-catalogue-and-families` does not touch,
so the two changes may run concurrently.

## 1. Registry: reach, cadence and measured latency (registry and worker owner)

- [x] 1.1 Add `reach` (per run cycle where cycles differ), `run_cadence_seconds`
  and a `publication_latency` block (estimate, observation count, last observed
  instant, `measured` flag) to every forecast record in
  `registry/source_data.py`, seeding ICON, GFS, GEFS and the four ECMWF records
  from `docs/research/wayfinder/planning-horizon-matrix.md` and leaving GDPS,
  GEPS, REPS and WeatherNext 2 with a null estimate and `measured: false`.
  Verify: `python3 registry/audit.py`
  Verify result: `python3 registry/audit.py` -> exit 0, "registry valid: 64
  sources"; "horizon: 24 records declare a reach (12 run cadence, 11 native
  cadence) across 17 registered adapters; 7 latencies seeded, 0 measured here".
  The 24 are the 17 records with a registered adapter plus GEFS, IFS ENS, both
  AIFS records, GEPS, REPS and WeatherNext 2. Observation and nowcast records
  carry `native_cadence_seconds` instead of a run cadence and no latency block,
  since they are not scheduled against a run.
- [x] 1.2 Refuse a schedulable record with no declared reach or no resolvable
  run cadence, and refuse a defaulted latency.
  Verify: `python3 -m unittest discover -s registry/tests -v -k reach`
  Verify result: `python3 -m unittest discover -s registry/tests -v -k reach`
  -> 34 tests, OK (88 OK across the whole registry suite). Also
  `cd api && uv run pytest tests/test_ingest_registry_reach.py
  tests/test_ingest_manifest.py -q` -> 28 passed, and the full
  `cd api && uv run pytest` -> 856 passed, 36 skipped.

## 2. Worker: scheduling, polling and latency re-measurement (registry and worker owner)

- [x] 2.1 Schedule forecast sources at run time plus measured latency, and at
  run time exactly where no latency is measured; schedule observation and
  nowcast sources at native cadence (radar 6 min, lightning 10, GOES 10, METAR
  and SWOB hourly, SWPC 1 min).
  Verify: `cd api && uv run pytest tests/test_worker_scheduling.py -k "latency or native_cadence"`
  Verify result: `cd api && uv run pytest tests/test_worker_scheduling.py -k
  "latency or native_cadence"` -> 31 passed, nothing deselected. The decisions
  are `latest_run_time`, `next_run_time`, `first_attempt` and `next_due` in
  `ingest/scheduler.py`; `worker/runtime.py`'s `Scheduler` reschedules through
  them and records `latency_measured` and the declared cadence per source.
  GFS 00z is first attempted at 05:18Z; GDPS, GEPS, REPS, HRDPS and RDPS at
  their run time exactly. Native cadences are the declared 360/600/600/3600/
  3600/60 s and are no longer clamped by the 300-1800 s derived poll window.
  The progress `cadence_seconds` the stall check counts is now the declared
  cadence rather than the poll interval, so a six-hourly model is not called
  stalled forty-five minutes after a run. Also `cd api && uv run pytest` ->
  887 passed, 36 skipped (856 + the 31 new; the 36 skips are unchanged).
- [x] 2.2 Poll every ten minutes until the run appears, bounded by the next
  scheduled run time, then report `cancelled` naming the run and poll duration
  with the previous run left visible; try the declared dated WXO-DD Datamart
  path for ECCC records and record which path answered.
  Verify: `cd api && uv run pytest tests/test_worker_scheduling.py -k "poll or datamart_fallback"`
  Verify result: `cd api && uv run pytest tests/test_worker_scheduling.py -k
  "poll or datamart_fallback"` -> 21 passed, 28 deselected. The decision is
  `poll_decision(PollState, run_cadence_seconds=..., now=...)` in
  `ingest/scheduler.py`; `worker/runtime.py`'s `Scheduler._poll` opens the poll
  on a forecast source's `cancelled` attempt, reschedules it every 600 s
  through `_schedule_poll`, and closes it at the next nominal run time with
  exactly `run <id> did not appear after polling <N> min; previous run stays
  visible`. No poll before the bound is a failure and nothing is substituted
  for the missing run; the previous run is never touched. The poll state lives
  in `progress[source_id]["polling"]` (`run_time`, `since`, `attempts`) and a
  run that appears writes `observed_publication` plus
  `observed_publication_run_time` for task 2.3 to re-measure from - a run that
  never appeared writes neither. `ingest/adapters/eccc_datamart.py` tries the
  record's `datamart_fallback_path` only when declared, records the answering
  path in `RunCandidate.detail`, `RunResult.notes` and every artifact's
  `provenance["datamart_path"]`, and names both paths when neither answers
  (the primary alone where no fallback is declared). Also `cd api && uv run
  pytest` -> 905 passed, 36 skipped (887 + 18 new; the 36 skips are unchanged).
- [ ] 2.3 Record the observed publication instant and the re-measured latency in
  the heartbeat document, writing nothing when the run never appeared.
  Verify: `cd api && uv run pytest tests/test_worker_heartbeat.py -k latency`
- [ ] 2.4 Retain the previous run when the newest run reaches less far, and
  serve the leads it lacks from the retained run with both run times.
  Verify: `cd api && uv run pytest tests/test_worker_scheduling.py -k short_cycle`

## 3. API: tiers, coverage, run staleness (API owner)

- [x] 3.1 Serve the two tier ranges, compute per-instant coverage from declared
  reach against runs actually retrieved, and refuse an instant in neither tier.
  Verify: `cd api && uv run pytest tests/test_timeline.py -k "tier or coverage"`
  Verify result: `cd api && uv run pytest tests/test_timeline.py -k "tier or
  coverage"` -> 15 passed, 10 deselected. Also `cd api && uv run pytest` ->
  871 passed, 36 skipped (856 before, plus the 15 new). The coverage read is
  `ArtifactStore.retained_artifacts`, ranked by the same two-run ceiling
  `prune` enforces; `current_artifacts` is unchanged. A run whose adapter
  declared no run time is credited only where it demonstrably published
  frames, because a reach is stated relative to a run time and the
  `model_runs` retrieval stamp is not one.
- [ ] 3.2 Carry `run_time` and `run_stale` (older than twice the declared run
  cadence) on every frame, null with a reason where the run time or cadence is
  unknown, and never withhold a frame for being run-stale.
  Verify: `cd api && uv run pytest tests/test_layers.py -k run_stale`
- [ ] 3.3 Set `staleness_tolerance_seconds` to one native interval per layer.
  Verify: `cd api && uv run pytest tests/test_layers.py -k tolerance`

## 4. Web: boundary, coverage list, run labels (web owner)

- [x] 4.1 Mark the 24 h boundary and the step change beyond it, with a text
  alternative naming both ranges and the no-frames-beyond case.
  Verify: `cd web && npm test -- --run boundary`
  Verify result: `cd web && npm test -- --run boundary` -> 17 passed (1 file), 0 failed.
- [x] 4.2 List the covering sources per instant with run times, offsets and
  run-stale badges, distinguishing nothing-covers-it from a failed request.
  Verify: `cd web && npm test -- --run coverage`
  Verify result: `cd web && npm test -- --run coverage` -> 13 passed (1 file), 0 failed.
- [x] 4.3 Label each run segment across a short-cycle run change and draw no
  value across the join.
  Verify: `cd web && npm test -- --run runchange`
  Verify result: `cd web && npm test -- --run runchange` -> 11 passed (1 file), 0 failed.

## 5. Gate

- [ ] 5.1 `make test`, `openspec validate horizon-tiers-cadence-and-staleness
  --strict`, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
