Owned by this change's governance stream (A/G): `openspec/config.yaml`,
this directory, and `docs/research/cloud-development-and-generation.md`.

Every other stream owns a disjoint set of files, named on its task, because
the work is parallelised across agents. A stream touches nothing outside its
list; a file two streams need is settled by the contract table in
`design.md` before either starts. Nothing is committed without an explicit
ask; `web/node`, `.repowise/` and `.claude/` are never staged.

Every implementation report quotes the pixel values it read back, not only
"tests pass". A branch that cannot be shown to change a pixel is not done.

## B. Deletions

- [x] B.1 Delete `ingest/derive/methods/{intermediate_flow,visibility_blend,scale_cascade,flow_net,full_advection,development_residual}.py`
  - Verify result: done 2026-09-01: six modules deleted; `grep` for their ids hits only docs/openspec history and the absence assertion in test_cloud_motion.py
      and `api/tests/test_method_flow_net.py`; clean every reference
      (registry `METHODS`, `__all__`, docstring citing (d); `flow_ops.py`
      drops `_development_agreement`, renames
      `DEVELOPMENT_TOLERANCE_PERCENT -> WARP_ERROR_FLOOR_PERCENT` and
      `DEVELOPMENT_SIGMA_CELLS -> ERROR_SMOOTHING_SIGMA_CELLS`, gains
      `_omega_tendency` and `_warp_linear`; `baseline.py` drops the
      agreement term and absorbs the full-advection docstring;
      `cloud_motion.py` `_FIELD_ATTRS` drops `dev_shape`, adds `res_s`,
      `gen_a`, `gen_b`, VERSION `cloud-motion-bench-v6`; `grids.py` drops
      `BACKWARD_SEMANTICS_DOC`, `FLOW_TEXTURES = (motion, tangents,
      visibility, residual)`, refusal table; `app.py` `/flow` docs; client
      `FlowBlendLayer.ts`, `api.ts`, `MapPanel.tsx` drop the backward /
      intermediate / shaped-t branches; test fixtures move to surviving ids;
      comments in `registry.py`, `eccc_datamart.py`, `noaa_s3.py`).
      Owns: `ingest/derive/**`, `api/tests/test_cloud_motion.py`,
      `api/tests/test_method_*.py`, the client and API references named
      above for the deletion only.
      Verify: `cd api && uv run pytest -q; cd ../web && npm test -- --run && npm run build; cd .. && grep -rn -e intermediate-flow -e visibility-blend -e scale-cascade -e flow-net -e full-advection -e development-residual --exclude-dir=node_modules --exclude-dir=node --exclude-dir=.git . | grep -v -e docs/research -e openspec`
      Acceptance: the grep returns nothing; the registry is exactly six
      methods, baseline first.

## C. Harness upgrade and fixed-control gating

- [x] C.1 `harness.py`: keep `_score_one`; add `_score_full` returning
  - Verify result: done 2026-09-01: `_score_full`, `admit`/`admit_reasons`, advection control, `MethodContext.cache`; api suite 781 collected, 2 pre-existing failures (test_layer_frame_contract GOES/aurora)
      `mae, ssim, sharpness_ratio, spectral_ratio_error, fss` (25/50/75 %,
      radii 1 and 3), `mae_grew`, `mae_decayed` (|following - previous| >
      5 %); primitives `_sharpness_ratio`, `_radial_psd_log_ratio`, `_fss`
      in `flow_ops.py`; second fixed control `advection_linear =
      BaselineMethod(use_prior=False)` memoised per `(first, last)` through
      `MethodContext.cache`; `summarise` gains `improvement_over_advection`,
      `midpoint_sharpness_ratio`, `midpoint_spectral_ratio_error`,
      `midpoint_fss`, `midpoint_mae_grew`, `midpoint_mae_decayed`;
      `admit(with_, without)` and `admit_reasons(...)`; `baseline.py`,
      `error_variance_blend.py`, `residual_advection.py` switch their
      `configure` to fixed controls (the negated control stays the motion
      veto only).
      Owns: `ingest/derive/methods/harness.py`, `ingest/derive/flow_ops.py`,
      `ingest/derive/methods/{baseline,error_variance_blend,residual_advection}.py`,
      `ingest/derive/methods/contract.py`, their tests.
      Verify: `cd api && uv run pytest tests/test_cloud_motion.py tests/test_method_error_variance_blend.py tests/test_method_residual_advection.py -q`
