Owned: `web/src/MapPanel.tsx`, `web/src/FlowBlendLayer.ts` (new),
`web/src/TimelineDock.tsx`, `web/src/styles.css`, `web/src/api.ts`,
`web/src/MapPanel.test.tsx`, `web/src/FlowBlendLayer.test.ts` (new),
`web/src/App.test.tsx` (one title assertion),
`api/weather_api/grids.py`, `api/weather_api/app.py`,
`api/weather_api/store.py` (sample_point skip), `api/pyproject.toml`,
`api/uv.lock`, `ingest/derive/` (new), `worker/runtime.py`,
`worker/Dockerfile`, `api/tests/test_cloud_motion.py` (new),
`api/tests/test_flow_endpoint.py` (new), `openspec/config.yaml`
(carve-out sentence).
Not touched: registry, compose service topology, docs/specv1.

## 1. Phase A - layout stability

- [x] 1.1 Status banner overlays the app shell (absolute, z-30; sticky
      again below 900px); dock snap note keeps a reserved line.
      Verify: `cd web && npm test -- --run src/App.test.tsx`

## 2. Phase A - client fetch/paint pipeline

- [x] 2.1 `refreshing` raster state holds the previous frame's slots at
      their own timestamps; text alternative discloses it; failures still
      clear to `unavailable`.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`
- [x] 2.2 In-flight dedupe per (layer, frame, extent); viewport-scoped
      abort (frame changes never abort); LRU 4 -> 40; MapLibre
      `updateImage`/`setPaintProperty` in place, teardown only on
      structural change.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`
      Note: the planned 120 ms scrub debounce was dropped as redundant -
      dedupe + prefetch + no-abort achieve the same bound without delaying
      cached paints.
- [x] 2.3 Idle prefetch of the full frame axis (and flow pairs when
      interpolation is on) for locally rendered layers only; proxied
      layers never prefetched.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`
- [x] 2.4 Rendered/satellite/aurora requests capped at 1024 px long edge
      with `raster-resampling: nearest`.
      Verify: `cd web && npm test -- --run && npm run build`

## 3. Phase A - server render cost

- [x] 3.1 Curvilinear pixel-to-cell lookup memoised per (revision +
      dataset identity, bounds, size, crs); finished-PNG LRU keyed by
      everything determining the bytes; `store.current()` memoised 5 s per
      weakly-referenced store instance; one-shot numpy PNG filter stream at
      zlib level 3.
      Verify: `cd api && uv run pytest tests/test_rendered_grids.py tests/test_rendered_cloud_curvilinear.py -q`

## 4. Phase B - derived motion

- [x] 4.1 `ingest/derive/cloud_motion.py`: DIS flow per adjacent pair,
      both directions, consistency score, warp/persistence MAE in
      provenance; digest-verified artifact readback; publishes one
      `cloud_motion` artifact chained to the base revision; degenerate
      scopes publish nothing. Worker loop + `--once` run the derive pass;
      worker image gains the `derive` extra (opencv-python-headless).
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`
- [x] 4.2 `GET /layers/{id}/flow`: exact-pair matching, frame-raster-
      aligned resampling, per-image quantization scale, derivation
      headers, 404 fail-closed paths incl. stale base revision; the
      artifact is skipped by the generic layer listing and `/point`.
      Verify: `cd api && uv run pytest tests/test_flow_endpoint.py -q`
- [x] 4.3 `FlowBlendLayer.ts` custom WebGL layer (warp + linear
      cross-dissolve, confidence gate, crossfade fallback, endpoint-exact
      by construction, premultiplied white output) wired into MapPanel for
      rendered-grid blends; flow fetch/cache with 'absent' memo; disclosure
      copy names the method actually applied; toggle title updated.
      Verify: `cd web && npm test -- --run`

## 5. Validation and live verification

- [x] 5.1 Full suites and spec validation.
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all && make test`
- [x] 5.2 `openspec/config.yaml` carve-out sentence amended for the
      motion-interpolation extension (owner approval 2026-08-31).
      Verify: `openspec validate --all`
- [ ] 5.3 Docker rebuild; one worker cycle derives cloud motion for the
      live HRDPS/RDPS/GFS artifacts; `/flow` answers with derived_motion
      headers; browser: no layout jump while scrubbing, cached frames paint
      instantly, prefetch warms the axis, interpolation ON shows clouds
      advecting between frames with the disclosure note; `/point`
      unchanged.
      Verify: `docker compose up -d --build api web worker` then the checks above
      Status 2026-08-31: stack rebuilt; the worker's first cycle derived and
      published cloud motion for all three sources (noaa-gfs, eccc-hrdps,
      eccc-rdps, each chained to its current surface revision). Live checks:
      /flow answers 200 with derived_motion, cloud-motion-dis-v1 and a
      per-image scale for HRDPS (36.46 px) and GFS (18.21 px); a
      non-adjacent pair answers 404; the cloud_motion artifact appears in
      neither /layers nor /point. Raster timing at a fixed 1024x800
      viewport: ~1.0 s first render (cold KDTree), 20-30 ms per further
      frame, 4-6 ms repeats from the render cache. The in-browser scrub /
      interpolation pass remains for the owner's own look.
