## ADDED Requirements

### Requirement: Native GDPS requests use bounded selected-time delivery
The isolated experiment SHALL resolve an aware selected instant to an advertised
native hourly GDPS frame at or before it and strictly less than one hour old.
It SHALL retrieve only the selected native 00/12 UTC run, lead and five declared
point fields from the dated 15 km `LatLon0.15` product, keyed by canonical
endpoint, run, lead, sorted unique fields and Avalon crop geography. Discovery,
transfers, child decode, output and aggregate cache SHALL have finite enforced
ceilings. It SHALL NOT use the separate 10 km sea-ice analysis, prefetch a run,
read retained artifacts, interpolate, substitute a neighbouring hour, derive
wind from U/V, or serve expired values.

#### Scenario: Ordinary point selection and fresh repeat
- **WHEN** two selected instants resolve to the same native GDPS hour and field set
- **THEN** one coalesced upstream operation fills the canonical cache and a fresh repeat adds zero provider payload requests
- **AND** response provenance preserves the actual run, native-valid time, final-byte retrieval completion, transport receipts and digest, native regular latitude/longitude geometry, units, masks, QC and nearest cell

#### Scenario: Expired replacement or source failure
- **WHEN** discovery, transfer, decode, identity, QC or resource validation fails, including after cache expiry
- **THEN** GDPS is explicitly unavailable and neither a retained artifact nor a neighbouring or expired value substitutes
- **AND** bounded expired acquisition identity remains disclosed for at most one further source TTL

#### Scenario: Timeline and deferred profile
- **WHEN** the existing GDPS timeline is requested
- **THEN** bounded directory metadata advertises only native hourly frames through f240 and fetches no GRIB payload
- **AND** a selected GDPS profile reports the #189 field scope unavailable without calling the provider or retained store
