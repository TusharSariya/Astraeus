## ADDED Requirements

### Requirement: The aurora layer is listed truthfully beside the rendered grids
The layer index SHALL list `noaa-swpc-aurora-oval` only while a fresh aurora
grid artifact is published, in the `rendered_grid` group, with
`evidence_basis: published_artifact`, times exactly the stored forecast
instants, truthful `legend_available`, and semantics stating the values are
OVATION model probabilities rendered by this experiment from the stored NOAA
grid. Absence of the artifact SHALL remove the layer with a notice; nothing
SHALL be invented.

#### Scenario: Listed while fresh
- **WHEN** a fresh aurora grid is published
- **THEN** the layer lists in the rendered-grid group with the stored instant
  as its only time

#### Scenario: Absent artifact, absent layer
- **WHEN** no aurora grid artifact is current
- **THEN** the layer is absent and a notice names the missing feed
