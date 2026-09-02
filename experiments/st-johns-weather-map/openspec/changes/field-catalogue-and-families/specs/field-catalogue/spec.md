## ADDED Requirements

### Requirement: The field catalogue is a versioned registry and the only source of field keys
The deployment SHALL keep a machine-readable field catalogue, versioned and
validated in CI. Every entry SHALL declare a stable key in the project style
(snake case, level suffix for height fields), the physical quantity, the
normalized unit, the level convention, the evidence classes it may carry, the
family it belongs to, and a CF `standard_name` where one exists. No adapter
manifest, derivation method or response field SHALL use a key absent from the
catalogue.

#### Scenario: A manifest names an uncatalogued key
- **WHEN** an adapter manifest declares a field key the catalogue lacks
- **THEN** manifest validation fails naming the key, and the adapter is not schedulable

#### Scenario: A manifest carries the wrong unit
- **WHEN** a manifest declares `temperature_2m` in kelvin and the catalogue says `degC`
- **THEN** validation fails with `bad_units` as it does today, now against the catalogue rather than the adapter's own declaration

### Requirement: One physical quantity per key
Two quantities SHALL never share a key. Where producers publish the same
word for different quantities, the catalogue SHALL carry distinct keys, and
the difference SHALL be recorded in the family's comparability note.

#### Scenario: Opacity-weighted and geometric cloud
- **WHEN** HRDPS total cloud and GFS total cloud are catalogued
- **THEN** they are distinct keys in the cloud-cover family, and the note says they are not comparable

#### Scenario: A time-averaged field
- **WHEN** GEFS six-hour-mean total cloud is catalogued
- **THEN** it is a third key in the family, never served under an instantaneous key

### Requirement: Families carry comparability
Every field SHALL belong to exactly one family. A family SHALL declare which
members are comparable with which, and the reason where they are not. Every
response that serves a field SHALL carry its family and, where more than one
member is present, the comparability between them.

#### Scenario: Two non-comparable members in one response
- **WHEN** `/point` serves HRDPS opacity-weighted cloud and GFS geometric cloud at one instant
- **THEN** both carry `family: cloud_cover` and `comparable: false` with the reason, and neither is presented as a check on the other

#### Scenario: Two comparable members
- **WHEN** `/point` serves HRDPS and RDPS opacity-weighted cloud
- **THEN** both carry `comparable: true`

### Requirement: Humidity phase is a required attribute with a below-freezing rule
Every humidity value SHALL carry its phase (`liquid` or `mixed`) as an
attribute stamped from the producer's own specific humidity, never assumed
from the GRIB code. Two humidity values of different phase SHALL be flagged
not comparable whenever either value's air temperature is below 273.16 K, and
comparable above it.

#### Scenario: Below freezing
- **WHEN** HRDPS (liquid) and GFS (mixed) relative humidity are served at -5 degC
- **THEN** the pair carries `comparable: false` with reason `phase`

#### Scenario: A humidity without a phase
- **WHEN** an adapter publishes a humidity field with no phase attribute
- **THEN** validation fails, because a threshold calibrated on one phase is not transferable

### Requirement: Level conventions
Height fields SHALL carry the level in the key (`_2m`, `_10m`, `_40m`,
`_80m`, `_120m`). Pressure-level fields SHALL be one profile field with a
pressure level coordinate, never one key per level.

#### Scenario: A 40 m field
- **WHEN** HRDPS 40 m temperature is catalogued
- **THEN** its key is `temperature_40m` and it is not a level of the profile field

#### Scenario: A pressure-level field
- **WHEN** relative humidity on 28 pressure levels is catalogued
- **THEN** it is one key with a level coordinate, and `/profile` samples it by level

### Requirement: One catalogue across domains
Meteorology, space weather, marine and astronomy geometry SHALL share one
catalogue, organised as families. Sun and Moon altitude, twilight boundaries,
Moon phase and Moon separation SHALL be catalogue fields of class
`derived_here` from the pinned DE442 ephemeris via a registered method.

#### Scenario: An aurora profile reads two domains
- **WHEN** a profile asks for cloud cover and planetary K index
- **THEN** both resolve in the one catalogue without a cross-catalogue join

#### Scenario: Sun altitude
- **WHEN** Sun altitude is served for a site and instant
- **THEN** it carries `evidence_class: derived_here`, the DE442 source and the geometry method entry

### Requirement: Raw and derived are served side by side
A source SHALL store what it publishes. A derived-here field of the same
family (speed and direction from u and v) SHALL be served beside the raw
values with its own class, and SHALL NOT replace them. A gap a source leaves
(direction from a speed-only product) SHALL stay `null` and SHALL be recorded
in the catalogue's per-source mapping.

#### Scenario: Wind from u and v
- **WHEN** HRDPS publishes u and v at 10 m
- **THEN** u and v are served as `retrieved`, and speed and direction are served beside them as `derived_here` naming the wind registry entry

#### Scenario: Speed-only wind
- **WHEN** REPS publishes wind speed and no components
- **THEN** speed is served, direction is `null`, and nothing derives a direction
