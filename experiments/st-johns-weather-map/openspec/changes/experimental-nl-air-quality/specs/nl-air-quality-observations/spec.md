## ADDED Requirements

### Requirement: The isolated adapter binds the exact provincial station CSV
The experiment SHALL retrieve only the Government of Newfoundland and
Labrador St. John's NAPS Station 010102 rolling CSV through one request capped
at 1 MiB. It SHALL validate the provisional warning, exact ten-column schema
and `StJohns` station identity before creating an artifact, and it SHALL NOT be
registered in the production scheduler.

#### Scenario: The response identity or shape changes
- **WHEN** the warning, schema or station identity differs, a selected value is
  malformed or invalid, or the byte bound is exceeded
- **THEN** retrieval fails closed and no artifact is published

### Requirement: Selected values preserve physical and temporal semantics
The adapter SHALL expose `PM2_5_RUN_AVG` as a 24-hour running-mean surface mass
concentration normalized from µg/m³ to kg/m³ and `O3` as surface mole fraction
retained from ppb as nmol/mol. It SHALL interpret `DATE_TIME` using
`America/St_Johns`, retain local and UTC identity, and explicitly defer PM10,
NO, NO2, NOx, SO2 and CO.

#### Scenario: Ozone lacks atmosphere state for mass conversion
- **WHEN** the CSV supplies ozone in ppb without temperature and pressure
- **THEN** the adapter preserves mole fraction and does not fabricate mass concentration

#### Scenario: A selected value is empty
- **WHEN** a selected CSV cell is empty
- **THEN** the artifact stores missing/null, is incomplete, and does not fill or substitute it

### Requirement: Every value remains provisional experimental evidence
Every selected value SHALL declare `uncalibrated_observation`, unknown quality
with provisional/unvalidated flags, restricted copyright, no redistribution,
no verification or derivation eligibility and `operational: false`.

#### Scenario: Live retrieval and API readback succeed
- **WHEN** the bounded source response becomes an immutable artifact and the
  FastAPI point route reads it successfully
- **THEN** the success does not promote source state, operational status,
  display-primary eligibility or rights
