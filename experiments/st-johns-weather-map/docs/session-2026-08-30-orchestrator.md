# Session log — 2026-08-30, truth boundary + live core spine

Orchestrated session. **All four parallel agents were killed mid-flight by the
session rate limit** before they could act on the stop-and-log instruction.
Three had already written logs; one had not. Their work is nevertheless on disk.

Read `docs/agent-{a,c,d}-handoff.md` before resuming. **There is no
`agent-b-handoff.md`** — Agent B (GeoMet) died first; its state is reconstructed
below from the filesystem, not from its own account, so treat it as unverified.

## Validation of the previous handoff

`HANDOFF.md` was checked against the code and against live endpoints. It is
accurate and in places understates the problem. The full validated findings are
in the approved plan at `~/.claude/plans/can-you-read-this-groovy-tower.md`.
The short version:

- The map is entirely fabricated. `web/src/MapPanel.tsx` paints fractal-noise
  "Doppler precipitation echoes with authentic dBZ color ramp" under a legend
  reading `15 dBZ / 35 dBZ / 55+ dBZ`. Nothing behind it is a response.
- `web/src/api.ts` labels every HTTP 200 "Live API"; `data_mode` is never read.
- `api/weather_api/app.py` swallows every live-store exception and falls
  through to `math.sin` synthetic weather in `fixtures.py`.
- Every adapter hard-codes `complete=True, qc_passed=True`.
- The API catalogue is 6 hand-written records, not the 59-record registry, and
  one of them (`cyyt-metar`) is not a real registry id.

## Live endpoint reality, verified 2026-08-30 ~02:30 UTC

| Path | Result |
|---|---|
| `dd.weather.gc.ca/today/model_hrdps/continental/2.5km/` | **404** — `today/model_hrdps/` is empty |
| `dd.weather.gc.ca/20260830/WXO-DD/model_hrdps/` | exists but **empty at 02:30Z** |
| `dd.weather.gc.ca/20260829/WXO-DD/model_hrdps/continental/2.5km/{00,06,12,18}/` | 200, real GRIB2 |
| `dd.weather.gc.ca/today/model_gdps/15km/` | **404** — GDPS is at `10km/`; the adapter says `15km` |
| `data.ecmwf.int/forecasts/20260830/` | **404** — only 0826–0829 listed |
| `aviationweather.gov/api/data/metar?ids=CYYT` | 200 |
| `api.weather.gc.ca/collections/swob-realtime/items` | 200 |
| `noaa-gfs-bdp-pds.s3.amazonaws.com` | 200 |
| `opendata.dwd.de/weather/nwp/icon/grib/00/t_2m/` | 200 |
| `api-iwls.dfo-mpo.gc.ca/api/v1/stations` | 200 |
| `smartatlantic.ca/erddap/.../SMA_st_johns.csv` | 200 |

**The dated directory rolls at 00Z and is empty for the first hours of the UTC
day.** Discovery must try today then fall back to yesterday. The current code
does neither and stamps `provider_run_id` with today's date regardless, so it
fails and mislabels runs every night.

## ECCC GeoMet — the significant find

`https://geo.weather.gc.ca/geomet/` is up, credential-free, and serves **37,918**
WMS layers plus WCS. `GetFeatureInfo` returns real numeric values carrying valid
time, run time, units and level — enough for honest provenance:

```
HRDPS-WEonG_2.5km_AirTemp     → value 17.729914
                                title_en "HRDPS-WEonG - Temperature [°C]"
                                time 2026-08-30T02:00:00Z
                                dim_reference_time 2026-08-29T18:00:00Z
HRDPS.CONTINENTAL.PRES_HR.850 → value 88.693535  "Relative humidity at 850 mb [%]"
```

Confirmed present: `RADAR_1KM_RRAI`, `Lightning_2.5km_Density`,
`Current-Alerts`, `AQHI-OBS`, 36 × `HRDPS-WEonG_2.5km_*` surface fields,
`HRDPS.CONTINENTAL.PRES_HR.{50..1015}` (a real pressure-level humidity profile,
the first this project has had), and 5,417 RDPS/GDPS/REPS/GEPS layers.

