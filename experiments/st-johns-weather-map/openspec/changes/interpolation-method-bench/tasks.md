Owned by this change (the bench itself): `ingest/derive/flow_ops.py`,
`ingest/derive/methods/` (the package: contract, harness, companion,
registry), `ingest/derive/cloud_motion.py`,
`api/weather_api/grids.py`, `api/weather_api/app.py`,
`api/weather_api/models.py`, `web/src/MethodMenu.tsx`, `web/src/api.ts`,
`web/src/TimelineDock.tsx`, `web/src/MapPanel.tsx`, `web/src/App.tsx`,
`web/src/styles.css` and their tests.

Owned by each method's own change: one module in `ingest/derive/methods/`
holding one class, its registry entry, its tests, and any shader branch in
`web/src/FlowBlendLayer.ts` it needs. A method change touches nothing else.

The package layout replaced a single module during the merge, and that was
the lesson of building six methods in parallel: every one of them appended to
the same tuple in the same file, and reconciling that by hand was most of the
merge cost. One module per method makes the next one a new file.

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
- [x] 7.2 `visibility-blend` - per-pixel asymmetric fusion weights from the
      local warp residuals, instead of a symmetric `(1-t, t)` blend.
      Verify: `cd api && uv run --extra derive --extra grib pytest tests/test_cloud_motion.py tests/test_flow_endpoint.py -q; cd ../web && npm test -- --run src/FlowBlendLayer.test.ts src/api.test.ts src/MapPanel.test.tsx`
      Status 2026-09-01: landed. Motion is the baseline's unchanged, so the
      only variable is the fusion. Weights are `v = 1/(1 + r/25)` on the
      smoothed midpoint-transported residual of each frame's own full-interval
      warp against the other retrieved frame (`r0` from `F01` against frame 1,
      `r1` from the separately derived `F10` against frame 0); the tolerance is
      the already-measured `DEVELOPMENT_TOLERANCE_PERCENT`, so no new constant
      was introduced. Fusion is `w0 = (1-t)v0`, `w1 = t v1`, renormalised - so
      `v0 == v1` is the baseline exactly, and endpoints are exact whatever the
      residuals say. Stored as `vis0`/`vis1`, served as `/flow?texture=visibility`
      (R/G, alpha opaque), refused for any method that does not derive them.

      Held-out skill, both methods on the SAME 6 real frames of the same cycle
      (2026-09-01 10:00Z onward, 256x256 EPSG:4326 raster over 46.6/-54.4 to
      48.6/-52.0, read from the running stack):

      | layer | baseline improvement over reversed flow | visibility-blend | baseline midpoint MAE % | visibility MAE % | baseline SSIM | visibility SSIM |
      | --- | --- | --- | --- | --- | --- | --- |
      | eccc-hrdps total cloud | 0.1105 | 0.0999 | 19.5588 | 19.5524 | 0.35465 | 0.35483 |
      | eccc-rdps total cloud | 0.0119 | 0.0107 | 16.9576 | 16.9585 | 0.37891 | 0.37869 |
      | noaa-gfs cloud_low | 0.1255 | 0.1258 | 17.9272 | 17.9352 | 0.60003 | 0.59954 |
      | noaa-gfs cloud_middle | 0.0562 | 0.0535 | 0.9332 | 0.9334 | 0.92273 | 0.92272 |
      | noaa-gfs cloud_high | 0.0572 | 0.0494 | 4.2883 | 4.2888 | 0.79235 | 0.79225 |

      A wash, and slightly negative on the headline control: the largest loss
      is -0.0106 (HRDPS) and the only gain is +0.0003 (GFS low). The two
      constructions differ by 0.04 to 0.13 percent cloud cover mean absolute at
      t = 0.25/0.5/0.75, and the mean per-pair weight asymmetry `|v0 - v1|` is
      0.015 to 0.103 - so the weights do part company, they just do not part
      company where the score is decided. NOT tuned to win; reported as
      measured.

      Pixel motion, measured off the drawn composites by sub-pixel phase
      correlation per 64x64 tile where the derived flow exceeds 2 px (a
      domain-wide peak reads ~0 over the Avalon because most of the field
      evolves in place - the real frame-to-frame global shift is 0.02 px on
      HRDPS), display weight forced to 1 to isolate the construction. Median
      shift per quarter step, cosine alignment with the derived flow, and the
      measured/expected ratio:

      | layer | tiles | median quarter-step px | range | cos vs flow | measured/expected |
      | --- | --- | --- | --- | --- | --- |
      | eccc-hrdps total cloud | 14 | 3.99 | 0.04 - 8.39 | 0.981 | 0.863 |
      | eccc-rdps total cloud | 13 | 4.47 | 0.04 - 11.62 | 0.922 | 0.912 |
      | noaa-gfs cloud_low | 16 | 9.48 | 1.99 - 30.74 | 0.895 | 1.077 |
      | noaa-gfs cloud_high | 6 | 11.38 | 6.01 - 12.98 | 1.000 | 0.989 |
      | noaa-gfs cloud_middle | 0 | - | - | - | - |

      The pixels move, in the flow's own direction, by very close to the
      expected fraction of the interval. `cloud_middle` is the honest negative
      and is not this method's: DIS returned a median flow of 0.005 px for that
      pair while the two real frames are 52.8 px apart, so no construction can
      move it - the baseline shows the identical picture there (difference from
      baseline 0.0000 percent).

      Composite t=0 and t=1 equal the retrieved frames bit for bit on every
      layer (`numpy.array_equal`).
