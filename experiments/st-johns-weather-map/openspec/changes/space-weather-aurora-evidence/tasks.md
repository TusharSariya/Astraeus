Owned: `ingest/adapters/swpc.py` (new), `ingest/adapters/__init__.py`
(`_MODULES` line), `ingest/registry.py` (`VARIABLE_OVERRIDES` entries only),
`registry/source_data.py` (three entries), `registry/catalogue_coverage.json`
(one mapping), `api/weather_api/store.py` (`FIELD_BY_VARIABLE` entry,
`read_series` only), `api/weather_api/aurora.py` (new),
`api/weather_api/app.py` (`/space-weather` route + aurora layer dispatch),
`api/weather_api/models.py` (space-weather models), `api/tests/test_adapter_swpc.py`
(new), `api/tests/test_space_weather.py` (new), `api/tests/test_aurora_layer.py`
(new), `api/tests/test_api.py` (count bump only), `web/src/api.ts`,
`web/src/types.ts`, `web/src/App.tsx`, `web/src/fixtures.ts`,
`web/src/App.test.tsx`, `web/src/api.test.ts`.
Not touched: `ingest/adapters/noaa_s3.py`, `api/weather_api/satellite.py`
internals, `api/weather_api/wms.py`, existing registry statuses,
`docs/specv1`.

## 1. Ingestion (WP-B1, WP-B2)

- [ ] 1.1 `swpc.py`: `noaa-swpc-kp` (artifacts `kp_observed` + `kp_forecast`
      with flag-coded `kp_status`), `noaa-swpc-rtsw` (`solar_wind`, time axis
      only), `noaa-swpc-ovation` (`aurora_grid` cropped to the context box,
      refused without its own timestamps); `_MODULES` extended.
      Verify: `cd api && uv run pytest tests/test_adapter_swpc.py`
- [ ] 1.2 Registry: three `space_weather` sources with parseable cadences
      (10 minutes / 1 minute / 3 hours) and freshness proses;
      `VARIABLE_OVERRIDES` entries; category outside FORECAST_CATEGORIES.
      Verify: `make test-registry && cd api && uv run pytest tests/test_adapter_swpc.py -k registry`

## 2. API (WP-B3, WP-B4, WP-B5)

- [ ] 2.1 `LiveStore.read_series` + `GET /space-weather`: latest Bz with
      age, Kp observed series, Kp forecast series with per-value status,
      per-feed freshness; fixture mode fails closed.
      Verify: `cd api && uv run pytest tests/test_space_weather.py`
- [ ] 2.2 `/point` serves `aurora_probability` as a sampled gridded value;
      the Kp/Bz series never appear in `/point`.
      Verify: `cd api && uv run pytest tests/test_space_weather.py tests/test_live_store.py`
- [ ] 2.3 Aurora layer `noaa-swpc-aurora-oval`: rendered-grid raster +
      legend with the disclosed transparency threshold and the Kp 4-5
      guidance caption; staleness fail-closed; 422/404/502 discipline.
      Verify: `cd api && uv run pytest tests/test_aurora_layer.py tests/test_satellite_layer.py tests/test_rendered_grids.py`

## 3. Web (WP-B6)

- [ ] 3.1 Kp and Bz metric cards from `/space-weather` (fail-closed text on
      error), aurora layer toggle in the rendered-grid group,
      `aurora_probability` evidence row.
      Verify: `cd web && npm test -- --run && npm run build`

## 4. Verification (WP-B7)

- [ ] 4.1 Live smoke: all four SWPC URLs answer with the pinned shapes
      (`time_tag`, `bz_gsm`, `Observation Time`/`Forecast Time`, coordinate
      ranges).
      Verify: `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q -k swpc`
- [ ] 4.2 `make test` fully green; `openspec validate
      space-weather-aurora-evidence --strict` and `openspec validate --all`;
      Docker: worker ingests real SWPC feeds, `/space-weather` answers,
      aurora raster + legend answer with provenance headers.