Owner decision this session: **GeoMet OGC becomes the ECCC spine**, collapsing
~30 bespoke GRIB2/XML adapters into one client. Raw GRIB2 stays only where
GeoMet lacks a field. Agent B's log records which layers were actually verified.

Caveat: WCS `GetCapabilities` is 200 but a naive `GetCoverage` returned an XML
fault — axis labels must come from `DescribeCoverage` first. WMS +
GetFeatureInfo is the proven path; WCS is unproven.

## Work completed directly (Step 6 — Compose, worker liveness, credentials)

| Change | File |
|---|---|
| `WEATHER_FIXTURE_MODE: "true"` removed; fail-closed `WEATHER_DATA_MODE` added | `compose.yaml` |
| Every host port now binds `127.0.0.1:` only | `compose.yaml` |
| API given read-only MinIO credentials — it previously had **none at all**, so it could not have read a published object even with fixture mode off | `compose.yaml` |
| Root MinIO credentials confined to a one-shot `minio-bootstrap` service; worker gets a scoped writer, API and titiler a scoped reader | `infra/minio/bootstrap.sh`, `compose.yaml` |
| Worker image no longer ships `mc`; it no longer administers MinIO | `worker/Dockerfile`, `worker/entrypoint.sh` |
| Heartbeat written **before every source**, not only between cycles | `worker/runtime.py` |
| Heartbeat carries per-source `last_success` + cadence; healthcheck fails on **stalled ingestion**, not merely a dead process | `worker/runtime.py` |
| A refresh job matching no schedulable adapter finishes `failed`, not `succeeded` | `worker/runtime.py` |
| 6 tests for liveness vs. progress | `api/tests/test_worker_heartbeat.py` |
| Truth-boundary smoke script + opt-in live smoke target | `scripts/smoke.sh`, `Makefile` |

### Judgment call worth knowing about

A source that has **never** succeeded does not fail the worker healthcheck —
only a source that used to succeed and then stopped. A permanently-404 endpoint
is an ingestion fact for `/sources/status` to report; failing container liveness
on it would restart-loop without fixing anything. Encoded in
`worker.runtime.stalled_sources` and tested.

### Verified

- `docker compose config --quiet` — passes.
- `api/tests/test_worker_heartbeat.py` — 6 passed, run with `--noconftest` to
  isolate from an in-flight parallel edit.
- The full API suite was **red at the time of writing**, from Agent C's
  in-progress `models.py` / `fixtures.py` change (`SourceRecord` gained required
  `category` and `schedulable` fields the fixture records do not supply). That
  fires through the autouse fixture in `conftest.py` and takes down the whole
  suite. Agent C was told to resolve or revert it before stopping — **confirm
  this is green before doing anything else.**

## GeoMet reviewed, fixed and wired — 4 new live sources

The 2,066-line unreviewed module was rewritten and is now registered for
`eccc-radar`, `eccc-lightning`, `eccc-cap-alerts` and `eccc-aqhi` — the four ids
nothing else claimed. **The project had no radar, lightning, hazard or air
quality ingestion at all before this.** All four publish live:

```
awc-metar-speci  surface           published  complete=t qc=t  passed
eccc-aqhi        aqhi              published  complete=t qc=t  passed
eccc-cap-alerts  alerts            published  complete=t qc=t  passed
eccc-cap-alerts  alerts_features   published  complete=t qc=t  passed
eccc-lightning   lightning         published  complete=t qc=t  passed
eccc-radar       radar             published  complete=t qc=t  passed
```

Every `passed` there is *earned* from `validate_run`, not a literal.

### Four real bugs the review caught — none would have been visible in a test

1. **The manifest interface was never actually matched.** An indirection layer
   called `RequiredField(...)` with a keyword that does not exist, caught the
   `TypeError`, and fell back to a positional call that put **`level` in the
   `units` slot**. Every field would have failed `bad_units`, so every model run
   would have been `complete=False` *forever*. `required_valid_times` was never
   passed at all.
