# Believable cloud motion: fix the gate, then let the wind help

## Why

The owner watched playback and said the interpolation "looks very fake, it
looks like blending, not very believable", and "it seems to jump when we get
real data still". Both are correct. Measured from the recording and from the
live API (2026-08-31):

- **The image never moves.** Phase correlation across 12 s of playback (~96
  weather-minutes) finds a displacement of 0 px in every frame pair.
- **Sharpness sawtooths at the real frames**: gradient energy peaks exactly
  at a published frame and dips between it and the next. That is the
  signature of a cross-dissolve, and it is what reads as a "jump" at real
  data. (The structural flash is gone; frame-to-frame difference is flat
  across the crossing.)
- **The derived motion was good and was being thrown away.** For the
  23:00->00:00Z HRDPS pair the flow's median displacement is 45 output
  pixels an hour (~15 grid cells) and warping frame 0 along it cuts MAE
  against frame 1 from 53.4 to 34.7 percent - 35% better than persistence.
- **But the confidence channel was zero for the median pixel** (23% above
  0.5). The shader mixes `mix(plain, warped, confidence)`, so three quarters
  of the map was a plain dissolve.
- **And the gate was not even selecting the right cells**: in the region
  scored exactly zero, warping still beat persistence 31.7 to 52.4.
- **So the C1 Hermite work was inert.** Tangent trust is the minimum
  confidence of the adjacent knots, so the served tangents equalled the
  segment flow: median |v - F| = 0.00 px. Nothing that change shipped was
  ever visible.

Root cause: `CONSISTENCY_LIMIT_CELLS = 2.0` scored forward-backward
agreement against an absolute two-cell tolerance while the field moves ~15
cells an hour - demanding the round trip close to 13% of the displacement,
which DIS on a coarse quantized cloud field never does.

## What changes

- **Relative consistency.** Forward-backward agreement is judged against the
  distance the flow claims (Sundaram, Brox & Keutzer 2010, as a continuous
  score): tolerance `max(1.5 cells, 0.35 |F|)`.
- **Fill, don't drop.** Cells the round trip fails inherit the
  confidence-weighted flow of their trusted neighbourhood (normalized
  convolution); the local trusted density is kept as `support`. An untrusted
  cell drifts with its neighbourhood instead of standing still under a
  moving field, and the advected/dissolved patchwork stops showing seams.
- **A display weight that measures the right thing.** The client now mixes
  on the photometric agreement of the two half-interval warps - does
  advecting these two frames toward each other land on the same picture? -
  gated by support. Chosen by held-out skill: weighting by
  `min(support, agreement)` scored +0.056 against a reversed-flow control on
  HRDPS and +0.351 on GFS; agreement-over-a-support-floor scored +0.090 and
  +0.377.
- **Held-out validation, and a veto.** For each interior frame the two
  neighbours are interpolated to the midpoint by exactly the client's rule
  and compared against the real frame that was held out - against a plain
  crossfade AND against the same construction with the motion reversed. The
  reversed control is the honest baseline: any blend of two warps is
  smoother than a dissolve, and pure noise "improves" on a crossfade by up
  to 2% that way while scoring 0.000 against the control. A variable that
  cannot beat the control by 2% is published with a zero display weight and
  crossfades everywhere.
- **Development-aware dissolve.** Where the two warps disagree - cloud grew
  or decayed in place rather than moved - the weight falls to a crossfade,
  because no motion field can move cloud that was never somewhere else.
- **Steering winds (the staged Phase B2, bundled at the owner's request).**
  HRDPS, RDPS and GFS now ingest 850/700/500 hPa u/v (verified present in
  both providers' listings), declared optional so a missing level costs the
  prior and never the artifact. The derive uses the stratum's steering wind
  only where the imagery is unsupported, weighted by its agreement with the
  trusted image flow, never where a well-supported flow reports the field
  standing still (the orographic in-place-development failure mode this
  peninsula lives in), and only for a variable whose held-out reconstruction
  it measurably improves - with both scores published either way.

Rendering is unchanged: rendered grids keep their hard native cells in every
path (owner decision 2026-08-31). Believability has to come from the motion.

## Impact

- Classification: Experiment, Spec-Impact: none (experiment-local specs).
- Affected specs: derived-motion-imagery (ADDED, MODIFIED).
- `openspec/config.yaml` carve-out amended: the motion field may be informed
  by the same model run's own steering wind under four simultaneous
  conditions (unsupported cells only, agreement-weighted, stationarity-gated,
  and only where held-out skill improves).
- Affected code: `ingest/derive/cloud_motion.py`,
  `ingest/adapters/eccc_datamart.py`, `ingest/adapters/noaa_s3.py`,
  `ingest/registry.py`, `api/weather_api/grids.py`, `web/src/MapPanel.tsx`,
  and their tests.
- Ingest cost: six more single-level GRIB files per lead hour for HRDPS and
  RDPS (~1.4 MB each, well inside the 10 MB per-file ceiling), which at the
  polite client's half-second host interval roughly doubles the HRDPS fetch,
  from about 150 requests per run to about 270. GFS adds six messages to a
  byte-range subset that already stays far under its 25 MB per-lead ceiling.
- Data: `cloud_motion` artifacts gain `{var}_advect_weight`; the surface
  artifacts gain six optional wind fields. Version bumps to
  `cloud-motion-development-v3`, so a cycle re-derives. Older artifacts keep
  serving their consistency in the blue channel rather than 404ing.
