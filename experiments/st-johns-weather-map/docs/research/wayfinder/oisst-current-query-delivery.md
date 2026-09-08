# Current NOAA OISST query delivery, September 8, 2026

Experiment under #153 and existing `current-sst-analysis-inputs` plus
`timestamp-demand-query-cache` contracts. Spec-Refs: GOV-SPEC-001,
GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006. No source admission or scheduler change.

The source-local `weather_api.oisst_query.OISSTQueryService` supplies
`point_fields(latitude, longitude, selected, refresh=False)`. Retain one service
instance. Suggested root-owned selector: `OISST SST`, source `noaa-oisst-v2-1`.
It supplies `sea_surface_temperature` and
`sea_surface_temperature_uncertainty`, native Celsius normalized to degC.
Daily noon UTC analysis is required exactly, current day or previous four days
only; future/archival/other-hour selections fail before transport. Discovery
preserves final/preliminary filename identity. No inferred run time, fog,
sea-ice science or interval carry-forward. `ice` and `anom` are explicitly
excluded by this ticket's owning design and remain outside the query output.

The existing capture adapter reads one NCEI daily file with a 32 MiB ceiling,
checks required fields/units/file identity/native time, and crops native cells
to the fixed 45–50.5 N, -58–-46 E box. Missing ocean/land cells stay null.
Every point retains artifact revision, raw preliminary/final filename in QC
flags, actual sampled native coordinate and native 0.25-degree resolution.
Quality remains the existing adapter QC, not a new confidence judgment.

One crop cache (512 KiB encoded JSON; at most 2,048 cells), one in-flight
acquisition and identical-miss coalescing. Fixed 300-second expiry uses the
final-download receipt, never subsequent QC completion. Failed refresh can
retain only an unexpired old crop. A 90-second Linux process bounds transport
and decode with 2 GiB address space and 64 MiB per-file limit; all scratch
lives under parent-owned workspace cleanup. `operational=false`, retrieved
published cells, `available-not-stored`, no native Series.

## Live proof and remaining closure work

[NOAA's primary documentation](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)
confirms daily 0.25-degree OISST v2.1 and a separate error field. At capture,
the anonymous September monthly listing's latest was
`oisst-avhrr-v02r01.20260906_preliminary.nc` (September 6 12:00 UTC), not a
September 8 nowcast. One listing request plus one 1,554,250-byte daily file
request was made. Actual bounded Linux leaf returned SST approximately
14.53 degC and error 0.29 degC at requested 47.5 N, -52.0 E; repeated point
and crop reads made zero additional provider requests.

Compact [receipt](oisst-current-query-receipt-20260908.json) records exact
URL, bytes, digest, actual completion, native time, values, sampled coordinate
and immutable artifact revision. Raw NetCDF/listing and source-helper point
JSON remain outside Git in `/private/tmp/astraeus-oisst-live-proof/` for root's
HTTP readback replay. No credentials or paid endpoints were used.

#153 is not closed by this helper alone: root must register the experimental
point descriptor and demonstrate actual Astraeus HTTP readback matching the
captured source/units/time/values/revision, then synchronize OpenSpec tasks.
No new scientific field or OISST ice admission is implied.

## Verification

```sh
docker run --rm --network none --memory 3g \
  -v /private/tmp/astraeus-api-first-oisst-delivery/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_oisst_query.py api/tests/test_adapter_sst_analysis.py -q -p no:cacheprovider
uv run --project tools/specs python tools/specs/specctl.py validate
```

Tests map native time/units/required-error refusal, final/preliminary identity,
missingness, exact-time and geographic preflight, cache reuse, coalescing,
failed-refresh expiry, delayed QC receipt and the real isolated Linux worker.
