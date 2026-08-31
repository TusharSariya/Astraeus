## Why

The map owner wants the map to answer an astronomer's and night photographer's
question the cloud layers cannot: even under a clear sky, is the air steady and
transparent? The two first-order ingredients are upper-air jet flow (strong
200-300 hPa wind shear degrades astronomical seeing) and total column moisture
(precipitable water degrades transparency). No provider publishes a seeing
product for this region, and this experiment does not invent indices - but the
raw ingredients are already inside the exact GFS pgrb2.0p25 files the worker
downloads every cycle: UGRD/VGRD at 200 mb and 300 mb and PWAT were verified
present in a live f006 .idx (2026-08-30). Today the adapter deliberately skips
them, so the evidence is discarded at the byte-range step.

What is verified: the five (parameter, level) messages exist in the live GFS
inventory; the current selected span measures ~10.5 MB per lead against a
25 MB ceiling. What is not verified until live smoke: the merged byte span
with the five extra messages, and cfgrib's decode of the two-level isobaric
subset - both are pinned by tests in this change.

No derived seeing category is served. An arc-second seeing value would be
fabricated, and a banded category has no pinned authority to stand on (the
fog_state precedent leaned on WMO table 4678). v1 serves the retrieved values
and the disclosed u/v-to-speed/direction derivation already used for 10 m
wind; a seeing_state category is a named deferred follow-up.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **GFS ingestion** (`ingest/adapters/noaa_s3.py`): `GFS_IDX_SELECTORS` gains
  `UGRD`/`VGRD` at `200 mb` and `300 mb` plus
  `PWAT`/`entire atmosphere (considered as a single layer)`, all still gated
  by the instantaneous-forecast filter. The decode loop is keyed on
  (shortName, cfgrib filter) instead of shortName alone so the isobaric
  `u`/`v` messages open with `typeOfLevel=isobaricInhPa` and are split by
  level into flat, level-suffixed variables (`wind_u_200hPa`,
  `wind_v_200hPa`, `wind_u_300hPa`, `wind_v_300hPa`); `pwat` decodes to
  `precipitable_water` (kg m-2). The run now publishes two artifacts: the
  existing `surface` zarr (which gains `precipitable_water`) and a new
  `upper_air` zarr carrying the four wind components. All five manifest
  fields are optional: inventory absence degrades the run, never fabricates.
- **Point evidence** (`api/weather_api/store.py`): `precipitable_water` is
  served as stored; the four upper-wind components are sampled only as
  derivation inputs (never served raw, exactly like `wind_u_10m`) and the
  existing MetPy u/v derivation emits `wind_speed_200hPa`,
  `wind_direction_200hPa`, `wind_speed_300hPa`, `wind_direction_300hPa` with
  the same disclosed derivation strings. An absent `upper_air` artifact means
  the fields are absent - never zero, never carried over.
- **Registry truthfulness**: `VARIABLE_OVERRIDES["noaa-gfs"]` lists the
  variables the adapter actually stores so run metadata stops inheriting the
  nine-variable default that no longer matches.
- **Web**: three new evidence rows (200 hPa wind, 300 hPa wind, precipitable
  water) in the conditions panel and map text alternative, labelled with the
  interpretation as caption text ("strong upper flow degrades seeing"), never
  as a computed verdict.

## Capabilities

### Modified Capabilities

- `grib-decoding`: the GFS subset selection covers five additional
  (parameter, level) messages, still instantaneous-only and still under the
  measured per-lead byte ceiling; the isobaric decode path splits levels into
  flat suffixed variables.
- `point-evidence-sampling`: upper-air wind components are derivation inputs
  only; precipitable water is served as stored; absence is absence.
