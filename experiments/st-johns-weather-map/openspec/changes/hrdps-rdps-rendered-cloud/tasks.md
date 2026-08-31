Owned: `ingest/grib.py`, `ingest/adapters/eccc_datamart.py`,
`api/weather_api/grids.py`, `api/weather_api/app.py` (legend-semantics header
only), `api/pyproject.toml`, `api/uv.lock`,
`api/tests/test_ingest_grib.py`, `api/tests/test_adapter_eccc_datamart.py`,
`api/tests/test_rendered_grids.py`,
`api/tests/test_rendered_cloud_curvilinear.py` (new).
Not touched: `web/src` code (fully generic over `/layers`), `registry/`,
`compose.yaml`, `docs/specv1`.

## 1. Ingest: declare total cloud from its WMO keys

- [x] 1.1 `open_grib(read_keys=...)`, `declare_wmo_total_cloud` (0/6/1 +
      first surface 1 only; records `original_units` and `units_basis`;
      never touches declared units), `normalize_units` preserves an
      existing `original_units`.
      Verify: `cd api && uv run pytest tests/test_ingest_grib.py -q`
- [x] 1.2 `total_cloud` in `HRDPS_VARS` (`TCDC`/`Sfc`) and `RDPS_VARS`
      (`TotalCloudCover`/`Sfc`), not GDPS; fetch requests the identity keys
      for that field and refuses it (`undeclared_units`) when the
      declaration does not apply; withholding comment records the owner
      decision.
      Verify: `cd api && uv run pytest tests/test_adapter_eccc_datamart.py -q`

## 2. API: curvilinear renderer and the two layers

- [x] 2.1 `sample_field_curvilinear` (nearest cell centre within half a cell
      diagonal; scipy cKDTree; refuses unmeasurable grids), `rasterize`
      dispatch on coordinate ndim, per-method render semantics /
      derivation / version with `X-Weather-Sample-Method`, `render_grid`
      dim ordering for rotated frames; scipy pinned as a direct dependency.
      Verify: `cd api && uv run pytest tests/test_rendered_cloud_curvilinear.py -q`
- [x] 2.2 `RenderedGridSpec` entries for `eccc-hrdps-surface-total-cloud`
      and `eccc-rdps-surface-total-cloud`; `grid_semantics` reads product
      and native resolution from artifact provenance.
      Verify: `cd api && uv run pytest tests/test_rendered_cloud_curvilinear.py tests/test_rendered_grids.py -q`
- [x] 2.3 Cloud legend composited over mid grey, backdrop disclosed in the
      legend-semantics header; mapping and colormap doc unchanged.
      Verify: `cd api && uv run pytest tests/test_rendered_grids.py -q`

## 3. Suites and validation

- [x] 3.1 Full API suite and web suite (no web code change; the interface
      is generic over the layer index).
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build`
      Status 2026-08-31: api 531 passed / 7 skipped; web 162 passed; build clean.
- [x] 3.2 `openspec validate --all` stays green with the new change.
      Verify: `openspec validate --all`

## 4. Live verification

- [ ] 4.1 Rebuild the Docker stack, let the worker complete an HRDPS and an
      RDPS ingest cycle under the new maps, then confirm: `/layers` offers
      both total-cloud rendered layers; the raster answers with
      `X-Weather-Sample-Method: curvilinear_nearest_cell` and white-alpha
      pixels; the legend is the grey-backed ramp; `/point` serves
      `total_cloud` from `eccc-hrdps`/`eccc-rdps`; the browser shows the
      layers toggleable in the rendered-grids group with the interpolation
      toggle applying.
      Verify: `docker compose up -d --build api web worker` then the checks above
      Status 2026-08-31: stack rebuilt; the first live cycle exposed that
      ecCodes returns `typeOfFirstFixedSurface` as the abbreviation 'sfc',
      not the coded 1 - the declaration correctly refused every file
      (undeclared_units) until the check accepted the abbreviation; fixed,
      pinned in tests, worker rebuilt. Second cycle: eccc-hrdps and
      eccc-rdps both succeeded. Verified live: both layers in `/layers`
      (group rendered_grid, 23 frames, provenance-driven semantics); raster
      200 with `X-Weather-Sample-Method: curvilinear_nearest_cell`,
      `rendered-grid-nearest-cell-v1`, every pixel white-or-transparent;
      legend 200, grey-backed ramp (196 grey at 0 to opaque white at 100),
      `renderer_colormap`; `/point` serving total_cloud from eccc-hrdps
      (96.7) and eccc-rdps (98.0) beside METAR and GFS. The in-browser
      toggle/interpolation pass remains for the owner's own look.
