## ADDED Requirements

### Requirement: Fetch-on-miss publishes immutable fragments through a complete manifest
Every adapter eligible for selection-scoped refresh SHALL declare a finite
expected fragment shape keyed by source, provider run, logical artifact, valid
time or interval, field group and member group. Each key SHALL declare fields,
units, geography, level/member/time scope and finite received/staged byte bounds.
An absent or invalid declaration SHALL fail before payload transfer.

The worker SHALL reuse verified retained fragments and fetch only absent keys.
Fragments are immutable. After every expected fragment validates, one database
transaction SHALL publish an immutable manifest referencing the complete set.
Readers SHALL assemble only through a published manifest. Failure or interruption
SHALL leave the prior manifest visible; a selected subset SHALL never replace a
whole aggregate while claiming run completeness.

#### Scenario: One expected fragment is missing
- **WHEN** a manifest retains every key except one selected valid-time/field group
- **THEN** the worker fetches that key only and publishes a new complete manifest without rewriting retained fragment bytes

#### Scenario: Expected shape is unknown
- **WHEN** an adapter cannot enumerate the requested logical artifacts, fields or members with finite bounds
- **THEN** refresh fails before transfer and no generic partial-fetch flag bypasses the refusal

#### Scenario: Publication is interrupted
- **WHEN** new fragments stage but complete-manifest publication does not commit
- **THEN** readers continue through the prior manifest and cannot observe the staged subset
