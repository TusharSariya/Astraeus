## ADDED Requirements

### Requirement: Motion confidence is judged relative to the motion it describes
The forward-backward consistency score SHALL judge the round-trip error
against the distance the flow itself claims, with an absolute floor for
near-stationary cells, rather than against a fixed tolerance. A cell whose
own estimate fails that test SHALL inherit the confidence-weighted flow of
its trusted neighbourhood, and the local density of trusted flow behind that
fill SHALL be kept as the cell's support. Where no trusted flow stands behind
a neighbourhood at all, support SHALL be zero and the display SHALL fall back
to the plain crossfade it already discloses.

#### Scenario: A fast cell and a stationary cell with the same round-trip error
- **WHEN** two cells each miss their round trip by two grid cells, one having
  claimed fifteen cells of motion and the other none
- **THEN** the fast cell is trusted and the stationary one is not

#### Scenario: A hole in an otherwise trusted field
- **WHEN** a patch of cells fails the consistency test inside a field that is
  trusted around it
- **THEN** the patch carries its neighbourhood's motion rather than standing
  still, and the cells that were trusted keep their own vectors exactly

#### Scenario: Nothing trustworthy anywhere
- **WHEN** no cell in a neighbourhood passes the consistency test
- **THEN** support is zero there and that area is displayed as a crossfade,
  not as motion nothing stood behind

### Requirement: The display weight measures whether advection explains the change
The weight the client mixes advection against a crossfade on SHALL be the
photometric agreement of the two frames warped to the midpoint along the
flow, gated by the support behind that flow. Where the two warps land on the
same picture the display SHALL advect; where they disagree - cloud having
grown or decayed in place rather than moved - it SHALL dissolve. The weight
SHALL be smoothed in space so the picture does not alternate between the two
rules cell by cell.

#### Scenario: A field that moves
- **WHEN** the same cloud appears displaced between two published frames
- **THEN** the agreement is high there and the display advects along the flow

#### Scenario: Cloud that grows where it stands
- **WHEN** cloud thickens in place between two published frames
- **THEN** the agreement is low there and the display dissolves rather than
  dragging cloud across the map to explain the change

### Requirement: Interpolated motion is validated against frames held out of it
The derivation SHALL measure, for each interior published frame, the error of
reconstructing that frame from its two neighbours by exactly the rule the
client applies, against both a plain crossfade of those neighbours and the
same construction with the motion reversed. Both scores SHALL be published in
the artifact's provenance. A variable whose reconstruction does not beat the
reversed-motion control by a stated margin SHALL be published with a zero
display weight, so it crossfades everywhere rather than presenting motion
that carries no information. Where a sequence is too short to hold a frame
out, the measurement SHALL be absent, never reported as zero.

#### Scenario: Motion that predicts the held-out frame
- **WHEN** the midpoint reconstruction of two neighbouring frames is closer
  to the real frame between them than the reversed-motion control is
- **THEN** the motion is displayed, and both scores are recorded

#### Scenario: Motion that carries no information
- **WHEN** the reconstruction is no better than the same construction with
  its motion reversed
- **THEN** every pair of that variable is published with a zero display
  weight and the client crossfades, disclosed

#### Scenario: Too few frames to validate
- **WHEN** fewer than three frames exist for a variable
- **THEN** the skill measurement is absent from provenance rather than
  reported as a zero improvement

### Requirement: A model steering wind may only fill what the imagery could not read
Where the model run publishes the stratum's steering wind, the derivation MAY
use that wind to fill cells whose image flow is unsupported. It SHALL NOT
override an observed motion; its weight SHALL be proportional to its
agreement with the trusted image flow, so an uncorroborated wind reaches
nothing; it SHALL be refused wherever a well-supported image flow reports the
field standing still; and it SHALL be applied at all only where it improves
the held-out reconstruction, with the scores both with and without it
published. The winds SHALL be declared optional at ingest, and SHALL never
reach a reading, a point response or any other data path.

#### Scenario: The imagery already saw the motion
- **WHEN** a cell's image flow is trusted
- **THEN** its vector is unchanged, however different the model wind is

#### Scenario: Cloud forming in place under a strong wind
- **WHEN** a well-supported image flow reports no motion while the model
  wind blows hard across the same cells
- **THEN** the prior is refused there, because orographic and marine cloud
  over this peninsula forms and dissipates in place while wind passes through

#### Scenario: A wind the imagery contradicts
- **WHEN** the model wind disagrees with the flow in the cells that are
  trusted
- **THEN** its weight falls toward zero everywhere, including in the cells
  the imagery could not read

#### Scenario: A level the provider did not publish
- **WHEN** a cycle carries no wind at the stratum's level
- **THEN** the run still publishes its surface artifact and its motion, with
  the prior simply absent from provenance
