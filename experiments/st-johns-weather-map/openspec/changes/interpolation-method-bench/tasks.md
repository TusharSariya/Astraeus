Owned by this change (the bench itself): `ingest/derive/flow_ops.py`,
`ingest/derive/methods.py`, `ingest/derive/cloud_motion.py`,
`api/weather_api/grids.py`, `api/weather_api/app.py`,
`api/weather_api/models.py`, `web/src/MethodMenu.tsx`, `web/src/api.ts`,
`web/src/TimelineDock.tsx`, `web/src/MapPanel.tsx`, `web/src/App.tsx`,
`web/src/styles.css` and their tests.

Owned by each method's own change: one new class in
`ingest/derive/methods.py`, its registry entry, its tests, and any shader
branch in `web/src/FlowBlendLayer.ts` it needs. A method change touches
nothing else.

## 1. The contract

- [x] 1.1 Extract the numeric primitives to `flow_ops` so a method can be
      written without touching the derive loop; dependency direction
      `flow_ops <- methods <- cloud_motion`.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`
- [x] 1.2 `InterpolationMethod` with `motion`, `composite` and `configure`;
      `MethodContext` carrying the frames' own indices so a method can read
      another variable at the same instants; `PairMotion` with per-method
      extra fields and diagnostics; the registry and its catalogue.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`

## 2. Measurement before methods

- [x] 2.1 The harness takes the method, scores at t = 1/3, 1/2 and 2/3 from
      three-interval hold-outs, and reports structural similarity beside MAE.
      The midpoint keeps its published names and stays the veto.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`

## 3. Publish every method

- [x] 3.1 The derive loops over enabled methods; fields gain a leading
      `method` axis with names unchanged; provenance gains `per_method` with
      each method's own scores; version bumps to `cloud-motion-bench-v4`.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q`

## 4. Serve and select

- [x] 4.1 `/flow?method=` selects on the method axis; an artifact without the
      axis serves the baseline; an unknown method is refused and a known one
      the artifact lacks is an absence naming it; the served method rides the
      response headers.
      Verify: `cd api && uv run pytest tests/test_flow_endpoint.py -q`
- [x] 4.2 `GET /methods` serves the registry with each method's measured
      skill read from provenance; an unmeasured method reports no score
      rather than a zero.
      Verify: `cd api && uv run pytest tests/test_flow_endpoint.py -q`

## 5. The menu

- [x] 5.1 `MethodMenu` beside the interpolation toggle it qualifies; the
      choice is per-viewer and best-effort; a stored method the server no
      longer publishes falls back to the default.
      Verify: `cd web && npm test -- --run src/App.test.tsx`
- [x] 5.2 The method is part of the flow cache key, is sent on every flow
      request, and any non-default method is named in the on-map disclosure.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx src/api.test.ts`

## 6. Governance and verification

- [x] 6.1 Spec deltas for derived-motion-imagery and web-evidence-interface,
      including the reserved generative slot and what it may not do without a
      carve-out.
      Verify: `openspec validate --all`
- [x] 6.2 Full suites and build.
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all && make test`
      Status 2026-08-31: api 571 passed / 7 skipped; web 203 passed and a
      clean build; openspec 28/28; make test green (publication invariants
      and specctl 0 errors).
- [x] 6.3 Docker rebuild; one cycle derives every enabled method under
      `cloud-motion-bench-v4`; `/methods` lists the bench with scores from
      that cycle; `/flow?method=` serves each; the artifact size before and
      after is recorded so the per-method cost is a measured number.
      Verify: `docker compose up -d --build api web worker` then the checks above
      Status 2026-09-01: a live cycle derived both methods under
      `cloud-motion-bench-v4` for all five rendered-grid layers.
      `/methods` reports `data_mode: live`, both methods `published: true`,
      no notices. Every combination of `method` x `texture`
      (motion / tangents / backward) serves 200 with the right method and
      shader named back in the headers, on the HRDPS 10:00 -> 11:00Z pair;
      the served flow scale is 21.0 output pixels, so the field is moving,
      and the C1 tangents are present.
      Held-out skill against the reversed-motion control, midpoint, from the
      same frames of the same cycle:

      | layer | baseline | intermediate-flow |
      | --- | --- | --- |
      | eccc-hrdps total cloud | 0.2331 | 0.2332 |
      | eccc-rdps total cloud | 0.1251 | 0.1240 |
      | noaa-gfs cloud_low | 0.3657 | 0.3675 |
      | noaa-gfs cloud_middle | 0.4197 | 0.4265 |
      | noaa-gfs cloud_high | 0.3792 | 0.3858 |
      | noaa-gfs total_cloud | 0.3359 | 0.3383 |

      Still to record: the artifact size before and after, which needs a
      stored-size comparison the running stack does not expose directly.

