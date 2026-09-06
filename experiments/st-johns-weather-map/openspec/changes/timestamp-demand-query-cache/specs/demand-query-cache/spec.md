## ADDED Requirements

### Requirement: A source query is driven by the selected timestamp
For the isolated experiment, a source query SHALL resolve the client's aware
selected timestamp to a provider-native valid time and retrieve only the
bounded data required for that selection. It SHALL NOT prefetch a complete run
or substitute a neighbouring timestamp merely to fill a cache.

#### Scenario: A provider publishes on a three-hour cadence
- **WHEN** the selected timestamp is not a native valid time and the source contract does not define interval applicability
- **THEN** the query returns an explicit unsupported-time outcome and does not fetch or interpolate adjacent frames

### Requirement: The query cache prevents duplicate provider traffic
A cache entry SHALL be keyed by provider, product, native source/run/valid-time
identity, selected eligible fields and geography. A fresh hit SHALL issue zero
provider payload requests. Concurrent identical misses or revalidations SHALL
coalesce to one bounded upstream operation.

#### Scenario: Two clients request the same missing selection
- **WHEN** both requests resolve to the same canonical provider request key
- **THEN** one upstream operation runs and both responses cite the same fetched content identity

### Requirement: Freshness and failure remain explicit
Each source SHALL derive a finite freshness interval from its provider contract
or recorded evidence. Expired content SHALL NOT be served as current. A failed,
invalid or oversized replacement SHALL NOT overwrite a still-valid entry, and
no stale fallback is permitted unless a later accepted source contract says so.

#### Scenario: Conditional revalidation fails after expiry
- **WHEN** the cached entry is expired and the provider revalidation is unavailable
- **THEN** the response is unavailable with the cached identity and expiry disclosed, and the expired values are not returned as current

### Requirement: Cache use preserves evidence semantics
The normalized cache entry and response SHALL preserve source/product/run,
provider publication and valid times, actual HTTP completion, native units,
geometry, masks, QC, missingness, request identity and content digest. Cache
storage technology is an implementation detail and SHALL NOT imply archive,
two-run retention, source admission or operational status.

#### Scenario: A cached response is served
- **WHEN** a fresh cache entry satisfies the exact canonical request
- **THEN** the response carries the same native evidence identity and retrieval provenance as the validated fill and is labelled experimental
