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

### Requirement: Reference validity and retention are bounded

Each reference source contract SHALL select `coverage_interval` or `effective_table`; `frame_window` is allowed only with primary evidence that the source publishes frames. A consumer interval SHALL be fully covered. Provider expiry SHALL make current data immediately unavailable without predecessor fallback. A source without provider expiry SHALL remain unavailable until its accepted contract declares `max_age`.

Each atomic acquisition SHALL reserve no more than 64 MiB before retrieval. At most one current and seven superseded revisions per source SHALL be retained. Superseded revisions SHALL be non-routable and evicted after 30 days; a ninth revision SHALL evict the oldest eligible predecessor first. Admission SHALL use the projected retained set under the unchanged global 64 GiB quota and SHALL refuse acquisition rather than evict the sole unexpired current revision.

#### Scenario: Ninth revision arrives

- **WHEN** seven superseded revisions and one current revision already exist and a bounded replacement passes validation
- **THEN** the oldest eligible superseded revision is evicted before the replacement becomes current

#### Scenario: Superseded revision reaches 30 days

- **WHEN** a superseded revision reaches 30 days of audit retention
- **THEN** it is removed even when fewer than eight revisions remain

#### Scenario: Quota cannot admit replacement

- **WHEN** eligible predecessor eviction cannot fit the projected revision group under the global quota
- **THEN** acquisition is refused and the sole unexpired current revision remains current

#### Scenario: Provider publishes no expiry

- **WHEN** a source has no provider expiry and no accepted `max_age`
- **THEN** its resource is unavailable

#### Scenario: Expired bytes remain retained

- **WHEN** current data expires while its bytes remain within audit-retention bounds
- **THEN** the route reports unavailable and does not fall back to a predecessor

### Requirement: Experimental visibility does not authorize science

A structurally valid, scientifically `unknown` revision MAY be visible only through the experimental reference route. Scientific and operational consumers SHALL refuse it until an accepted consumer profile declares it eligible.

#### Scenario: Structurally valid unknown resource is published

- **WHEN** a reference revision passes structural validation without an accepted consumer profile
- **THEN** the experimental route may return it with `operational: false` and `scientific_status: unknown`
- **AND** every scientific and operational consumer refuses it

### Requirement: Representation retention is explicit

Exact raw bytes and normalized form SHALL be retained when provider terms permit. If provider terms prohibit raw retention, the accepted source contract SHALL name the permitted representation and reproducible integrity evidence or activation remains blocked.

#### Scenario: Redistribution forbids raw retention

- **WHEN** provider terms prohibit retaining exact raw bytes and the source contract names no permitted representation and integrity evidence
- **THEN** activation remains blocked
