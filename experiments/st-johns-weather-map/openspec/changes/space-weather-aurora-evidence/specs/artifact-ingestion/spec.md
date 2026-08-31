## ADDED Requirements

### Requirement: SWPC feeds are ingested as retrieved, timestamped by themselves
The three SWPC adapters SHALL ingest over polite anonymous HTTPS JSON and
SHALL take every timestamp from the feed's own fields: the Kp series from
their `time_tag`s, the aurora grid from its `Observation Time` and `Forecast
Time`. An aurora payload missing either timestamp SHALL be refused rather
than stamped with the wall clock. The aurora grid SHALL be cropped to the
Atlantic context box and stored in percent as retrieved; the Kp and
solar-wind series SHALL be stored on a bare time axis with no invented
coordinates. An empty or unparseable feed SHALL raise unavailability, never
publish an empty artifact.

#### Scenario: Timestamps from the payload
- **WHEN** the OVATION payload carries Observation and Forecast Time
- **THEN** the artifact's run time is the observation instant and its valid
  time the forecast instant

#### Scenario: A payload without its timestamps is refused
- **WHEN** the OVATION payload lacks its Forecast Time
- **THEN** the run is refused as unavailable and nothing is published

#### Scenario: An empty feed publishes nothing
- **WHEN** a feed answers with an empty list
- **THEN** the adapter raises unavailability and no artifact is created
