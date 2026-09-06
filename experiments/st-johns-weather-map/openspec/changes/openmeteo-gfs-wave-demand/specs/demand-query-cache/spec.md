## MODIFIED Requirements

### Requirement: Retrieved live evidence is bounded and truthful

For the experimental `openmeteo-gfs-wave` source, `/point?product=GFS+Wave`
SHALL make at most one bounded canonical provider request per fresh identical
coordinate, selected native hour, field set, model, and cell-selection key.
It SHALL request only `ncep_gfswave016`, `cell_selection=sea`, and the nine
catalogued native wave, swell, and wind-wave fields for the selected hour.
It SHALL return only the provider's matching native hour and returned sea-grid
cell, with Open-Meteo intermediary and NOAA/NCEP producer attribution. The
served fields SHALL carry the registered canonical keys `significant_wave_height`,
`wave_period`, `wave_direction`, `swell_height`, `swell_wave_period`,
`swell_wave_direction`, `wind_wave_height`, `wind_wave_period`, and
`wind_wave_direction`. It SHALL expose this reprocessed evidence as readable
non-primary alternatives with evidence-only selection. It SHALL not use a nearby
hour, a stale cache entry, a retained artifact, a producer-run stamp from another
endpoint, or a derived wave quantity.

#### Scenario: Exact native response is available

- **WHEN** a valid exact UTC hourly selection has a fresh provider response
- **THEN** the response carries each valid native field with its documented
  units and provenance, `run_time: null`, `operational: false`, and the
  returned sea-grid coordinate

#### Scenario: One native field is absent

- **WHEN** one requested native field is absent, malformed, or has an unknown
  unit while another requested field validates
- **THEN** that field is null with an explicit native-field-unavailable flag
- **AND** the valid sibling fields remain available

#### Scenario: The sea response carries no value

- **WHEN** every requested native field is null
- **THEN** the source response is unavailable and does not report calm seas

#### Scenario: Cache freshness ends

- **WHEN** the finite source-local cache entry expires and replacement retrieval
  fails
- **THEN** the expired entry is not returned