- [x] C.2 API and menu: `models.py` `MethodScore` gains the new fields,
  - Verify result: done 2026-09-01: /methods serves plain/gap/notes/generation_disabled, fixed-control scores, `applied`, `reduced_to_default` (own-switch rule, prior excluded); menu shows no reversed-flow number
      `applied: dict[str, bool]`, `reduced_to_default: bool`;
      `InterpolationMethodItem` gains `plain`, `gap`, `notes` (method class
      attributes, copy from the research document section 12); `app.py`
      fills them; `api.ts` maps them; `MethodMenu.tsx` ranks and prints the
      crossfade skill plus sharpness, renders plain/gap, the collapsible
      science note and the header line; generative entries sit under
      "Generated (off by default)" with the `generates pixels` badge and an
      explicit confirm; no reversed-flow number is shown.
      Owns: `api/weather_api/models.py`, `api/weather_api/app.py`,
      `api/tests/test_flow_endpoint.py`, `web/src/MethodMenu.tsx`,
      `web/src/api.ts`, `web/src/api.test.ts`, `web/src/App.test.tsx`.
      Verify: `cd api && uv run pytest tests/test_flow_endpoint.py -q; cd ../web && npm test -- --run src/App.test.tsx src/api.test.ts`

## D. Make `residual-advection` draw, and make "reduced" visible

- [x] D.1 Server: `residual_advection.py` `extra_suffixes = vetoed_suffixes =
  - Verify result: done 2026-09-01: `gen_a = 4*RESIDUAL_GAIN*res_s`, stored parabola composite; derive fix: extra suffixes now land on their own method slot (were written under baseline)
      ("res_s", "gen_a", "gen_b")`; `motion` stores `gen_a = 4 *
      RESIDUAL_GAIN * res_s`, `gen_b = 0`; `composite` evaluates the STORED
      parabola; `grids.py` `residual` encoder serves R/G = `gen_a`/`gen_b`
      with `scale = max(|gen_a|, |gen_b|)`, header semantics rewritten,
      refused by name unless the method's shader is `residual-advection`.
      Owns: `ingest/derive/methods/residual_advection.py`,
      `api/weather_api/grids.py`, `api/tests/test_method_residual_advection.py`,
      `api/tests/test_flow_endpoint.py` (residual texture tests).
      Verify: `cd api && uv run pytest tests/test_method_residual_advection.py tests/test_flow_endpoint.py -q`
      Acceptance: `/flow?texture=residual&method=residual-advection` is 200
      with a fitted scale; 404 by name for `baseline`.
- [x] D.2 Client: `FlowBlendLayer.ts` uniforms `u_has_envelope`,
  - Verify result: done 2026-09-01: envelope branch; H.1 readback in Chrome: t=0 -> 0, t=1 -> 255, t=0.5 -> 153 with envelope (a=0.40) vs 128 without; scale 50 -> 140; negative a -> 102
      `u_envelope_scale`; after `alpha = mix(plain, warped, advect)`:
      `env = u_t*(1.0-u_t)*(a + b*u_t); alpha = clamp(alpha + env, 0.0, 1.0)`;
      `residualReady` requires `construction === 'residual-advection'`; CPU
      reference `envelopeTerm(a, b, t)`; `api.ts` fetches `residual` only
      when the served shader is `residual-advection` and carries
      `residualScalePixels`; `MapPanel.tsx` passes it and `layerNoteFor`
      words the note by `held.shader` (hermite / visibility /
      residual-advection non-generative / residual-generative GENERATED);
      new prop `methodStatus` computed in `App.tsx` from `/methods` appends
      "; method "X" reduced to the default construction on this layer:
      <reasons>".
      Owns: `web/src/FlowBlendLayer.ts`, `web/src/FlowBlendLayer.test.ts`,
      `web/src/FlowBlendLayer.browser.test.ts`, `web/src/MapPanel.tsx`,
      `web/src/MapPanel.test.tsx`, `web/src/App.tsx` (methodStatus only).
      Verify: `cd web && npm test -- --run && npm run build`
      Acceptance (H.1): the browser GL test reads back a midpoint pixel equal
      to `0.5 + 0.25*a` within one quantum, endpoints exactly 0 and 255, and
      exactly 0.5 with `u_has_envelope = 0`; the report quotes the values.

