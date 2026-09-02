## ADDED Requirements

### Requirement: Non-comparable family members are never drawn as one thing
The interface SHALL group layers and readings by family, SHALL show each
member's key and definition, and SHALL NOT draw two non-comparable members on
one colour ramp, one axis or one difference view without a visible statement
that they are not comparable and why. Switching the map between
non-comparable members SHALL change the legend.

#### Scenario: Switching cloud sources
- **WHEN** the reader switches the cloud layer from HRDPS to GFS
- **THEN** the legend changes to the geometric-overlap definition and the ramp is not presented as the same scale

#### Scenario: A difference view is requested
- **WHEN** the reader asks for HRDPS minus GFS cloud
- **THEN** the interface refuses the difference with the comparability reason, rather than drawing a number

### Requirement: Available-not-stored is shown as such
Where a source publishes a field the deployment does not store, the interface
SHALL show it as available upstream and not stored, distinct from unavailable
and from blocked.

#### Scenario: A GFS field not stored
- **WHEN** the reader opens a GFS field marked `available-not-stored`
- **THEN** the interface says the producer publishes it and this deployment does not store it, and shows no value
