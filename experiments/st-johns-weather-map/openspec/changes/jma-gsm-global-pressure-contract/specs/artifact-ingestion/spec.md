## ADDED Requirements

### Requirement: JMA global pressure completeness follows the producer product

After owner acceptance of a response-provenance rule, the
`openmeteo-jma-gsm` global pressure artifact SHALL require temperature,
wind speed and wind direction at 1000, 925, 850, 700, 600, 500, 400, 300, 250,
200, 150 and 100 hPa. It SHALL require producer RH and intermediary-derived dew
point and cloud at 1000, 925, 850, 700, 600, 500, 400 and 300 hPa. It SHALL
account for vertical velocity and geopotential height at the 12 global levels.

At 975, 950, 900 and 800 hPa every one of the eight field families SHALL be
recorded as unsupported by the global producer product with the returned null
mask. The artifact SHALL NOT interpolate those values, substitute another
model or JMA regional product, relabel missing values, or claim a complete
16-level profile.

#### Scenario: Complete candidate global inventory after provenance acceptance

- **WHEN** every required global-product field contains a finite value at each
  required valid time and the API returns nulls at 975, 950, 900 and 800 hPa
- **THEN** source completeness may pass for the 12-level global product, while
  the four unsupported levels and their masks remain explicit

#### Scenario: A candidate global field is missing

- **WHEN** temperature, wind, required RH-derived evidence, vertical velocity,
  or geopotential height is null or omitted at one of its required native
  global levels and valid times
- **THEN** the source artifact is incomplete and cannot publish

#### Scenario: A consumer requires all 16 levels

- **WHEN** a consumer requires canonical evidence at 1000, 975, 950, 925, 900,
  850, 800, 700, 600, 500, 400, 300, 250, 200, 150 and 100 hPa
- **THEN** the 12-level global source does not satisfy that consumer even when
  its own source-completeness verdict passes

### Requirement: JMA pressure provenance distinguishes production and derivation

Every pressure value SHALL record the caller-selected `models=jma_gsm` access
path and Open-Meteo as intermediary. It SHALL NOT claim response-level model
or run identity when the response does not provide it. Producer-origin RH
SHALL retain `raw_phase_unknown`. Dew point and cloud SHALL identify
Open-Meteo as the deriving intermediary and JMA temperature/RH as inputs.
Open-Meteo geometric vertical velocity, formatted in the requested wind-speed
unit, SHALL be marked as derived from producer omega and temperature and remain
distinct from the canonical `Pa/s` field. Geopotential-height response
semantics SHALL remain intermediary-reprocessed until their conversion is
accepted.

JMA's native 70, 50, 30, 20 and 10 hPa fields SHALL be recorded as
intermediary-dropped by the pinned ingest path and SHALL NOT be inferred from
the absence of API arrays. Hourly values SHALL record intermediary temporal
processing; they SHALL NOT claim a specific producer run or interpolation
method when the rolling response supplies no value-level run reference.

#### Scenario: Derived dew point and cloud are retained

- **WHEN** Open-Meteo returns dew point or cloud derived from JMA temperature
  and RH
- **THEN** the value is marked intermediary-derived with its inputs, units,
  valid time and missing mask rather than presented as a JMA producer field

#### Scenario: Upper-level RH-derived fields are unavailable

- **WHEN** a level is 250, 200, 150 or 100 hPa
- **THEN** RH, dew point and cloud are explicitly unavailable while the other
  native field families retain their independent disposition
