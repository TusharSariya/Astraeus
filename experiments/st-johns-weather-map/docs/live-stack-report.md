# Live stack report — 2026-08-30 (Agent H)

Scope: bring `docker compose up --build --wait` up for real, run the
truth-boundary smoke test, exercise real ingestion, and report honestly.
Ownership: `compose.yaml`, the three Dockerfiles, `.dockerignore`s,
`infra/minio/bootstrap.sh`, `worker/entrypoint.sh`, `scripts/smoke.sh`,
`.env.example`, this file. No application source under `ingest/`,
`api/weather_api/`, `registry/`, `web/src/`, `worker/runtime.py`, or
`infra/postgres/` was touched.

## Summary

The stack comes up clean on the first try (`docker compose up --wait`, no
retries needed) and stays healthy. Manual ingestion of `awc-metar-speci`
succeeded and its values are readable end to end through `/point` with honest
provenance — the first genuinely live evidence this project has produced.
The smoke test caught one real, reproducible truth-boundary defect (not
fixture fallthrough, but a stale in-memory cache masking a storage outage) and
one script bug in itself, which I fixed. GRIB2-based adapters
(eccc-hrdps, eccc-rdps, eccc-swob) failed to decode/publish; they correctly
failed closed and published nothing.

## 1. Bringing the stack up

```
docker compose build      # ~35s warm, single pass, no errors
docker compose down -v
docker compose up --wait
```

All six services reported healthy on the first attempt:

```
NAME                                   STATUS
astraeus-st-johns-weather-api-1        Up (healthy)
astraeus-st-johns-weather-minio-1      Up (healthy)
astraeus-st-johns-weather-postgres-1   Up (healthy)
astraeus-st-johns-weather-titiler-1    Up (healthy)
astraeus-st-johns-weather-web-1        Up (healthy)
astraeus-st-johns-weather-worker-1     Up (healthy)
```

Verified directly (not assumed) before bringing the stack up:

- Both `api` and `worker` images contain `ingest/manifest.py` and
  `ingest/meteorology.py` — `python -c "import ingest.manifest,
  ingest.meteorology"` succeeds in both.
