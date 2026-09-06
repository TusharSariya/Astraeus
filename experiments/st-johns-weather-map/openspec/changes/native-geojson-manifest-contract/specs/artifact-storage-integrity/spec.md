## ADDED Requirements

### Requirement: Native snapshot runs publish atomically
A native GeoJSON run that passes its approved structural manifest SHALL use the
existing immutable-object staging and single `publish_run` transaction for all
required artifacts. Validation or publication failure SHALL leave the prior
current run unchanged. Source-time-less snapshots SHALL follow the existing
latest-and-previous complete-run retention rule and SHALL NOT participate in
valid-time window arithmetic.

#### Scenario: Fourth hurricane artifact fails validation
- **WHEN** three required artifacts validate and the fourth fails
- **THEN** none become current and the previously visible four-artifact run remains usable

#### Scenario: Query window overlaps the evidence window
- **WHEN** a source-time-less snapshot's query window overlaps the configured evidence window
- **THEN** that overlap does not manufacture valid-time retention eligibility