- [x] 7.3 `scale-cascade` - bandpass decomposition with per-band
      advect/dissolve weights, so coarse structure advects while fine texture
      dissolves (S-PROG/ANVIL).
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py -q; cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all`
      Status 2026-09-01: landed `enabled = False`. Four-octave à trous
      cascade (dilations 1/2/4/8 plus residual), every band advected along
      the pair's own flow, each band mixed on its own development agreement
      stored as a ratio on the display weight so the held-out veto reaches it.
      Motion is the baseline's unchanged, so the only variable is the
      composite. Measured on the six live rendered-grid cloud layers of the
      2026-09-01 06Z cycle read from the running stack's object store (HRDPS
      148x149 and RDPS 35x36 total cloud, 21 frames each; GFS 61x121
      low/middle/high/total, 27 frames), all held-out fractions, mean change
      against the baseline:
      - per-band CONSTANT multipliers, the obvious reading of the method:
        every configuration lost, monotonically. Finest band at 0.5 cost
        +0.271 MAE / -0.0095 SSIM at the midpoint; a three-octave 0.5-decay
        profile cost +1.142 MAE / -0.0566 SSIM; the best admissible constant
        profile was the degenerate one that turns the cascade off.
      - per-band MEASURED weights, by depth: 1 octave -0.033 MAE / +0.0015
        SSIM (better on 3 of 6 layers), 2 octaves -0.105 / +0.0038 (5 of 6),
        3 octaves -0.144 / +0.0046 (6 of 6), 4 octaves -0.161 / +0.0048
        (6 of 6). Four shipped; the fifth buys +0.0002 SSIM per extra stored
        field. The veto-safe ratio storage costs +0.002 MAE / +0.00006 SSIM
        against absolute weights, i.e. nothing.
      - THE DECISIVE CONTROL, and the reason it is disabled: giving every
        band the same per-pixel ratio - total weight unchanged, scale
        dependence removed - scores -0.214 MAE / +0.00586 SSIM against the
        baseline, BEATING the cascade's -0.142 / +0.00468 on five of the six
        layers (RDPS the exception). The whole gain is that a bandpass agrees
        with its own warp far more readily than the full field does against
        an absolute 25-percent tolerance, so the display simply advects
        harder; splitting that boost by scale costs some of it back. The
        cascade's own contribution, isolated, is negative. Not tuned further.
      Head-to-head against `BaselineMethod` on the same frames via
      `_interpolation_skill`, midpoint, no steering prior:
      HRDPS total cloud, baseline MAE 20.5086 / SSIM 0.280488 / +0.2331 vs
      the reversed control; scale-cascade 20.0776 / 0.288817 / +0.2572.
      GFS low cloud, baseline 7.1322 / 0.804231 / +0.3609; scale-cascade
      6.9455 / 0.811231 / +0.4051. Real gains - but smaller than the
      scale-blind control's, which is what refuses the method.
      Pixel-motion harness (headless, real frames + this method's own derived
      motion, composites phase-correlated pairwise). HRDPS 10:00->11:00Z,
      mean derived flow +6.756/-0.946 cells: measured shifts per quarter
      +0.546/-0.594, +0.471/-0.525, +0.438/-0.479, +0.444/-0.585 cells,
      summing to +1.900/-2.183 over the interval. GFS low cloud, mean flow
      +1.111/+0.319: +0.561/+0.084, +0.824/+0.145, +0.802/+0.140,
      +0.630/+0.071, summing to +2.818/+0.439. Nonzero, monotone in the
      flow's direction, and t=0 / t=1 equal the retrieved frames bit for bit.
      Second reason it stays disabled, independent of the control: the client
      cannot draw it. Evaluating a four-octave à trous pyramid at the warped
      sample point is a nested dilated blur per fragment - the collapsed 1-D
      kernel for the fourth octave spans 31 taps, of order 961 texture reads
      per frame per sample point - so `web/src/FlowBlendLayer.ts` is
      deliberately untouched: no shader branch was added, because none could
      be correct. Drawing this would need the band decomposition served as
      textures, which is the render path's to give.
      Finding for the bench owner, not acted on here: on this data the
      shipped `_display_weight` under-advects, and a per-pixel boost with no
      cascade at all beats the cascade. That belongs to whoever owns
      `flow_ops`.
- [x] 7.4 `height-steering` - per-pixel steering level from GOES-19 ACHAF
      cloud-top height into the 850/700/500 hPa winds; needs a carve-out
      amendment for the cross-source prior.
      Verify: `cd api && uv run --extra derive --extra grib pytest tests/test_method_height_steering.py tests/test_adapter_goes_abi.py tests/test_cloud_motion.py tests/test_flow_endpoint.py; cd .. && openspec validate --all`
      Status 2026-09-01: landed, and it needs two things the owner has to
      decide - the carve-out amendment (wording in proposal.md) and a spec
      delta for a DATA change.

      **The data change, called out loudly.** The brief and the proposal both
      said ACHAF cloud-top height was "already in the store". It was not.
      `goes_abi.py` downloaded ACHAF, used it to displace pixels, and dropped
      it; the published artifact carried exactly `cloud_class`,
      `cloud_probability`, `parallax_uncorrected`. The adapter now RETAINS it
      as `cloud_top_height` (float32, metres, NaN wherever no valid retrieval
      reached the cell, and only where parallax was actually applied - cloudy
      AND retrieved). No new retrieval; the number was already moving the
      picture. It is display-derivation input only and pinned absent from
      `FIELD_BY_VARIABLE` and `DERIVATION_INPUTS` by test. This forced the one
      existing assertion at `test_adapter_goes_abi.py:361`, a set equality on
      the published layout, to gain the new name - approved by the coordinator
      before it was touched.

      Regridding rule: nearest source cell, on the GOES artifact's regular
      lat/lon axes, accepted only where the destination centre falls INSIDE
      that cell (half a source step per axis) and NaN otherwise. Index
      arithmetic, no tree, no interpolation. Nearest rather than an area mean
      because a mean height over a cell holding two strata is a height no
      cloud has. A curvilinear observation grid, a shape that does not match
      its coordinates, or a scan more than 3600 s from the pair midpoint are
      all refused, and each sends the cell back to the single steering level.

      Storage cost, measured on the real 298x487 GOES grid with its real 0.703
      cloudy fraction: 237,536 bytes before, 570,323 after with a spatially
      smooth height (+140.1%) and 615,987 with incompressible noise (+159.3%).
      At one scan per ten minutes that is +47.9 to +54.5 MB per day. This is
      the largest number in this task and the owner should see it before the
      spec delta is written; uint16 metres would halve it losslessly against
      what ACHAF actually resolves.
      Third method on the motion artifact: the live 2-method HRDPS
      `cloud_motion` is 30,799,865 bytes, so a third costs about +15.4 MB per
      HRDPS cycle.

      Held-out skill against the reversed-motion control, midpoint, from the
      live 06Z cycle read read-only out of the running stack. A = baseline no
      prior, B = baseline + the shipped single-level prior, C = height-steering
      against the live store as it is, D = height-steering with a STAND-IN
      per-cell height (the live GOES artifact predates the adapter change and
      a fresh ACHAF pull was not permitted, so D/E use heights derived from the
      retrieved GFS strata and are a measurement of the MECHANISM, never a
      live result), E = D with the one-hour scan window lifted:

      | layer / variable | A | B | C | D | E |
      | --- | --- | --- | --- | --- | --- |
      | hrdps total_cloud, 09 frames | 0.1996 | 0.1958 | 0.1958 | 0.1963 | 0.1990 |
      | hrdps total_cloud, 3 frames | 0.0726 | 0.0717 | 0.0717 | 0.0694 | 0.0694 |
      | gfs total_cloud | 0.3405 | 0.3402 | 0.3402 | 0.3415 | 0.3426 |
      | gfs cloud_low | 0.3594 | 0.3633 | 0.3633 | 0.3643 | 0.3647 |
      | gfs cloud_middle | 0.4376 | 0.4367 | 0.4367 | 0.4393 | 0.4402 |
      | gfs cloud_high | 0.3544 | 0.3511 | 0.3511 | 0.3501 | 0.3508 |

      C equals B to within 1e-12 on every row, verified as an equality rather
      than asserted: with no `cloud_top_height` published yet, fence five fires
      on every cell and this method IS the shipped single-level prior. That is
      the correct behaviour and it is the honest headline for today's store.
      With a per-cell height present the largest gain is +0.0035 (GFS mid
      cloud, E over B) and the largest loss is -0.0023 (HRDPS 3-frame window).
      A wash, in the same class as `intermediate-flow` at 7.1. Note also that
      the single-level prior itself is a small LOSS against no prior at all on
      HRDPS (0.1958 vs 0.1996) and GFS high cloud (0.3511 vs 0.3544) on this
      cycle, so fence four would decline it there - consistent with the earlier
      finding that it was declined for GFS mid and high.

      Pixels measured moving, headless (phase correlation between consecutive
      composites of this method's own composite, on the real 12:00Z -> 13:00Z
      pair, PNG strip and GIF written). `t = 0` and `t = 1` return the real
      frames by BIT EQUALITY, not within a tolerance, on every run:

      | run | mean derived flow | summed t=0 -> t=1 image shift |
      | --- | --- | --- |
      | hrdps total_cloud, live | +10.269, -1.383 cells | +0.60, -0.76 px |
      | hrdps total_cloud, per-cell height on 0.723 of cells | +10.386, -2.132 cells | +0.43, -0.84 px |
      | gfs total_cloud, live | +1.547, +0.155 cells | +2.77, +0.63 px |
      | gfs total_cloud, per-cell height on 0.664 of cells | +1.572, +0.159 cells | +2.76, +0.67 px |
      | gfs cloud_middle, live | +2.033, +0.213 cells | +3.82, +0.12 px |
      | gfs cloud_middle, per-cell height | +2.044, +0.220 cells | +3.92, +0.15 px |

      The image shift agrees in direction with the derived flow in all six
      (dot +4.4 to +8.1). HRDPS moves far less than its 11-cell flow because
      the display weight gates most of that field to a crossfade, which is the
      shipped behaviour and not this method's doing.

      The composite is `BaselineMethod`'s, inherited unchanged and pinned
      bit-for-bit by test, and the shader stays `hermite`: the only variable
      under test is the motion field, which is what makes the comparison
      controlled.

      **The ceiling on this method, measured.** An observed cloud top is valid
      at ONE instant and these are forecast layers running to +24 h, so even
      once `cloud_top_height` is published the observation can only reach the
      pairs near the scan. Counted against the live 06Z cycle and the 12:40Z
      scan: 2 of 20 HRDPS pairs and 2 of 26 GFS pairs fall inside the
      one-hour window. Every other pair falls back to the single level by
      fence five. That is not a tuning choice to be relaxed - widening the
      window is applying an observation to weather it did not observe - and it
      means the honest expected value of this method on a 28-hour forecast
      artifact is roughly a tenth of the already-small per-cell effect above.
      Recommendation: keep it registered and enabled for the record, do not
      promote it over `baseline`, and read this row as evidence that 7.6
      (`goes-transfer`) is the GOES lever worth spending on, since it uses the
      ten-minute sequence as MOTION rather than as a one-instant attribute.
- [x] 7.5 `development-residual` - signed growth and decay from the model's
      own vertical velocity, endpoint-exact by construction; needs new
      ingest.
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all && make test`
      Status 2026-09-01: landed, and MEASURED A WASH TO A SLIGHT LOSS on the
      one real sample scored so far. It is registered and served but
      `configure` refuses it on that sample, which is the mechanism working.

      Construction. The un-advected part of the display becomes
      `previous + s(t)*(following - previous)` with
      `s(t) = t + phi*t*(1 - t)` and `phi` in [-1, 1] the per-cell shaping.
      `t(1-t)` vanishes at both ends, so `s(0) = 0` and `s(1) = 1` are algebra
      rather than a clamp; `|gain*phi| <= 1` (gain fixed at 1, the
      monotonicity limit) keeps `s` monotone and therefore inside [0, 1], so
      the shaped value is a CONVEX COMBINATION of the two retrieved frames at
      that cell. Omega decides only WHEN the change between two retrieved
      values is delivered, never what the change is. Measured on the real
      pair: worst excursion above `max(previous, following)` 0.000e+00 and
      below `min(previous, following)` 0.000e+00 percent cloud.
      `phi ~ (omega_1 - omega_0) * sign(following - previous)`, clipped at a
      measured tendency scale and smoothed over `DEVELOPMENT_SIGMA_CELLS`;
      the residual reaches the picture only through `1 - advect_weight`, so
      where the imagery shows motion the motion wins.

      Ingest. Vertical velocity on pressure surfaces at the three steering
      levels, declared optional exactly as the steering winds are. Names
      verified against the real provider listings on 2026-09-01, not guessed:
      GFS `.idx` carries `VVEL:850 mb` / `700 mb` / `500 mb` (and `DZDT`
      beside each, deliberately not taken); HRDPS publishes
      `VVEL_ISBL_0850/0700/0500`, RDPS `VerticalVelocity_IsbL-0850/0700/0500`.
      One HRDPS message was decoded to confirm the identity from its own
      coded keys rather than its filename: WMO discipline 0, category 2,
      number 8 on `typeOfFirstFixedSurface` 100, which ecCodes 2.48.0 names
      `w`, paramId 135, `Pa s**-1`. Negative is ascent.

      `OMEGA_TENDENCY_SCALE_PA_PER_S = 0.35` is a measurement, not a taste:
      HRDPS 700 hPa omega over the Avalon crop, 2026-09-01 00Z f006 -> f007,
      gives |omega| median 0.15 and |omega_1 - omega_0| median 0.090, p90
      0.265, p95 0.335, p99 0.465 Pa s-1.

      Held-out, five real HRDPS frames (00Z f005..f009, Avalon crop,
      total_cloud), midpoint, all three constructions on the same frames:

      | construction | MAE % | SSIM | vs reversed flow |
      | --- | --- | --- | --- |
      | baseline | 14.5465 | 0.40435 | +0.15119 |
      | development-residual, residual OFF | 14.5465 | 0.40435 | +0.15119 |
      | development-residual, residual ON | 14.5657 | 0.40401 | +0.15088 |

      So the residual costs -0.0003 against the reversed-flow control, and
      `configure` publishes both numbers and applies nothing. NOT tuned until
      it won; the scale constant stayed at the measured value.

      It does do the thing advection cannot, which is why it stays
      registered. At t = 0.5 over the 6027 cells where advection failed and
      the two frames disagree, against a constant-rate dissolve: growing with
      ascent stronger early +1.645 %cloud (n=2618), growing with ascent
      stronger late -1.439 (n=1240), decaying forced early -1.466 (n=825),
      decaying forced late +0.623 (n=1344). All four signs are the physical
      ones.

      Pixel motion, headless (no browser: the Chrome tab is
      `visibilityState: hidden`, so rAF never fires and MapLibre never
      paints). Phase correlation between consecutive composites at
      t = 0, 0.25, 0.5, 0.75, 1. A real frame against a known 6-cell eastward
      roll of itself, motion derived by the method: +5.985 px summed, dy
      -0.009 - a known translation reproduced to under a pixel. On the four
      real pairs the advection branch (weight forced to 1) sums to +2.36,
      +2.64, +4.06 and +9.52 px eastward, the way the derived flow points.
      As drawn on the derived weight it is +1.29, +0.77, +0.97, +1.15 px,
      because the two RETRIEVED frames themselves phase-correlate to only
      +0.66, +0.07, +0.28 and -0.08 px at responses 0.11 to 0.32: this field
      is being remade hourly rather than carried across the peninsula, mean
      |change| 18.9 percent per hour. That is the honest reading of why the
      display weight holds advection back here, and it is the regime this
      method was built for - which makes the flat held-out result the more
      interesting negative, not a lesser one.

      Still to do: score it on GFS strata and on RDPS (only HRDPS total cloud
      has been scored), and rerun after a live cycle actually ingests omega -
      every number above comes from GRIB files fetched directly for the
      harness, since no stored artifact carries omega yet.
