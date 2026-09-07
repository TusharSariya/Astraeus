# ECCC analysis experimental integration

## ADDED Requirements

### Requirement: Native air-quality fields remain isolated until semantically catalogued

The experimental WCS path SHALL enumerate and retain every selected RAQDPS and RDAQA field with its provider coverage id, published units, vertical level, product phase, valid time, reference time when published, response headers, and actual HTTP completion time. A field whose unit, attribution, averaging interval, or analysis phase has no canonical catalogue key SHALL remain source-scoped and nonpublishable; it SHALL NOT be converted to a differently dimensioned catalogue key or omitted from the acquisition receipt. Product phase, vertical scope, and any statistic window SHALL be explicit in the selected field contract, normalized variable attributes, artifact provenance, and retained receipt; they SHALL NOT be inferred later from a coverage identifier or variable spelling.

#### Scenario: GeoMet gas is published as mole fraction

- **WHEN** a selected RAQDPS or RDAQA gas coverage publishes `mol/mol` and the catalogue maps that species only as mass concentration
- **THEN** the experimental reader preserves the raw mole-fraction units and source identity
- **AND** the complete product remains nonpublishable pending an accepted canonical contract

#### Scenario: Source-scoped field reaches the normal point route

- **WHEN** a staged source-scoped raw field has no accepted catalogue and manifest mapping
- **THEN** the normal point route omits it
- **AND** test-only injected mappings are described as serialization evidence rather than admission

### Requirement: HRDPA preserves one exact six-hour analysis accumulation

After owner acceptance, the selected-timestamp demand path SHALL request only
the exact advertised `HRDPA_2.5km_Precip-Accum6h` coverage time and SHALL expose
the provider value as a six-hour precipitation accumulation ending at that
time. It SHALL preserve the published units, nodata mask, WCS geometry and
unknown provider resampling method. It SHALL NOT divide the accumulation into a
rate, assign a forecast lead, invent a model run, or substitute a neighbouring
analysis time.

#### Scenario: Selected time is advertised

- **WHEN** HRDPA advertises the requested analysis end time and returns a valid bounded coverage
- **THEN** the applicable published cell is returned with `accumulation_period_hours = 6` and `cell_methods = "time: sum"`
- **AND** provenance identifies `eccc-hrdpa`, the exact coverage, selected time, published units, requested and sampled geometry, final-byte completion, digest and cache expiry

#### Scenario: Selected time is not advertised

- **WHEN** the requested timestamp is between or outside advertised HRDPA coverage times
- **THEN** HRDPA is unavailable for that selection
- **AND** no earlier or later analysis value is returned

### Requirement: Initial HREPA demand fields remain provider-published percentiles

After owner acceptance and provider evidence for units and geometry, the
initial HREPA demand path SHALL treat `HREPA.6P_2.5km_PCT25` and
`HREPA.6P_2.5km_PCT75` as two distinct provider-published six-hour analysis
percentiles at an exact advertised time. It SHALL preserve each coverage's
native value, units, mask, identity and unknown quality state. It SHALL NOT
recompute a percentile, interpolate between the two fields, expose a member or
control, infer a probability distribution, or relabel either percentile as
analysis uncertainty or confidence.

#### Scenario: Two percentile coverages are complete

- **WHEN** both selected HREPA percentile coverages return the same exact analysis time with compatible published units and geometry
- **THEN** both source-scoped percentile fields may be returned as retrieved evidence
- **AND** provenance binds each value to its own coverage id and percentile rank

#### Scenario: HREPA field evidence is incomplete

- **WHEN** a percentile lacks provider-evidenced units or geometry, the two selected coverages disagree on time, or either required coverage is missing or malformed
- **THEN** the HREPA percentile group is unavailable
- **AND** no partial group, inferred statistic, member, probability, uncertainty or confidence value is returned

### Requirement: Analysis demand caches are finite and never serve expired values

The HRDPA and HREPA demand readers SHALL cache only bounded normalized response
data and typed request/transport provenance under a canonical key containing
source, coverage, selected time, subset and shape. The cache SHALL have finite
entry, aggregate-byte, TTL and failure-backoff limits; SHALL coalesce identical
misses; and SHALL make zero upstream requests for a fresh hit. Expiry SHALL NOT
renew on a hit. A failed refresh SHALL withhold every expired value while MAY
retain bounded acquisition identity and expiry metadata.

#### Scenario: Identical selected-time query repeats

- **WHEN** an identical canonical HRDPA or HREPA request repeats before expiry
- **THEN** the reader returns the same normalized identity from its finite cache
- **AND** it makes no additional WCS request and does not extend expiry

#### Scenario: Refresh after expiry fails

- **WHEN** a cached analysis response expires and its replacement fails transport, validation, time, unit, mask or geometry checks
- **THEN** every expired analysis value is withheld
- **AND** the response reports unavailable with only the bounded prior identity and expiry metadata permitted by the public contract

### Requirement: The wider HREPA inventory remains explicitly unresolved

The source integration SHALL keep precipitation analysis, analysis uncertainty,
confidence index, probability products, and 24 perturbed members plus control
in the #134 residual until provider evidence identifies their exact coverage
ids, units, statistic definitions, time identity, masks and quality semantics
and the owner accepts their public mappings. The absence of those mappings
SHALL NOT remove them from the all-source completion scope or permit values to
be fabricated from PCT25 and PCT75.

#### Scenario: A wider HREPA field is requested before acceptance

- **WHEN** a caller requests an unresolved HREPA analysis, uncertainty, confidence, probability, member or control field
- **THEN** that field is explicitly unsupported or unavailable with the missing contract named
- **AND** the two selected percentile candidates are not used as substitutes
