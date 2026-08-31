# Design: C1 Hermite multi-frame cloud motion

## The motion model

Per cloud variable, per adjacent pair (k, k+1), the derive already holds
DIS forward flow F_{k->k+1} and backward flow F_{k+1->k} (grid cells).
New: per-knot velocity by QVI central difference (Xu et al., NeurIPS 2019):

    v_k = 1/2 (F_{k->k+1} - F_{k->k-1})

where F_{k->k-1} is pair (k-1,k)'s backward flow, anchored at frame k -
already computed, no new solver runs. Sequence ends use the one-sided
velocity v = F. On segment k the trajectory is the cubic Hermite with
endpoints x_k, x_{k+1} and tangents v_k, v_{k+1}; displacement from the
earlier endpoint on the unit interval:

    d0(t) = v_k t + b t^2 + c t^3
    b = 3F - 2 v_k - v_{k+1}
    c = -2F + v_k + v_{k+1}
    d1(t) = F - d0(t)

Properties: d0(0) = 0 and d1(1) = 0 (endpoint-exact, the real frames show
untouched); adjacent segments share knot velocities so velocity is C1 at
every real frame; v_k = v_{k+1} = F recovers d0(t) = F t - exactly the
shipped linear advection. The blend formula is unchanged:

    C_t(x) = (1-t) C0(x - d0(t,x)) + t C1(x + d1(t,x))

with the same per-pixel forward-backward-consistency confidence gating to
plain crossfade.

Rejected alternatives (citations in
`docs/research/cloud-motion-interpolation.md`):
- Global cubic/spline through all knots: non-local (one bad flow perturbs
  the whole curve) and high-order fits amplify outliers (Velocity
  Disambiguation, arXiv 2311.08007). Hermite is local: an error touches
  two segments.
- Per-interval quadratic (QVI/EQVI as-is): captures curvature but does not
  share knot velocities between segments, so residual snap survives.
- Learned VFI (FILM/RIFE/tracking-based): replaces a transparent, provable
  construction with an opaque one - fails the evidence-honesty bar.
- Sequence-level DARTS/RTS smoothing: kept as a possible pre-filter later;
  smoothing V alone under linear playback still leaves C0 kinks.

## Robustness

- **Consistency collapse:** where the forward-backward check fails at a
  knot (same criterion and threshold as the shipped confidence), that
  knot's tangent is set to the segment's F - the segment degrades to the
  already-approved linear model, then per-pixel confidence degrades to
  crossfade. Graceful ladder: C1 Hermite -> linear advection -> crossfade.
- **Tangent clamping (overshoot):** real accelerations (fronts changing
  speed) can make Hermite arcs overshoot between endpoints. Clamp each
  tangent's deviation: |v - F| <= max(0.5 |F|, 1.0 cells), applied
  per-component-magnitude on the vector deviation (Fritsch-Carlson in
  spirit).
- **Quantization:** tangents are quantized to 8 bits over their own
  per-image scale (headers as for flow); scales are computed from the
  actual max magnitude so the step stays sub-pixel in practice.

## Artifact and API shape

- Zarr `cloud_motion` gains, per cloud variable, dims (pair, y, x):
  `{var}_vs_u`, `{var}_vs_v` (tangent at pair_from), `{var}_ve_u`,
  `{var}_ve_v` (tangent at pair_to), alongside u01/v01/u10/v10/confidence.
  VERSION `cloud-motion-hermite-v2`; provenance names the QVI
  central-difference + Hermite construction and that neighbouring frames'
  flows inform the tangents.
- `/flow?texture=motion` (default): unchanged bytes and headers.
  `/flow?texture=tangents`: RGBA = (vs_u, vs_v, ve_u, ve_v) quantized over
  `X-Weather-Flow-Scale` for that image; same sampler alignment, same
  exact-pair rule, 404 when the artifact predates tangents (client then
  draws linear motion - the weaker approved method, disclosed).

## Client

- MapPanel fetches the tangent texture with the flow texture (same cache,
  prefetch, 'absent' memo). FlowBlendLayer gains u_tangents,
  u_has_tangents, u_tangent_scale_uv; the fragment shader computes b and c
  per pixel and displaces by the cubic.
- **Stack stability:** with interpolation on, a locally rendered layer's
  `exact` resolution draws through the same flowblend entry (frame0 =
  frame1 = the real frame, t = 0, no flow) so the painted layer-id list is
  identical on both sides of a real-frame crossing and the reconcile takes
  the in-place path. The t = 0 identity keeps this honest: the output is
  the retrieved frame, and no blend note is shown for an exact frame.
- Disclosure for a tangent-backed blend: "advection-corrected along motion
  fitted through neighbouring frames (C1 trajectories)"; linear and
  crossfade wordings unchanged.

## Failure modes carried in the register

Orographic/in-place development (motion is the wrong story - out of scope
here, addressed by the staged development-gate change), chaining drift
(bounded: tangents use only +/-1 pair, never long chains), overshoot
(clamped), ghost doubling (confidence gate, unchanged), 8-bit shimmer
(per-image scales).
