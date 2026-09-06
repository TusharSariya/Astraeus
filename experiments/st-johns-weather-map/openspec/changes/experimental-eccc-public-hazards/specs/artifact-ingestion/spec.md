## ADDED Requirements

### Requirement: Experimental structured hazards preserve published content
The isolated hazard adapter SHALL retrieve only explicitly selected ECCC OGC
FeatureCollections under a finite byte limit. It SHALL preserve every geometry
and property without inferring science, record a disposition for every
schema-listed property, and flag additional properties as uncontracted. A
valid empty active collection SHALL publish as observed-empty; transport,
oversize, malformed JSON, wrong collection shape, or a missing required
collection SHALL be unavailable and SHALL NOT publish a partial product.

#### Scenario: Hurricane collections are seasonally empty
- **WHEN** every selected hurricane collection returns a valid empty FeatureCollection
- **THEN** all four artifacts are complete, `observed-empty`, and `operational: false`

#### Scenario: One required collection is absent
- **WHEN** a hurricane candidate lacks one of the four selected collections
- **THEN** fetch fails before writing any artifact and does not treat the remaining collections as the hurricane product

#### Scenario: Stored outlook reads through the API
- **WHEN** a retrieved outlook GeoJSON artifact is opened by the live artifact reader
- **THEN** `/layers/{layer_id}/features` returns its original properties with source and run provenance and `operational: false`
