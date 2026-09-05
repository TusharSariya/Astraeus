## ADDED Requirements

### Requirement: Capacity admission accounts for every retained and staged byte
The system SHALL admit a source run only when the two normally retained visible
runs, the complete incoming staged run, incremental bytes retained only by
unexpired snapshot pins, and a conservative measured derived/format/manifest
and sizing-variance allowance fit the 64 GiB hard quota. For each local
filesystem, it SHALL also require every additional allocation made by the
operation, including download/decode temporaries and locally stored staged or
published bytes, plus a measured overhead and sizing-variance allowance to fit
actual free space. It SHALL avoid double-counting the same allocation across
these projections and SHALL reserve the projected filesystem bytes atomically
against concurrent admissions. An unmeasured bound or allowance SHALL block
admission. It SHALL calculate these upper bounds before payload retrieval and
reconcile them to observed bytes after staging. It SHALL NOT infer a fixed
reserve percentage, double-count normally retained runs as pinned bytes or omit
a staged run from publication-peak accounting.

#### Scenario: A third run is staged while two runs are visible
- **WHEN** two complete runs are retained and the next run is considered
- **THEN** admission counts both visible runs and the complete staged run before download

#### Scenario: An unexpired snapshot pins a displaced revision
- **WHEN** a snapshot needs bytes outside the normal two-run inventory
- **THEN** only those incremental bytes count against the pin envelope and total quota until fixed expiry

#### Scenario: A complete-run bound is unknown
- **WHEN** metadata, index, chunk layout or representative retrieval cannot establish a conservative complete-run bound
- **THEN** the run remains non-operational and no unbounded full payload retrieval begins

#### Scenario: Local temporary space is insufficient
- **WHEN** all additional allocations on a filesystem plus its measured allowance exceed unreserved current free space
- **THEN** the operation does not begin even when the projected object-store total is below 64 GiB

#### Scenario: Concurrent operations contend for local space
- **WHEN** two operations would each fit the same currently free bytes but their combined conservative allocations would not
- **THEN** atomic reservation admits at most the operations whose combined bounds fit and refuses the rest before transfer

### Requirement: Source budgets preserve complete admitted products
Every admitted product/access path SHALL have numeric provider-request and rate
ceilings plus finite per-operation received-byte, decode-memory, temporary-disk,
wall-time, concurrency and refresh safety bounds based on real full-field and
full-member evidence. The shared daily direct-feed receive ceiling SHALL be
disabled. Provider limits SHALL be hard ceilings and operation limits SHALL
respect them. Metadata, failed requests and retries SHALL count. Cancellation
and throttle responses SHALL stop work and permit only bounded backoff. A
budget failure SHALL preserve the last visible revision and report
`retrieval_failed` with `upstream_budget_exhausted`. It SHALL NOT reduce an
admitted field, level, ensemble member, native resolution or retention promise,
and SHALL NOT silently substitute another product.

#### Scenario: An operation transfer bound would be exceeded
- **WHEN** the next complete product retrieval would exceed its metadata-derived received-byte bound
- **THEN** retrieval does not begin, the last visible revision remains, and the source reports `upstream_budget_exhausted`

#### Scenario: A provider throttles a batch
- **WHEN** the upstream returns its throttle response
- **THEN** the batch stops, counts the failed request, and retries only after bounded backoff inside the approved budget

### Requirement: Free access is proven per charge surface
Source subscription, requester-pays transfer, query processing, egress and
compute SHALL each be demonstrated to incur no charge before operational
admission. A free dataset listing or successful small response SHALL NOT be
treated as proof that the other charge surfaces are free. A path whose charge
state is unknown or nonzero SHALL remain blocked without enabling billing or
incurring paid use.

#### Scenario: A provider-paid dataset accepts a requester billing project
- **WHEN** the client would attach requester-billing identity even though the dataset does not require it
- **THEN** admission fails until the client is proven not to propagate that identity
