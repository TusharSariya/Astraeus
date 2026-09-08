## ADDED Requirements

### Requirement: RAP uses a verified native product footprint
RAP SHALL identify the exact producer product and distributed grid independently
of the RAP model family. The known awp130 and awp236 products SHALL NOT supply Avalon
values. The initial eligible product SHALL be `awip32` North American grid 221,
with native Lambert 349 by 277 geometry and 32,463 m spacing. Each acquired
message SHALL validate this geometry and projected support for the evidence
box; a changed grid or product SHALL remain unavailable pending review. Rectangular extrema or a successful HTTP subset request
SHALL NOT establish native coverage. Sampling SHALL reuse the accepted native
point sampler and preserve native coordinates and masks without extrapolation.
The crop SHALL retain one native-cell halo, including cells outside the request
box that can be the nearest native cell of an eligible boundary request.

#### Scenario: A successful HTTP request has no native cells
- **WHEN** a RAP response contains no eligible cells in the declared domain
- **THEN** the source reports unsupported coverage and contributes no value

#### Scenario: A different RAP grid is available
- **WHEN** another product filename is discovered
- **THEN** its grid and coverage are verified independently before admission

### Requirement: Initial RAP values preserve native quantity and time
The initial slice SHALL expose only verified instantaneous TCDC entire-atmosphere
percent and VIS surface metres through mapped catalogue fields. Metadata SHALL
match source, product, run, lead, native grid, level, unit and step type. Selected
valid time SHALL equal native run plus lead; missing native steps SHALL remain
unavailable without nearest-time, neighbouring-grid or model substitution.
Unknown aerosol units/species and unverified wind orientation SHALL remain
unavailable. The full remaining RAP field/profile objective SHALL remain tracked.

#### Scenario: Accumulated or differently supported field is returned
- **WHEN** a requested instantaneous field has incompatible step or level metadata
- **THEN** the field is rejected rather than relabelled

#### Scenario: Requested exact lead is absent
- **WHEN** no eligible published run contains the selected native valid time
- **THEN** the response names RAP and its absence without borrowing GFS values

#### Scenario: A boundary request selects a native cell outside the request box
- **WHEN** an eligible request's nearest native cell lies just beyond the evidence box
- **THEN** the retained halo preserves its value/mask and actual coordinates rather than selecting a farther in-box cell

### Requirement: RAP delivery uses bounded finite caching and truthful provenance
RAP SHALL use selected-time bounded acquisition, finite TTL and byte/entry LRU
limits, same-key coalescing, bounded failure backoff and the existing isolated
decoder. The fixed lifetime SHALL be 600 seconds from final upstream completion;
response bookkeeping, decoding, validation and hits SHALL NOT renew it. A
result already expired at validation SHALL NOT be admitted. The cache SHALL
retain at most four cropped entries and apply a 60-second failure backoff.
A fresh cache hit SHALL issue no provider request. Failed refresh SHALL
withhold expired values. Native run/valid time and final-byte retrieval time
SHALL remain distinct and attached to public source provenance. No permanent
artifact publication or full-run prefetch SHALL be required for delivery.

#### Scenario: Concurrent identical requests miss the cache
- **WHEN** multiple clients request the same canonical RAP selection
- **THEN** one bounded acquisition fills the shared finite entry

#### Scenario: An expired entry cannot refresh
- **WHEN** the provider fails after the entry expiry
- **THEN** expired values remain absent with a typed source-specific failure


### Requirement: Initial RAP public mapping remains narrow and nonprimary
The shared point reader SHALL expose only `noaa-rap` / `awip32` deterministic
VIS surface metres as `visibility` and instantaneous entire-atmosphere TCDC
percent as `total_cloud_geometric`. It SHALL retain unknown scientific QC,
retrieved evidence, available-not-stored storage, operational false and
nonprimary display. This proposal SHALL NOT admit smoke/AOD, profiles, wind
transforms, consensus contributions or native Series. No unsupported run
selector SHALL be silently interpreted as latest.

#### Scenario: A native bitmap cell is missing
- **WHEN** either accepted field is missing at the selected native cell
- **THEN** that field remains null with its native identity and is not replaced by another field, cell or model

#### Scenario: Validation consumes the fixed lifetime
- **WHEN** validation finishes at or after final completion plus 600 seconds
- **THEN** no expired values are returned or inserted as a fresh entry
