# Open-Meteo deterministic atmosphere and Bright Sky MOSMIX evidence

Evidence date: 2026-09-05 UTC. Tracking: [issue 98](https://github.com/TusharSariya/Astraeus/issues/98).

This is an isolated experiment under `GOV-SPEC-001`, `GOV-SPEC-002`,
`GOV-SPEC-004`, `GOV-SPEC-005` and `GOV-SPEC-006`. The source contracts are
draft input. The adapters remain absent from the adapter loader, registry
entries remain `catalogued`, and `operational` remains false.

## Draft source contract

The Open-Meteo sources use `api.open-meteo.com/v1/forecast` with exact selectors
`jma_gsm`, `meteofrance_arpege_world025` and
`ukmo_global_deterministic_10km`. Requests name one model, UTC,
`elevation=nan`, `cell_selection=nearest`, SI wind and a finite hourly window.
Bright Sky uses exact `wmo_station_id=71801`; source 1228,
`ST.JOHNS NEUFUNDL.` and `observation_type=forecast` must appear once, and every
weather row must carry `source_id=1228`. Nearest-station fallback is forbidden.

Both routes return point series on EPSG:4326. Values retain returned
coordinates, valid time, original and normalized units, response and artifact
SHA-256, exact request, producer, intermediary and field disposition. Both
rolling responses expose no per-value producer cycle, so `run_time` is null and
run certainty is `unknown`; adjacent `meta.json` is not borrowed as lineage.

| Source | Retrieved and stored | Raw/deferred accounting |
|---|---|---|
| JMA GSM, ARPEGE World, UKMO Global | temperature, dew point, total/low/mid/high cloud, 10 m wind speed/direction, MSL pressure, preceding-hour precipitation; source-specific pressure temperature and wind profiles | RH is requested and confirmed `raw_retrieved`, but canonical publication is deferred because no saturation phase is declared. The [pressure-profile addendum](openmeteo-pressure-profiles.md) inventories all eight documented upstream profile families at every source-specific level and retains deferred fields and null masks without interpolation. |
| MOSMIX 71801 | temperature, dew point, total cloud, visibility, 10 m wind speed/direction and gust, MSL pressure, preceding-hour precipitation | RH, gust direction, hourly/six-hour probability, sunshine, solar, condition and icon are retained exactly in `raw_deferred_fields`; each status comes from the response as `raw_retrieved` or `raw_returned_null`. Unknown catalogue semantics remain `canonical_deferred`. |

Every selected Open-Meteo array is mandatory. The parser accepts the complete
unsuffixed shape currently returned for one explicit model or a complete shape
suffixed with that selector. Mixed shapes, any non-selected suffix (including
an unknown model such as `gfs_global`), an omitted
array or an omitted unit fail before artifact creation. The artifact carries
the registry's six documented transformations: regridding, elevation
downscaling (disabled here), cell selection, temporal interpolation,
intermediary field derivation and accumulation redistribution. Precipitation
carries `reporting_interval=preceding_hour` and
`reporting_interval_hours=1` for both providers.

Open-Meteo values are `reprocessed`. UKMO stays research-only under the recorded
CC BY-SA 4.0 restriction. Bright Sky remains DWD-produced and Bright
Sky-reprocessed. The local Open-Meteo ceiling is 40 weighted/minute, 400/hour,
2,000/day and 50,000/month, one request at a time. Each response is limited to
4 MiB and one point/window; there is no artificial daily byte cap or bulk loop.
Provider 429, malformed JSON, wrong units, misaligned arrays, missing selected
fields, wrong source identity and empty windows fail closed. The existing
stage/publish seam preserves the previous visible revision unless a run is
complete and passes QC. The physical experiment allocation remains bounded by
the existing finite disk and operation quotas.

## Evidence

The reproducible smoke command made exactly four anonymous requests for a
three-step window at `2026-09-05T14:49:22Z`. It retained small raw responses,
immutable Zarr artifacts, provenance, checksums, all field dispositions and a
numeric read through `weather_api.store.LiveStore` under
`docs/research/wayfinder/evidence/openmeteo-brightsky-20260905-corrective/`.
All three Open-Meteo artifacts were complete and QC-passed. MOSMIX returned a
null gust throughout this live window, so its manifest honestly records
`complete=false`, `qc_passed=true`; the artifact is retained as evidence but is
not publishable and no prior visible revision would advance.

| Source | Outcome | Artifact SHA-256 | Bytes |
|---|---|---|---:|
| `openmeteo-jma-gsm` | complete, QC pass; run unknown | `32d461050f1035d7ee42f748a1348d5aac6f58524b2d6a2e41f2f000f80c0500` | 14,131 |
| `openmeteo-arpege` | complete, QC pass; run unknown | `62551eeec6252b4b3cee7d4883caed82bcf428a24e0ce2cdb101445ac713ba97` | 14,132 |
| `openmeteo-ukmo-global` | complete, QC pass; run unknown | `060051a22d1523e7ef4df57b4ea2b4e99f6e2694a86dbf38e4ea05dfb7c7b922` | 14,101 |
| `brightsky-dwd-mosmix-71801` | incomplete (null gust), QC pass; exact source; run unknown | `4952ed3ad9b76c4de790ed4720c4418c13e2318fd50b7d6df60a0784d59f6e70` | 12,918 |

The fixture suite covers complete unsuffixed and selected-model-suffixed
shapes, omitted selected fields, mixed identities and known or unknown foreign
suffixes,
source/name/type/row mismatches, response-derived optional-field status,
intervals, transformations, malformed JSON, 429 and artifact integrity. The
point-handler test uses the real `LiveStore` download, checksum, Zarr-open and
sampling path with a test-local product mapping; it no longer constructs a
`Sample` manually. A zero-request retained-bundle replay repeats that full path
through four test-local HTTP product routes. It compares all 39 selected stored
fields with the actual response values and null masks and verifies each
artifact checksum. MOSMIX's selected gust remains null. The same replay stages
the incomplete/QC-passed MOSMIX revision and proves publication is refused
while the prior visible revision remains `prior-visible`.

A separate three-request pressure-profile proof under
`evidence/openmeteo-profiles-20260905/` retains the source-specific live
responses. A zero-request corrected reprocessing pass regenerates the profile
artifacts and replays every advertised level through the real `LiveStore` and
`/profile` endpoint. Raw fields retain their literal units and null masks;
pressure-coordinate metadata survives artifact reopen. JMA is explicitly
incomplete because its required canonical temperature and wind arrays are null
at four advertised levels, and the publication proof preserves the prior
visible revision. ARPEGE and UKMO are canonically complete. None is registered
or scheduled.

Verification commands:

```text
cd experiments/st-johns-weather-map
uv run --project api python scripts/openmeteo_brightsky_live_smoke.py ../../docs/research/wayfinder/evidence/openmeteo-brightsky-20260905-corrective
uv run --project api python scripts/openmeteo_brightsky_retained_http.py ../../docs/research/wayfinder/evidence/openmeteo-brightsky-20260905-corrective
uv run --project api pytest api/tests/test_adapter_openmeteo.py -q
PYTHONPATH=api:. uv run --project api python scripts/openmeteo_profile_evidence.py ../../docs/research/wayfinder/evidence/openmeteo-profiles-20260905 ../../docs/research/wayfinder/evidence/openmeteo-profiles-20260905
cd ../..
uv run --project tools/specs python tools/specs/specctl.py validate
```
