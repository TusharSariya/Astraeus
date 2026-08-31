# Design

## The interpolation construction

Advection-corrected interpolation between two known frames C0, C1:

```
V      = dense optical flow C0 -> C1   (grid cells per frame interval)
C_t(x) = (1-t) * C0(x - t*V(x))  +  t * C1(x + (1-t)*V(x))
```

Chosen over alternatives on the research findings:
- **Endpoint-exact**: at t=0/1 the warp offsets vanish and the real frame
  shows untouched - the property the evidence rule wants.
- **Growth/decay absorbed by construction**: a cloud present only in C1
  fades in at its advected position instead of popping; where V=0 the
  formula IS the plain crossfade.
- **Model winds rejected as primary motion**: no endpoint consistency
  (visible snap at each real frame), wrong for stationary/regenerating
  cloud (orographic caps), and total cloud has no single steering level.
  Optical flow from the frames themselves captures apparent displacement
  including propagation of formation zones. Winds remain a possible future
  flow prior/QC.
- **DIS (OpenCV) as the estimator**: the choice radar nowcasting
  standardised on (rainymotion Dense models), Apache-2, milliseconds per
  pair at our grid sizes; deep models (RAFT/RIFE/FILM) offer no clear win
  on smooth bounded scalar fields at far higher cost.

Key references (from the two research reports): pySTEPS advection-correction
example (https://pysteps.readthedocs.io/en/stable/auto_examples/advection_correction.html);
Pulkkinen et al. 2019 GMD (pySTEPS); Ayzel et al. 2019 GMD (rainymotion);
Anagnostou & Krajewski lineage (Nielsen 2014, Seo & Krajewski 2015); Shapiro
et al. 2010/2015 (spatially variable advection correction); Vandal & Nemani
2021 (optical-flow temporal interpolation of GOES imagery - the direct cloud
precedent); NVIDIA DLSS 3/4 frame generation (one flow, N intermediates -
the amortisation this design copies); RainViewer's radar animation player
(the closest shipped analogue).

## Division of labour

- **Worker** computes flow offline (seconds per run), because both frames
  are known and the result is reusable by every client: the DLSS lesson -
  one flow field amortised over arbitrarily many intermediate displays.
- **API** serves the flow resampled to the exact frame-raster grid of the
  request, so the shader needs no reprojection: vectors arrive in output
  pixels, quantized over a per-image scale declared in a header (keeps
  8-bit precision tight; a fixed global scale would quantize slow motion
  into shimmer).
- **Client shader** does only warps and mixes of the two retrieved frames.
  Only the alpha channel matters: the frames are the declared
  white-with-alpha colormap, so alpha IS the scalar, and warping the
  texture is warping the value (the "colormap after warp" artifact does not
  arise for a single-hue ramp).

## Artifact modes and their mitigations

- **Ghost doubling** where the two directions disagree (cloud birth/death):
  forward-backward consistency baked into the texture's blue channel;
  low-confidence pixels blend toward the plain crossfade.
- **Halo/dragging at cloud edges**: softened by the Gaussian presmooth
  before flow estimation and the confidence gate; residual halo is bounded
  by the crossfade fallback.
- **Boundary streaking** (HRDPS diamond edge): warp samples clamp at the
  texture edge where frames are already transparent; the visible effect is
  a fade, not a streak of invented cloud.
- **Quantization shimmer**: per-image scale header, not a global constant.

## Publication shape

The motion artifact publishes under the SAME source id with logical name
`cloud_motion` (provider_run_id suffixed `+cloud-motion` so its run rows
never collide with the surface run). That chains its provenance to the base
revision explicitly, reuses stage_and_publish's atomicity, and needs no new
registry "source" for something that is not a retrieval. It is skipped by
the generic layer listing and by `/point` sampling; only `/flow` reads it.
Staleness is structural: the artifact names its base revision, and the API
refuses to serve motion whose base is not the current surface revision.

## Phase-A cache honesty notes

- The server render cache keys include the open dataset's identity plus the
  revision id, so a republished revision can never inherit pixels.
- The 5 s `store.current()` memo is bounded, per store instance, and weakly
  referenced (a test's fake store never answers for another); every layer's
  own staleness tolerance dwarfs it.
- The client's hold-previous state (`refreshing`) keeps the *previous real
  frame under its own timestamp*; the text alternative says exactly that,
  and a failed retrieval still clears to `unavailable` - stale pixels under
  a new timestamp remain forbidden.
- Prefetch is restricted to layers whose rasters this experiment renders
  itself (zero upstream calls), preserving the WMS budget requirement that
  only visible layers spend upstream requests.
