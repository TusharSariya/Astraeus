## ADDED Requirements

### Requirement: RAQDPS and RDAQA use dimensionally exact canonical air-quality keys
The catalogue SHALL reuse `pm2_5_surface`, `pm2_5_column`, `pm10_surface`, and `ozone_surface_mole_fraction`. It SHALL add `pm10_column`, surface mole-fraction keys for nitric oxide, nitrogen dioxide and sulphur dioxide, four wildfire-attributed surface/column PM2.5/PM10 keys, and wildfire-attributed surface PM2.5 24-hour mean and maximum keys exactly as listed in the approved design. Surface mass SHALL use `kg m-3`, column burden `kg m-2`, and gas mole fraction `nmol mol-1`. A gas mole fraction SHALL NOT map to an existing mass-concentration key.

#### Scenario: GeoMet gas arrives in mol/mol
- **WHEN** O3, NO, NO2 or SO2 is decoded from a selected GeoMet coverage in `mol mol-1`
- **THEN** each finite value is multiplied by exactly 1e9 and stored in its canonical `nmol mol-1` mole-fraction key
- **AND** provenance retains the original unit and scale factor
- **AND** missing values remain missing, non-finite values are refused, and verification allows at most one ULP of the expected binary64 result

#### Scenario: PM10 entire-atmosphere coverage arrives
- **WHEN** `RAQDPS.EATM_PM10` is decoded in `kg m-2`
- **THEN** it maps to `pm10_column` and never to `pm10_surface`

### Requirement: Wildfire attribution remains a producer product attribute
Selected RAQDPS wildfire-plume and RDAQA FireWork-contribution particulate fields SHALL use the wildfire canonical keys and SHALL declare `attribution: producer_wildfire_smoke_contribution`. That attribute SHALL NOT be presented as an independently verified source-apportionment result or substituted for total particulate mass.

#### Scenario: FireWork-contribution analysis is available
- **WHEN** the RDAQA FireWork PM2.5 and PM10 coverages validate
- **THEN** they retain wildfire attribution and cannot satisfy total `pm2_5_surface` or `pm10_surface`