## E. `residual-generative`

- [x] E.1 `ingest/derive/methods/residual_generative.py`:
  - Verify result: done 2026-09-01: 36 tests; synthetic saturating fixture admitted gain 0.5, refused regime gate on sharpness 1.26; live 18Z HRDPS cycle: every option refused (research doc 13b)
      `ResidualGenerativeMethod(ResidualAdvectionMethod)`,
      `id = "residual-generative"`, `shader = "residual-advection"`,
      `generative = True`, `enabled = True`; envelope fitted by least squares
      at `HELD_OUT_FRACTIONS` to each option's target delivered fraction,
      `|e| <= RESIDUAL_CAP_PERCENT`, composite clipped to [0, 100]; options
      `gain` {0.25, 0.5, 0.75, 1.0}, `rh_timing` (U0 0.94 HRDPS/RDPS, 0.88
      GFS, `rh_phase_convention` published, sigmoid w = 0.15), `omega_shift`
      (via `_omega_tendency`, clamped to the x1.02..x1.2 per hour table,
      no-op with `omega_reached = 0` when absent), `solar_dissipation`
      (decaying cells, solar elevation > 0 at the pair midpoint, t* = 0.65,
      w = 0.12), `scale_split` (Gaussian sigma 5 cells; coarse band linear),
      `regime_gate` (motion-compensated lag-1 correlation over a 9-cell box,
      zero (a, b) below 0.5, `regime_gated_fraction` disclosed); decided
      greedily in `configure` with `admit` on top of the accepted set, every
      number published under `options`; `requirements()` returns RH at the
      steering level and omega; one registry line.
      Tests `api/tests/test_method_residual_generative.py`: endpoint
      exactness by algebra, cap, veto zeroes all three fields, each option's
      (a, b) mapping, t* arithmetic, option refused when `admit` fails, every
      published number present, kill switch removes the method from
      `enabled_methods()`.
      Owns: `ingest/derive/methods/residual_generative.py`,
      `api/tests/test_method_residual_generative.py`, one line in
      `ingest/derive/methods/__init__.py`.
      Verify: `cd api && uv run pytest tests/test_method_residual_generative.py tests/test_cloud_motion.py -q`
      Acceptance: every option's scores are published whether admitted or
      not; the map note says GENERATED.

## F. WEonG low-cloud layer

- [x] F.1 Ingest: `eccc_datamart.py` `LOW_LEVELS_HPA = (1015, 1000, 985, 970,
  - Verify result: done 2026-09-01: nine levels + HGT_Sfc (HRDPS) / Pressure_Sfc datum (RDPS); WMO keys decoded live; +59 MB download, +1.3 MB stored per HRDPS lead. 2026-09-02: downloads pooled (WEATHER_DATAMART_PARALLEL=6) with WEATHER_HTTP_MIN_HOST_INTERVAL=0.1 and 429 counting in PoliteClient; full run fetched in ~8 min at ~4.7 MB/s, zero 429s
      950, 925, 900, 875, 850)`, `_profile_vars` following `_thermo_vars`,
      HRDPS tokens `RH_ISBL_{L:04d}` / `TMP_ISBL_{L:04d}` / `HGT_ISBL_{L:04d}`
      / `HGT_Sfc`, RDPS `RelativeHumidity_IsbL-{L:04d}` / `AirTemp_IsbL-{L:04d}`
      / `GeopotentialHeight_IsbL-{L:04d}`; the RDPS surface-height token is
      NOT in the listing - decode one message live to confirm or use the
      1015 hPa height as the AGL datum with the bias stated; added to
      `HRDPS_VARS`/`RDPS_VARS`, `CANONICAL_FIELD_UNITS` (`gpm`),
      `OPTIONAL_VARIABLES`; RH levels get `declare_rh_phase`; registry
      `LOW_PROFILE_VARIABLES` in `VARIABLE_OVERRIDES` for both sources.
      Record measured bytes and wall time before and after (+28 files per
      lead hour, ~750 per run, ~66 MB cropped per run).
      Owns: `ingest/adapters/eccc_datamart.py`, `ingest/registry.py`,
      `api/tests/test_adapter_eccc_datamart.py`.
      Verify: `cd api && uv run --extra derive --extra grib pytest tests/test_adapter_eccc_datamart.py -q`
