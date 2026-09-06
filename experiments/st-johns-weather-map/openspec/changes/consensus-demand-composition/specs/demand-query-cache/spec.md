## ADDED Requirements

### Requirement: BLEND composes migrated point demand responses
The live BLEND point path SHALL query each currently migrated, registry-eligible
forecast source for the selected aware instant without reading ArtifactStore.
The source queries SHALL run concurrently within their existing source-local
bounds and caches. A failed, timed-out, malformed, or unavailable source SHALL
be omitted independently and SHALL NOT erase another successful response.

#### Scenario: One source fails
- **WHEN** HRDPS returns validated point evidence and GFS fails
- **THEN** HRDPS remains available with its original source, run, native-valid, retrieval, units, quality, mask, and sampled-cell provenance
- **AND** the response names the omitted GFS demand result
- **AND** no retained GFS or HRDPS artifact is read or substituted

### Requirement: Existing consensus eligibility and calculation govern demand evidence
Demand acquisition SHALL preserve the accepted registry `consensus.eligible`,
centre, category, evidence-class, member, and ensemble-shape rules. It SHALL
feed the existing `_consensus_candidates` policy and `build_consensus`
calculation without changing their minimum evidence, one-representative-per-
centre, or ensemble-distribution semantics. Non-temperature response fields
SHALL remain source evidence but SHALL NOT become new consensus inputs.

#### Scenario: Current migrated deterministic sources lack an ensemble
- **WHEN** current demand evidence contains fresh HRDPS and GFS deterministic values but no eligible demand ensemble family
- **THEN** minimum consensus evidence is not met
- **AND** fresh HRDPS is the truthful primary fallback
- **AND** GFS remains visible as independent supporting evidence with its own provenance

### Requirement: Demand fields remain intact through composition
The BLEND response SHALL return each source's original demand-built evidence
fields without reconstructing storage identity, geometry, missingness, quality,
or units. The consensus eligibility projection MAY read only the attributes the
accepted consensus policy requires and SHALL NOT mutate the returned fields.

#### Scenario: A source carries complete point provenance
- **WHEN** a migrated source returns a field with native time, run, retrieval, sampled cell, mask, units, and quality
- **THEN** the BLEND response carries those values unchanged
