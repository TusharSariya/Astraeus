## ADDED Requirements

### Requirement: Provider-declared cloud strata are served as retrieved
`cloud_low`, `cloud_middle` and `cloud_high` SHALL be served only where a
provider itself declares the stratum as a retrievable field (GFS
`LCDC`/`MCDC`/`HCDC` at the provider's low/middle/high cloud layers), with
that provider's `source_id`, units and levels in provenance. They SHALL NOT
be derived from observation cloud layers or from any other field; the
prohibition on deriving strata from METAR/TAF layer reports is unchanged.
Where no provider stratum was retrieved for the coordinate and time, the
three fields SHALL remain null with unavailable provenance, and
`UNAVAILABLE_POINT_FIELDS` SHALL keep listing them.

#### Scenario: GFS strata at a covered coordinate
- **WHEN** `noaa-gfs` published `cloud_low`/`cloud_middle`/`cloud_high` for
  the requested coordinate and time
- **THEN** `/point` returns the three fields in percent with
  `source_id: noaa-gfs` provenance naming the provider's cloud layers

#### Scenario: No provider stratum retrieved
- **WHEN** no source with provider-declared strata published for the
  coordinate and time, even if METAR cloud layers were retrieved
- **THEN** `cloud_low`, `cloud_middle` and `cloud_high` are null with
  `data_mode: "unavailable"` provenance and nothing is derived from the
  layers
