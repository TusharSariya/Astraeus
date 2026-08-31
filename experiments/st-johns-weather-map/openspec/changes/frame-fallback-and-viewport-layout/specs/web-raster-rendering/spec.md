## ADDED Requirements

### Requirement: A blended layer is two retrieved frames composited for display, committed atomically
A display-interpolated layer SHALL consist of exactly two real retrieved
images — the layer's previous and next published frames — drawn at fractional
opacities weighted by the time fraction. Each image SHALL keep its own
`X-Weather-*` provenance and each SHALL individually satisfy the existing
provenance rules before either is drawn. The pair SHALL be committed
atomically: if either image fails retrieval, provenance validation, or arrives
after the selection has moved on, no partial blend SHALL be shown — the layer
falls back to the nearer single frame at its full intended opacity with the
snapped-frame disclosure. The composited pixels are client display derivation:
they SHALL never be stored, sampled, or described as evidence, and the
disclosure SHALL call them display compositing of the two named frames. A
frame image already retrieved for the same layer, frame time and extent SHALL
be reused rather than refetched when it moves between the pair's positions, so
blending stays inside the documented upstream request budget.

#### Scenario: Both frames arrive
- **WHEN** interpolation is on and both neighbouring frames are retrieved with valid provenance for the current selection
- **THEN** both are drawn at opacities weighted by the time fraction, in time order, and the text alternative names both frames and the compositing

#### Scenario: One frame fails
- **WHEN** one of the pair returns an error, invalid provenance, or the selection has moved before it arrives
- **THEN** no half-blend is shown: the nearer retrieved frame is drawn at full intended opacity with the fallback disclosure, or nothing is drawn with the reason stated

#### Scenario: A scrub across a frame boundary reuses images
- **WHEN** the reader scrubs past a published frame so the frame that was "next" becomes "previous"
- **THEN** its already-retrieved image for the same extent is reused, not refetched
