## ADDED Requirements

### Requirement: Native GeoJSON is validated without canonical-field invention
A native GeoJSON source MAY declare a structural branch of `RunManifest` that
is mutually exclusive with canonical fields. It SHALL name every required
logical artifact and source collection, the provider's exact property paths,
JSON types and nullability, allowed provider-declared geometry types, time
policy, and required acquisition receipts. Validation SHALL compute the frozen
one-way verdict from the assembled artifacts. It SHALL NOT translate a native
property or geometry into a canonical meteorological field without a separate
accepted science and registry contract.

#### Scenario: Required collection is absent
- **WHEN** one collection required by a native multi-artifact manifest is absent
- **THEN** completeness is false and no artifact from the run is published

#### Scenario: Provider adds an undeclared property
- **WHEN** a feature contains a property outside the pinned source schema
- **THEN** the property is preserved verbatim and reported as uncontracted rather than silently assigned canonical meaning

#### Scenario: Native geometry is malformed
- **WHEN** a feature's geometry is neither null nor a mapping of a provider-declared GeoJSON type
- **THEN** structural validation fails and the run is not publishable

### Requirement: Structural validity is distinct from provider quality
Native-document validation SHALL report local `format_valid` separately from
`provider_qc`. Provider QC SHALL be `unknown` unless the manifest declares an
exact provider QC property and value mapping. The publication gate SHALL be
computed by the shared validator, never asserted by an adapter. Provenance
SHALL state `scope: structural_format` so a passed format check cannot be read
as a scientific-quality claim.

#### Scenario: Structurally valid guidance has no provider QC flag
- **WHEN** every declared structure and receipt check passes but the source supplies no declared QC value
- **THEN** local format is valid, provider QC is unknown, and provenance makes both facts explicit

#### Scenario: Provider explicitly fails quality
- **WHEN** a declared provider QC property maps to failed
- **THEN** the shared verdict fails the publication gate and the prior revision remains current

### Requirement: Query snapshots do not acquire fabricated source times
A source whose manifest declares `query_snapshot` SHALL publish `run_time:
null` and no valid times. Its immutable identity SHALL derive from source id,
schema version and the ordered required collection body digests. Query window,
HTTP completion times and run retrieval time SHALL remain acquisition
provenance and SHALL NOT become a producer frame.

#### Scenario: Active collection is empty
- **WHEN** every required collection returns a valid empty FeatureCollection
- **THEN** the snapshot is structurally complete and observed-empty with no run or valid instant, while retaining its exact query window and receipts

#### Scenario: Replay uses retained receipts
- **WHEN** a retained response is replayed for validation
- **THEN** its original receipt is preserved unchanged and no timestamp or response header is reconstructed

### Requirement: Every native collection has an acquisition receipt
Each required collection SHALL carry the exact URL and query, received body
byte count, body SHA-256, HTTP completion UTC and relevant response headers.
The assembled run's retrieval time SHALL equal the latest required request
completion. A missing or invalid receipt SHALL make the run incomplete.

#### Scenario: One receipt is missing
- **WHEN** all required bodies exist but one required collection receipt does not
- **THEN** publication is refused before any current pointer changes
