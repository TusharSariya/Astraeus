# Real-time scrubbing and motion-compensated cloud interpolation

## Why

Scrubbing the timeline was slow and jumpy: the "CHECKING API" status banner
mounted as a flow child of the 100dvh shell on every scrub tick and resized
the whole map (the frame-fallback design called for a reserved row; the
implementation drifted); the drawn frame was removed the moment the next one
missed cache, so the map blanked for seconds; there was no request dedupe,
no prefetch, a 4-frame client cache, full MapLibre source teardown per
frame, ~2048-wide PNG requests, and a server that rebuilt a KDTree and ran
a Python-loop PNG encoder on every request with no render cache. And the
opt-in display interpolation - two stacked rasters at fractional opacities -
composites as 1-(1-a)(1-b), visually a barely-perceptible pulse.

The owner asked for real-time scrubbing and a genuinely smooth, realistic
transition between forecast frames. Two deep-research passes (references in
design.md) converged: the radar-nowcasting literature already names the
right construction - **advection-corrected interpolation** (Anagnostou &
Krajewski; the pySTEPS advection-correction example): dense optical flow
between the two known frames (OpenCV DIS, the estimator radar nowcasting
standardised on), then both frames warped toward each other along the field
and cross-dissolved. It is endpoint-exact (t=0/1 shows the real frames
untouched), absorbs cloud growth/decay by construction, degrades to a plain
crossfade where flow is zero or unconfident, and costs seconds per model
run to precompute. Model winds are deliberately NOT the motion source (no
endpoint consistency; clouds are not materially conserved) - kept only as a
possible future prior/QC.

Owner approvals (2026-08-31, via plan approval): both phases; the evidence
carve-out extended to disclosed, display-only, motion-interpolated frames;
motion interpolation for rendered-grid layers only (proxied and observed
layers unchanged).

## What Changes

Phase A - real-time scrubbing (no synthesized pixels):
- Status banner and the dock snap note become overlays/reserved lines; the
  workspace never reflows on a scrub tick (`styles.css`, `TimelineDock.tsx`).
- MapPanel: a cache miss keeps the previous frame drawn (`refreshing` state,
  own timestamps, fail-closed `unavailable` still clears); MapLibre image
  sources update in place (`updateImage`) instead of teardown; in-flight
  request dedupe; the abort scope is the viewport, not the frame; per-layer
  LRU 4 -> 40; idle-priority prefetch of the full frame axis for locally
  rendered layers only (rendered grids, satellite mask, aurora - zero
  upstream budget; proxied layers stay strictly on-demand).
- Locally rendered rasters are requested at a bounded 1024 px long edge and
  scaled on the GPU with `raster-resampling: nearest` (same stored cells,
  ~10x smaller PNGs).
- Server: the curvilinear pixel-to-cell lookup (KDTree + pitch) is memoised
  per artifact revision and extent; finished PNGs are cached (keyed by
  layer, frame, revision + dataset identity, bounds, size, CRS);
  `store.current()` is memoised 5 s per store instance (weakly referenced);
  the PNG encoder builds its byte stream in one numpy operation.

Phase B - motion-compensated interpolation (display-only, disclosed):
- Worker (`ingest/derive/cloud_motion.py`): after each publish of a cloud
  source (noaa-gfs strata + total, eccc-hrdps/rdps total cloud), DIS flow
  per adjacent frame pair, forward and backward, with a forward-backward
  consistency score and warp-vs-persistence MAE recorded; published as one
  derived `cloud_motion` artifact whose provenance names the method,
  version and exact base revision. A degenerate pair stores nothing.
- API: `GET /layers/{id}/flow?from&to&bounds&size&crs` serves the pair's
  motion as an RGBA texture (R/G = vector over a declared per-image scale,
  B = consistency), resampled with the same pixel-to-cell rule as the frame
  raster so the textures align; `X-Weather-Image-Basis: derived_motion`
  plus derivation headers; 404 when absent (stale base revision included).
  The `cloud_motion` artifact is skipped by the generic layer listing and
  by `/point` sampling: it is not a layer and never a reading.
- Web: rendered-grid blends draw through one custom WebGL layer
  (`FlowBlendLayer.ts`): both real frames warped along the flow and
  linearly cross-dissolved, per-pixel confidence gating down to a plain
  crossfade, and a plain *linear* crossfade when no flow exists - which
  also fixes the 1-(1-a)(1-b) compositing artefact. A scrub tick within one
  pair updates one uniform. The on-map note names the method actually
  applied ("temporally interpolated for display ... advection-corrected" /
  "linear cross-dissolve; no derived motion field for this pair").

## Non-goals

- Proxied (GeoMet live) and observed layers keep their existing behaviour;
  no flow is computed from provider-rendered pixels.
- No extrapolation past the last published frame; motion exists only
  *between* adjacent published frames.
- The backward warp uses the negated forward field; cells where the derived
  backward flow disagreed carry low confidence and crossfade instead (the
  full bidirectional texture is a possible refinement, not shipped).

## Evidence status

Verified by unit test: DIS recovers a known translation; the blend formula
is endpoint-exact; degenerate pairs publish nothing; the flow endpoint
aligns, quantizes and fails closed. Verified live after deploy (tasks 5.x):
worker derives motion for real HRDPS/RDPS/GFS runs and the browser draws
the shader path. Unverified: perceptual quality across many weather
regimes - the QC MAEs recorded per pair are the audit trail for that.
