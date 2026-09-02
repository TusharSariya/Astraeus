## MODIFIED Requirements

### Requirement: Relative humidity is derived only when it was not published
Relative humidity SHALL be taken directly when a source published it. It SHALL
be derived from temperature and dew point only when both are present, the
source published no direct value, and the derivation is an enabled entry in
the derivation method registry. The derived value SHALL carry
`evidence_class: derived_here`, SHALL name the registry entry, its version and
citation, SHALL list both inputs with their provenance, and SHALL carry a
quality no better than the worse input. The derivation SHALL use an explicit
liquid-water phase, because letting the library choose would silently switch
to ice below freezing and change the number. This rule is the general case for
every field: a published field is never replaced by a derivation for that
source.

#### Scenario: A published value is preserved
- **WHEN** the artifact carries a published relative humidity field
- **THEN** that value is used, labelled `retrieved`, and nothing is derived for that source

#### Scenario: One input is missing
- **WHEN** the artifact has temperature but no dew point and no published relative humidity
- **THEN** no relative humidity is derived for that source and the field is `null`

#### Scenario: A derived value is labelled
- **WHEN** relative humidity is derived
- **THEN** the value carries `evidence_class: derived_here`, the registry entry name and version, the citation, both inputs, and the worse input's quality with a `derived` flag

#### Scenario: The registry entry is disabled
- **WHEN** the relative-humidity entry is disabled at any level
- **THEN** the field is `null` with a notice naming the entry, and no unregistered fallback computes it

## ADDED Requirements

### Requirement: Sampling admits or excludes an artifact by its classes
Point, profile and timeline sampling SHALL read each artifact's manifest
classes and SHALL exclude artifacts whose classes include
`generated_display`. Exclusion SHALL never depend on a logical-name match.
Values of class `reprocessed`, `intermediary_derived` and
`uncalibrated_observation` SHALL be sampled and served as non-primary.

#### Scenario: A generated artifact under a new name
- **WHEN** a generated artifact is published under a logical name the sampler has never seen
- **THEN** it is excluded by class and the point response stays frame-exact

#### Scenario: A reprocessed artifact
- **WHEN** a reprocessed artifact covers the coordinate
- **THEN** its value is served, labelled, and the field's primary is chosen from retrieved values only