2. **Hardcoded `"status": "passed"`** in both vector adapters — precisely the
   defect this whole session removed everywhere else.
3. **The radar trap was live.** The service really does answer
   `{"value": 0, "class": "Undetected"}`, and the old code wrote that straight
   through — publishing **`0 mm/h` as a measurement** on every clear scan. "No
   echo" is not "no precipitation", and a zero there is a lie.
4. **Manifest units were read back out of the dataset**, making the unit check
   tautological — it could never fail.

A 3×3 point lattice also returned nothing for AQHI, caught only by running it
live: a vector `GetFeatureInfo` resolves against a search area derived from map
resolution, so a probe 0.3° from a station returns zero features. Replaced with
declared query boxes.

### The loader now fails loudly

`ingest/adapters/__init__.py` used `except ModuleNotFoundError: continue`, which
cannot tell "this family has not landed yet" (deliberate, tolerated) from "this
module exists and its imports are broken" (must be loud). It now uses
`importlib.util.find_spec`. Confirmed working: a missing `numpy` in a bare
interpreter propagated instead of silently registering nothing.

13 adapters register cleanly, with the collision resolved as decided —
Datamart owns `eccc-hrdps`/`eccc-rdps`/`eccc-gdps`, GeoMet owns the other four.

### Carried forward, honestly

- **`HRDPS.CONTINENTAL.PRES_HR.{level}`** — the pressure-level humidity profile,
  the only real vertical profile this project has — is preserved as a tested
  module-level function. It **needs a registry record that does not exist yet**;
  filing it under `eccc-radiosonde` would be a category lie, since that record
  is upper-air *observations*. Needs something like
  `eccc-hrdps-pressure-levels`. Not invented.
- **`HRDPS-WEonG_2.5km_*` maps to `eccc-hrdps-weg-prognos`, which nothing
  claims** — a free win, out of scope at the time.
- **CAP alert feature schema is unverified** — no alert was in force during
  testing. The adapter therefore interprets nothing: it validates a feature
  *count* and publishes the `FeatureCollection` byte-for-byte.

## LIVE STACK — first real evidence, and one blocker found and fixed

The stack came up on the first attempt: all six services healthy, no Dockerfile
or Compose fix needed. **Real CYYT METAR data landed end to end** and reads back
through the API with honest provenance:

```
data_mode: "live",  operational: false
temperature 18.0 degC        dew_point 17.0 degC
relative_humidity 93.9 %     mean_sea_level_pressure 1011.8 hPa
visibility 24140.16 m        total_cloud 100 %
every field source_id: awc-metar-speci
```

`/catalog` returns the real 59-record registry, not the 6-record fixture list.
`make smoke` passes, including the storage-outage case.

### The blocker: a warm cache masked a storage outage

`LiveStore` kept an unbounded in-memory dataset cache with no invalidation tied
to storage reachability. Because `current_artifacts()` only touches Postgres,
stopping MinIO left the API happily serving values out of RAM. A cold process
correctly returned `unavailable`; a warm one returned live numbers.

**Same request, two different answers depending on how long the process had been
up.** A truth boundary that depends on process age is not a boundary.

The sharper problem was not staleness: with the object store unreachable the API
cannot tell that a revision has been *superseded*, so it would serve withdrawn
evidence as current.

Fixed in `api/weather_api/store.py`: an `assert_object_store_reachable()` probe
on all three sampling entry points (point, profile, timeline), cache eviction
for revisions that are no longer published, and a bounded LRU
(`MAX_CACHED_DATASETS = 32` — every new run mints a new revision id, so the old
cache never stopped growing). Six new tests, plus proof against the live stack:

```
1. warm cache, MinIO up   -> live,        values present
2. MinIO stopped          -> unavailable, 0 non-null values
3. MinIO restarted        -> live,        values present again
```

