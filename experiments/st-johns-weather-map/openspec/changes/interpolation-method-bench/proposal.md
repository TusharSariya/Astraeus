# An interpolation bench: several methods, published together, switchable

## Why

The owner asked what the research says about making interpolation represent
reality more closely, and then chose the better frame: rather than argue for
one lever, build the bench that lets each be implemented independently and
compared. That fits how everything else in this experiment is decided - the
display weight, `SUPPORT_FLOOR` and the veto threshold were all chosen by
held-out skill rather than by argument.

The literature offers four separable levers, none of which is obviously the
winner for hourly 2.5 km cloud fields over the Avalon:

- **Construction fixes, no new data.** The client samples frame 0 at `t·F01`
  and frame 1 at `-(1-t)·F01`, which assumes `F01` inverts exactly - the very
  thing the consistency score measures as violated. Super SloMo (Jiang et al.
  CVPR 2018) approximates the intermediate flow from *both* directions, and
  `F10` is already stored and never served. The two warps are then fused
  `(1-t, t)`; Super SloMo and softmax splatting (Niklaus & Liu, CVPR 2020)
  both find per-pixel visibility weighting to be the main artifact killer at
  motion boundaries. And the display weight varies in space but is
  scale-blind, where pySTEPS' S-PROG and ANVIL decompose into a spatial
  cascade because coarse scales advect faithfully while fine scales
  decorrelate fast.
- **Growth and decay**, the acknowledged hard limit of every advection method
  (Vandal & Nemani, IEEE TGRS 2021, name it as the failure mode; NowcastNet,
  Nature 2023, attacks it with a learned intensity residual). This experiment
  interpolates *model output*, so the model's own vertical velocity says
  where cloud is being made, and a diagnostic closure turns interpolated
  humidity into cloud fraction - the physical route to what NowcastNet learns.
- **Height-resolved steering.** `total_cloud` superposes strata moving at
  different speeds, so no single flow field is correct for it. This is the
  multi-layer AMV problem, where height assignment is up to 70% of the error.
  Both halves are already in the store: GOES-19 ACHAF cloud-top height and
  the 850/700/500 hPa winds.
- **A shorter gap.** Interpolation error grows with the interval, and HRDPS
  is hourly while the GOES-19 ACMF full disk this experiment already ingests
  is ten-minutely. Transferring motion from the frequent product to the
  infrequent one is precisely CMORPH's design.

Estimator choice is measured *not* to be the lever here (0.30 -> 0.33 across
five DIS configurations; pySTEPS reports under 2% spread), so it is ranked
last deliberately.

## What changes

This change ships the bench and, after it, seven methods built against it -
six in parallel worktrees, merged here. `baseline` is what
`cloud-motion-development-v3` already did, and it now runs through the same
machinery as every other.

- **A method registry** (`ingest/derive/methods/`, one module per method):
  one class per method
  declaring how it derives motion from a frame sequence and how it
  composites two frames at a fraction `t`. The composite is the Python
  statement of what that method's shader does, so the held-out harness scores
  every method by its own rule rather than by the baseline's.
- **Every enabled method is derived every cycle**, stored on a leading
  `method` axis with the field names unchanged, so the scores in provenance
  come from the same held-out frames of the same cycle and rank the methods
  directly. Switching is a selection among published fields, never a
  recomputation.
- **A measurement upgrade the bench needs to be honest.** The harness took
  one hard-coded construction, scored at the midpoint, on MAE alone. It now
  takes the method, scores at `t = 1/3, 1/2, 2/3` (a midpoint-only score
  cannot see a construction that is right in the middle and wrong on the way
  there, which is what the reader watches during playback), and reports
  structural similarity beside MAE - because MAE rewards blur, and blur is
  the artifact this bench exists to remove.
- **`GET /methods`** serves the registry with each method's measured skill
  read from provenance, and `/flow?method=` serves one method's fields, named
  back in `X-Weather-Interpolation-Method`.
- **A menu in the timeline dock**, next to the interpolation toggle it
  qualifies, one method at a time. The on-map disclosure names any method
  other than the default.
- **A reserved slot for a generative method**, off by default and flagged
  `generative`, which cannot ship without a carve-out amendment that makes
  the disclosure say the pixels were generated. Flow-estimating networks need
  no such amendment: every displayed pixel still comes from a retrieved frame.
- **Every method declares what it needs** to differ from the default, and the
  menu shows an unmet requirement. Three of the seven reduce exactly to the
  baseline on this deployment - no published cloud-top height, no ingested
  vertical velocity, one GOES scan rather than a sequence - and a method that
  silently reduces to another construction is a control that appears to do
  something. Saying so is what keeps it honest.

## What the bench measured

Seven methods, one cycle, the same held-out frames. Skill against the
reversed-motion control, midpoint:

| layer | baseline | intermediate | visibility | height-steer | dev-residual | goes-transfer |
| --- | --- | --- | --- | --- | --- | --- |
| HRDPS total | 0.2370 | 0.2375 | 0.2358 | 0.2370 | 0.2370 | 0.2370 |
| RDPS total | 0.1251 | 0.1240 | 0.1246 | 0.1251 | 0.1251 | 0.1251 |
| GFS low | 0.3657 | 0.3675 | 0.3651 | 0.3657 | 0.3657 | 0.3657 |
| GFS middle | 0.4197 | 0.4265 | 0.4189 | 0.4197 | 0.4197 | 0.4197 |
| GFS high | 0.3792 | 0.3858 | 0.3785 | 0.3792 | 0.3792 | 0.3792 |
| GFS total | 0.3359 | 0.3383 | 0.3349 | 0.3359 | 0.3359 | 0.3359 |