- [x] 7.6 `goes-transfer` - motion from the ten-minute GOES sequence applied
      to the hourly model layers (CMORPH); needs a carve-out amendment. The
      highest expected gain, and the one whose honest answer may be "show the
      GOES layer instead".
      Verify: `cd api && uv run pytest tests/test_goes_transfer.py -q; cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && openspec validate --all`
      Status 2026-09-01: landed, and it does not earn its place on this
      cycle's data. Composite is the baseline's, inherited unchanged, so the
      only variable under test is the motion field. 24 new tests; api 598
      passed / 12 skipped; web 207 passed and a clean build; openspec 28/28.

      **The premise does not hold against what this project stores.** The
      adapter publishes ONE scan per revision (`valid_time` length 1) and
      `published_companion` reaches only the current revision, so the
      ten-minute sequence the method needs is not in the artifact. Measured
      here against the 35 retained `noaa-goes-east/cloud_mask` revisions
      rebuilt into one sequence - real retrieved scans, but not what a live
      derive would see. As shipped, every pair fails fence 5 and the method
      is the baseline exactly. Fixing that is an adapter change (accumulate
      a rolling scan sequence in one artifact), not a method change.

      **Fence 5 on the real record**, HRDPS pairs from 10:00Z, GOES record
      08:40:20.5Z to 12:30:20.5Z with a missing 11:10Z scan:
      10:00->11:00Z accepted (10 scans); 11:00->12:00Z refused (1200 s hole);
      12:00->13:00Z, 13:00->14:00Z, 14:00->15:00Z, 15:00->16:00Z refused (no
      scan at the far endpoint). 1 of 5 pairs reachable, and only 1 of 20 in
      the full 21-frame forecast - the structural limit of the method: the
      model layer is a forecast running a day ahead and the observation only
      exists in the past.

      **Fence 4 could not be exercised at all.** The held-out harness scores
      across doubled (2 h) and tripled (3 h) intervals, and no such span is
      covered by an unbroken GOES chain here, so every leave-one-out score is
      bit-identical with and without the transfer (delta +0.0000 on all six
      variables). The transfer is therefore never applied.

      **Direct pair-level warp skill** on the one spannable pair
      (10:00->11:00Z), predicting frame 1 from frame 0, MAE percent:

      | layer | persistence | baseline | goes-transfer | change | mean flow shift | weight |
      | --- | --- | --- | --- | --- | --- | --- |
      | eccc-hrdps total_cloud | 19.7393 | 12.7654 | 13.0630 | -2.33% | 2.177 cells | 0.192 |
      | eccc-rdps total_cloud | 21.1087 | 13.7611 | 13.8468 | -0.62% | 0.153 cells | 0.073 |
      | noaa-gfs cloud_low | 12.4044 | 8.5132 | 8.4518 | +0.72% | 0.049 cells | 0.045 |
      | noaa-gfs cloud_middle | 10.6560 | 7.1311 | 7.1711 | -0.56% | 0.107 cells | 0.076 |
      | noaa-gfs cloud_high | 11.8386 | 8.6725 | 8.6230 | +0.57% | 0.142 cells | 0.073 |
      | noaa-gfs total_cloud | 14.5326 | 11.3246 | 11.3836 | -0.52% | 0.115 cells | 0.100 |

      A wash, and slightly negative on HRDPS, which is where the transfer
      reaches furthest (19% mean weight). Same reading as intermediate-flow:
      the estimator is not the lever on these fields.

      **A mask is not a fraction.** Motion only is transferred; no satellite
      pixel is composited into a model layer. Flow is derived from
      `cloud_probability` (continuous, retrieved) rather than the four-level
      `cloud_class`; the class ramp 0/25/75/100 is the documented fallback.
      Measured on the GOES grid itself over the contiguous 15-scan run
      08:40:20.5Z-11:00:20.5Z, scored against the same probability truth:
      probability warp MAE 8.2250 vs class-ramp 8.2913 (0.8% worse), median
      forward-backward consistency 0.8750 vs 0.8681. So the categorical field
      does degrade the flow, measurably and only slightly.

      **"Show the GOES layer instead."** Same harness, same construction,
      different sequences: the ten-minute GOES cloud mask scores midpoint MAE
      7.7182 with SSIM 0.6178 and +0.1773 against the reversed control; HRDPS
      total cloud scores MAE 20.5086, SSIM 0.2805, +0.2331. Against the
      control the observation does NOT beat the model layers (GFS strata
      reach +0.36 to +0.42), but its reconstructions are far more
      structurally intact - SSIM 0.62 against HRDPS's 0.28. The ten-minute
      observed product is the more coherent picture to interpolate; making it
      a drawable animated layer is a better use of this evidence than
      transferring its motion onto an hourly forecast. Recorded as a finding,
      not proposed here.

      **Pixels move.** Headless harness, real frames, this method's own
      derived motion, phase correlation between consecutive composites.
      HRDPS total cloud 10:00->11:00Z (148x149, display-weighted mean flow
      u +7.230 / v -2.677 cells/hour): per-quarter displacement 0.579, 0.305,
      0.307, 0.628 px, summing to (+1.063, -1.447) px. GFS cloud_middle
      (61x121, mean flow u +1.874 / v +0.125): 0.785, 0.848, 0.840, 0.764 px,
      summing to (+3.207, +0.426) px. Both agree in sign with the flow, and
      t=0 and t=1 are bit-identical to the two real frames.

      Blocked on the owner: this crosses a source boundary and needs the
      carve-out amendment (wording reported with the change). Until that
      lands the method is registered and derived but transfers nothing on
      live data, because no live pair passes fence 5.
