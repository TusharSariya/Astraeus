Owned: `api/pyproject.toml`, `ingest/adapters/goes_abi.py` (new),
`ingest/adapters/__init__.py` (`_MODULES` line only),
`registry/source_data.py` (`noaa-goes-east` cadence/freshness strings only),
`api/weather_api/satellite.py` (new), `api/weather_api/grids.py` (shared
helper exposure only), `api/weather_api/app.py` (satellite dispatch, layer
index, legend), `api/tests/test_adapter_goes_abi.py` (new),
`api/tests/test_satellite_layer.py` (new), `api/tests/test_api.py`,
`api/tests/test_layer_coverage.py`, `web/src/api.ts`, `web/src/App.tsx`,
`web/src/api.test.ts`, `web/src/App.test.tsx`, `web/src/MapPanel.test.tsx`,
`docs/geomet-layers.md`. Not touched: registry status fields,
`api/weather_api/wms.py`, `ingest/adapters/noaa_s3.py` and other adapters,
`docs/specv1`.

## 1. Dependencies (WP-1)

- [x] 1.1 `api/pyproject.toml` gains `netcdf4` and declares `pyproj` as a
      direct dependency (currently transitive via metpy).
      Verify: `cd api && uv sync && uv run python -c "import netCDF4, pyproj; print(pyproj.CRS(dict(proj='geos', h=35786023, sweep='x', lon_0=-75)))"`

## 2. Ingest adapter (WP-2)

- [x] 2.1 `ingest/adapters/goes_abi.py`: S3 listing discovery (newest-prefix
      fallback), paired ACMF+ACHAF download via `PoliteClient`, fixed-grid
      index window from the file's own projection attrs, parallax correction
      with `parallax_uncorrected` flagging, nearest-neighbour regrid to a
      regular lat/lon grid never finer than the local native footprint,
      DQF-bad preserved as an explicit invalid class, zipped-Zarr publish
      with scan times from `time_coverage_*` and disclosure attrs. An empty
      listing publishes nothing.
      Verify: `cd api && uv run pytest tests/test_adapter_goes_abi.py`
- [x] 2.2 `ingest/adapters/__init__.py` registers the module;
      `registry/source_data.py` `noaa-goes-east` cadence becomes parseable
      "10 minutes" (freshness checked likewise); status untouched.
      Verify: `cd api && uv run pytest tests/test_adapter_goes_abi.py && cd .. && cd api && uv run pytest`

## 3. API layer (WP-3)

- [x] 3.1 `api/weather_api/satellite.py`: layer spec, five-state colormap
      (clear transparent; three confidence whites; invalid distinct
      non-white), render via `grids.rasterize`/`encode_png`, rendered-grid
      provenance headers with source id `noaa-goes-east` and observed-scan
      time semantics, 422 beyond half-cadence, 404 missing artifact, 502
      unreadable, staleness -> unavailable listing, legend with
      checker-backed clear swatch and the required caption disclosures.
      Verify: `cd api && uv run pytest tests/test_satellite_layer.py`
- [x] 3.2 `api/weather_api/app.py` dispatches the new id at the rendered
      intercepts (raster + legend) and lists it in `/layers` beside the four
      untouched GeoMet proxies.
      Verify: `cd api && uv run pytest tests/test_satellite_layer.py tests/test_wms_proxy.py tests/test_api.py tests/test_layer_coverage.py tests/test_rendered_grids.py`

## 4. Web (WP-4)

- [x] 4.1 `web/src/api.ts` evidence-basis wording covers a satellite-group
      rendered layer ("drawn by this experiment from stored NOAA cloud-mask
      values"); `App.tsx` lists five satellite layers; unavailable state
      pinned; the four provider-composite expectations unchanged.
      Verify: `cd web && npm test -- --run && npm run build`

## 5. Verification (WP-5)

- [x] 5.1 `docs/geomet-layers.md` gains a note pointing at the cloud-mask
      layer; `make test` fully green.
      Verify: `make test`
- [x] 5.2 `docker compose up -d --build worker api web`; curl `/layers`
      (five satellite layers; cloud mask with observed-only times), one
      cloud-mask raster 200 `image/png` with `X-Weather-Image-Basis:
      rendered_grid` and `X-Weather-Source-Id: noaa-goes-east`, legend 200;
      live smoke against the real bucket proves real-granule decode
      (scale/offset/_FillValue of `Cloud_Probabilities`).
      Verify: `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke`
- [x] 5.3 `openspec validate goes19-cloud-mask-overlay --strict` and
      `openspec validate --all` pass.
      Verify: `openspec validate goes19-cloud-mask-overlay --strict && openspec validate --all`
