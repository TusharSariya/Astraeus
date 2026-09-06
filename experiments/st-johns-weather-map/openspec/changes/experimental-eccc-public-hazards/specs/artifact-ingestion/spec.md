## ADDED Requirements

### Requirement: Experimental structured hazards preserve provider content
The isolated hazard adapter SHALL retrieve only explicitly selected ECCC OGC
FeatureCollections under a finite byte limit. It SHALL preserve every geometry
and property without inferring science, record a disposition for every
schema-listed property, and flag additional properties as uncontracted. A
valid empty active collection SHALL be retained as observed-empty; transport,
oversize, malformed JSON, wrong collection shape, or a missing required
collection SHALL be unavailable and SHALL NOT retain a partial product. Until
an owner-approved canonical hazard `RunManifest` exists, the shared one-way
validator SHALL return `complete: false` with `manifest_unresolved`; neither an
empty nor non-empty experimental snapshot is publishable.
An observed-empty snapshot SHALL have no producer run time or valid times. It
SHALL retain the exact requested window and retrieval timestamp as query
provenance without treating either as a source observation time.
Every collection acquisition SHALL retain its exact URL and query, body byte
count and SHA-256, HTTP completion time, and relevant response headers from
discovery through artifact provenance. A multi-collection run's retrieval time
SHALL be the latest required request completion time.

#### Scenario: Hurricane collections are seasonally empty
- **WHEN** every selected hurricane collection returns a valid empty FeatureCollection
- **THEN** all four artifacts are retained together as `observed-empty` and `operational: false`, with `complete: false`, `manifest_unresolved`, `run_time: null`, no producer valid times, and the exact query window and retrieval timestamp

#### Scenario: One required collection is absent
- **WHEN** a hurricane candidate lacks one of the four selected collections
- **THEN** fetch fails before writing any artifact and does not treat the remaining collections as the hurricane product

#### Scenario: Acquisition receipt is missing
- **WHEN** a discovered candidate lacks the receipt for one required collection
- **THEN** fetch is unavailable before writing any artifact rather than reconstructing its request time or headers

#### Scenario: Nonpublishable empty outlook has no API frame
- **WHEN** an observed-empty outlook snapshot has no provider source time and no canonical manifest
- **THEN** its local artifact retains the empty collection and query provenance, while `/layers/{layer_id}/features` has no published frame and invents no source time
