## ADDED Requirements

### Requirement: Knot velocities make interpolated motion C1 across real frames
The cloud-motion derive SHALL additionally compute, for every interior
published frame k, a per-pixel knot velocity as the central difference of
the two adjacent already-derived flows (v_k = 1/2 (F_{k->k+1} -
F_{k->k-1})), one-sided at the sequence ends, and store each pair's two
Hermite tangents (v at pair_from, v at pair_to) in the same `cloud_motion`
artifact under derivation version `cloud-motion-hermite-v2`. Tangents SHALL
be derived ONLY from the layer's retrieved frames' own flows - never from
another source or model field. Where the knot's forward-backward
consistency fails, the stored tangent SHALL equal the segment's own flow
(collapsing that segment to the previously approved linear advection), and
tangents SHALL be clamped against overshoot. Adjacent segments share knot
velocities, so displayed velocity is continuous at every real frame.

#### Scenario: Tangents from neighbouring pairs only
- **WHEN** the derive runs over a sequence of at least three frames
- **THEN** each interior knot's tangent is the central difference of the
  two adjacent pairs' flows, the ends are one-sided, and provenance names
  the construction and version

#### Scenario: A distrusted knot degrades to linear
- **WHEN** the forward-backward consistency check fails at a knot
- **THEN** the stored tangent equals the segment flow, so that segment
  renders exactly as the linear advection already approved

### Requirement: The tangent texture is served aligned or not at all
`GET /layers/{id}/flow` SHALL accept `texture=motion` (default; the
existing flow texture, unchanged) and `texture=tangents` (RGBA carrying
the pair's start and end tangent vectors, quantized over a per-image scale
declared in `X-Weather-Flow-Scale`, resampled with the same pixel-to-cell
rule as the frame raster). An artifact that carries no tangents, or any
condition that would 404 for the motion texture, SHALL answer 404 - the
client then draws the linear advection or crossfade, never an invented
curve. An unrecognised `texture` value SHALL answer 422.

#### Scenario: Tangents aligned with the frames
- **WHEN** tangents are requested over the frame raster's own bounds/size
- **THEN** pixels correspond one-to-one with the frame raster's, the scale
  header decodes both vectors to output pixels, and pixels over no stored
  cell carry zero tangents

#### Scenario: An old artifact has no tangents
- **WHEN** the current `cloud_motion` artifact predates
  `cloud-motion-hermite-v2`
- **THEN** `texture=tangents` answers 404 and the display uses the linear
  advection with its existing disclosure

### Requirement: Cubic displacement stays endpoint-exact and disclosed
When the display-interpolation setting is on and a pair's tangent texture
is held, the blend SHALL displace along the cubic Hermite d0(t) = v_k t +
(3F - 2v_k - v_{k+1}) t^2 + (-2F + v_k + v_{k+1}) t^3 and d1(t) = F -
d0(t), preserving d0(0) = 0 and d1(1) = 0 so both real frames show
untouched, with the existing per-pixel confidence gate to plain crossfade.
Without tangents the displacement SHALL be exactly the linear advection;
without motion, the plain crossfade. The disclosure SHALL name the method
actually applied, including that curved motion is fitted through
neighbouring retrieved frames, and remain display only, never evidence.

#### Scenario: No snap at a real frame
- **WHEN** the scrubber crosses a published frame with tangent-backed
  blends on both sides
- **THEN** the drawn cloud velocity is continuous through the crossing
  (shared knot velocity), and at the frame instant the output is exactly
  the retrieved frame

#### Scenario: Fallback ladder is honest
- **WHEN** the tangent texture is absent but motion is held, or both are
  absent
- **THEN** the blend is respectively the linear advection or the plain
  crossfade, and the note names the method actually in use