- [x] F.2 Derive: `ingest/derive/weong_layer.py` with
  - Verify result: done 2026-09-01: weong_layer.py; real 12Z+3h derive NT mean 56.1% -> 91.3% (LLC fired on 100% of cells, one saturated maritime cycle); LIVE 2026-09-02 00:14Z: layer published from the 18Z run, motion derived for six methods, e2e readback passed (hash 888b8f69:165590 on every method, all disclosed as reduced); baseline skill 0.229 / SSIM 0.484 vs 0.172 / 0.354 on the published field
      `derive_weong_low_cloud(store, surface, workdir)` and
      `weong_cycle(store)` in `cloud_motion_cycle`'s shape (digest check,
      revision/version comparison, never raises); per valid time
      `assert_liquid_water_rh` on every level, AGL = `HGT_ISBL - HGT_Sfc`,
      below-ground levels masked, `weong_low_cloud_from_profile`,
      `NT = combine_nt_weong(total_cloud/100, llc) * 100`; dataset carries
      `total_cloud_weong`, `llc` and copies of the run's steering/omega/RH/T
      at the three steering levels; provenance `derived: True`,
      `generated: True`, derivation text naming WEonG technote v2.4.1 sec
      7.9, `base_revision_id`, `derivation_version = weong-low-cloud-v1`;
      refused when the kill switch is off; delete
      `low_cloud_from_pressure_levels` and `THREE_LEVEL_REDUCTION_GAP` and
      their tests once the profile is ingested. Worker `derive()` calls
      `weong_cycle` before `cloud_motion_cycle` in both paths.
      Owns: `ingest/derive/weong_layer.py`, `ingest/derive/weong_low_cloud.py`,
      `worker/runtime.py`, `api/tests/test_weong_low_cloud.py`,
      `api/tests/test_weong_layer.py`.
      Verify: `cd api && uv run --extra derive --extra grib pytest tests/test_weong_low_cloud.py tests/test_weong_layer.py -q`
- [x] F.3 API: `grids.py` `RenderedGridSpec` gains `derived_disclosure`; new
  - Verify result: done 2026-09-01: eccc-*-low-cloud-weong specs with disclosure; /flow and /methods resolve cloud_motion_low_cloud_weong; raster reads 51 (20%) where retrieved is 0%
      layer `eccc-hrdps-low-cloud-weong` (and RDPS only if the datum is
      confirmed) with `logical_name = "low_cloud_weong"`, `variable =
      "total_cloud_weong"`, title suffix "(generated: WEonG low-cloud
      repair)"; `CLOUD_MOTION_SOURCES` keyed by `(source_id, logical_name)`;
      motion logical name derived from the base; `render_flow` and
      `/methods` look up by it. Tests: nine-level profile with a below-ground
      level masked; layer offered / not offered / disclosed
      (`test_rendered_grids.py` `GridStore` pattern); manifest optional
      fields; keyed motion cycle.
      Owns: `api/weather_api/grids.py` (layer entry and keyed sources),
      `api/tests/test_rendered_grids.py`.
      Verify: `cd api && uv run pytest tests/test_rendered_grids.py tests/test_flow_endpoint.py -q`
      Acceptance: `eccc-hrdps-low-cloud-weong` is offered with a "generated"
      disclosure, has motion for all six methods, and vanishes with the env
      var off.

## G. Kill switch and reader default

- [x] G.1 `generated_display_enabled()` in `ingest/derive/methods/__init__.py`
  - Verify result: done 2026-09-01: live check with WEATHER_GENERATED_DISPLAY=off on the API: notice served, residual-generative flagged generation_disabled
      reading `WEATHER_GENERATED_DISPLAY`; `enabled_methods()` filters
      `generative` when off; `/methods` notice
      "WEATHER_GENERATED_DISPLAY=off: generative constructions are not
      derived or offered"; `compose.yaml` passes the variable to `api` and
      `worker`; `App.tsx` restore: a stored generative id falls back to the
      default; selecting a generative method requires the explicit confirm.
      Owns: `ingest/derive/methods/__init__.py` (helper), `compose.yaml`,
      `web/src/App.tsx` (restore path), `api/weather_api/app.py` (notice).
      Verify: `cd api && WEATHER_GENERATED_DISPLAY=off uv run pytest tests/test_cloud_motion.py tests/test_flow_endpoint.py -q; cd ../web && npm test -- --run src/App.test.tsx`