## 7. The methods themselves

Each is an independent change against the contract above, landing one at a
time, each with its own held-out score from the same cycle as the baseline.
Ranked by expected gain per unit of effort, from the research:

- [x] 7.1 `intermediate-flow` - Super SloMo's quadratic-in-t intermediate
      flow from both `F01` and `F10` (both already stored, `F10` never
      served), instead of assuming the forward flow inverts.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py tests/test_flow_endpoint.py -q; cd ../web && npm test -- --run src/FlowBlendLayer.test.ts src/api.test.ts`
      Status 2026-08-31: landed. Motion is the baseline's unchanged, so the
      only variable is the composite. Held-out numbers, midpoint, from the
      tests that pin them:
      - purely translating blob sequence (5 frames, DIS-derived flows, so the
        round trip nearly inverts): baseline MAE 0.00419 percent / SSIM
        0.998930; intermediate-flow MAE 0.00380 / SSIM 0.999068. A 9 percent
        MAE reduction, which is the expected near-tie: where `F10 == -F01` the
        two constructions are algebraically identical.
      - deliberately disagreeing directions (true motion 12 cells east, both
        derived fields carrying the same +2-cell bias: `F01 = +14`,
        `F10 = -10`): baseline MAE 0.03284 / SSIM 0.999912; intermediate-flow
        MAE 0.00005 / SSIM 1.000000. The shared bias cancels in
        `(1-t)F01 - t F10` rather than being carried whole.
      - full derive over the 5-frame fixture, both methods on the same frames:
        baseline and intermediate-flow both midpoint MAE 0.0003 percent, SSIM
        0.99999, improvement over reversed flow 0.9998, display weight median
        1.000 - indistinguishable on a fixture whose flows do invert, which is
        the honest result there.
      Live cycle 2026-09-01 (see 6.3 for the table): a wash. The largest gain
      is +0.0068 on GFS mid cloud and the largest loss is -0.0011 on RDPS;
      HRDPS moves by +0.0001. The honest reading is that after the
      neighbourhood fill the two derived directions invert well enough that
      the two constructions coincide on real fields, so the synthetic
      disagreement case below is not a regime this data reaches. The method
      stays registered because it costs nothing to keep and is the correct
      construction where the round trip does fail, but it is not the lever.
      `/flow?texture=backward` now serves `u10`/`v10` (R/G, alpha opaque),
      404 naming the absence for an artifact that predates the stored field.
- [ ] 7.2 `visibility-blend` - per-pixel asymmetric fusion weights from the
      local warp residuals, instead of a symmetric `(1-t, t)` blend.
- [ ] 7.3 `scale-cascade` - bandpass decomposition with per-band
      advect/dissolve weights, so coarse structure advects while fine texture
      dissolves (S-PROG/ANVIL).
- [ ] 7.4 `height-steering` - per-pixel steering level from GOES-19 ACHAF
      cloud-top height into the 850/700/500 hPa winds; needs a carve-out
      amendment for the cross-source prior.
- [ ] 7.5 `development-residual` - signed growth and decay from the model's
      own vertical velocity, endpoint-exact by construction; needs new
      ingest.
- [ ] 7.6 `goes-transfer` - motion from the ten-minute GOES sequence applied
      to the hourly model layers (CMORPH); needs a carve-out amendment. The
      highest expected gain, and the one whose honest answer may be "show the
      GOES layer instead".
- [ ] 7.7 `flow-net` - a network that emits a displacement field only. Ranked
      last on this experiment's own measurement that the estimator is not the
      lever (0.30 -> 0.33 across five configurations).
