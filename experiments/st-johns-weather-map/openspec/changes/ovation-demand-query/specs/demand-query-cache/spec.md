## MODIFIED Requirements

### Requirement: Retrieved live evidence is bounded and truthful

For experimental `noaa-swpc-ovation`, a raster selected at an aware UTC instant
SHALL issue at most one canonical current-grid request for concurrent cache
misses. It SHALL accept no body above 1 MiB, retain no response body, retain at
most one normalized entry no larger than 256 KiB plus bounded freshness and
identity metadata, and record completion immediately after the final response
byte. It SHALL use provider finite freshness and SHALL not serve an expired
entry if replacement retrieval fails.

The entry SHALL preserve native OVATION percent cells after the existing
Atlantic-context crop, including zero values and missing cells, and preserve
payload Observation Time and Forecast Time. It SHALL answer only when the
selected instant lies within 600 seconds of that Forecast Time. It SHALL not
select a neighbouring time, stored artifact, interpolated cell, or invented
forecast/run identity. A success SHALL remain `operational: false` and name
`evidence_basis: demand_query`.

#### Scenario: A fresh current document supports the selection

- **WHEN** the decoded Forecast Time is within 600 seconds of the selected UTC
  instant
- **THEN** the raster uses those exact native cells and reports the bounded canonical/effective URL, safe request/response headers,
  final-byte receipt, byte identity/expiry, Forecast Time, Observation Time,
  and demand-query evidence basis

#### Scenario: The selection has no native current frame

- **WHEN** the selected instant is more than 600 seconds from Forecast Time
- **THEN** the raster is unavailable and no nearest frame is substituted

#### Scenario: Freshness ends before replacement succeeds

- **WHEN** the finite entry expires and canonical retrieval fails
- **THEN** its cells are discarded and no raster values are served
- **AND** the unavailable response may disclose only bounded cached digest and
  expiry metadata with `values_withheld: true`
