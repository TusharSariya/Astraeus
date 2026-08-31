## ADDED Requirements

### Requirement: The painted stack is stable across real-frame crossings
When display interpolation is on, a locally rendered layer SHALL draw
through the same blend layer at an exact frame as it does between frames
(both frame inputs the real frame, fraction 0, no motion), so the set of
painted map layers is identical on both sides of a real-frame instant and
the reconcile updates in place instead of tearing the stack down. The
output at an exact frame SHALL be exactly the retrieved frame, and no
blend disclosure SHALL be shown for it. With interpolation off, and for
layers that are not locally rendered, the existing raster path is
unchanged.

#### Scenario: Scrubbing across a published frame does not flash
- **WHEN** the scrubber moves from between-frames onto a published frame
  and past it, with interpolation on
- **THEN** no map layer is removed or re-added, the frame paints without a
  blank interval, and the blend note appears only while the instant sits
  strictly between two frames

#### Scenario: Exact frame remains exact
- **WHEN** the selected instant equals a published frame's instant
- **THEN** the drawn pixels are the retrieved frame's (fraction 0
  identity), and the text alternative describes an exact frame, not a
  composite
