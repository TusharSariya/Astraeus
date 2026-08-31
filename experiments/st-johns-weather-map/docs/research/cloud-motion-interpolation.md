# Cloud-motion interpolation: research survey

Deep-research survey commissioned by the owner (2026-08-31) after shipping
pairwise advection-corrected interpolation
(`scrub-performance-and-motion-interpolation`) and observing velocity snap
at real-frame crossings. Three parallel reports: the video-frame-
interpolation / graphics literature, the meteorological literature, and
documented industry practice. This document consolidates all three with
citations. It is reference material, not a specification; the normative
requirements live in `openspec/`.

## 1. Terminology

Several fields name overlapping ideas:

- **Temporal interpolation / video frame interpolation (VFI)** - the
  computer-vision umbrella term: synthesize frames *between* two known
  frames. What this experiment does.
- **Frame generation / frame insertion** (NVIDIA DLSS-FG) and **MEMC /
  frame-rate conversion** (TV "motion smoothing") - the real-time,
  latency-bound cousins. Both are pairwise and constant-velocity.
  DLSS-4 "multi frame generation" generates multiple *outputs* per pair;
  its motion model is still anchored on one frame pair
  ([DLSS 3](https://www.nvidia.com/en-us/geforce/news/dlss3-ai-powered-neural-graphics-innovations/),
  [DLSS 4](https://www.nvidia.com/en-us/geforce/news/dlss4-multi-frame-generation-ai-innovations/)).
  TV MEMC (3DRS lineage, de Haan et al.) reuses temporal predictor
  candidates for coherence but interpolates each pair at constant
  velocity.
- **Advection-corrected interpolation** - the meteorological name for the
  construction we ship: warp both endpoint frames along a motion field
  and cross-dissolve, `C_t = (1-t)*C0(x - t*V) + t*C1(x + (1-t)*V)`
  (Anagnostou & Krajewski; pySTEPS advection-correction example).
- **Motion smoothing / temporally consistent optical flow** - making the
  velocity field coherent across a *sequence*, the multi-frame upgrade.
- **Extrapolation / nowcasting** - forecasting past the last frame. Not
  our problem: both endpoints are always retrieved, which is exactly why
  our version can stay honest.

## 2. Candidate families

### 2.1 Pairwise advection (shipped: `cloud-motion-dis-v1`)

OpenCV DIS dense optical flow per adjacent pair, both directions,
forward-backward consistency confidence, endpoint-exact warp-and-dissolve,
per-pixel fallback to linear crossfade. Trajectories are piecewise linear:
position is C0, velocity discontinuous at every real frame - the observed
"jump at the half hour" (frames are hourly UTC; St. John's is UTC-2:30, so
real frames land at :30 local).

### 2.2 Per-interval quadratic: QVI / EQVI

- Xu, Siyao, Sun, Yin, Yang, "Quadratic Video Interpolation", NeurIPS
  2019. Per-pixel constant acceleration from the two flows anchored at a
  frame: velocity `v0 = 1/2 (f_{0->1} - f_{0->-1})` (central difference),
  acceleration `a = f_{0->1} + f_{0->-1}`.
  https://proceedings.neurips.cc/paper/2019/hash/d045c59a90d7587d8d671b5f5aec4e7c-Abstract.html
- Liu, Xie, Siyao, Sun, Qiao, Dong, "Enhanced Quadratic Video
  Interpolation", ECCV Workshops 2020 (AIM winner). Least-squares
  rectification of (v, a) over three anchored flows, with a consistency
  weight falling back to plain QVI. https://arxiv.org/abs/2009.04642
- Caution: high-order *global* fits amplify outliers - a cubic through
  four raw correspondences can perform worse than quadratic ("Velocity
  Disambiguation for Video Frame Interpolation",
  https://arxiv.org/pdf/2311.08007).

Captures curvature; but segments do not share knot velocities, so residual
snap can survive at frame boundaries.

### 2.3 C1 Hermite trajectories from chained flows (chosen: `cloud-motion-hermite-v2`)

Per-segment cubic Hermite (Catmull-Rom) with knot velocities shared
between segments:

    v_k  = 1/2 (F_{k->k+1} - F_{k->k-1})        (QVI central difference)
    d0(t) = v_k t + b t^2 + c t^3               (displacement from frame k)
    b    = 3F - 2 v_k - v_{k+1}
    c    = -2F + v_k + v_{k+1}
    d1(t) = F - d0(t)                           (displacement to frame k+1)

Properties: endpoint-exact (`d0(0)=0`, `d1(1)=0`); C1 at every knot by
construction (shared velocities); local (an error touches two segments);
collapses to the shipped linear model at `v = F`. Precedents: cubic
splines through whole-sequence tracks are the state of the art in
tracking-based VFI (Briedis et al., "Controllable Tracking-Based Video
Frame Interpolation", SIGGRAPH 2025,
https://studios.disneyresearch.com/2025/07/17/controllable-tracking-based-video-frame-interpolation/;
CPFlow, NeurIPS 2023, https://npucvr.github.io/CPFlow/). Runtime cost: one
extra quantized tangent texture per pair; a scrub tick stays one uniform.

### 2.4 Sequence-level motion estimation and smoothing

- **DARTS** (Ruzanski & Chandrasekar): the advection PDE solved by least
  squares over the spatio-temporal DFT of *many* frames (pySTEPS default
  nine) - one smooth motion field explaining the whole sequence. Their
  companion paper is one of the few meteorological works on temporal
  *interpolation* between observed frames: "Weather Radar Data
  Interpolation Using a Kernel-Based Lagrangian Nowcasting Technique",
  IEEE TGRS 53(6), 2015, https://ieeexplore.ieee.org/document/6985678/
- **Variational temporal smoothness**: Weickert & Schnorr, JMIV 2001,
  https://link.springer.com/article/10.1023/A:1011286029287
- **KalmanFlow** (ICIP 2018, https://ieeexplore.ieee.org/document/8451564/);
  offline we could run an RTS smoother over the 20 pairwise fields.
- **pySTEPS / MAPLE / VET**: Pulkkinen et al., GMD 12, 2019,
  https://gmd.copernicus.org/articles/12/4185/2019/ - multi-frame
  Lucas-Kanade accumulation, variational echo tracking, semi-Lagrangian
  integration that interpolates intensities once per full trajectory.
  Calibrating result: flow-estimator choice moved forecast skill by <2%;
  temporal treatment mattered more.
- Kept as a possible pre-filter: smoothing V alone under linear playback
  still leaves C0 kinks, just smaller.

### 2.5 NWP steering-wind priors per cloud stratum (staged follow-on)

- **CIRACast** - Miller, Rogers, Haynes, Sengupta, Heidinger, "Short-term
  solar irradiance forecasting via satellite/model coupling", Solar
  Energy 168, 2018, https://www.osti.gov/pages/servlets/purl/1414069.
  Satellite cloud groups advected along GFS 4-D winds interpolated in
  time, steering level from cloud-top height - explicitly to capture
  "curved flows as opposed to linear extrapolation".
- **Liang et al.**, "Improving Radar Echo Lagrangian Extrapolation
  Nowcasting by Blending Numerical Model Wind Information", Mon. Wea.
  Rev. 148(3), 2020,
  https://journals.ametsoc.org/view/journals/mwre/148/3/mwr-d-19-0193.1.xml.
  WRF winds blended into the VET cost function: useful skill extended by
  about one hour over 16 typhoon cases - the strongest verification that
  a wind prior beats pure image motion.
- **INCA** (Haiden et al., Wea. Forecasting 26, 2011): motion vectors
  QC'd against model winds at 500/700 hPa, blended toward NWP with lead
  time. **STEPS** (Bowler, Pierce, Seed, QJRMS 132, 2006) and pySTEPS
  blending (Imhoff et al., QJRMS 2023) blend the advection field itself
  toward NWP with lead time.
- Conventional steering levels: low cloud ~925-850 hPa (cloud-base-ish -
  EUMETSAT assigns low-level AMVs to cloud *base*), mid ~700-500, high
  ~400-250; better, weight model u/v by the stratum's cloud fraction over
  its levels. AMV background: Apke et al., BAMS 106(2), 2025,
  https://journals.ametsoc.org/view/journals/bams/106/2/BAMS-D-24-0027.1.xml
- Our position is unusually strong: the frames *are* model output, so the
  winds are exactly consistent with the cloud fields. Timing consensus
  (solar CMV literature): image motion beats NWP winds inside ~4 h, so
  for inter-frame interpolation the image flow stays primary and winds
  are prior / low-confidence fill / QC.

### 2.6 Development-aware gating: growth and decay vs motion (staged follow-on)

- The classic failure: **orographic and marine-stratus clouds form and
  dissipate in place while the wind blows through them**. CIRACast
  documents false advection of stationary orographic clouds (Colorado
  Front Range) and marine stratocumulus (California coast) - the exact
  Avalon Peninsula regime. Foresti et al. show terrain-anchored growth/
  decay is climatologically repeatable (QJRMS 144, 2018,
  https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/qj.3364; Wea.
  Forecasting 34, 2019,
  https://journals.ametsoc.org/view/journals/wefo/34/5/waf-d-18-0206_1.xml).
- **NowcastNet** (Zhang et al., Nature 619, 2023) formalizes evolution as
  motion field + intensity-residual under a continuity-inspired loss.
  **MetNet-2/3** ablations show NWP state channels carry real growth/decay
  information (https://www.nature.com/articles/s41467-022-32483-x).
- **Vandal & Nemani**, "Temporal Interpolation of Geostationary Satellite
  Imagery With Optical Flow", IEEE TNNLS 2021,
  https://ntrs.nasa.gov/api/citations/20210020625/downloads/Temporal_Interpolation_of_Geostationary_Satellite_Imagery_With_Optical_Flow.pdf -
  per-pixel visibility maps weighting the two warped endpoints; fails on
  convection, like every advection method.
- For interpolation the task is easier than forecasting: both endpoints
  are known, so development only needs to be *detected*, not predicted -
  photometric disagreement of the two warps, RH tendency, and
  strong-wind-but-zero-flow signatures, baked as a per-pair weight
  between advected blend and in-place crossfade.

### 2.7 Learned VFI (rejected for this experiment)

FILM (ECCV 2022, https://arxiv.org/abs/2202.04901), RIFE, ABME, AMT,
softmax splatting (Niklaus & Liu, CVPR 2020), tracking-based Disney
SIGGRAPH 2025, dense long-range trackers (DOT CVPR 2024, MFT WACV 2024,
CoTracker). State of the art for natural video, but they synthesize
pixels through learned networks - opaque against this experiment's
governing rule that every displayed pixel be traceable to retrieved
frames by a stated, provable construction. WR-Net-style "warp then
refine" (https://arxiv.org/pdf/2303.04405) would invent appearance. The
Vandal & Nemani GOES work shows learned interpolation is viable for
satellite imagery, and its documented failure mode (convection) is the
one §2.6 addresses more cheaply and transparently.

## 3. Industry practice (documented only)

- **Dark Sky** ("How Dark Sky Works", Grossman 2011,
  https://jackadam.github.io/2011/how-dark-sky-works/; HN launch thread
  https://news.ycombinator.com/item?id=3186978): server-side OpenCV
  optical flow; motion shipped as an RGB texture (R=u, G=v, **B =
  intensity change** - growth/decay encoded alongside motion); on-device
  GPU shader for both smooth animation and next-hour extrapolation;
  rolling hindcast verification drives per-storm confidence. The one
  documented commercial pipeline, and architecturally what this
  experiment ships.
- **Apple Weather**: Dark Sky tech confirmed inside
  (https://support.apple.com/en-us/102594); no engineering sources, no
  transferred patents found. The Dark Sky founders launched **Acme
  Weather** in Feb 2026 (TechCrunch); nothing disclosed.
- **ACME AtronOmatic / MyRadar**: server-side GPU re-rendering at high
  frame density (https://acmeaom.com/); patent US11561326B1 - dense
  optical flow + linear advection corrected by a U-Net taking **NWP
  fields as input channels** to restore growth/decay
  (https://patents.google.com/patent/US11561326B1/en).
- **RainViewer**: pysteps-based; "Smooth Radar" is an explicit toggle and
  their blog warns it "may make it appear to be raining ... where it is
  not" (https://www.rainviewer.com/blog/rain-on-the-map-but-not-outside.html).
- **Windy**: staff-confirmed optical flow for satellite animation
  (https://community.windy.com/topic/12184/windy-com-introduces-real-time-satellite-animation);
  users document "ghost rain" smearing from intensity-blind advection
  (https://community.windy.com/topic/43347/radar-interpolation). Wind
  particle animation is the open Mapbox/earth.nullschool technique
  (https://blog.mapbox.com/how-i-built-a-wind-map-with-webgl-b63022b5537f).
- **LibreWXR** (https://github.com/JoshuaKimsey/LibreWXR): open-source;
  interpolates hourly ECMWF frames to 10-minute steps with dense optical
  flow server-side; lead-time-ramped Gaussian coarsening degrades
  interpolated detail honestly.
- **Cross-cutting**: no product documents multi-frame or spline motion
  for display; none blends NWP winds into *display* motion; the shipped
  toggle-off default and endpoint-exact construction already avoid the
  ghost-rain artifact class users complain about elsewhere.

## 4. Failure-mode register

| Failure | Mechanism | Mitigation here |
| --- | --- | --- |
| Orographic / in-place development | clouds form and decay in place; motion is the wrong story | out of scope for hermite-v2; staged development gate (§2.6); confidence gate limits damage |
| Chaining drift | correspondences chained over many frames accumulate error | tangents use only the +/-1 adjacent pairs, never long chains |
| Overshoot at real accelerations | Hermite arcs can bow outside the endpoints when tangents disagree with F | tangent clamping: deviation limited to max(0.5·F, 1 cell) |
| Ghost doubling | the two warped copies disagree mid-pair | forward-backward consistency gate to plain crossfade (shipped) |
| 8-bit quantization shimmer | coarse vector steps at large scales | per-image quantization scales, sub-pixel steps in practice |
| Blank flash at frame crossings | painted stack changed shape at exact frames | exact frames draw through the blend shader at t = 0 (this change) |

## 5. What this experiment ships, in these terms

`scrub-performance-and-motion-interpolation` shipped §2.1 (pairwise
advection, disclosed, endpoint-exact, opt-in). `multi-frame-cloud-motion`
ships §2.3 (C1 Hermite tangents from adjacent pairs) plus the stack
stability fix, with the graceful ladder C1 Hermite -> linear advection ->
crossfade. §2.5 and §2.6 are approved as staged follow-ons, gated on a
visual assessment of hermite-v2 and carrying the §4 orographic warning as
a design constraint. §2.7 stays rejected. All of it is display-only under
the owner-approved carve-out in `openspec/config.yaml`; data paths remain
frame-exact.