Also fixed in `scripts/smoke.sh`: `jq '.operational // "absent"'` treats `false`
as falsy, so the check could never observe a correct `operational: false` and
reported "absent" regardless of the real value. A check that cannot fail is
worse than no check.

### Still broken: no forecast-model coverage at all

Both GRIB2 families fail to decode with `only 0-dimensional arrays can be
converted to Python scalars` — a numpy 2.5.2 / cfgrib 0.9.15.1 / eccodes 2.48.0
incompatibility. `noaa-gfs` separately rejects every byte-range subset for
exceeding its own 25 MiB ceiling. **Both fail closed correctly** — nothing is
published and nothing is fabricated — but the practical result is that HRDPS,
RDPS, GDPS and GFS currently contribute nothing. Only observations are live.

## FINAL STATE — all gates green

| Gate | Result |
|---|---|
| `api` tests | **186 passed, 0 failed** |
| `registry` tests | 6 passed |
| `web` tests | 13 passed (was 7) |
| `web` build | passes (`tsc -b` + `vite build`) |
| SQL invariants (`make test-sql`) | 17/17 hold against real PostgreSQL |
| `docker compose config` | passes |

The stale tests are resolved. Highlights from the second wave:

- Every adapter test now asserts the **fail-closed** contract, with a
  mirror-image negative case: drop one declared field and the run must come
  back `complete=False` and publish nothing.
- The ECCC 00Z-rollover case is covered — today's date directory empty,
  yesterday's populated, discovery falls back and still stamps the run from the
  **filename**, not from `window.now`. That bug would have broken ingestion
  every night.
- ECMWF and DWD are tested as deliberately non-publishing, asserting the raised
  message names the real blocker (4-day retention / icosahedral grid). Inventing
  either would have been fabrication.
- `web` gained a `MapPanel.test.tsx` proving a missing layer renders its
  unavailable state **and still shows its `semantics` text** — that is where
  "no echo means no detected precipitating echo, not clear sky" reaches a user.

### One real gap closed during integration

Agent E flagged that `ingest/manifest.py:validate_run` accepted a `window`
parameter and never read it. That was a genuine hole: the validator checked
that required valid times were *present*, but nothing stopped a run carrying
extra steps *outside* the -3h/+24h boundary. It matters twice — the API samples
the nearest published step within an hour, so an out-of-window step can answer a
question it has no business answering, and every extra step spends the 25 GiB
cap on evidence nothing may display.

Now flagged `out_of_window:<iso>` as a **QC** failure (a contract violation, not
a gap), capped at five named steps plus a summary so the flag list stays
readable. Four tests cover it, including the inclusive-edge case.

Writing those tests immediately caught a bug in the fix itself:
`numpy.datetime64(v, "ns").item()` returns an **int**, not a `datetime`, because
nanoseconds exceed `datetime`'s microsecond resolution. Cast through
`datetime64[s]` first.

## EARLIER STATE — reconstructed after the first wave of agents died

Verified directly, not taken from any agent's word:

- **Every Python file parses.** No module is half-edited or syntactically broken.
- **`api` suite: 9 failed, 155 passed** (measured after all four agents stopped;
  Agent A's log says 18, which was its own earlier reading before Agent C's
  work landed — trust the 9). Agent A's log accounts for the failures as
  an *existing test asserting the behaviour we deliberately deleted*
  (`complete is True`, `"status": "passed"`, the old `today/` discovery URLs,
  ECMWF/DWD returning candidates). Agent A did not get to update them. This is
  the single largest piece of unfinished work.
- **`web`: TypeScript compiles (`tsc -b` exit 0); 3 of 7 tests fail.** Agent D
  did not update `App.test.tsx`, which asserts copy and a fetch-mock shape the
  rewrite changed.
- **Agent C reported its own scope green** before dying, and the
  `SourceRecord` / `fixtures.SOURCES` breakage I flagged mid-session is resolved.
- **`registry` suite: 6 passed.** Categories corrected; no `status` changed.

### Agent B (GeoMet) — reconstructed, unverified

