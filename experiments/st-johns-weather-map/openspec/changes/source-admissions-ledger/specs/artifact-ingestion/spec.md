## MODIFIED Requirements

### Requirement: Credentials live only in the environment and their absence is honest
Provider credentials SHALL be read from the environment through one lookup module and nowhere else, and SHALL never be written to an artifact, provenance block, log line, fixture, commit or browser bundle. A missing credential SHALL leave its source honestly non-active with a stated reason; it SHALL NOT crash the worker, disable an unrelated source, or fall through to a substituted value. A source in registry state `credential-required` is admitted and fails closed: with no credential resolved at runtime the adapter SHALL NOT construct or log a prepared URL, SHALL NOT emit a request, SHALL NOT read a fixture on a live path, and SHALL raise `CredentialMissing` for that source alone. The absence SHALL be reported with the record's own reason naming the missing credential, and the source's registry state SHALL be unchanged, because a key that has not arrived is not a demotion and a key that arrives is not a promotion.

#### Scenario: A credential is not configured
- **WHEN** a credential-gated source is attempted with no key in the environment
- **THEN** `CredentialMissing` is raised for that source alone, no evidence is reported for it, no request is prepared or logged, and every other source's run continues

#### Scenario: A key that would appear in a URL
- **WHEN** an error or log message could carry a key supplied as a query parameter
- **THEN** the value is redacted before it is emitted, and a prepared URL carrying a key placeholder is not logged at all

## ADDED Requirements

### Requirement: A restricted-terms source is retrieved for research use and never redistributed
An adapter for a record declaring restricted terms SHALL retrieve for this deployment's own reader only. Its values SHALL NOT be written to any artifact, export, public catalogue payload or shared bundle that leaves this deployment, and any such path SHALL refuse them naming the recorded terms rather than filtering them silently. The record's terms text, its source URL and `redistribution: false` SHALL be carried into provenance for every value, so a reader can see the constraint on the value in front of them. Where the terms are absent from the record, the adapter SHALL NOT run and the field SHALL be absent with the missing terms named, because retrieving under terms nobody recorded is retrieving under terms nobody can honour.

#### Scenario: A research-use value on an export path
- **WHEN** an export or public catalogue payload is assembled and a value from `openmeteo-ukmo-global`, `google-weathernext-2`, `nl-511` or `falchi-night-sky-atlas` would be included
- **THEN** the path refuses that value naming the recorded terms, the rest of the payload is produced, and the refusal is visible rather than a silent omission

#### Scenario: A record declaring restricted terms with no terms text
- **WHEN** an adapter starts for a record whose `redistribution` is `false` and whose terms text is empty
- **THEN** the adapter does not run, the field is absent naming the missing terms, and nothing is fetched

#### Scenario: Provenance carries the constraint
- **WHEN** a research-use value is served at `/point`
- **THEN** its provenance names the terms, their source URL and that redistribution is refused

### Requirement: An admitted source whose endpoint dies fails closed and keeps its state
Where an admitted source's endpoint returns an error, an empty directory that still answers 200, a body that fails schema or content validation, or a response whose every requested column is null, the adapter SHALL treat it as a retrieval failure and SHALL NOT publish an artifact. The failure SHALL be recorded with the source id, the endpoint and the observed condition; the field SHALL be absent with provenance naming that failure; the record's registry state SHALL be unchanged; and no fixture, neighbouring source, previous run or interpolated value SHALL be served in its place on any data path. An all-null column from a source that admits it selects cells by its own policy SHALL be treated as a retrieval failure, not as a measurement of nothing, so that a silent coastal null is never read as calm.

#### Scenario: A directory that answers 200 with only documentation
- **WHEN** a Datamart path returns 200 and contains only `doc/`
- **THEN** the run fails with the empty-listing condition recorded, no artifact is published, the field is absent naming the failure, and the record stays in the state the owner declared

#### Scenario: Every marine column is null
- **WHEN** `openmeteo-gfs-wave` is fetched without `cell_selection=sea`, or returns all-null columns over a coastal cell
- **THEN** the result is a retrieval failure naming the all-null condition, not a published calm sea state

#### Scenario: An empty result that is the answer
- **WHEN** a lightning or radar retrieval succeeds and genuinely detected nothing
- **THEN** the artifact is published as an empty detection with provenance, and it is distinguishable at every layer from a retrieval that failed
