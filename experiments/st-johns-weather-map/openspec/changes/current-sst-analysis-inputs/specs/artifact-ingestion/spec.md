## ADDED Requirements

### Requirement: Current SST analyses preserve producer identity and quality
The experiment SHALL acquire current Met Office OSTIA and NOAA OISST v2.1 as
separate Level-4 SST analysis sources over 45.0 to 50.5 N and 58.0 to 46.0 W.
Each artifact SHALL preserve its analysis time, native grid, native units,
normalized units, uncertainty, missingness, product identity and retrieval
time, and SHALL expose the immutable artifact revision on API readback. OSTIA SHALL additionally retain its native surface mask. OISST SHALL
retain whether a daily file is preliminary or final.

#### Scenario: Current OISST is preliminary
- **WHEN** NCEI publishes the current day only with `_preliminary` in its name
- **THEN** discovery selects it and the artifact carries preliminary identity
  rather than presenting it as final

#### Scenario: A required quality field is missing
- **WHEN** either product omits its declared SST or uncertainty field
- **THEN** the run is refused and no thinner artifact is published

#### Scenario: SST is read for coastal-condition evidence
- **WHEN** an SST artifact is sampled
- **THEN** it reports the retrieved SST and provenance without computing or
  asserting fog, a fog probability or an activity score

### Requirement: Current SST retrieval is bounded and anonymous
The OSTIA adapter SHALL use the time-chunked anonymous Zarr route and download
only native chunks intersecting the evidence box. The OISST adapter SHALL use
the anonymous NCEI daily NetCDF route. Every request SHALL pass through the
shared polite client with a declared byte ceiling.

#### Scenario: An upstream response exceeds its ceiling
- **WHEN** metadata, a native chunk or a daily file exceeds its declared bound
- **THEN** retrieval aborts and the source reports unavailable without
  publishing an artifact
