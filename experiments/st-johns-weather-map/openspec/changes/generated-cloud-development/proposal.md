# Science-backed cloud generation between checkpoints

## Why

The bench (`interpolation-method-bench`) answered the owner's first question
honestly: no construction that only warps and mixes two retrieved frames is
the lever on hourly HRDPS cloud, because that field is remade in place
between frames rather than carried across the peninsula. Seven methods were
offered; three drew the baseline picture under another name, and the score
shown beside them - skill against the reversed-motion control - cannot rank
methods at all, because that control moves with the method.

The owner then changed the governing rule (decision 2026-09-01, applied to
`openspec/config.yaml` as carve-out (d)):

> we are allowed to generate data based off of science and literature and
> research to fill in gaps (say two HRDPS images, or two precipitation or
> humidity runs) ... it MUST be backed by science, preferring the most robust
> implementation and must be able to be disabled.

This change is that amendment made real. Between two retrieved frames the
display may now draw a value that is in neither frame, but only from a
published, cited construction; only where it measurably beats a FIXED control
on both mean error and structural similarity; only bounded, endpoint-exact and
named as GENERATED on the map; off by default for the reader; switchable at
three levels; and never on a data path.

## What the research settled

Recorded in `docs/research/cloud-development-and-generation.md`, sections
0-12. The points this change stands on:

- Holding both endpoints is advection correction, an analysis problem, not
  nowcasting (Anagnostou & Krajewski 1999; Shapiro et al. 2010). The growth
  and decay that advection cannot explain is directly computable as
  `s = warp(I1, backward) - I0` - NowcastNet's source term, computed rather
  than learned because both endpoints are held.
- Two endpoints fix the net change per cell. Physics can decide WHEN in the
  interval and WHERE within a region that change is delivered, never what it
  is. Cloud that forms and clears entirely inside one hour is unrecoverable
  and the menu copy says so.
- The strongest quantitative both-endpoints result is a spatially varying,
  non-linear-in-time weighting (Vandal & Nemani, GOES band 13, RMSE 2.29 to
  0.99 at t = 0.5 against linear). Scale-dependent lifetimes (STEPS) are the
  only physical argument for a non-uniform envelope. Daytime low-cloud
  clearing accelerates once thin (Ghonima et al. 2016; Pauli et al. 2022).
- No published method interpolates NWP cloud between output times, and none
  uses omega or RH tendency. Every timing option here is a physics-based
  prior with no interpolation precedent, so the harness decides and a refusal
  of every one of them is a valid result to report.
- Verified live: HRDPS/RDPS TCDC is instantaneous (PDT 4.0) and
  opacity-weighted; GFS TCDC is a geometric max-random fraction and the
  adapter already selects the instantaneous record; HRDPS and RDPS publish RH,
  T and geopotential height at 1015-850 hPa; ECCC's own WEonG NT is smoothed
  [0.25, 0.5, 0.25] hourly, so the producer treats hourly cloud timing as
  uncertain to about an hour.
- Pointwise error rewards blur. Methods are ranked on fixed controls only,
  with sharpness and spectral ratio beside MAE and SSIM, and error stratified
  by cells that grew and cells that decayed.

## What changes

**Six methods are deleted, not disabled.** Each is a transfer from video or
nowcasting that measured worse, or is undrawable, and under the amended rule a
construction with no science behind it has no place in the registry:

| deleted | measured reason |
| --- | --- |
| `intermediate-flow` | a wash: +0.0068 best, -0.0011 worst, the two directions invert well enough after the fill that it coincides with the baseline on real fields |
| `visibility-blend` | slightly negative on the headline control (-0.0106 HRDPS); weights part company where the score is not decided |
| `scale-cascade` | refused by its own scale-blind control (same per-pixel boost, no cascade, beat it on 5 of 6 layers); no correct one-pass shader exists |
| `flow-net` | lost to DIS on 5 of 6 layers; the single win was resolution, not learning |
| `full-advection` | not a method: a display-weight change, absorbed into the baseline as `advect_weight = clip(support / SUPPORT_FLOOR)` |
| `development-residual` | a wash to a slight loss (-0.0003) and gated on the moving control; its omega term folds into the computed residual's timing |

**Five methods are kept**, baseline first: `baseline` (now without the
development test, which measured worse on growth, decay and sharpness on every
layer), `error-variance-blend`, `residual-advection`, `height-steering` and
`goes-transfer`. The owner keeps the last two enabled as they are.

**One generative method is added**: `residual-generative`, a sibling of
`residual-advection` on the same shader, flagged `generative`, offering the
timing options as switches (humidity threshold crossing under GEM's own
Sundqvist closure, omega shift, daytime dissipation, scale split, regime
gate), each admitted greedily on the fixed control with every number
published whether admitted or not.

**The computed residual actually draws.** The shader evaluates an envelope
`e(t) = t(1-t)(a + b t)` after the advection mix, stored per cell as `gen_a`,
`gen_b`, served as the `residual` texture with a fitted scale, refused by name
for any method whose shader is not `residual-advection`.

