## ADDED Requirements

### Requirement: JMA global pressure completeness follows the producer product

The `openmeteo-jma-gsm` global pressure artifact SHALL require temperature,
wind speed and wind direction at 1000, 925, 850, 700, 600, 500, 400, 300, 250,
200, 150 and 100 hPa. It SHALL require producer RH and intermediary-derived dew
point and cloud at 1000, 925, 850, 700, 600, 500, 400 and 300 hPa. It SHALL
account for vertical velocity and geopotential height at the 12 global levels.

At 975, 950, 900 and 800 hPa every one of the eight field families SHALL be
recorded as unsupported by the global producer product with the returned null
mask. The artifact SHALL NOT interpolate those values, substitute another
model or JMA regional product, relabel missing values, or claim a complete
16-level profile.

#### Scenario: Complete native global inventory

- **WHEN** every required global-product field contains a finite value at each
  required valid time and the API returns nulls at 975, 950, 900 and 800 hPa
- **THEN** source completeness may pass for the 12-level global product, while
  the four unsupported levels and their masks remain explicit

#### Scenario: A native global field is missing

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

Every pressure value SHALL name JMA global GSM as producer and Open-Meteo as
intermediary. RH SHALL retain `raw_phase_unknown`. Dew point and cloud SHALL
identify Open-Meteo as the deriving intermediary and JMA temperature/RH as
inputs. Open-Meteo geometric vertical velocity in `m/s` SHALL remain distinct
from producer omega and from the canonical `Pa/s` field. Geopotential-height
response semantics SHALL remain raw until their unit mapping is accepted.

JMA's native 70, 50, 30, 20 and 10 hPa fields SHALL be recorded as
intermediary-unexposed and SHALL NOT be inferred from the absence of API
arrays. Hourly values SHALL declare Open-Meteo temporal interpolation from the
native six-hourly global forecast, and run identity SHALL remain unknown when
the rolling response supplies no value-level run reference.

#### Scenario: Derived dew point and cloud are retained

- **WHEN** Open-Meteo returns dew point or cloud derived from JMA temperature
  and RH
- **THEN** the value is marked intermediary-derived with its inputs, units,
  valid time and missing mask rather than presented as a JMA producer field

#### Scenario: Upper-level RH-derived fields are unavailable

- **WHEN** a level is 250, 200, 150 or 100 hPa
- **THEN** RH, dew point and cloud are explicitly unavailable while the other
  native field families retain their independent disposition

