# Open-Meteo deterministic atmosphere and Bright Sky MOSMIX evidence

Evidence date: 2026-09-05 UTC. Tracking: [Implement Open-Meteo deterministic
atmosphere and Bright Sky MOSMIX](https://github.com/TusharSariya/Astraeus/issues/98).

This is an isolated experiment under `GOV-SPEC-001`, `GOV-SPEC-002`,
`GOV-SPEC-004`, `GOV-SPEC-005` and `GOV-SPEC-006`. The source-specific contract
below is draft input. The adapters are intentionally absent from the adapter
loader, registry entries remain `catalogued`, and `operational` remains false.

## Draft source contract

The three Open-Meteo sources use `api.open-meteo.com/v1/forecast` with the exact
selectors `jma_gsm`, `meteofrance_arpege_world025` and
`ukmo_global_deterministic_10km`. Requests name one model, UTC, `elevation=nan`,
`cell_selection=nearest`, SI wind and a finite hourly window. Producer and
intermediary remain separate. Bright Sky uses `/weather` with the exact
`wmo_station_id=71801`; source 1228, `ST.JOHNS NEUFUNDL.`, must appear in the
response. A coordinate or nearest-station fallback is forbidden.

Both routes return point series on EPSG:4326. Values retain returned coordinates,
valid time, original units, normalized units, response SHA-256, exact request,
producer, intermediary and field disposition. Open-Meteo's rolling response and
Bright Sky's response expose no per-value producer cycle, so `run_time` is null
and run certainty is `unknown`. Adjacent `meta.json` is not borrowed as lineage.

| Source | Retrieved and stored | Missing, unsupported or deferred |
|---|---|---|
| JMA GSM, ARPEGE World, UKMO Global | temperature, dew point, total/low/mid/high cloud, 10 m wind speed/direction, MSL pressure, hourly precipitation | RH deferred because no saturation phase is declared; profiles are deferred because this bounded contract has no accepted profile mapping |
| MOSMIX 71801 | temperature, dew point, total cloud, visibility, 10 m wind speed/direction, MSL pressure, hourly precipitation | RH missing/null and phase undeclared; gust, probability, sunshine and solar unsupported by the field catalogue; Bright Sky `condition` deferred because it is intermediary-derived |

Open-Meteo values are `reprocessed`. UKMO stays research-only under the recorded
CC BY-SA 4.0 restriction; this evidence does not approve redistribution. Bright
Sky remains DWD-produced and Bright Sky-reprocessed under DWD terms. The local
Open-Meteo ceiling is 40 weighted/minute, 400/hour, 2,000/day and 50,000/month,
one request at a time. Each response is limited to 4 MiB and one point/window;
there is no bulk loop. Provider 429, malformed JSON, wrong units, misaligned
arrays, wrong station, empty window and all-missing selected fields fail closed.

Publication uses the existing deterministic zipped-Zarr writer and stage/publish
store seam. An incomplete or failed-QC run cannot publish, so the prior visible
revision remains. Rollback is removal of this unregistered module and its tests;
no scheduler or deployed database/object store was changed.

## Evidence

A bounded live retrieval at `2026-09-05T14:28:27Z` made four anonymous requests,
one per source, for 24 hours. All four produced complete, QC-passed immutable
artifacts. Response/artifact evidence was:

| Source | Returned identity | Response SHA-256 | Zarr bytes |
|---|---|---|---:|
| `openmeteo-jma-gsm` | cell 47.5, -52.5; run unknown | `a30dbe005723696fb19ab7b32998418c6cafebcc2cda8a4c64462d36df1a7769` | 14,727 |
| `openmeteo-arpege` | cell 47.5, -52.75; run unknown | `952fa60659ed3cb9e590f117450f57cedac181cb66db947e85ea992175742fda` | 14,641 |
| `openmeteo-ukmo-global` | cell 47.53125, -52.734375; run unknown | `2ec12663b7cad3c76c3ff723790dc6f690ba41373a45e3c4c3e64524f3c67d0a` | 14,545 |
| `brightsky-dwd-mosmix-71801` | exact WMO 71801, Bright Sky source 1228; run unknown | `aefd9a467b5b98c8e348d80cec2e1e0448e8bd8bdddaab1b28fe8102602e0db0` | 12,441 |

The test suite covers representative fixtures, model-suffixed arrays, field
dispositions, units, timestamps, unknown rolling run identity, malformed JSON,
partial arrays, 429, exact-station enforcement and deterministic artifact
round-trip. It also opens the immutable artifact and reads its value through the
real Astraeus `/api/experiments/weather/v0/point` handler using a test-only
product mapping; the response stays `operational: false` and preserves source
and `reprocessed` provenance. No production product mapping is added.

Verification commands:

```text
uv run --project experiments/st-johns-weather-map/api pytest experiments/st-johns-weather-map/api/tests/test_adapter_openmeteo.py -q
uv run --project tools/specs python tools/specs/specctl.py validate
```
