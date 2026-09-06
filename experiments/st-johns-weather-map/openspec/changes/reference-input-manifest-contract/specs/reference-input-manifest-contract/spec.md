# Reference-input manifest contract

## ADDED Requirements

### Requirement: Reference identity and time semantics are explicit

A reference-input manifest SHALL declare source and product identity, immutable revision rule, exact access paths, schema/version identity, required payload fields and units, byte ceiling, raw epoch scale, coverage/effective interval, provider publication time when present, HTTP retrieval completion, and expiry when published. It SHALL NOT invent a model run time or conflate UTC, TAI, TT, TDB, and UT1.

#### Scenario: Calendar date and MJD disagree

- **WHEN** a reference row publishes both a calendar date and MJD that identify different instants in the declared time scale
- **THEN** structural validation fails and the revision is not publishable

### Requirement: Structural QC and scientific suitability are separate

`complete` and `qc_passed` SHALL be computed from the manifest and retrieved payload. Scientific suitability SHALL remain `unknown` unless an accepted consumer profile declares the required version, time coverage, frame, accuracy, and prediction eligibility; successful retrieval or parsing SHALL NOT promote it.

#### Scenario: Kernel parses without an accepted use profile

- **WHEN** every required kernel member and version marker passes structural validation but no accepted consumer profile names it
- **THEN** structural QC may pass while `scientific_status` remains `unknown`
- **AND** no science calculation may consume it

### Requirement: Reference resources carry no invented geography

A non-spatial reference manifest SHALL declare `spatial_scope: not_applicable` or `global_reference`, SHALL carry no fabricated latitude/longitude axes, and SHALL be excluded from point, layer, timeline, consensus, and nearest-time sampling.

#### Scenario: Global time table is read

- **WHEN** a leap-second table is served
- **THEN** it is returned through the dedicated reference-resource route without latitude, longitude, or evidence-box claims

### Requirement: Reference groups publish and read atomically

All artifacts and identity companions required by one reference revision SHALL be staged and integrity-checked before one transaction advances the group pointer. Readers SHALL resolve and verify one complete revision and SHALL NOT combine members from different revisions.

#### Scenario: Companion identity retrieval fails

- **WHEN** a kernel payload arrives but its required version note fails retrieval or validation
- **THEN** no current pointer advances and the prior complete revision remains visible

### Requirement: Reference validity policy is explicit

Each reference source contract SHALL select a temporal policy of `frame_window`, `coverage_interval`, or `effective_table`. The generic manifest SHALL NOT infer an exception from payload shape. Each resource SHALL also declare bounded acquisition size, freshness and expiry. A consumer request SHALL fail closed when the selected policy does not cover its requested interval or the resource has expired.

#### Scenario: Historical leap epochs are present

- **WHEN** a current leap table contains effective boundaries from earlier decades
- **THEN** activation remains blocked until its source contract selects `effective_table`
- **AND** the generic validator does not silently apply or waive weather-window QC

### Requirement: Reference retention is owner-declared within the existing quota

Reference resources SHALL remain under the global storage quota with no cold tier. A source SHALL NOT activate until its accepted contract selects existing frame purge, current-only, or current-plus-previous retention and declares a maximum-byte projection. Expiry SHALL NOT silently select an older expired revision.

#### Scenario: Current table expires

- **WHEN** the provider expiry instant passes before a replacement becomes current
- **THEN** the read route does not substitute its previous revision
- **AND** exact unavailable/grace behavior remains governed by the owner-selected expiry policy
