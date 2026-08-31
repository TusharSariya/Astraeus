Owned: `web/src/MapPanel.tsx`, `web/src/FlowBlendLayer.ts`,
`web/src/api.ts`, `web/src/MapPanel.test.tsx`,
`web/src/FlowBlendLayer.test.ts`, `ingest/derive/cloud_motion.py`,
`api/weather_api/grids.py`, `api/weather_api/app.py`,
`api/tests/test_cloud_motion.py`, `api/tests/test_flow_endpoint.py`,
`docs/research/cloud-motion-interpolation.md` (new),
`openspec/config.yaml` (carve-out sentence).
Not touched: registry, compose topology, worker/runtime.py, docs/specv1.

## 1. Stable blend stack across real frames

- [x] 1.1 With interpolation on, a locally rendered layer's exact frame
      draws through the flowblend entry (frame0 = frame1, t = 0, no flow);
      the painted layer-id list is identical across blend -> exact ->
      blend, the reconcile takes the in-place path, and no blend note is
      shown for an exact frame.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`

## 2. Research document

- [x] 2.1 `docs/research/cloud-motion-interpolation.md`: terminology map,
      candidate families with equations/citations/applicability, industry
      practice, failure-mode register, and what this experiment ships.
      Verify: file review; no build impact

## 3. Derive: Hermite tangents

- [x] 3.1 `cloud_motion.py`: knot velocities by QVI central difference
      from already-computed adjacent flows; one-sided at ends; consistency
      collapse to v = F; tangent clamping; per-pair `{var}_vs_u/vs_v/
      ve_u/ve_v` in the artifact; VERSION `cloud-motion-hermite-v2`;
      provenance names the construction.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`

## 4. API: tangent texture

- [x] 4.1 `/flow?texture=tangents` serves (vs_u, vs_v, ve_u, ve_v) RGBA
      aligned with the frame raster, own quantization scale header;
      `texture=motion` default unchanged; 404 when the artifact carries no
      tangents; invalid `texture` answers 422.
      Verify: `cd api && uv run pytest tests/test_flow_endpoint.py -q`

## 5. Web: cubic displacement shader

- [x] 5.1 FlowBlendLayer: tangent texture slot + uniforms; fragment
      computes b, c and displaces by the cubic; `blendReference` extended
      with a CPU `hermiteDisplacement` reference; tests pin d0(0)=0,
      d1(1)=0, linear collapse at v=F, and shared-knot C1 velocity.
      Verify: `cd web && npm test -- --run src/FlowBlendLayer.test.ts`
- [x] 5.2 MapPanel/api.ts: fetch, cache and prefetch the tangent texture
      with the flow texture; disclosure names "motion fitted through
      neighbouring frames (C1 trajectories)" when tangents are held.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`

## 6. Governance, validation, live verification

- [x] 6.1 `openspec/config.yaml` carve-out amended: motion derived from
      the layer's retrieved frame sequence (owner approval 2026-08-31,
      plan approval for multi-frame-cloud-motion).
      Verify: `openspec validate --all`
- [x] 6.2 Full suites and build.
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all && make test`
- [ ] 6.3 Docker rebuild; worker re-derives with tangents for all three
      sources; `/flow?texture=tangents` answers 200 with its scale header;
      browser: scrub across :30 NT with interpolation on - no flash, no
      direction snap at real frames; `/point` unchanged.
      Verify: `docker compose up -d --build api web worker` then the checks above
      Status 2026-08-31: stack rebuilt (worker again after the version-bump
      re-derive fix); one cycle re-derived cloud motion for noaa-gfs,
      eccc-hrdps and eccc-rdps under cloud-motion-hermite-v2. Live:
      `texture=tangents` answers 200 for all three rendered layers
      (double-width 512x200 at a 256x200 request, alpha fully opaque,
      per-image scale header, Hermite semantics); default texture answers
      200 with the v2 version; `texture=curvature` answers 422; cloud_motion
      appears in neither /layers nor /point, and /point answers live and
      unchanged. Machine checks done; the in-browser scrub across :30 NT
      (no flash, no direction snap) remains for the owner's own look.
      Fix 2026-08-31 (owner report: rendered layers drew NOTHING): the
      blend shader had never drawn a pixel in a real browser - the vertex
      matrix used MapLibre's modelViewProjectionMatrix, which operates on
      world-pixel coordinates, while our vertices are unit mercator; the
      quad projected ~50k units off screen, silently (no GL error, and
      jsdom tests mock GL so nothing caught it). Fixed to
      defaultProjectionData.mainMatrix (FlowBlendLayer.ts render). Verified
      live in Chrome against the deployed containers by driving map._render
      and diffing canvas pixels: shader on vs off changes 78k/90k sampled
      pixels, and t=0.1 vs t=0.9 renders show the cloud field translated
      (cross-correlation peak at a >=30 px shift), i.e. real advection.
      This also retro-explains the original "jumps at the half hour"
      report: with the blend layer never drawing, imagery appeared only at
      exact frames and vanished between them.
