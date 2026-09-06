## ADDED Requirements

### Requirement: Every production integration has an accepted source contract
Before a production adapter is registered or scheduled, one accepted source
contract SHALL identify exactly one producer product and one actual access path.
It SHALL enumerate all selected upstream fields and every relevant
missing/unsupported/deferred field; canonical mappings; native and normalized
units; levels, grid, projection and resolution; masks and quality flags;
producer run, member, lead, valid, publication and retrieval identity; cadence
and evidence window; licence and each charge surface; provider ceilings and
finite operation bounds; provenance and transformations; API readback shape;
failure behavior; and rollback. It SHALL NOT permit a vendor alias,
`best_match`, new product version or alternate access path to substitute for
the contracted source.

#### Scenario: An adapter exists before its source contract is accepted
- **WHEN** a fixture or exploratory adapter can retrieve and decode a source but its exact source contract is draft or absent
- **THEN** it remains isolated experiment code, is not registered in a production scheduler and cannot claim conforming implementation

#### Scenario: A researched field is deliberately not selected
- **WHEN** the upstream product exposes a relevant field that the integration does not retrieve
- **THEN** the contract records that field as unsupported or deferred with its reason instead of silently omitting it

#### Scenario: An access path returns a similar product
- **WHEN** an aggregator default, alias or fallback resolves to a different producer, product version, member or run
- **THEN** retrieval fails for the contracted source and no substitute artifact is published

### Requirement: Every integration passes the shared five-part evidence gate
Before a source may be considered for promotion, its evidence bundle SHALL link
exact reproducible commands and results for a representative fixture, a bounded
live upstream retrieval, immutable artifact validation, Astraeus API readback,
and absence/failure/provenance tests. The evidence SHALL cover every selected
field, member and required lead, and SHALL prove source/product/run/valid/
publication/retrieval identity, units, masks, quality, missingness, digest and
size. Passing the gate SHALL NOT itself promote registry state or set
`operational: true`.

#### Scenario: Live retrieval succeeds but API readback is absent
- **WHEN** the adapter fetched and validated a real upstream response but no API request proves the stored artifact and its provenance can be read back
- **THEN** the evidence gate remains incomplete and promotion is unavailable

#### Scenario: A field is present only in the fixture
- **WHEN** a selected field is absent, unsupported or renamed in the live product
- **THEN** the live run fails its declared manifest, the previous revision stays visible and the discrepancy is recorded instead of serving the fixture value

#### Scenario: Failure occurs after partial staging
- **WHEN** retrieval, decode, validation or publication fails after one or more artifacts are staged
- **THEN** no logical stream advances, the API reports the source unavailable or its last visible revision according to the accepted failure contract, and the evidence records cleanup and provenance behavior

