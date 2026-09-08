# Open-Meteo #99 closure checkpoint, September 8

Non-normative verification against integration head
`d4c3a47400665bfb60ae1fb3255a3c954c3a956f`. No source behavior, source admission,
contracts or operational status changed.

## Actual GFS Wave API readback

At `2026-09-08T00:21:22Z`, the existing local Uvicorn API served two actual HTTP
GETs to `/api/experiments/weather/v0/point` with latitude `47.5615`, longitude
`-52.7126`, product `GFS Wave`, and valid time `2026-09-08T00:00:00Z`.
Both returned HTTP 200 and live evidence-only, operational-false responses. The
second read reused the same source-local cache entry: exactly one anonymous
public provider request supplied both reads.

The canonical provider request used model `ncep_gfswave016`, `cell_selection=sea`,
GMT, identical start/end hours, and all nine existing native fields. Its 676-byte
body was below the existing 2 KiB ceiling; final-byte completion was
`2026-09-08T00:21:22.125536Z`. SHA-256:
`902b0756b3819f58bbbc247a8e47bb1f6e9dbf72c81d87c57fae727c845db436`.
The returned sea cell was `47.666668,-52.666664`; producer run remained null,
source remained reprocessed and non-primary. The cache TTL was 300 seconds.

All nine fields were retrieved; none was missing in this response. Height,
period, direction were respectively `1.74 m / 8.35 s / 94 degrees`; swell was
`1.52 m / 8.1 s / 86 degrees`; wind-wave fields were each zero in their respective
units. These zero values were preserved. Direction retains the source's
wave-from convention; no direction or period calculation was introduced.
The [compact receipt](openmeteo-gfs-wave-http-20260908.json) records all canonical
keys, original and normalized units, values, quality flags and request identity.
No raw provider body or immutable source artifact was retained.

The temporary proof script `/private/tmp/gfs-wave99-proof.py` starts the actual
app in a local Uvicorn thread, installs the existing real HTTP query service,
counts provider request hooks, checks both HTTP bodies and inspects its existing
cache receipt. It ran with:

```sh
PYTHONPATH=/private/tmp/astraeus-openmeteo99/experiments/st-johns-weather-map/api:/private/tmp/astraeus-openmeteo99/experiments/st-johns-weather-map /private/tmp/astraeus-api-first-delivery/experiments/st-johns-weather-map/api/.venv/bin/python /private/tmp/gfs-wave99-proof.py
```

The server was stopped and HTTP client closed by the script. The temporary
script is verification evidence, not a maintained source worker.

## Exact remaining issue criteria

[Issue #99](https://github.com/TusharSariya/Astraeus/issues/99) already records
GFS Wave completed by PR #232. This current readback reconfirms that slice;
it does not complete the other named products.

- `openmeteo-marine-currents-sealevel` remains catalogued with a `link_only`
  path. Its registry explicitly says no adapter until the producer question is
  answered: Open-Meteo's Meteo-France label versus Mercator/Copernicus provenance.
  Its four declared fields are SST, current velocity, current direction and
  sea-level height MSL. None is retrieved by this GFS Wave proof. Closing that
  slice requires authoritative producer/licence resolution and an accepted
  source-local field/time/unit/direction/mask contract before implementation.
- `openmeteo-glofas` remains catalogued with a `link_only` path and explicitly
  no adapter until an activity profile requires discharge. Its single declared
  field, river discharge, is not retrieved here. Closure needs owner resolution
  of that restriction and an accepted daily routing-cell/missingness contract;
  the small Waterford catchment must not be represented as a resolved gauge.

No owning implementation OpenSpec change for these two held paths exists at the
reviewed head. No API/registry mount or field widening is proposed. Their old
successful endpoint research is not current implementation proof.

[Map #70](https://github.com/TusharSariya/Astraeus/issues/70)'s current owner
correction supersedes #99's older immutable-artifact completion wording:
selected timestamp, bounded upstream cache miss, native normalization and API
readback are the delivery path; mandatory immutable ArtifactStore publication,
background full runs and full-horizon prefetch are no longer completion gates.
The existing GFS Wave OpenSpec tasks already mark the completed slice correctly
and were not rewritten to imply the two held sources are implemented.

Spec-Impact: none; current-source evidence and explicit unresolved criteria only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

Verification: network-disabled Linux `python -m pytest api/tests/test_gfs_wave_delivery.py api/tests/test_openmeteo_gfs_wave_query.py -o addopts= -q -p no:cacheprovider --tb=short` on `astraeus-lightning-proof:c88ff83`, with this experiment mounted read-only at `/work`: 16 passed in 3.54s. `uv run --project tools/specs python tools/specs/specctl.py validate`: 0 errors, 0 warnings. `git diff --check`: passed.