- [x] 7.7 `flow-net` - a network that emits a displacement field only. Ranked
      last on this experiment's own measurement that the estimator is not the
      lever (0.30 -> 0.33 across five configurations).
      Verify: `cd api && uv run pytest tests/test_method_flow_net.py tests/test_cloud_motion.py tests/test_flow_endpoint.py`
      Status 2026-09-01: landed REGISTERED AND DISABLED. The estimator is RAFT
      (BSD-3-Clause, Copyright 2020 princeton-vl) run through onnxruntime as a
      lazily imported optional `flownet` extra that NO image selects; the graph
      is located by `WEATHER_FLOW_NET_MODEL` and is not vendored. Everything
      downstream is the baseline's - `composite` is the inherited object, pinned
      by test - so the estimator is the only variable. The network emits a
      displacement field only, so `generative` stays False and no carve-out is
      needed.
      Held-out improvement over the reversed-flow control, midpoint, same
      frames of the live 2026-09-01 cycle, read read-only from the main stack:

      | layer | grid | DIS | DIS @360x480 | flow-net |
      | --- | --- | --- | --- | --- |
      | eccc-hrdps total_cloud | 148x149 | 0.2331 | 0.2506 | 0.2968 |
      | eccc-rdps total_cloud | 35x36 | 0.1183 | 0.1387 | 0.0889 |
      | noaa-gfs cloud_low | 61x121 | 0.3609 | 0.4041 | 0.3330 |
      | noaa-gfs cloud_middle | 61x121 | 0.4197 | 0.4419 | 0.3413 |
      | noaa-gfs cloud_high | 61x121 | 0.3792 | 0.3953 | 0.2843 |
      | noaa-gfs total_cloud | 61x121 | 0.3359 | 0.3627 | 0.2826 |

      flow-net wins on one layer of six and loses on five, worst on the
      coarsest grids; mean change -0.037. The DIS column reproduces the 6.3
      table exactly (HRDPS 0.2331, GFS mid 0.4197), so the harness is measuring
      the shipped construction. The single HRDPS win is largely resolution, not
      learning: DIS run at the network's own 360x480 and resampled back scores
      0.2506 there, and Gaussian-smoothing the native DIS field instead scores
      0.2320 against 0.2331 - so the lever is the RESOLUTION the estimator runs
      at, not the estimator family. That reproduces pySTEPS (GMD 2019, under 2%
      spread across estimators) rather than breaking it.
      Cost had it been enabled: 689 ms/pair against `_dis_flow`'s 2.2 ms
      (312x), constant in grid size because the graph's input is fixed;
      ~370 flow calls per variable per cycle once the held-out harness and
      `configure` are counted, so roughly 25 min added to a six-variable cycle.
      Image cost ~150 MB on the worker only (onnxruntime 75 MB installed,
      protobuf/flatbuffers ~10 MB, graph 64 MB). No heavy framework was added:
      torch was never a candidate.
      Degradation is pinned: with the runtime absent, the graph absent, or the
      graph corrupt, the method falls back to `_dis_flow`, reproduces the
      baseline's fields bit for bit, and reports `flow_net_fell_back = 1.0` in
      provenance so DIS numbers can never be published under this method's name.
      Pixel motion verified headlessly on real HRDPS frames, not in a browser.
      Against a known +9 col / -5 row roll of a real frame the network recovers
      +8.993 / -4.991 cells and the composites phase-correlate to +1.16/-0.59,
      +4.57/-2.47, +7.78/-4.44, +8.98/-4.99 px at t = 0.25/0.5/0.75/1.0
      (correlation peaks 0.91-0.99); t=0 and t=1 equal the real frames exactly.
      On the genuine 10:00->11:00Z pair the advected component moves
      +1.68/-1.39 px at t=0.25 and +3.47/-2.84 px at t=0.5 along a +8.19/-4.86
      cell flow. Beyond t=0.5 on that pair the correlation peak collapses to
      0.12-0.15 and the whole-composite correlation disagrees in sign with the
      derived flow: the two real frames are not a rigid translation, which is
      the in-place development regime this peninsula lives in, and is a limit
      of phase correlation as an instrument rather than of the method.
      Recommendation: keep disabled. Follow-up worth more than this method -
      running the EXISTING DIS estimator at a higher internal resolution beat
      native DIS on all six layers (+0.016 to +0.043) for microseconds. That is
      a baseline change and is deliberately not made here.
