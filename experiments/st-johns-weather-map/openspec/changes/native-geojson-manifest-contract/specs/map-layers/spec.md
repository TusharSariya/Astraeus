## ADDED Requirements

### Requirement: Source-time-less vectors use snapshot identity lookup
A published vector snapshot with no producer run or valid times SHALL NOT gain
a frame in the layer time axis. The layer index MAY expose its current
immutable snapshot identity and query provenance separately. Snapshot features
SHALL be read only by that exact current identity, never by snapping a requested
valid time to retrieval time or query-window boundaries. The current snapshot
SHALL become unavailable more than 86,400 seconds after the latest required
HTTP completion, with no fallback. This ceiling measures acquisition age only
and SHALL NOT be reported as a producer valid time or cadence.

#### Scenario: Valid observed-empty snapshot
- **WHEN** an exact current snapshot identity names a validated empty FeatureCollection
- **THEN** snapshot lookup returns HTTP 200, `features: []`, `observed_empty: true`, its query window, retrieval time, schema version and acquisition receipts

#### Scenario: Snapshot identity is unknown or superseded
- **WHEN** the requested identity is not the current complete run, including when it names the retained previous revision
- **THEN** lookup returns 404 and does not substitute another snapshot

#### Scenario: Current snapshot exceeds its acquisition-age ceiling
- **WHEN** the latest required receipt completion is more than 86,400 seconds old
- **THEN** lookup reports unavailable with an expired reason and does not serve the current or previous snapshot

#### Scenario: Store or integrity failure
- **WHEN** metadata or object storage is unavailable or the stored bytes fail digest verification
- **THEN** snapshot lookup reports unavailable and does not use cached or fixture content

#### Scenario: Frame endpoint receives a query-snapshot layer
- **WHEN** `/features?valid_time=` is used for a layer with no declared source frame
- **THEN** no frame resolves and retrieval time is not substituted