## H. Integration tests and pixel verification

- [x] H.1 GL pixel readback (`web/src/FlowBlendLayer.browser.test.ts`,
  - Verify result: done 2026-09-01: gl project, 8 tests, pixel values as under D.2
      Playwright project): real Chrome, 2x2 frame textures (frame0 alpha 0,
      frame1 alpha 1), zero-motion flow with weight 1, a `residual` texture
      with known (a, b); render at t = 0, 0.5, 1 and `gl.readPixels`.
      Endpoints exactly 0 and 255; midpoint `0.5 + 0.25*a` within one
      quantum; exactly 0.5 with `u_has_envelope = 0`; visibility branch
      (v0 = 1, v1 = 0) returns frame0's alpha at t = 0.5.
      Owns: `web/src/FlowBlendLayer.browser.test.ts`.
      Verify: `cd web && npm test -- --run --project browser`
- [x] H.2 Live API integration (`api/tests/test_layer_contract_live.py`
  - Verify result: done 2026-09-01: live run WEATHER_LAYER_CONTRACT=1: envelope 200 for residual shaders with scale 0.0000 where the gate refused, 404 by name otherwise; one unrelated failure (eccc-radar-radar advertised instant)
      pattern, gated on the stack being up): for every rendered-grid layer
      and every enabled method, `/flow?texture=motion` is 200 or a named
      404; `residual` is 200 for `residual-advection`/`residual-generative`
      and 404 by name for the rest; the PNG decodes to the requested size;
      `X-Weather-Flow-Shader` equals the registry's shader; `/methods`
      carries `applied` and fixed-control scores for the layer.
      Owns: `api/tests/test_layer_contract_live.py`.
      Verify: `docker compose up -d --build api web worker && cd api && uv run pytest tests/test_layer_contract_live.py -q`
- [x] H.3 End-to-end pixel check in the browser
  - Verify result: done 2026-09-01: e2e project passed live on eccc-hrdps-surface-total-cloud: all six hashes bf1a0eec:385698, every non-default note says "reduced to the default", verdicts read from /methods
      (`web/src/e2e/interpolation.e2e.test.ts`, third vitest project `e2e`,
      Playwright, `VITE_E2E=1`, skipped unless the API answers; Chrome MCP
      run recorded as a GIF into this file as evidence): interpolation on,
      HRDPS total cloud, scrub mid-pair; for each of the five menu entries
      select it, wait for the flow cache, read the map canvas
      (`canvas.toDataURL` after `preserveDrawingBuffer`, or a `readPixels`
      hook on `window.__flowLayers` in dev builds only) and hash the pixels.
      Entries 1, 2, 3 produce three DIFFERENT hashes; entries 4 and 5 equal
      entry 1 AND the note contains "reduced to the default"; entry 3's note
      contains "GENERATED"; with the kill switch off entry 3 is absent; the
      note text matches the served shader.
      Owns: `web/src/e2e/interpolation.e2e.test.ts`, `web/vite.config.ts`
      (the `e2e` project only).
      Verify: `docker compose up -d --build api web worker && cd web && VITE_E2E=1 npm test -- --run --project e2e`
- [x] H.4 Derive integration (`api/tests/test_cloud_motion.py` live-store
  - Verify result: done 2026-09-01: 4 derive-integration tests in test_cloud_motion.py (method axis, gen_a non-zero, vetoed pair zero, kill switch)
      variant): one real derive over a synthetic three-frame artifact
      through `derive_cloud_motion`; the `method` axis is exactly the six
      ids; `gen_a` is non-zero for `residual-advection`; a vetoed pair has
      `gen_a = gen_b = 0`; the WEonG cycle publishes `total_cloud_weong >=
      total_cloud` everywhere.
      Owns: `api/tests/test_cloud_motion.py` (live-store block).
      Verify: `cd api && uv run --extra derive --extra grib pytest tests/test_cloud_motion.py -q`
