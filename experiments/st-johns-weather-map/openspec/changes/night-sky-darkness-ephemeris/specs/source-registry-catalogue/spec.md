## ADDED Requirements

### Requirement: A pinned static dataset is catalogued without a schedule
A retrieved-once, checksum-pinned dataset (the DE442 ephemeris) SHALL be a
registry entry like any retrieved source - producer, endpoints, licence,
attribution - with a cadence prose that deliberately does not parse to a
schedule and a freshness of "not applicable", so the ingestion worker SHALL
never schedule it and no freshness verdict SHALL ever be produced for it.

#### Scenario: Registered but never scheduled
- **WHEN** the worker builds its schedule from the registry
- **THEN** `nasa-jpl-de442` is not among the scheduled sources, while it
  remains present in the catalogue with its pinned URL and checksum context

#### Scenario: The registry audit still holds
- **WHEN** the registry audit runs
- **THEN** the entry passes the same schema as every other source
