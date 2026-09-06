## ADDED Requirements

### Requirement: GEFS demand retrieves one bounded native member family
The operational-false experiment SHALL resolve an aware selected timestamp to one provider-native GEFS run and lead. It SHALL request only the seven registered family records from each of the 31 declared member objects, whose provider identities are `gec00` and `gep01` through `gep30`. It SHALL NOT prefetch another lead or a complete run.

Before discovery or payload, the operation SHALL reserve a finite bound covering all retained indexed bodies and selected GRIB ranges, bounded decode concurrency, normalized output, temporary filesystem geometry, subprocess output, and admitted cache backing bytes. A limit that cannot cover the complete simultaneous topology SHALL refuse before provider I/O.

#### Scenario: One selected native lead is requested
- **WHEN** the selected timestamp resolves to an eligible GEFS lead
- **THEN** the canonical cache key names the run, lead, product set, 31 member objects, seven field selectors, and geographic bounds
- **AND** an identical fresh request adds zero discovery, index, or range requests

### Requirement: GEFS member completeness and native intervals remain explicit
The response SHALL preserve every returned member identifier and SHALL identify `gec00` as the provider-declared control. Temperature at two metres remains the one mandatory record for admitting a member. A member missing that record SHALL remain absent with its reason. Each of the other six registered records remains optional per member and SHALL carry its own absence reason without erasing an otherwise admitted member. No member or optional value SHALL be reconstructed or replaced from another member. The response SHALL state 31 members declared, the members used for each field, whether each field is partial, whether the control is included, and every known absence reason. It SHALL NOT invent a 31-of-31 eligibility threshold; downstream statistics and consensus SHALL apply only their existing method-specific guards to the resolved member set.

The `total_cloud_mean_6h` record SHALL preserve the exact provider-declared averaging interval start and end parsed from its index label, including the 0-3 hour window at f003 and the labelled window thereafter. It SHALL NOT be exposed or compared as instantaneous geometric cloud.

#### Scenario: A member range fails
- **WHEN** one declared member cannot return mandatory `temperature_2m`
- **THEN** the cached family names that member and failure without inventing values
- **AND** downstream eligibility applies the unchanged incomplete-family policy

#### Scenario: An optional member field is absent
- **WHEN** an admitted member has temperature but lacks one of the other six registered records
- **THEN** the member remains admitted and that field names the member-specific absence
- **AND** the response does not imply that the optional field used all 31 members


### Requirement: GEFS availability uses a bounded exact control index
The operational-false implementation SHALL probe the selected native lead in at most two cycles, starting at the latest six-hour cycle at or before min(selected instant, acquisition clock), then its predecessor. A latency estimate SHALL NOT prove availability or skip a successfully published eligible cycle. The successful index receipt and SHA-256 SHALL bind the canonical request key and cached family. Before I/O the envelope SHALL reserve two additional one-MiB index bodies. Resolution SHALL use a one-entry 600-second cache and 60-second failure backoff. A fresh identical query SHALL add zero discovery, index, range or decode operations.

Failed member-index attempts SHALL be recorded separately from completed-body receipts, with known status (or null), attempt completion, error type and body-not-retained disposition. Successful range receipts SHALL survive subsequent decode failure. Missing mandatory temperature SHALL exclude that member; optional field absence SHALL remain explicit. Existing family QC and storage-scope judgments SHALL remain unchanged.

### Requirement: The response carries the existing consensus result separately
The point response MAY carry a typed consensus summary with availability, server-computed temperature in degC, fixed method, derived-here class, centre range, deterministic contributor IDs, full input evidence, ensemble-witness IDs and refusal reason. It SHALL equal the existing `build_consensus` result over its served fields. Inputs and witnesses SHALL bind to that response. Ensembles SHALL NOT contribute numerically.

The client SHALL show the summary temperature under Consensus only when shape, fixed method/class, input binding and eligible witness binding validate. Missing, unavailable, malformed or unbound summaries SHALL show consensus unavailable without native temperature substitution. The client SHALL NOT recalculate the authoritative mean. Ensemble rows and difference selectors SHALL preserve each served native run, member, control and statistic identity; missing set metadata SHALL NOT erase a member's known run.

#### Scenario: Actual native replay is suspect
- **WHEN** retained f006 contains31 members but DPT absence makes original storage-scope QC suspect
- **THEN** the API retains suspect and Consensus remains unavailable
- **AND** positive Consensus display verification uses separately labelled synthetic contract fixtures