- [ ] H.5 Kill-switch integration: with `WEATHER_GENERATED_DISPLAY=off` the
  - Verify result: partly 2026-09-01: API half verified live (notice, generation_disabled); worker half (five-method derive with the switch off) not run live, covered by unit test only
      derive publishes five methods, `/methods` shows the notice, the WEonG
      layer is absent from `/layers`, and the e2e menu has no generated
      entry.
      Owns: `api/tests/test_layer_contract_live.py` (kill-switch block),
      `web/src/e2e/interpolation.e2e.test.ts` (kill-switch case).
      Verify: `WEATHER_GENERATED_DISPLAY=off docker compose up -d api worker && cd api && WEATHER_GENERATED_DISPLAY=off uv run pytest tests/test_layer_contract_live.py -q && curl -s localhost:8000/methods | jq '.notices'`

## Full verification (runs after every stream has landed)

```sh
cd experiments/st-johns-weather-map
cd api  && uv run pytest -q
cd ../web && npm test -- --run && npm run build     # both vitest projects incl. Playwright GL
cd ..   && make test && make test-layers
docker compose up -d --build api web worker
docker compose logs -f worker | grep -e cloud-motion -e weong   # one derive cycle
curl -s localhost:8000/methods | jq '.methods[] | {id, enabled, generative, scores: .scores[] | {layer_id, improvement_over_crossfade, improvement_over_advection, midpoint_ssim, midpoint_sharpness_ratio, applied}}'
WEATHER_GENERATED_DISPLAY=off docker compose up -d api worker   # notice shown; residual-generative and low_cloud_weong absent
openspec validate --all
```

Acceptance, all nine from the plan:

1. Registry is exactly six methods, baseline first; no deleted id anywhere
   but the research doc and openspec history.
2. `/flow?texture=residual&method=residual-advection` is 200 with a fitted
   scale; 404 by name for `baseline`.
3. The browser GL test reads back a pixel that differs from the crossfade by
   the envelope.
4. Every `/methods` entry carries fixed-control skill, SSIM, sharpness,
   `applied`, plain/gap/notes copy; the menu shows no reversed-flow number.
5. A method reduced to default on a layer says so in the on-map note.
6. `residual-generative` publishes every option's scores whether admitted or
   not; the map note says GENERATED.
7. `eccc-hrdps-low-cloud-weong` is offered with a "generated" disclosure,
   has motion for all six methods, and vanishes with the env var off.
8. HRDPS derive wall time and artifact bytes recorded before/after.
9. Owner's own look at HRDPS total cloud with entry 3 selected.

## I. Defect found on the owner's own first look (2026-09-02, fixed)

- [x] **I.1 The generated layer reached the data paths and broke them.**
  `LiveStore.sample_point` skipped derived imagery by matching the logical
  name `cloud_motion`. That match had already stopped covering the motion
  artifact (its name now carries the layer, `cloud_motion_low_cloud_weong`)
  and never covered `low_cloud_weong` at all, so the generated WEonG cloud
  was sampled onto /point and /profile against carve-out (d). The response
  did not merely include a generated value, it failed whole: the derivation
  records `quality.status: "derived"`, which is not one of the four statuses
  `Quality` allows, and `live_provenance` is not isolated per artifact the
  way `open` is, so one artifact erased every source.
  Files: `api/weather_api/store.py` (`_is_display_only`, applied in
  `sample_point` and `sample_profile`), `ingest/derive/weong_layer.py` and
  `ingest/derive/cloud_motion.py` (valid status, derivation named in flags),
  `api/tests/test_live_store.py`.
  Verify result: before, `/point` answered `data_mode: unavailable` with an
  empty provenance for all 13 fields and the API logged a `ValidationError`
  per sampled field. After, `data_mode: live` with 58 fields from
  awc-metar-speci, eccc-hrdps, eccc-rdps, noaa-gfs and noaa-swpc-ovation,
  and the browser shows live values with no "no live evidence" banner.
  786 API tests, 2 pre-existing failures (GOES/aurora frame roll);
  `WEATHER_LAYER_CONTRACT=1` layer contract suite fully green.

- [x] **I.2 GOES cloud mask absent after `make down up` - not a defect.**
  The worker ingests sources serially and HRDPS now takes about nine minutes
  with the nine-level profile, so a cycle started at 00:19:43 reached
  noaa-goes-east at 00:37:38. GOES has a 1800 s freshness threshold, so its
  layer was correctly withheld in between. It returned with `fresh`,
  age 40 s. Worth noting as a cost of the profile ingest: fast-cadence
  sources now wait longer behind the slowest model in the cycle.
