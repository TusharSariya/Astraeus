## ADDED Requirements

### Requirement: One selection snapshot binds the existing workbench reads
The existing workbench SHALL open one selection snapshot that fixes its Focus,
selected instant, product, enabled layers, evidence-window boundaries, relevant
atomic manifest revisions, registry and field-catalogue revisions, derivation
versions and absence inventory. `/timeline`, `/layers` and `/point` SHALL accept
only that opaque snapshot identity and SHALL answer from the fixed revision set.
They SHALL NOT contact an upstream provider. A continuation that changes the
selection SHALL be refused.

#### Scenario: Publication occurs between reads
- **WHEN** a new manifest publishes after the snapshot's `/timeline` response and before its `/point` response
- **THEN** `/point` and `/layers` still use the snapshot's original revisions and all three responses name the same snapshot id

#### Scenario: A read would need upstream data
- **WHEN** the selected manifest lacks a requested fragment
- **THEN** the read returns the exact absence and eligible refresh selection without contacting the provider

### Requirement: Selection snapshots expire after fifteen minutes without renewal
A snapshot SHALL set `expires_at` to exactly 15 minutes after its database-server
`selected_at`. Paging, reading, job polling and change checks SHALL NOT extend
that deadline. An expired snapshot SHALL require restart and SHALL NOT be
presented as current. Its capacity SHALL remain charged after expiry until the
durable fenced cleanup path proves all allocations are reconciled.

#### Scenario: A read at the deadline
- **WHEN** database server time reaches the snapshot's `expires_at`
- **THEN** every bound read is refused as expired and no new deadline is minted

#### Scenario: Cleanup has not completed
- **WHEN** the snapshot expired but its pinned bytes have not been exclusively reconciled
- **THEN** its reservation remains charged and can cause a new snapshot admission to fail

### Requirement: Only an explicit selection refresh queues acquisition
A cache miss SHALL NOT itself start acquisition. An explicit refresh SHALL queue
the worker with the canonical missing selection and baseline snapshot. The
durable job SHALL be idempotent while nonterminal and SHALL report progress and
terminal outcomes per requested source and expected fragment. A partial job MAY
publish complete manifests for successful sources but SHALL NOT publish an
incomplete manifest for any source.

#### Scenario: Two identical refresh requests
- **WHEN** the same canonical selection and baseline snapshot are refreshed while its durable job is nonterminal
- **THEN** both responses identify the same job and no duplicate payload fetch begins

#### Scenario: One source fails
- **WHEN** one source publishes a complete manifest and another source fails validation
- **THEN** the job is partial, names both outcomes, and the failed source's prior manifest remains visible

### Requirement: Explicit refresh replaces the visible evidence atomically
Acquisition completion SHALL NOT mutate the active snapshot. After a terminal
job, an explicit replacement SHALL create a new snapshot for the preserved
selection. The client SHALL replace Map, timeline and point together only after
all three validated responses name that new snapshot. A failed member read
SHALL leave the earlier snapshot visible with its identity and age.

#### Scenario: A new manifest is ready
- **WHEN** acquisition succeeds while the earlier snapshot remains open
- **THEN** the UI reports new data available and keeps the earlier values until the reader explicitly replaces them

#### Scenario: Replacement point read fails
- **WHEN** new timeline and layer responses validate but the new point response is unavailable
- **THEN** none of the three visible surfaces adopts the new snapshot

### Requirement: Live-proxy rasters disclose their separate evidence boundary
A live-proxy raster SHALL remain outside the immutable artifact revision set.
Its response SHALL disclose that status and the requested instant, actual served
valid/reference times, retrieval completion and proxy cache status. It SHALL NOT
alter snapshot-bound `/timeline` or `/point` evidence. A served future frame or
a frame at least one hour old SHALL be refused for the existing Map.

#### Scenario: The proxy advances during a snapshot
- **WHEN** a proxy serves a newer image after the snapshot was selected
- **THEN** the image names its actual served time while the snapshot's stored reads and revision identity remain unchanged
