## ADDED Requirements

### Requirement: A generated display term is cited, bounded, gated on a fixed control and switchable
Between two retrieved frames of one layer, the derivation MAY publish a
display term that draws a value in neither frame, only under carve-out (d)
of the governing rule, every condition together. The term SHALL be produced
by a published, cited physical or statistical construction and by nothing
fitted to the pictures it produces; SHALL read only the same model run's own
retrieved fields and the layer's own retrieved frames; SHALL be zero at both
real instants by construction, so every retrieved frame shows untouched;
SHALL be bounded to the variable's physical range and to a published cap;
SHALL be applied only for a variable whose held-out reconstruction it
measurably improves on a FIXED control, on both mean error and structural
similarity, with every score published in provenance whether it was admitted
or not; SHALL be flagged `generative` in the registry, disabled by the
deployment kill switch `WEATHER_GENERATED_DISPLAY=off` before any derive, and
off by default for the reader; and SHALL never reach a data path. A term
whose ingredient is absent SHALL reduce to the permitted advection, say so in
provenance, and never fail the motion artifact. A pair the motion veto
refused SHALL carry a zero term.

#### Scenario: The term at a real frame
- **WHEN** the selected instant is a published frame instant
- **THEN** the generated term is exactly zero there and the retrieved frame
  draws untouched, by algebra rather than by a clamp

#### Scenario: The fixed control is not beaten
- **WHEN** a generated option does not strictly improve the midpoint
  reconstruction over a plain crossfade of the same frames, or lowers its
  structural similarity, or pushes the sharpness ratio further from one
- **THEN** the option is not applied, its scores are still published with
  `applied: false`, and the drawn construction is the one without it

#### Scenario: The ingredient is absent
- **WHEN** the run carries no humidity or vertical velocity at the level the
  term reads
- **THEN** the method publishes its motion with the term absent, records the
  absence in provenance, and the map draws the permitted advection

#### Scenario: The kill switch is off
- **WHEN** `WEATHER_GENERATED_DISPLAY=off` is set for the worker
- **THEN** no generative method is derived, scored or offered, and no
  generated field appears in any artifact of that cycle

#### Scenario: A vetoed pair
- **WHEN** the motion veto refuses a pair
- **THEN** every generated field of that pair is zero, so a field whose
  motion was refused cannot carry a generated term

#### Scenario: A data path asks
- **WHEN** `/point`, `/timeline` or `/features` is read for an instant
  between two frames
- **THEN** the response is frame-exact and carries no generated value

### Requirement: Retired constructions are absent, not disabled
A method that measured worse than the default, or that cannot be drawn, and
that is not a published, cited construction under carve-out (d), SHALL be
deleted from the registry rather than registered disabled. Its identifier
SHALL appear nowhere in code, tests, served responses or the client; its
measured reason for retirement SHALL be recorded in the research record and
the change history so a reader can find it.

#### Scenario: A deleted method is requested
- **WHEN** a request names a method the registry no longer carries
- **THEN** it is refused as an unknown method, never answered with the
  fields of the method that replaced it

#### Scenario: The retirement is findable
- **WHEN** a reader looks for why a former method is gone
- **THEN** the research record names it with the measurement that retired it

## MODIFIED Requirements

### Requirement: A method is scored by the construction it actually draws with
The held-out measurement SHALL evaluate the rule the client applies for the
method being scored, not the rule of any other method. It SHALL reconstruct
held-out frames at more than one fraction of an interval, and SHALL report a
structural measure beside the mean absolute error, because a construction
that dissolves harder is closer on average while being less like the
weather. Methods SHALL be ranked against each other, and any generated term
admitted, only on FIXED controls - a plain crossfade of the same two frames
and linear advection along the baseline flow on the same two frames - never
on a control that moves with the method. Beside mean error and structural
similarity the measurement SHALL report a sharpness ratio, a spectral ratio
error, a fractions skill score at published thresholds and neighbourhoods,
and mean error stratified into cells that grew and cells that decayed. The
reversed-motion control SHALL remain the veto on whether MOTION is displayed
and SHALL be used for nothing else. A method that has not been scored SHALL
publish no score rather than a zero.

#### Scenario: A method whose composite differs from the baseline's
- **WHEN** a method mixes its two warps by a rule of its own
- **THEN** its published score is the error of that rule's reconstruction,
  not of the baseline's

#### Scenario: Right in the middle, wrong on the way there
- **WHEN** a construction reconstructs the midpoint well and the thirds
  badly
- **THEN** the published scores show it, because more than the midpoint is
  measured

#### Scenario: Winning by blurring
- **WHEN** a construction lowers its mean absolute error by dissolving more
- **THEN** its structural score and sharpness ratio fall at the same time,
  so the measures together distinguish a smoother answer from a better one

#### Scenario: Two methods compared
- **WHEN** two methods' scores are compared to rank them
- **THEN** the comparison is on the fixed-control skill of the same held-out
  frames, and the reversed-motion number is not used

#### Scenario: A method that failed on the cells that changed
- **WHEN** a construction reconstructs cells that grew or decayed worse than
  the default while its whole-field error is lower
- **THEN** the stratified scores show it, so a whole-field mean cannot hide
  a development failure

#### Scenario: No held-out frames
- **WHEN** a variable carries too few frames to hold one out
- **THEN** the method publishes no score for it and is shown unscored, never
  as zero skill