**HRDPS gets ECCC's own low-cloud repair as a separate derived layer**:
`eccc-hrdps-low-cloud-weong` (`logical_name = low_cloud_weong`, variable
`total_cloud_weong`), built from the run's own nine-level RH/T/height profile
under WEonG technote v2.4.1 sec 7.9, disclosed as generated, with its own
motion artifact for every method, absent when the kill switch is off. The
provider `surface` artifact is untouched.

**A kill switch and a reader default.** `WEATHER_GENERATED_DISPLAY=off`
refuses every generative method and the WEonG derive at derive time and says
so on `/methods`; the menu never restores a stored generative choice and asks
for an explicit confirm before selecting one.

**The menu speaks plainly.** Five entries, each with a plain sentence, a gap
sentence and a collapsed science note (copy in
`docs/research/cloud-development-and-generation.md` section 12); the score
line is skill over a plain crossfade plus a sharpness ratio, never the
reversed-motion number; a method that reduced to the default on a layer says
so on the map.

## What is verified and what is not

Verified before this change: the WEonG formulae and table against the primary
PDF; both models' RH phase conventions from their own specific humidity; GFS
PDT 4.0 vs 4.8 and HRDPS/RDPS PDT 4.0 by byte decode; the Datamart profile
tokens by listing; the measured harm of the development test on live
artifacts. Measured once the streams ran (2026-09-01/02, recorded in
`tasks.md` and research sections 13, 13b and 13c):

- The fixed-control gate admitted no method's own term on any layer of that
  cycle - HRDPS, every GFS layer and the WEonG layer alike. All six entries
  drew the baseline and each disclosed "reduced to the default". The residual
  beat its own negation on skill and structure but lowered SSIM (0.3543 to
  0.3514) and sharpness (0.856 to 0.837) against plain advection, so the gate
  refused it. This is the outcome the proposal said would be valid to report,
  and it is reported rather than tuned away.
- The pixels change when a term is admitted: a real Chrome readback with a
  known envelope returns 153 at the midpoint against 128 without it, with the
  endpoints exactly 0 and 255.
- The WEonG-repaired field interpolates markedly better than the published
  one (skill 0.2293 / SSIM 0.484 against 0.1715 / 0.354), supporting the
  finding that opacity weighting rather than motion costs HRDPS its
  structural score.
- Parallel Datamart downloads carried the extra profile at 4.7 MB/s against
  1.5 MB/s serially, with zero 429 responses, fetching an HRDPS run in about
  eight minutes.

Still unverified: the RDPS surface-height datum is reconstructed from surface
pressure in log-pressure rather than read from published orography, and has
not been checked against real terrain; the worker half of the kill switch is
covered by unit tests only; and the WEonG low-level cloud diagnostic fired on
every cell of the one saturated maritime cycle observed, which needs more
regimes before it is trusted.

Nothing here displays a value the system cannot retrieve as if it were
retrieved. The generated term is built only from the same run's own retrieved
fields and the layer's own retrieved frames, is zero at every real instant,
and is named as generated wherever it is drawn.

## Impact

- Classification: Experiment, Spec-Impact: none (experiment-local specs).
- Affected specs: derived-motion-imagery (ADDED, MODIFIED),
  web-evidence-interface (ADDED, MODIFIED), rendered-grid-imagery (ADDED),
  artifact-ingestion (MODIFIED), point-evidence-sampling (ADDED - a derived
  artifact is excluded from sampling on its provenance, not its name, after
  the generated layer reached `/point` and failed the whole response).
- Governing rule: amended by the owner as carve-out (d) in
  `openspec/config.yaml`; (c) retired and subsumed by (d); (a) and (b) stand.
- Affected code: `api/weather_api/store.py` (the data-path boundary),
  `ingest/derive/methods/` (six modules deleted, one added,
  registry and kill switch), `ingest/derive/flow_ops.py`,
  `ingest/derive/methods/harness.py`, `ingest/derive/cloud_motion.py`,
  `ingest/derive/weong_layer.py` (new), `ingest/derive/weong_low_cloud.py`,
  `ingest/adapters/eccc_datamart.py`, `ingest/registry.py`,
  `worker/runtime.py`, `api/weather_api/grids.py`, `api/weather_api/app.py`,
  `api/weather_api/models.py`, `web/src/FlowBlendLayer.ts`, `web/src/api.ts`,
  `web/src/MapPanel.tsx`, `web/src/MethodMenu.tsx`, `web/src/App.tsx`,
  `compose.yaml`, and their tests.
- Data: motion artifacts bump to `cloud-motion-bench-v6` (fields `res_s`,
  `gen_a`, `gen_b` added; `dev_shape` dropped; the `residual` texture keeps
  its name but changes meaning, so the version and header semantics prevent
  a stale client misreading it). New derived artifact `low_cloud_weong` at
  `weong-low-cloud-v1`. HRDPS/RDPS ingest gains 28 optional files per lead
  hour (~750 per run, ~66 MB cropped) against the 25 GiB cap.
- Cost, flagged: generative `configure` multiplies harness runs, and the
  `MethodContext.cache` sharing of baseline motion is load-bearing.
- Rollback: `WEATHER_GENERATED_DISPLAY=off` removes every generated
  construction from derive, `/methods`, `/layers` and the menu without a
  code change; a stored generative menu choice is never restored.
