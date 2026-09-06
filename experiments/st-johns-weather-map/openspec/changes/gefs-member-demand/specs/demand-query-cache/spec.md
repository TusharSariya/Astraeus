## ADDED Requirements

### Requirement: GEFS demand retrieves one bounded native member family
The operational-false experiment SHALL resolve an aware selected timestamp to one provider-native GEFS run and lead. It SHALL request only the seven registered family records from each of the 31 declared member objects, whose provider identities are `gec00` and `gep01` through `gep30`. It SHALL NOT prefetch another lead or a complete run.

Before discovery or payload, the operation SHALL reserve a finite bound covering all retained indexed bodies and selected GRIB ranges, bounded decode concurrency, normalized output, temporary filesystem geometry, subprocess output, and admitted cache backing bytes. A limit that cannot cover the complete simultaneous topology SHALL refuse before provider I/O.

#### Scenario: One selected native lead is requested
- **WHEN** the selected timestamp resolves to an eligible GEFS lead
- **THEN** the canonical cache key names the run, lead, product set, 31 member objects, seven field selectors, and geographic bounds
- **AND** an identical fresh request adds zero discovery, index, or range requests

### Requirement: GEFS member completeness and native intervals remain explicit
The response SHALL preserve every returned member identifier and SHALL identify `gec00` as the provider-declared control. A missing, malformed, oversized, failed-QC, or incomplete member SHALL remain absent with its reason; it SHALL NOT be reconstructed or replaced from another member. The family SHALL enter the existing consensus policy only when its accepted member-completeness and applicability guards pass.

The `total_cloud_mean_6h` record SHALL preserve the exact provider-declared averaging interval. It SHALL NOT be exposed or compared as instantaneous geometric cloud.

#### Scenario: A member range fails
- **WHEN** one declared member cannot return every mandatory selected record
- **THEN** the cached family names that member and failure without inventing values
- **AND** downstream eligibility applies the unchanged incomplete-family policy
