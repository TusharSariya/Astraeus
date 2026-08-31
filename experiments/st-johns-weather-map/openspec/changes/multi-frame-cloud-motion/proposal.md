# Multi-frame cloud motion: C1 trajectories and a stable blend stack

## Why

Scrubbing interpolated HRDPS "jumps around at the half hour mark where we
have real data" (owner, 2026-08-31). Frames are hourly UTC; St. John's is
UTC-2:30, so real frames land at :30 local. Two verified causes:

1. **Structural teardown flash.** At exactly a real frame the resolution is
   `exact` (one slot); either side it is `blend` (two slots). The map-sync
   reconcile compares painted layer ids (`flowblend-<id>` vs
   `raster-<id>-0`), sees a different stack, removes everything and
   rebuilds; the rebuilt shader layer draws nothing until its textures
   decode. Every crossing flashes twice.
2. **Piecewise-linear motion.** Motion is estimated per adjacent pair;
   trajectories follow flow(A->B) then snap to flow(B->C). Velocity is C0
   but not C1 at every knot, so clouds visibly change speed and direction
   in a step at each real frame.

The owner asked for multi-frame curve fitting ("three points creates an
arc, 5 points create an S") and commissioned deep research. Three reports
(VFI/graphics literature, meteorological literature, industry practice;
consolidated in `docs/research/cloud-motion-interpolation.md`) converge:

- The construction is published: QVI (NeurIPS 2019) estimates per-pixel
  knot velocity as the central difference of the flows to the neighbouring
  frames; per-segment cubic Hermite trajectories sharing knot velocities
  are C1 at every real frame by construction, endpoint-exact, and local.
- No documented commercial product (Dark Sky, Apple Weather, ACME
  AtronOmatic/MyRadar, RainViewer, Windy) uses more than a frame pair for
  display motion; NVIDIA DLSS-4 multi frame generation is still anchored
  on one pair. This change goes beyond them by exploiting offline access
  to the whole retrieved sequence.
- The flow-estimator itself is not the lever (pySTEPS: <2% skill spread
  across estimators); temporal consistency is.

## What changes

- **Web (stability):** when interpolation is on, a locally rendered layer
  draws through the blend shader even at an exact frame (frame0 = frame1,
  t = 0, identity by construction), so the painted stack never changes
  shape across a real-frame crossing.
- **Worker:** the cloud-motion derive additionally computes per-knot
  velocities v_k = 1/2(F_{k->k+1} - F_{k->k-1}) from the already-computed
  adjacent flows (one-sided at the sequence ends), clamps tangents against
  overshoot, collapses to v = F where consistency fails, and stores
  per-pair Hermite tangents (v_start, v_end) alongside the existing flow.
  Derivation version becomes `cloud-motion-hermite-v2`.
- **API:** `/layers/{id}/flow` gains `texture=tangents` (RGBA: start/end
  tangent vectors, own quantization scale header); `texture=motion`
  (default) is unchanged. Same alignment, pair matching, and 404
  fail-closed paths.
- **Web (motion):** the blend shader evaluates the cubic Hermite
  displacement d0(t) = v_k t + b t^2 + c t^3 (b = 3F - 2v_k - v_{k+1},
  c = -2F + v_k + v_{k+1}), d1(t) = F - d0(t); without a tangent texture it
  is exactly the existing linear advection; without a flow texture it is
  the plain crossfade. Disclosure names the method actually applied.
- **Governance:** the config carve-out sentence is amended - the disclosed
  motion field may be derived from the layer's retrieved frame sequence
  (neighbouring frames' flows inform knot velocities), still
  endpoint-exact, display-only, never on data paths.
- **Docs:** `docs/research/cloud-motion-interpolation.md` records the
  three research reports, the terminology, all candidate families with
  citations, and the failure-mode register.

Out of scope (staged follow-on, owner-approved sequencing): per-stratum
NWP steering-wind priors and the development-aware advection-vs-crossfade
gate. Both carry the orographic in-place-development failure mode and get
their own change after this one is visually assessed.

## Impact

- Classification: Experiment, Spec-Impact: none (experiment-local specs
  under `openspec/`).
- Affected specs: derived-motion-imagery (ADDED), web-raster-rendering
  (ADDED).
- Affected code: `ingest/derive/cloud_motion.py`, `api/weather_api/grids.py`,
  `api/weather_api/app.py`, `web/src/FlowBlendLayer.ts`,
  `web/src/MapPanel.tsx`, `web/src/api.ts`, tests, `openspec/config.yaml`.
- Data: `cloud_motion` artifacts grow four tangent variables per cloud
  variable; a re-derive replaces them under the same logical name. Old
  artifacts without tangents keep serving linear motion (fail-open to the
  weaker, already-approved method - never to invention).