- `ingest/adapters/eccc_geomet.py` is present in both images but, per the
  session doc, still not registered in `ingest/adapters/__init__.py` (Agent
  G's file) — did not touch it.
- `registry/` is copied as only `registry/source_data.py` into both images,
  as before; `grep -rn "^from registry\|^import registry"` across
  `api/weather_api`, `worker`, `ingest` shows the only import is
  `from registry.source_data import registry` in `api/weather_api/store.py` —
  the namespace-package assumption still holds, nothing new imports more of
  `registry/`.
- Worker image ecCodes: **updated 2026-08-30 (WP1).** The Debian
  `libeccodes-dev` 2.28.0 apt package is gone; the worker now selects the
  `grib` extra in `api/pyproject.toml` (`eccodeslib==2.48.0.26`, pulling
  `eckitlib==2.1.1.26`, cp313 manylinux_2_28 x86_64/aarch64 wheels) and
  `findlibs` resolves the library from that wheel. Verified inside the image
  with `-W error::UserWarning` (no version warning fires):
  `eccodes.__version__=2.48.0`, `codes_get_api_version()=2.48.0`,
  `findlibs.find('eccodes')=/app/.venv/lib/python3.13/site-packages/eccodeslib/lib64/libeccodes.so`,
  `codes_definition_path()=/MEMFS/definitions` (definitions compiled into the
  library; no `ECCODES_DEFINITION_PATH` needed). The API image does not select
  the extra and does not install ecCodes; `import ingest.grib` succeeds anyway
  there (grib decoding is lazily imported and never touches native libs on the
  API's read path). See "TCDC finding" below for what the upgrade did and did
  not change.

**No compose/Dockerfile/bootstrap fixes were needed.** Everything in my
ownership worked as written:

- `minio-bootstrap` ran with the current MinIO/mc release pair
  (`minio/minio:RELEASE.2025-07-23T15-54-02Z` /
  `minio/mc:RELEASE.2025-07-21T05-28-08Z`) with **no syntax changes required**.
  `mc admin policy create` (with `mc admin policy update` fallback) and
  `mc admin policy attach` both worked verbatim:

  ```
  minio-bootstrap-1  | Added `root` successfully.
  minio-bootstrap-1  | Bucket created successfully `root/weather-artifacts`.
  minio-bootstrap-1  | Successfully set bucket quota of 25 GiB on `weather-artifacts`
  minio-bootstrap-1  | Created policy `weather-writer` successfully.
  minio-bootstrap-1  | Created policy `weather-reader` successfully.
  minio-bootstrap-1  | Added user `weather-writer` successfully.
  minio-bootstrap-1  | Added user `weather-reader` successfully.
  minio-bootstrap-1  | Attached Policies: [weather-writer]
  minio-bootstrap-1  | To User: weather-writer
  minio-bootstrap-1  | Attached Policies: [weather-reader]
  minio-bootstrap-1  | To User: weather-reader
  minio-bootstrap-1  | minio bootstrap complete: bucket=weather-artifacts quota=25GiB writer=weather-writer reader=weather-reader
  ```

- `api` and `worker` both waited correctly on
  `minio-bootstrap: condition: service_completed_successfully`.
- All host ports are `127.0.0.1`-bound; root MinIO credentials are used only
  inside `minio-bootstrap`.

## 2. Smoke test

Ran `./scripts/smoke.sh` against the live stack.

### Fix made to the script itself

`scripts/smoke.sh` had a genuine bug: `jq -r '.operational // "absent"'`.
jq's `//` alternative operator treats `false` as falsy, so this expression
returns `"absent"` for a **correct** `operational: false` response — it could
never observe the real value, and every endpoint failed this check regardless
of whether the API was honest. Fixed to
`if has("operational") then (.operational | tostring) else "absent" end`, and
made the trailing `ok` line conditional on that block actually passing rather
than always printing (it previously printed "ok" unconditionally even when
the loop above had just recorded failures). This is a stricter check, not a
weaker one — before the fix it could never fail on a real "absent" case since
the same jq bug also masked genuinely missing keys as `"false"`... no,
actually it masked `false` as `"absent"`, so the failure mode was "always
FAIL," not "never FAIL." Verified after the fix that legitimate
`operational: false` responses now correctly read as `false` and pass.

### First run (before restarting the API after clearing caches)

```
== reachability ==
  ok    health responds
  ok    ready responds
  ok    timeline responds
== truth boundary ==
  point data_mode = live
  ok    operational=false on every endpoint
== canonical catalogue ==
  catalog sources = 59 (registry has 59; 6 means the fixture catalogue is still wired)
  active=0 with last_retrieval=2
== fail-closed on storage outage ==
  outage data_mode = live, non-null field values = 6
  FAIL  storage outage produced values; this is the fixture fallthrough

smoke FAILED: 1 check(s)
```

### The one real failure — genuine defect, not fixed (not my file)

This is **not** the fixture fallthrough the smoke test was written to catch.
Isolated the mechanism directly:

1. With MinIO stopped and the on-disk artifact cache
   (`/tmp/weather-artifacts/*.zarr.zip` inside the `api` container) present,
   `/point` returns live values — expected, since `LiveStore` in
   `api/weather_api/store.py` deliberately caches the verified zip on disk
   (`store.py` lines ~139–153) so a request doesn't need to re-download an
   already-verified artifact.
2. Cleared the on-disk cache (`rm /tmp/weather-artifacts/*.zip` inside the
   running `api` container) with MinIO still stopped, and requested `/point`
   again: **still returned live values.** The disk cache was not the reason.
3. Root cause: `LiveStore` also keeps an **unbounded in-process memory
   cache** of the opened dataset, keyed by `revision_id`
   (`self._datasets.get(artifact.revision_id)` around `store.py` lines
   177–179), with no invalidation tied to store reachability or freshness.
   Once a revision's dataset has been opened once, the running API process
   will keep serving it from RAM forever, even if MinIO is completely gone,
   because it never has to touch the store to answer the request again.
4. Confirmed the fail-closed path *is* correct on a genuinely cold process:
   restarted the `api` container (`docker compose restart api`, disk cache
   already empty) with MinIO still stopped, then requested `/point`:

   ```json
   {"data_mode":"unavailable","operational":false,
    "fields":[{"field":"temperature","value":null}, ... all fields null]}
   ```

   All twelve fields came back `null`, `data_mode: "unavailable"`, exactly as
   intended — the fail-closed contract exists and works for a fresh process.

**Finding for the owner of `api/weather_api/store.py`:** `LiveStore`'s
in-memory `self._datasets` cache has no TTL or store-reachability check, so a
storage outage that happens *after* a revision has already been served once in
this process's lifetime is invisible to `/point` — it keeps serving the
previously-fetched (genuinely real, not fabricated, but now unverifiable)
values indefinitely. This does not fabricate data, but it violates the
project's own rule that a storage outage must surface as `unavailable`; a
long-running API process could serve a value that is hours or days stale with
no way for a client to tell the store went away. Recommend either an
outage-aware invalidation, a TTL on `self._datasets` tied to the freshness
threshold already computed per field, or a periodic revalidation ping to the
store. Restored MinIO afterward; did not touch `store.py`.

### Other smoke findings (all pass, recorded for completeness)

- `point data_mode = live` — correct, not `fixture`.
- `catalog sources = 59` — the real registry, not the old 6-record fixture.
- `active=0 with last_retrieval=2` — no source claims `active` without a
  recorded retrieval (2 sources — `awc-metar-speci` and `awc-taf` — have
  `last_retrieval` set from the manual runs below; `awc-taf`'s run staged but
  did not qualify as complete, so it never published, consistent with "no
  source may claim active without live evidence").
- `operational: false` on every endpoint, confirmed correctly now that the
  jq bug is fixed.

## 3. Real ingestion — AWC METAR/SPECI for CYYT

```
$ docker compose exec worker python /app/worker/runtime.py --once --source awc-metar-speci
2026-08-30T03:22:10.045458+00:00 scheduling 1 source(s): awc-metar-speci
2026-08-30T03:22:24.969231+00:00 awc-metar-speci: succeeded - published 1 artifact(s)
```

Postgres afterward:

```
    source_id    |   state    | complete | qc_passed | byte_size |          created_at
-----------------+------------+----------+-----------+-----------+-------------------------------
 awc-metar-speci | published  | t        | t         |     11991 | 2026-08-30 03:22:24.944549+00
 awc-taf         | staged     | f        | t         |      7792 | 2026-08-30 03:18:54.983206+00
 awc-metar-speci | superseded | t        | t         |     11991 | 2026-08-30 03:18:54.026688+00
(3 rows)

    source_id    | logical_name |             revision_id              |          updated_at
-----------------+--------------+--------------------------------------+-------------------------------
 awc-metar-speci | surface      | 7678aa03-a305-4c06-a002-7fa913ddfffa | 2026-08-30 03:22:24.951478+00
(1 row)
```

Read back through the public API — **the prize: real METAR values with
honest provenance**:

```
GET /api/experiments/weather/v0/point?latitude=47.5615&longitude=-52.7126
data_mode: live
fields:
  mean_sea_level_pressure = 1011.8 hPa
  temperature             = 18.0 degC
  relative_humidity       = 93.9 %
  visibility              = 24140.16 m
  dew_point               = 17.0 degC
  total_cloud             = 100.0 %
provider: NOAA/NWS Aviation Weather Center
product: METAR/SPECI
retrieval_time: 2026-08-30T03:22:24.840018Z
freshness: fresh (age_seconds ~= 243, threshold_seconds = 1200)
licence: AviationWeather.gov terms / US government data
adapter_version: awc-metar-v1
```

This is real, live weather for CYYT (St. John's) retrieved from
`aviationweather.gov`, published through the ingest pipeline, stored in
Postgres + MinIO, and served back through the API's evidence-boundary path
with full provenance — the first genuinely live end-to-end evidence this
project has produced. Note the worker also auto-ran this same source once on
its own during the `up --wait` cycle before any manual command was issued
(the timeline endpoint already showed `awc-metar-speci` data at
`2026-08-30T01:00–03:00Z` before I ran anything by hand).

### eccc-swob, eccc-hrdps, eccc-rdps, noaa-gfs — tried, correctly fail closed

```
$ docker compose exec worker python /app/worker/runtime.py --once --source eccc-swob
2026-08-30T03:22:50.614663+00:00 eccc-swob: failed - run staged but incomplete or QC-failed; previous revision stays visible
```

Automatic scheduling (during `up --wait` and the subsequent manual runs) also
exercised `eccc-hrdps` and `eccc-rdps`, both of which failed to decode:

```
Failed to decode https://dd.weather.gc.ca/20260830/WXO-DD/model_hrdps/continental/2.5km/00/024/20260830T00Z_MSC_HRDPS_UGRD_AGL-10m_RLatLon0.0225_PT024H.grib2: only 0-dimensional arrays can be converted to Python scalars
...
2026-08-30T03:21:39.632807+00:00 eccc-hrdps: cancelled - candidate unusable: No GRIB2 fields could be fetched or cropped for eccc-hrdps
```

> **RETRACTED 2026-08-30.** The diagnosis below was wrong, and it was wrong in a
> way that sent later readers hunting a dependency conflict that never existed.
> It is kept, struck through, because the reasoning is instructive.
>
> ~~this looks like a NumPy 2.x / cfgrib 0.9.15.1 / eccodes-python 2.48.0
> compatibility break in scalar extraction~~
>
> **Actual cause:** `crop_to_bbox` in `ingest/grib.py` assumed 1-D latitude and
> longitude axes. HRDPS and RDPS publish on a **rotated** lat/lon grid
> (`RLatLon` in the filename), so cfgrib correctly returns `latitude` and
> `longitude` as **2-D** coordinates over anonymous `y`/`x` dims. `latitudes[0]`
> is therefore a 2540-element row, and `float()` on it raises. `open_dataset`
> had already **succeeded**; the adapter's broad `except` re-labelled our own
> `TypeError` as a decode failure, which is why it read like a cfgrib bug.
>
> The pins are innocent and **were never changed**. numpy 1.x would have raised
> the same `TypeError`, only worded "only length-1 arrays".
>
> It stayed hidden because the one test covering this path monkeypatched
> `crop_to_bbox` away *and* fed it a 1-D grid — the suite was green exactly where
> production died.
>
> Fixed: rotated grids are now cropped by index window; provider cells and real
> coordinates survive unchanged; no regridding. Real HRDPS, RDPS and GFS data
> decode end to end. See the `grib-decoding` capability in `openspec/specs/`.

The identical `only 0-dimensional arrays can be converted to Python scalars`
error appears for every HRDPS and RDPS field across every step attempted — not a
data-availability problem, since the files themselves are fetched (the ECCC
00Z-rollover fallback worked; it found the populated `20260830` HRDPS/RDPS run).

`ecmwf-ifs` and `dwd-icon-global` both correctly declined to publish for the
reasons already documented in the session log (ECMWF 4-day retention window,
DWD's icosahedral mesh) — this is intended, not a bug.

`noaa-gfs` correctly refused to fetch a byte range exceeding its own safety
ceiling rather than silently pulling the full 521 MiB file:

```
Failed processing GFS subset https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20260829/18/atmos/gfs.t18z.pgrb2.0p25.f007: ... range set exceeded the 26214400 byte ceiling
```

This is fail-closed behavior working as intended (no fabricated GFS values,
nothing published), though it also means GFS never actually lands data in
this configuration — worth the ingest owner's attention if GFS was expected
to be a working source, since the byte ceiling as configured appears to always
reject its subsets.

`eccc-taf` (`awc-taf`) staged but did not qualify as complete/QC-passed and
correctly did not publish, leaving the previous (nonexistent) revision
untouched — no data appeared where none should.

## 4. Worker health

```
$ docker compose ps worker
astraeus-st-johns-weather-worker-1   Up (healthy)

$ docker compose exec worker python /app/worker/runtime.py --check-heartbeat; echo "exit=$?"
exit=0
```

Heartbeat contents after the runs above show the intended distinction working
correctly: sources that have **never** succeeded
(`dwd-icon-global`, `eccc-gdps`, `eccc-hrdps`, `eccc-rdps`, `eccc-swob`,
`ecmwf-ifs`, `noaa-gfs`, all with `last_success: null`) do **not** fail the
healthcheck (exit 0, container reports healthy) — only `awc-metar-speci`,
which has actually succeeded before, is tracked against its cadence for
staleness. This is the judgment call from the session log and it behaves as
documented.

## Remaining defects and who owns them

| Defect | Where | Owner | Severity |
|---|---|---|---|
| `LiveStore` in-memory dataset cache never invalidates on storage outage; `/point` keeps serving previously-fetched live values indefinitely after MinIO becomes unreachable, instead of degrading to `unavailable` | `api/weather_api/store.py`, `LiveStore.__init__`/`_datasets` cache (~lines 117–180) | api owner | Release blocker per the smoke test's own bar — reproduced directly, not fixture fallthrough, but violates the same "storage outage must surface as unavailable" rule |
| All HRDPS/RDPS GRIB2 fields fail to decode (`only 0-dimensional arrays can be converted to Python scalars`); every ECCC GRIB adapter run is `cancelled`/publishes nothing | `ingest/grib.py` + pinned `numpy`/`cfgrib`/`eccodes` versions in `api/pyproject.toml` | ingest/dependency owner | High — blocks all GRIB-based sources; correctly fails closed so no bad data leaks, but zero forecast coverage results |
| `noaa-gfs` subset requests always exceed the configured 26,214,400-byte range ceiling and are rejected; GFS never publishes in this configuration | `ingest/adapters/noaa_s3.py` / storage cap config | ingest owner | Medium — fails closed correctly, but source is effectively dead as configured |
| `eccc_geomet.py` (2,066 lines) still not registered in `ingest/adapters/__init__.py`; present in both images, unexercised | `ingest/adapters/eccc_geomet.py`, `ingest/adapters/__init__.py` | Agent G | Informational — confirmed still true, did not touch either file per instructions |
| ~~Worker image logs an ecCodes version warning (`2.28.0` installed vs. `2.42.0+` recommended) at every cfgrib import~~ **Fixed 2026-08-30 (WP1):** ecCodes 2.48.0 via the `eccodeslib` wheel, no warning | `worker/Dockerfile`, `api/pyproject.toml` `grib` extra | WP1 | Closed — and confirmed *not* to be the reason MSC total cloud decodes as `unknown`; see "TCDC finding" |
| MSC total cloud (`HRDPS TCDC_Sfc`, `RDPS TotalCloudCover_Sfc`) decodes with `units='unknown'` under ecCodes 2.48.0; `total_cloud` withheld from all three Datamart var maps | `ingest/adapters/eccc_datamart.py` (comment above `HRDPS_VARS`) | owner decision (stop gate) | Medium — no cloud cover from ECCC models until the owner chooses between publishing from the WMO 0/6/1 keys or carrying a local ecCodes definitions overlay |

## TCDC finding — 2026-08-30 (WP1, ecCodes 2.48.0)

Question asked: does upgrading the worker's ecCodes from 2.28.0 to 2.48.0
make MSC's total cloud cover decode with declared units, so `total_cloud`
can be published from HRDPS/RDPS?

Answer: **no.** One polite download per product (via
`ingest.http.PoliteClient`, 10 MB cap) of today's 12Z PT006H files, decoded
inside the rebuilt worker image. Keys verbatim:

```
=== eccc-hrdps TCDC_Sfc ===
listing: https://dd.weather.gc.ca/20260830/WXO-DD/model_hrdps/continental/2.5km/12/006/ -> ['20260830T12Z_MSC_HRDPS_TCDC_Sfc_RLatLon0.0225_PT006H.grib2']
downloaded bytes: 2750816
  centre = 'cwao'
  tablesVersion = 4
  localTablesVersion = 1
  discipline = 0
  parameterCategory = 6
  parameterNumber = 1
  productDefinitionTemplateNumber = 0
  typeOfFirstFixedSurface = 'sfc'
  typeOfSecondFixedSurface = 255
  paramId = 0
  shortName = 'unknown'
  name = 'unknown'
  units = 'unknown'
  cfVarName = 'unknown'
  cfgrib data_var 'unknown' units='unknown' GRIB_units='unknown' GRIB_paramId=0 GRIB_cfName='unknown' min=0.0 max=100.0
=== eccc-rdps TotalCloudCover_Sfc ===
listing: https://dd.weather.gc.ca/20260830/WXO-DD/model_rdps/10km/12/006/ -> ['20260830T12Z_MSC_RDPS_TotalCloudCover_Sfc_RLatLon0.09_PT006H.grib2']
downloaded bytes: 684348
  centre = 'cwao'
  tablesVersion = 4
  localTablesVersion = 1
  discipline = 0
  parameterCategory = 6
  parameterNumber = 1
  productDefinitionTemplateNumber = 0
  typeOfFirstFixedSurface = 'sfc'
  typeOfSecondFixedSurface = 255
  paramId = 0
  shortName = 'unknown'
  name = 'unknown'
  units = 'unknown'
  cfVarName = 'unknown'
  cfgrib data_var 'unknown' units='unknown' GRIB_units='unknown' GRIB_paramId=0 GRIB_cfName='unknown' min=0.0 max=100.0
=== eccc-gdps listing probe ===
gdps discover: eccc-gdps: no populated run cycle under https://dd.weather.gc.ca/{20260830,20260829}/WXO-DD/model_gdps/10km/
```

Cause, confirmed in this exact ecCodes build without any further download
(a `GRIB2` sample message with the same discipline/category/number and first
surface, varying only the second surface):

```
typeOfSecondFixedSurface=255 -> paramId=0 shortName='unknown' name='unknown' units='unknown'
typeOfSecondFixedSurface=8 -> paramId=228164 shortName='tcc' name='Total Cloud Cover' units='%'
```

ecCodes' `grib2/shortName.def` concept `tcc` (and the matching `name`,
`units`, `paramId` concepts) requires WMO 0/6/1 **with
`typeOfSecondFixedSurface=8`** (top of atmosphere). CWAO stamps 255
(missing), and ecCodes ships no `localConcepts/cwao` that would recognise the
CWAO encoding. That is a definitions mismatch, independent of library age:
2.28.0 and 2.48.0 behave identically here, and the retracted "needs
>= 2.42.0" sentence in the adapter comment has been replaced with this cause.

What the message *does* say: WMO code table 4.2, discipline 0, category 6,
number 1 is "Total cloud cover" in `%`, and the values span 0.0–100.0. What
the decoder says: `units='unknown'`. This experiment publishes only what the
provider/decoder declares, so `total_cloud` stays out of `HRDPS_VARS`,
`RDPS_VARS` and `GDPS_VARS`, the other six HRDPS fields publish, and a new
test pins that a declared `total_cloud` arriving as `unknown` fails
`validate_run` with `bad_units:total_cloud:unknown`.

**Owner question (stop gate 1):** should the adapter publish total cloud as
`percent` on the authority of the WMO 0/6/1 table entry (i.e. trust the
header keys rather than the ecCodes concept), or carry a local ecCodes
definitions overlay (`ECCODES_DEFINITION_PATH` with a `localConcepts/cwao`
that maps 0/6/1 + second surface 255 to `tcc`/`%`), or leave it withheld?
Neither is done here. GDPS: no populated cycle in the last two dated
directories at the time of the probe, so no GDPS mapping either way.

## What I did NOT change

No application source under `ingest/`, `api/weather_api/`, `api/tests/`,
`registry/`, `web/src/`, `worker/runtime.py`, or `infra/postgres/` was
touched. `ingest/adapters/eccc_geomet.py` and
`ingest/adapters/__init__.py` (Agent G's files) were not touched. No registry
source was marked `active`. No credentials were requested or embedded outside
`.env.example`'s existing local-only defaults.

## Final state — left running

The stack is left **up and healthy** for inspection:

```
NAME                                   STATUS
astraeus-st-johns-weather-api-1        Up (healthy)
astraeus-st-johns-weather-minio-1      Up (healthy)
astraeus-st-johns-weather-postgres-1   Up (healthy)
astraeus-st-johns-weather-titiler-1    Up (healthy)
astraeus-st-johns-weather-web-1        Up (healthy)
astraeus-st-johns-weather-worker-1     Up (healthy)
```

`api/tests` (`uv run pytest`, run from `api/`): **186 passed.**
`docker compose config --quiet`: passes.
`./scripts/smoke.sh`: **1 failure** — the `LiveStore` cache-invalidation
defect above (real finding, correctly not papered over).
