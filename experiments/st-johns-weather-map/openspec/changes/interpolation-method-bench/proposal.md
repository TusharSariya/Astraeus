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

This change ships the bench, not the methods. Exactly one method is
registered - `baseline`, which is what `cloud-motion-development-v3` already
did - and it now runs through the same machinery every later method will.

- **A method registry** (`ingest/derive/methods.py`): one class per method
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

## Impact

- Classification: Experiment, Spec-Impact: none (experiment-local specs).
- Affected specs: derived-motion-imagery (ADDED), web-evidence-interface
  (ADDED).
- The evidence rule is unchanged. A method decides how retrieved frames are
  warped and mixed; none may invent content that was not retrieved, and
  endpoint exactness is a property tests pin for every method.
- Affected code: `ingest/derive/flow_ops.py` (new, the primitives extracted
  so a method can be written without touching the derive loop),
  `ingest/derive/methods.py` (new), `ingest/derive/cloud_motion.py`,
  `api/weather_api/grids.py`, `api/weather_api/app.py`,
  `api/weather_api/models.py`, `web/src/MethodMenu.tsx` (new),
  `web/src/api.ts`, `web/src/TimelineDock.tsx`, `web/src/MapPanel.tsx`,
  `web/src/App.tsx`, and their tests.
- Data: motion artifacts gain a `method` axis. Version bumps to
  `cloud-motion-bench-v4`, so a cycle re-derives. An artifact without the
  axis is read as the single method it was, so a map that worked yesterday
  keeps working.
- Cost: derive time and artifact size grow roughly linearly in the number of
  enabled methods. With one method registered that is today's cost; the
  measured size is to be recorded as methods land, and a method that cannot
  earn its storage can be registered `enabled = False`.
