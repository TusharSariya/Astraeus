## ADDED Requirements

### Requirement: RAP uses a verified native product footprint
RAP SHALL identify the exact producer product and distributed grid independently
of the RAP model family. The known awp130 and awp236 products SHALL NOT supply Avalon
values. A replacement product SHALL remain unavailable until decoded native
geometry proves the declared evidence-box coverage and a valid sampling cell
for the selected Focus. Rectangular extrema or a successful HTTP subset request
SHALL NOT establish native coverage. Sampling SHALL reuse the accepted native
point sampler and preserve native coordinates and masks without extrapolation.

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

### Requirement: RAP delivery uses bounded finite caching and truthful provenance
RAP SHALL use selected-time bounded acquisition, finite TTL and byte/entry LRU
limits, same-key coalescing, bounded failure backoff and the existing isolated
decoder. A fresh cache hit SHALL issue no provider request. Failed refresh SHALL
withhold expired values. Native run/valid time and final-byte retrieval time
SHALL remain distinct and attached to public source provenance. No permanent
artifact publication or full-run prefetch SHALL be required for delivery.

#### Scenario: Concurrent identical requests miss the cache
- **WHEN** multiple clients request the same canonical RAP selection
- **THEN** one bounded acquisition fills the shared finite entry

#### Scenario: An expired entry cannot refresh
- **WHEN** the provider fails after the entry expiry
- **THEN** expired values remain absent with a typed source-specific failure
