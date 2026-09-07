# Isolated CAMS AOD finite delivery, 2026-09-07

Classification: experiment. This extends the existing
`experimental-openmeteo-composition` experiment under the owner's API-first
execution plan. It does not accept source contracts, register routes, schedule
retrieval, activate the source, or assert V1 conformance.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

The selected gap was `openmeteo-cams-aod`: the named `cams_global` adapter
already acquired and validated composition artifacts, but lacked a source-local
finite query/cache seam. The query now reuses that adapter's discovery,
normalization, zipped-Zarr writer and completeness/QC gate. Configurable adapter
coordinates preserve the previous St John's defaults. No alternative model,
particulate/AQHI substitution, or pressure-profile assumption was added.

`OpenMeteoCamsAodQueryService.query(latitude, longitude, start, end=None,
refresh=False)` returns an immutable tuple of actual intermediary timestamps
and dimensionless total AOD at 550 nm. It accepts 1–24 exact hourly selections,
retains absent hours and returned nulls, and adds no interpolation. The
Open-Meteo hourly product itself is reprocessed from CAMS; neither its cadence
nor its returned 0.1-degree cells are represented as the producer's native
three-hour / 0.4-degree grid. The latest metadata initialization remains context;
per-value run identity stays unknown.

`point_fields(latitude, longitude, selected, refresh=False)` is the proposed
root-owned delivery hook. Both field and key are
`aerosol_optical_depth_550nm`, matching existing immutable-artifact readback.
It retains producer, intermediary, sampled coordinates, units, transformations,
response digest and unknown run identity. The finite entry provides Series
input; public contract identity and integration remain root-owned.

Acquisition permits two concurrent distinct selections, coalesces identical
misses, makes two anonymous requests with one attempt each through `PoliteClient`,
and caps each JSON response at 16 KiB with 1 KiB transport chunks. Canonical
shape admits at most 24 values before artifact creation. Temporary response and
artifact files are removed after validation. Cache retention is capped at 32
entries and 256 KiB of conservatively accounted normalized data. Five-minute
expiry is fixed when acquisition completes; reads never extend it. Explicit
refresh replaces only after success. Failure preserves any old entry only until
its original deadline; expiration during validation refuses admission.

Official documentation checked on 2026-09-07:
[Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api)
documents anonymous latitude/longitude requests, the explicit `cams_global`
domain, AOD and hourly selection. Upstream CAMS's three-hour cadence is distinct
from intermediary hourly delivery. This inspection did not capture a live
provider response or establish current source coverage, commercial eligibility,
production admission, or a new science contract.

Verification maps GOV-SPEC-004/006 to
`api/tests/test_openmeteo_cams_aod_query.py`: exact named transport, real
`PoliteClient` with mock HTTP, adapter/Zarr readback, identity/units, native
gaps/nulls, invalid coordinates/times, field inventory and QC refusal, HTTP
429/503 failure, bounded acquisition, concurrent coalescing, successful/failed
refresh, fixed expiry, eviction, and expiry during validation. Existing
`test_adapter_openmeteo.py` verifies regression of the reused source adapter.

Executed offline Linux proof (actual image, no provider network):

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-openmeteo/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_openmeteo_cams_aod_query.py \
  api/tests/test_adapter_openmeteo.py -q -p no:cacheprovider
```

Result: 61 tests passed. Source-specific tests number 27; existing adapter tests
number 34. This is fixture-backed software evidence, with zero provider calls.
`uv run --project tools/specs python tools/specs/specctl.py validate` passed with
0 errors / 0 warnings; `git diff --check` passed.
