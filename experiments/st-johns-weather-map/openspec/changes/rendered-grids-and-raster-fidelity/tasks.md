Owned: `ingest/adapters/eccc_geomet.py` (`map_image`/`_render`/`GeoMetImage`
only), `api/weather_api/wms.py`, `api/weather_api/app.py`,
`api/weather_api/models.py` (`Layer.group` literal only),
`api/weather_api/grids.py` (new), `api/tests/test_wms_proxy.py`,
`api/tests/test_rendered_grids.py` (new), `web/src/api.ts`,
`web/src/MapPanel.tsx`, `web/src/api.test.ts`, `web/src/MapPanel.test.tsx`,
`web/src/App.test.tsx`. Not touched: `registry/`, `ingest/adapters/awc.py`,
`ingest/meteorology.py`, `ingest/adapters/noaa_s3.py`, `docs/specv1`.

## 1. Raster fidelity (WP-R)

- [x] 1.1 `map_image` accepts `crs="EPSG:3857"`: bounds projected to
      spherical-mercator metres, bbox sent `minx,miny,maxx,maxy`; EPSG:4326
      keeps its latitude-first order; unsupported CRS refused client-side
      before any upstream call; provenance records the real CRS.
      Verify: `cd api && uv run pytest tests/test_wms_proxy.py`
- [x] 1.2 `/layers/{id}/raster` gains `crs` (default EPSG:4326, 422
      otherwise), passes it upstream, and answers with `X-Weather-Crs`.
      Verify: `cd api && uv run pytest tests/test_wms_proxy.py`
- [x] 1.3 The four GOES-East satellite proxies are requested/served as
      `image/jpeg` with `transparent=FALSE`; all other layers stay
      transparent PNG; content type on the response is the upstream's own.
      Verify: `cd api && uv run pytest tests/test_wms_proxy.py`
- [x] 1.4 Web requests every raster with `crs=EPSG:3857` and physical-pixel
      sizes (DPR capped at 2, `renderPixelSize`), keeps corner-pinning (now
      exact), keeps the "no frame here" and provenance-header behaviour.
      Verify: `cd web && npm test -- --run && npm run build`

## 2. Rendered cloud-strata grids (WP-S)

- [x] 2.1 `weather_api/grids.py`: nearest-neighbor rasterization of the
      stored grid at its native cells, exact in EPSG:4326 and EPSG:3857,
      NaN/outside transparent, declared colormap, pure-python PNG encoder,
      legend ramp. Non-uniform axes refused rather than guessed.
      Verify: `cd api && uv run pytest tests/test_rendered_grids.py`
- [x] 2.2 `/layers/{id}/raster` and `/legend` intercept the three
      `noaa-gfs-surface-cloud-*` ids: 200 with full `X-Weather-*`
      provenance (image basis `rendered_grid`, colormap, derivation
      strings, model run, CRS); 422 for a frame not stored within
      half-cadence tolerance; 404 for a missing artifact/variable; 502 for
      an unreadable artifact. `operational` false throughout.
      Verify: `cd api && uv run pytest tests/test_rendered_grids.py`
- [x] 2.3 `/layers` lists the three strata layers with group
      `rendered_grid`, `evidence_basis: published_artifact`, times exactly
      the ingested valid times, truthful `legend_available`, and the
      required semantics text; absence produces a notice or silence, never
      a guessed layer. `models.py` group literal extended.
      Verify: `cd api && uv run pytest tests/test_rendered_grids.py`
- [x] 2.4 Web: `rendered_grid` group in the drawer and coverage ribbon
      (shared order/labels), rendered-grid provenance accepted in
      `loadLayerRaster`, legend captioned as this experiment's own
      colormap, evidence-basis wording corrected for the rendered case.
      Verify: `cd web && npm test -- --run`

## 3. Verification

- [x] 3.1 `make test` fully green with the added tests.
- [x] 3.2 `docker compose up -d --build api && docker compose up -d --build
      --no-deps web`; curl: `/layers` lists the three strata layers with
      times; one strata raster answers 200 `image/png` with blocky
      nearest-neighbor cells and rendered-grid headers; a satellite raster
      answers `image/jpeg`; a forecast raster with `crs=EPSG:3857` answers
      200 `image/png`.
- [x] 3.3 `openspec validate rendered-grids-and-raster-fidelity --strict`
      and `openspec validate --all` pass; `make spec-validate` unchanged.
