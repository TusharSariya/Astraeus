## ADDED Requirements

### Requirement: Cloud motion is derived offline, provenance-chained, and fail-closed
For each published cloud-carrying surface artifact (noaa-gfs strata and
total cloud; eccc-hrdps and eccc-rdps total cloud), the worker SHALL derive
dense optical flow between every pair of adjacent published frames (both
directions) with a forward-backward consistency score, and publish it as one
`cloud_motion` artifact under the same source id. The artifact's provenance
SHALL name the method, a derivation version, and the exact base revision it
was computed from, and SHALL record per-variable quality (pair count,
full-warp MAE vs persistence MAE). A pair whose flow cannot be computed, a
variable with fewer than two frames, or a surface artifact whose bytes fail
their digest SHALL derive NOTHING for that scope - absence is the fallback,
never a guessed field. The artifact SHALL NOT appear in the layer index and
SHALL NOT be sampled by any data path.

#### Scenario: A publish is followed by its motion artifact
- **WHEN** a cloud source's surface artifact is published and the derive
  pass runs
- **THEN** a `cloud_motion` artifact for exactly that revision is published,
  with method, version, base revision and per-variable quality in provenance

#### Scenario: Nothing derivable
- **WHEN** a variable carries fewer than two frames, or the flow solver
  fails for a pair
- **THEN** that scope is absent from the artifact (or the artifact is not
  published at all), and the client crossfades - no motion is invented

#### Scenario: Not a layer, not a reading
- **WHEN** `/layers` and `/point` are read while a `cloud_motion` artifact
  is current
- **THEN** neither lists nor samples it; only the flow endpoint serves it

### Requirement: The flow endpoint serves aligned, quantized, disclosed motion
`GET /layers/{id}/flow` SHALL serve the derived motion for exactly one
adjacent published frame pair (`from`/`to` must match the pair's real
instants) of a rendered-grid layer, resampled to the requested bounds/size
with the same pixel-to-cell rule as the frame raster so flow pixels align
with frame pixels, vectors converted to output pixels and quantized to 8
bits over a per-image scale declared in `X-Weather-Flow-Scale`, consistency
in the blue channel. Responses SHALL carry `X-Weather-Image-Basis:
derived_motion`, the derivation and its version, the two real frame
instants, and `X-Weather-Operational: false`. The endpoint SHALL answer 404
- never a substitute - when the pair, the variable, the motion artifact, or
a motion artifact matching the CURRENT surface revision does not exist, and
404 for any non-rendered-grid layer.

#### Scenario: An aligned texture with its scale
- **WHEN** flow is requested for a published pair over the frame raster's
  own bounds and size
- **THEN** the texture's pixels correspond one-to-one with the frame
  raster's, the declared scale decodes the vectors to output pixels, and
  pixels over no stored cell carry zero flow and zero confidence

#### Scenario: A stale motion artifact is refused
- **WHEN** the surface artifact has moved to a new revision but the motion
  artifact still derives from the old one
- **THEN** the endpoint answers 404 naming the mismatch, and the client
  crossfades until the derive pass catches up

### Requirement: Motion-interpolated display is opt-in, endpoint-exact and disclosed
When the display-interpolation setting is on, a rendered-grid layer's blend
SHALL be drawn by warping the two retrieved frames toward each other along
the pair's derived motion field and cross-dissolving linearly
(advection-corrected interpolation), with per-pixel confidence gating down
to the plain linear crossfade and the plain linear crossfade used entirely
when no motion texture exists. At the two real frame instants the output
SHALL be exactly the retrieved frame. Every pixel drawn SHALL be sampled
from one of the two retrieved frame textures - never generated from
anything else. The on-map disclosure SHALL name the two real frame instants
and the method actually applied ("advection-corrected along a motion field
derived from the two published frames" or "a linear cross-dissolve; no
derived motion field for this pair") and state that it is display only, not
evidence. Observed-group layers SHALL never be interpolated; proxied
forecast imagery keeps the existing stacked display compositing. Data paths
(`/point`, `/features`, stories, readings) SHALL remain frame-exact.

#### Scenario: Scrubbing between two frames with motion
- **WHEN** interpolation is on and the selected instant sits between two
  published frames whose motion texture is held
- **THEN** the cloud field moves along the derived motion as the scrubber
  moves, passes through each real frame untouched, and the corner note
  names both instants and the advection-corrected method

#### Scenario: No motion for the pair
- **WHEN** the flow request answered 404 (or has not yet answered)
- **THEN** the blend is a linear cross-dissolve of the two retrieved frames
  and the note says so - the absence is disclosed, never papered over
