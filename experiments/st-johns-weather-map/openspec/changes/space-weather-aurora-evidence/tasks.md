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

- [x] 1.1 `swpc.py`: `noaa-swpc-kp` (artifacts `kp_observed` + `kp_forecast`
      with flag-coded `kp_status`), `noaa-swpc-rtsw` (`solar_wind`, time axis
      only), `noaa-swpc-ovation` (`aurora_grid` cropped to the context box,
      refused without its own timestamps); `_MODULES` extended.
      Verify: `cd api && uv run pytest tests/test_adapter_swpc.py`
      (2026-08-31: 10 passed, 1 live-smoke skipped by default)
- [x] 1.2 Registry: three `space_weather` sources with parseable cadences
      (10 minutes / 1 minute / 3 hours) and freshness proses;
      `VARIABLE_OVERRIDES` entries; category outside FORECAST_CATEGORIES.
      Verify: `make test-registry && cd api && uv run pytest tests/test_adapter_swpc.py -k registry`
      (2026-08-31: 6 + 1 passed)

## 2. API (WP-B3, WP-B4, WP-B5)

- [x] 2.1 `LiveStore.read_series` + `GET /space-weather`: latest Bz with
      age, Kp observed series, Kp forecast series with per-value status,
      per-feed freshness; fixture mode fails closed.
      Verify: `cd api && uv run pytest tests/test_space_weather.py`
      (2026-08-31: 12 passed)
- [x] 2.2 `/point` serves `aurora_probability` as a sampled gridded value;
      the Kp/Bz series never appear in `/point`.
      Verify: `cd api && uv run pytest tests/test_space_weather.py tests/test_live_store.py`
      (2026-08-31: 12 + 25 passed)
- [x] 2.3 Aurora layer `noaa-swpc-aurora-oval`: rendered-grid raster +
      legend with the disclosed transparency threshold and the Kp 4-5
      guidance caption; staleness fail-closed; 422/404/502 discipline.
      Verify: `cd api && uv run pytest tests/test_aurora_layer.py tests/test_satellite_layer.py tests/test_rendered_grids.py`
      (2026-08-31: 11 + 11 + 17 passed)

## 3. Web (WP-B6)

- [x] 3.1 Kp and Bz metric cards from `/space-weather` (fail-closed text on
      error), aurora layer toggle in the rendered-grid group,
      `aurora_probability` evidence row.
      Verify: `cd web && npm test -- --run && npm run build`
      (2026-08-31: 162 passed across 5 files; build clean)

## 4. Verification (WP-B7)

- [x] 4.1 Live smoke: all four SWPC URLs answer with the pinned shapes
      (`time_tag`, `bz_gsm`, `Observation Time`/`Forecast Time`, coordinate
      ranges).
      Verify: `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q -k swpc`
      (2026-08-31: 1 passed against the real feeds)
- [x] 4.2 `make test` fully green; `openspec validate
      space-weather-aurora-evidence --strict` and `openspec validate --all`;
      Docker: worker ingests real SWPC feeds, `/space-weather` answers,
      aurora raster + legend answer with provenance headers.
      (2026-08-31: make test green - api 515 passed/7 skipped, web 162,
      registry 6, sql invariants, specctl 0 errors; openspec --strict and
      --all valid, 22 items. Docker stack rebuilt: /space-weather live with
      60 observed Kp records, forecast statuses observed/estimated/predicted,
      Bz -4.43 nT fresh with feed-declared spacecraft "ACE, IMAP, SOLAR1";
      aurora layer listed in rendered_grid with the stored Forecast Time;
      raster 200 with X-Weather-Image-Basis: rendered_grid and
      X-Weather-Source-Id: noaa-swpc-ovation; legend 200 renderer_colormap;
      /point serves aurora_probability from cell 48.0,-53.0 and no Kp/Bz
      field appears in /point.)
