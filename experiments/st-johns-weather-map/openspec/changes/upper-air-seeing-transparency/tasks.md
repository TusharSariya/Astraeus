Owned: `ingest/adapters/noaa_s3.py`, `ingest/grib.py`
(`normalize_units` unit-spelling alias only), `ingest/registry.py`
(`VARIABLE_OVERRIDES` entry only), `api/weather_api/store.py`
(`FIELD_BY_VARIABLE`, `DERIVATION_INPUTS`, wind-derivation loop in
`live_point_fields` only), `api/tests/test_adapter_noaa_s3.py`,
`api/tests/test_api.py` (additions only), `web/src/api.ts`,
`web/src/App.tsx`, `web/src/api.test.ts`, `web/src/App.test.tsx`.
Not touched: other adapters, `api/weather_api/satellite.py`,
`api/weather_api/wms.py`, `api/weather_api/grids.py`, registry statuses,
`sample_profile`, `docs/specv1`.

## 1. Ingestion (WP-C1)

- [x] 1.1 `GFS_IDX_SELECTORS` gains the four isobaric wind pairs and PWAT;
      `select_gfs_ranges` returns selected (param, level) pairs; decode loop
      keyed on (shortName, cfgrib filter) with the isobaric split into
      `wind_u_200hPa`/`wind_v_200hPa`/`wind_u_300hPa`/`wind_v_300hPa` and
      `pwat` -> `precipitable_water`; `GFS_VAR_MAP`/`GFS_MANIFEST` extended
      (all new fields optional); run publishes `surface` (+precipitable
      water) and `upper_air` artifacts.
      Verify: `cd api && uv run pytest tests/test_adapter_noaa_s3.py`
- [x] 1.2 `VARIABLE_OVERRIDES["noaa-gfs"]` lists the stored variables.
      Verify: `cd api && uv run pytest tests/test_worker_runtime.py -q`

## 2. Point evidence (WP-C3)

- [x] 2.1 `FIELD_BY_VARIABLE` serves `precipitable_water`;
      `DERIVATION_INPUTS` gains the four upper wind components; the wind
      derivation loop emits level-suffixed speed/direction for 200 and
      300 hPa with disclosed derivation strings; absent artifact -> absent
      fields (test).
      Verify: `cd api && uv run pytest tests/test_api.py`

## 3. Web (WP-C4)

- [x] 3.1 Evidence rows for `wind_speed_200hPa`, `wind_speed_300hPa`,
      `precipitable_water` in the conditions panel and text alternative,
      captioned as interpretation, never verdicts.
      Verify: `cd web && npm test -- --run && npm run build`

## 4. Verification (WP-C5)

- [x] 4.1 Live smoke: real f000 `.idx` carries all five new (param, level)
      pairs and the merged selected span is under `MAX_BYTES_PER_LEAD`.
      Verify: `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q -k gfs`
- [x] 4.2 `make test` fully green; `openspec validate
      upper-air-seeing-transparency --strict` and `openspec validate --all`
      pass.
