# GraphCast native point experimental delta

Status: draft. This specification authorizes no production behavior.

## ADDED Requirements

### Requirement: Exact published native identity

The isolated experiment SHALL accept only an explicit NOAA/CIRA
`GRAP_v100_GFS` or `GRAP_v100_IFS` object revision and SHALL verify native
`model_name=graphcast`, initializer, initialization, version, coordinate axes,
units and exact six-hour valid time before returning native `t2` or `msl`.

#### Scenario: A bounded point is decoded

- **WHEN** pinned ranges and native metadata match the selected identity
- **THEN** native values retain K/Pa units, selected coordinate, run/time,
  initializer, publisher version, null masks and range receipts

#### Scenario: A request or native object is ambiguous

- **WHEN** identity, coordinates, time, dimensions, unit, chunk or byte limits fail
- **THEN** the experiment refuses the reading without substitution or publication

### Requirement: Experimental isolation

The module SHALL remain unregistered and SHALL NOT claim GenCast delivery or
operational readiness. An attempt SHALL receive at most 8 MiB in 128 requests,
within 90 seconds, decoding at most two float32 native global planes.

#### Scenario: Production code imports its registry

- **WHEN** the normal API registry loads
- **THEN** this experimental reader is not registered or scheduled