`scale-cascade` and `flow-net` are registered disabled: the first has no
correct one-pass shader (a four-octave a trous pyramid at the warped sample
point is ~961 texture reads per fragment) and was refused by its own
scale-blind control anyway; the second needs an ONNX runtime and a graph that
are not in the image, and lost to DIS on five of six layers.

The honest summary is that **no construction is the lever here**. One method
is marginally positive, one marginally negative, three inert, two undrawable.
Three findings from the attempt outrank every method in it:

1. **Running DIS on an upsampled field beats native DIS on all six layers**,
   +0.0155 to +0.0398, mean +0.0294, for a `cv2.resize`. Roughly five times
   the best method here, and it is a change to the baseline rather than a new
   plugin. Verified against live artifacts.
2. **HRDPS hourly cloud is remade, not advected.** Two consecutive retrieved
   frames phase-correlate to 0.07-0.66 px while changing by 18.9 %cloud an
   hour. No motion-based construction can win against that, which is why six
   did not.
3. **The observed ten-minute product is the coherent one.** GOES cloud mask
   reconstructs at SSIM 0.618 against HRDPS total cloud's 0.281. The gap
   being interpolated across is the binding constraint, not the algorithm.

## Impact

- Classification: Experiment, Spec-Impact: none (experiment-local specs).
- Affected specs: derived-motion-imagery (ADDED), web-evidence-interface
  (ADDED).
- The evidence rule is unchanged. A method decides how retrieved frames are
  warped and mixed; none may invent content that was not retrieved, and
  endpoint exactness is a property tests pin for every method.
- Affected code: `ingest/derive/flow_ops.py` (new, the primitives extracted
  so a method can be written without touching the derive loop),
  `ingest/derive/methods/` (new package, one module per method),
  `ingest/derive/cloud_motion.py`, `ingest/adapters/goes_abi.py` (retains the
  cloud-top height it already retrieved for parallax),
  `ingest/adapters/eccc_datamart.py`, `ingest/adapters/noaa_s3.py`,
  `ingest/registry.py`, `ingest/grib.py` (optional vertical velocity),
  `api/weather_api/grids.py`, `api/weather_api/app.py`,
  `api/weather_api/models.py`, `web/src/MethodMenu.tsx` (new),
  `web/src/api.ts`, `web/src/TimelineDock.tsx`, `web/src/MapPanel.tsx`,
  `web/src/App.tsx`, and their tests.
- Data: motion artifacts gain a `method` axis. Version bumps to
  `cloud-motion-bench-v4`, so a cycle re-derives. An artifact without the
  axis is read as the single method it was, so a map that worked yesterday
  keeps working.
- Cost: derive time and artifact size grow roughly linearly in the number of
  enabled methods - six are enabled, so the motion artifact carries six slots
  on its method axis. A method that cannot earn its storage is registered
  `enabled = False` rather than deleted, so its code and its last measured
  score stay readable.
- Cost, flagged rather than accepted: retaining `cloud_top_height` grows the
  GOES artifact by 140 percent (237,536 -> 570,323 bytes per scan), which at
  one scan per ten minutes is +48 to +55 MB/day. Its only consumer is
  `height-steering`, which the table above shows is identical to the baseline
  on live data and is structurally capped at 2 of 21 forecast pairs, because
  an observed cloud top is valid at one instant while the layers are
  forecasts to +24 h. `uint16` metres would halve it losslessly against what
  ACHAF resolves. This is the one item in the change whose cost is not
  currently earned.

## Carve-out amendment requested by 7.4 (`height-steering`)

Not applied here. Three methods need amendments this session and the owner
applies them together in one coherent paragraph; this is the exact wording
7.4 needs, in the voice of the existing steering-prior paragraph in
`openspec/config.yaml`, to be appended directly after it.

> That wind's LEVEL may additionally be chosen per cell by a retrieved
> observation of the cloud top over that cell - GOES-19 ABI ACHAF cloud-top
> height, and nothing else (interpolation-method-bench 7.4 2026-09-01) - under
> every one of the four conditions above, unchanged, and under two more. The
> observation contributes no motion of its own: it selects which of the same
> model run's own retrieved 850/700/500 hPa winds a cell takes, interpolated
> between them at the observed height and clamped at the outermost published
> level, never extrapolated beyond it. And where no valid height was retrieved
> for a cell - clear sky, off the observation's grid, a flagged retrieval, or a
> forecast pair with no scan within an hour of it - that cell keeps the
> variable's single steering level exactly, so an absent height is an absent
> height and the construction reduces to the one already permitted above. The
> observed height is display-derivation input only; like the steering winds it
> reaches no reading, and the fraction of cells it actually reached is
> published in provenance so the claim is checkable.

Why an amendment is needed at all: the existing carve-out permits the model
run's own steering wind "and by nothing else", and this crosses a source
boundary - a GOES observation informing a model layer's motion. The narrow
form above is what the method actually does. The observation never becomes a
displacement; it only decides which already-permitted wind a cell reads.

This also makes one data change that is not a display change and needs its own
spec delta, which the owner writes at merge: `ingest/adapters/goes_abi.py` now
RETAINS the ACHAF cloud-top height it was already downloading and already
using to displace pixels, as `cloud_top_height` (float32, metres, NaN wherever
no valid retrieval reached the cell). It is display-derivation input only, in
no served-field map, pinned absent from `FIELD_BY_VARIABLE` and
`DERIVATION_INPUTS` by test.
