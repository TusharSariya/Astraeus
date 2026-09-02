## Why

The store was sized for a candidate field list. The field catalogue decision
(wayfinder ticket 18) changed the scope to every field every admitted source
publishes, and the re-run size probe measured what that costs:
`docs/research/wayfinder/size-probe-full-fields.md` on branch
`research/size-probe-full-fields` puts the core scenario at 7.5 GB resident
and about 108 GB per cycle on the wire, core plus planning reductions at
11.1 GB and about 525 GB per cycle, and core plus planning with subsetted
ensemble members at 18.2 GB and about 1.73 TB per cycle. With the two-run
staging overlap `infra/STORAGE.md` already mandates, only the core scenario
fits the current 25 GiB bucket quota. The earlier probe,
`docs/research/wayfinder/size-probe.md` on branch `research/size-probe`,
measured the same box under the candidate list at 284 to 505 MB and is
superseded on scope, not on method.

Retention is the second half of the problem. `infra/STORAGE.md` keeps the
latest and previous complete run per logical stream with a three-hour floor
for high-cadence observations, and `evidence-window-timeline` fixes the
window at `now-3h .. now+24h`. The planning tier reaches 14 days (wayfinder
tickets 15 and 23), so a forecast frame that is legitimately served today
fails the out-of-window QC gate that `artifact-ingestion` applies. Nothing in
the specification says what happens to a frame that falls out of the back of
the window, so a reader cannot tell "we never retrieved it" from "we held it
and it aged out", and nothing says what a restart may assume about what is
already on disk.

The owner resolved this on 2026-09-02 (wayfinder ticket 20,
`https://github.com/TusharSariya/Astraeus/issues/20`): 64 GiB hot quota, no
cold tier, retention as a sliding valid-time window used as a restart cache,
idempotent re-fetch, and a third absence state for a frame that aged out.
This change writes that decision into the specification. It changes no
adapter, promotes no registry state, and adds no source.

## What Changes

- **The hot quota becomes 64 GiB**, enforced exactly as the 25 GiB quota is
  today: a MinIO bucket quota set idempotently before the worker loop, with
  room reserved before a download so an oversize artifact is never uploaded.
  Scenario C of the full-field probe is the sizing case.
- **There is no cold tier.** Nothing spills anywhere. Reaching the quota is a
  failure that fails closed; it is never resolved by evicting a visible
  revision or by moving bytes off the hot store.
- **The evidence window becomes a sliding valid-time window** from `now-24h`
  to `now+14d`, replacing the fixed `now-3h .. now+24h` window. It bounds the
  API's accepted `valid_time`, the ingestion `FetchWindow`, the out-of-window
  QC gate, and what the store retains.
- **Retention is that window, used as a restart cache.** The store keeps every
  frame whose valid time lies inside it and purges frames as they fall
  outside. Per forecast source it keeps the latest complete run plus the
  previous complete run, which is what atomic publication already needs and
  what makes run-to-run change visible. Observations and nowcasts keep the
  full 24 hours of history, raising the three-hour floor.
- **No vintage archive is ever accumulated.** Keeping every run whose valid
  times still fall inside the window would be dozens of runs per source. The
  store keeps two runs per forecast source and no more; a third run displaces
  the oldest at publication.
- **Ingestion is idempotent by provider run id and frame time.** A frame
  already present for the same provider run id and valid time is not fetched
  again. Stopping and restarting the stack re-fetches only what the window is
  missing.
- **Derived artifacts are recomputed, not re-fetched.** A derived-here or
  display-derived artifact whose retained inputs are present is rebuilt from
  those inputs on restart; a derived artifact whose inputs have aged out is
  absent and says so, rather than causing its inputs to be fetched again.
- **Aged out is a third absence state.** A frame the store held and purged is
  reported as `aged out at <last valid time>`, beside `null` (never
  retrieved) and `blocked` (licence, credential or partnership), and distinct
  from `retrieval failed`. It is also distinct from `available-not-stored`
  from `field-catalogue-and-families`, which was never fetched at all.
- **Fail-closed behaviour is pinned** for the four cases this change creates:
  the quota is reached, a purge runs while a reader holds an artifact open,
  the worker restarts mid-publication, and a run never completes.

## Capabilities

### Modified Capabilities

- `artifact-storage-integrity`: the 64 GiB quota with no cold tier, retention
  as a sliding valid-time window, the two-run forecast rule and the 24-hour
  observation floor, purge safety against an open read, and the recorded
  last valid time that makes an aged-out report possible.
- `artifact-ingestion`: the out-of-window QC gate moves to `now-24h ..
  now+14d`; ingestion becomes idempotent by provider run id and frame time;
  derived artifacts are recomputed rather than re-fetched.
- `ingestion-worker-scheduling`: a restart resumes the window instead of
  refilling it; the quota outcome names the 64 GiB cap; a run that never
  completes neither publishes nor holds staging bytes indefinitely.
- `evidence-window-timeline`: the window requirement becomes the sliding
  24-hour-back to 14-day-ahead window; readiness is judged against it; the
  aged-out absence state is reported on the timeline and in point responses.

## Impact

- `infra/STORAGE.md`: quota 25 GiB to 64 GiB, retention rewritten as the
  sliding window plus restart cache, the three-hour observation floor becomes
  24 hours, cold tier explicitly ruled out.
- `infra/docker-compose.yml` and the worker bootstrap that sets the bucket
  quota: the configured cap and its unit suffix.
- `api/weather_api/config.py` and the store environment: the window bounds
  become configuration read from one place rather than two literals.
- `api/weather_api/store.py`: window-bounded coverage resolution; the purge
  sweep; `aged_out` and `last_valid_time` on absence notices.
- `api/weather_api/models.py`: `aged_out` as an absence reason beside `null`
  and `blocked`, carrying `last_valid_time`.
- `ingest/scheduler.py` and `ingest/store.py`: the idempotency key of
  provider run id plus frame time; the recompute-not-refetch path for derived
  artifacts; the restart resume.
- `ingest/validate.py`: the out-of-window bounds.
- `web/src/`: the aged-out badge and legend entry, distinct from null,
  blocked, available-not-stored and retrieval failed.
- No adapter retrieval logic changes, no registry status is promoted,
  `operational` stays `false`. Spec-Impact: none outside this experiment.