`ingest/adapters/eccc_geomet.py` exists: **2,066 lines**, parses cleanly.
It contains a streaming capabilities parser, `GeoMetClient`, `TimeExtent`
handling, `parse_title_units`, `wind_components`, and pinned layer constants
(`RADAR_1KM_RRAI`, `RADAR_1KM_RSNO`, `Lightning_2.5km_Density`,
`Current-Alerts`, `AQHI-OBS`).

**It is NOT registered** — `eccc_geomet` is absent from `_MODULES` in
`ingest/adapters/__init__.py`, so nothing imports or runs it. That makes it
inert and safe, but also entirely unexercised: **no test covers it and no live
call through it has been observed.** Do not wire it in without reading it first
and running it against the live service. Its pinned layer ids are plausible and
match what I verified independently, but which of them *Agent B* actually
confirmed is unknown.

## Storage integrity — PROVEN against real PostgreSQL

Agent A's `002_run_publication.sql` is no longer just believed correct. New:
`infra/postgres/tests/publication_invariants.sql` + `scripts/sql-test.sh`,
wired in as `make test-sql` and added to `make test`. It spins up a disposable
postgis container, loads both migrations in filename order exactly as the
compose init directory does, and asserts 17 properties. **All 17 pass.**

The ones that matter most:

- *An incomplete parent run cannot publish even when its artifact rows claim
  otherwise.* This is precisely the IFS defect from the original handoff — a run
  published as "complete and QC-passed" while its logs showed skipped fields.
  Under `001` alone it would still publish, because `publish_revision` gated on
  the artifact's own copied flags and never consulted `model_runs`.
- *The failed publish left the previous pointer byte-for-byte unchanged.*
- *A run containing one bad artifact publishes none of them* — including the
  artifact already processed before the bad one was reached, which rolls back.
- All four immutable columns (`sha256`, `object_key`, `byte_size`, `created_at`)
  reject rewrites, while `state` / `superseded_at` stay mutable.
- A run with no staged artifacts, and a nonexistent run, are errors rather than
  silent successes.

### A real flake caught while building the gate

The first version polled `pg_isready`, which passes against the **temporary**
server the postgis entrypoint runs for its own init before shutting it down and
restarting for real. The next command then died with *"the database system is
shutting down."* The gate now requires four consecutive successful queries, so a
restart mid-poll resets the count. Worth knowing: any future script that waits
on this image with `pg_isready` has the same latent bug.

## First action on resuming

**Update the stale tests first.** Nothing else can be trusted until the suite is
green, and the tests are the only unfinished half of otherwise-complete work.

1. Fix the 9 API failures (`test_adapter_{dwd,eccc_datamart,eccc_ogc,ecmwf,noaa_s3}.py`,
   `test_ingest_store.py`). Agent A's handoff lists each with its cause and fix. Note especially
   `test_ingest_store.py::test_publication_happens_only_after_every_artifact_is_staged`:
   fix the **test double** (its `RecordingCursor.fetchone()` returns `'id-1'`
   where `publish_run` correctly coerces an integer), not the production code —
   the SQL function genuinely returns `integer`.
2. Fix the 3 web failures in `App.test.tsx`, then add Agent D's missing CSS
   rules. `.map-text-alternative` must be visually hidden (sr-only) — right now
   it renders as visible text over the map pane.
3. `make test` green, then `docker compose up --build --wait`.
4. `make smoke` — asserts the truth boundary against real HTTP, including
   stopping MinIO to prove a storage outage returns `unavailable` with null
   values rather than a fixture number. Mocked tests cannot catch that.
5. Only then decide what to do with `eccc_geomet.py`: review it, test it, and
   register it — or delete it and rewrite. Do not assume it works.

## Unchanged and deliberately so

No registry source was marked `active`. No credentials were requested. No V1
contract, production spec or `.repowise/` file was touched. `operational` stays
`False` everywhere. `HANDOFF.md` was **not** rewritten — per its own rule, it is
only updated once behaviour and smoke evidence are current, which they are not.
