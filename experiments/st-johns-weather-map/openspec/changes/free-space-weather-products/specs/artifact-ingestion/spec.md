## ADDED Requirements

### Requirement: Series feeds are retrieved under a byte ceiling and receipted
A coordinate-free series feed SHALL be retrieved by streaming under a declared
byte ceiling, refused mid-stream when it grows past it, and receipted with
URL, request parameters, byte count, SHA-256, capture instant and the
provider's Last-Modified. The receipt SHALL be stored in the artifact's
provenance; the payload SHALL NOT be stored in provenance, in test fixtures
or in Git. A body that is empty, not JSON, or answered with an error status
SHALL be refused as unavailable.

#### Scenario: Oversize feed
- **WHEN** a feed's body exceeds its ceiling
- **THEN** retrieval stops, the scratch file is removed and the adapter
  raises unavailability

#### Scenario: Receipt without payload
- **WHEN** an artifact is published
- **THEN** its provenance `retrieval` block carries the receipt fields and no
  provider bytes
