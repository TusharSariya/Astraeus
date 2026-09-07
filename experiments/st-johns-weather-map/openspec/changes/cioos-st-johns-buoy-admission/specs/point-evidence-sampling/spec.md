## ADDED Requirements

### Requirement: CIOOS buoy evidence is one named native station report

After owner acceptance, the CIOOS `SMA_st_johns` reader SHALL retain only a row
whose `station_name`, finite coordinate pair and native timestamp validate
against its canonical metadata. It SHALL report that row as a named station
observation, never as a grid cell, interpolation, alternate station or model
value. When both finite `precise_lat` and `precise_lon` are present it SHALL
report that pair; otherwise it SHALL report the finite `latitude`/`longitude`
pair. A missing station name, mixed coordinate pair, identity mismatch or
unacceptable selected time SHALL produce unavailable evidence.

#### Scenario: A row lacks a complete native coordinate pair

- **WHEN** a selected row has only one finite precise coordinate and no valid
  fallback pair
- **THEN** no buoy value is emitted and provenance states that native station
  identity was incomplete
