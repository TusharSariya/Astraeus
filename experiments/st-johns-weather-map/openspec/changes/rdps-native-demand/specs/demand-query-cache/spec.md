## ADDED Requirements

### Requirement: Native RDPS requests use bounded selected-time delivery
The isolated experiment SHALL resolve an aware selected instant to an advertised
native hourly RDPS frame at or before it and strictly less than one hour old.
It SHALL retrieve only the selected native run/lead and requested existing
surface or profile fields, keyed by canonical endpoint/run/lead, sorted unique
fields and crop geography. Discovery, transfers, child decode, output and cache
SHALL have finite enforced ceilings. No full run, retained artifact fallback,
interpolation, or new scientific derivation SHALL answer an RDPS demand request.

#### Scenario: Ordinary selection and repeated native request
- **WHEN** two selected instants resolve to the same native RDPS hour and field set
- **THEN** they use the same canonical cache entry, concurrent misses coalesce and a fresh repeat adds zero provider payload
- **AND** response provenance preserves actual run, native-valid, retrieval completion, transport identity, units, masks and nearest rotated-grid cell

#### Scenario: Unsupported or failed source
- **WHEN** no advertised native lead covers the selection or discovery, transfer, decode, identity, QC or resource validation fails
- **THEN** the source is explicitly unavailable and neither a retained artifact nor a neighbouring hour substitutes

#### Scenario: Profile and metadata availability
- **WHEN** the existing RDPS profile or timeline is requested
- **THEN** profile acquisition requests only its declared pressure-level fields and timeline acquisition reads bounded directory metadata without GRIB prefetch
- **AND** advertised availability is distinguished from retrieved values, with missing fields retaining their missing disposition
