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
