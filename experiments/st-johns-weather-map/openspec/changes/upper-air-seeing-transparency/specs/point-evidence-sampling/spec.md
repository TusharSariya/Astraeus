## ADDED Requirements

### Requirement: Upper-air winds are served only as disclosed derivations
The stored upper-air wind components (`wind_u_200hPa`, `wind_v_200hPa`,
`wind_u_300hPa`, `wind_v_300hPa`) SHALL never be served as point evidence
fields. Point evidence SHALL offer `wind_speed_200hPa` /
`wind_direction_200hPa` and `wind_speed_300hPa` / `wind_direction_300hPa`
derived from both components via the same disclosed MetPy derivation used for
10 m wind, with the derivation and its version in provenance and the
vertical level stated. A missing component SHALL yield no derived field.
`precipitable_water` SHALL be served exactly as stored (kg m-2) with full
provenance. No seeing index, seeing category, or observability verdict SHALL
be computed from these fields.

#### Scenario: Derived pair from stored components
- **WHEN** both `wind_u_200hPa` and `wind_v_200hPa` sample at the requested
  point and instant
- **THEN** the response carries `wind_speed_200hPa` and
  `wind_direction_200hPa` with the MetPy derivation and version in
  provenance, and carries neither raw component

#### Scenario: One component missing
- **WHEN** only one 300 hPa component is available
- **THEN** no 300 hPa wind field of any kind is served

#### Scenario: No upper-air artifact
- **WHEN** the published GFS run carries no `upper_air` artifact
- **THEN** the upper-wind fields are absent from the response - not zero,
  not carried over from an older run

#### Scenario: Precipitable water as stored
- **WHEN** `precipitable_water` samples at the requested point
- **THEN** it is served with its stored value and units and no derived
  transparency verdict accompanies it
