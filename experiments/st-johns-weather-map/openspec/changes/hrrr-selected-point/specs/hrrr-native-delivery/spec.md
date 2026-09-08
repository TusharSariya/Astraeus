## ADDED Requirements

Draft only. These requirements do not authorize implementation or publication.

### Requirement: Native HRRR sectors remain separate and coverage is measured
A selected reader SHALL identify NOAA HRRR, native sector, surface product,
provider cycle, forecast lead, exact native valid instant and GRIB grid. CONUS
`wrfsfc` and Alaska `wrfsfc.ak` SHALL NOT substitute for one another. A nearby
cell outside the supported native footprint SHALL NOT answer a request.
Avalon SHALL remain unsupported for both captured sectors. Native projection,
scanning and coordinate metadata SHALL take precedence over a generic product
page; changed geometry SHALL be explicitly revalidated.

#### Scenario: An Avalon Focus requests either HRRR sector
- **WHEN** native geometry has no cell supporting that coordinate
- **THEN** the source reports unsupported geography without distant-cell substitution

#### Scenario: Alaska metadata differs from the product web page
- **WHEN** the native GRIB reports polar stereographic geometry
- **THEN** the reader preserves that geometry and does not relabel it Lambert

### Requirement: A query acquires only its selected native frame
The reader SHALL discover bounded actual current product availability, select
one native valid instant and request only accepted field-message ranges for
that frame. It SHALL verify HTTP 206, exact Content-Range, message framing,
centre/product/grid/run/lead and field units before admitting a reading. It
SHALL NOT infer current availability from historical cadence documentation,
prefetch a run, interpolate missing times or infer an accumulation interval.

#### Scenario: A requested frame or field is absent
- **WHEN** the bounded published inventory contains no exact eligible record
- **THEN** the result stays unavailable without another run, model or nearby time

### Requirement: Native values retain finite evidence semantics
Each accepted field contract SHALL define exact parameter/level/native units,
normalization if any, bitmap missingness and native interval semantics before
it is selectable. Final-byte receipt, digest, immutable native identity and
fixed expiry SHALL survive decoding and cache reuse. Identical misses SHALL
coalesce; expired values SHALL be withheld. Source-local byte/time/process and
cache ceilings SHALL be specified and tested before public wiring.

#### Scenario: Cached evidence expires during validation
- **WHEN** validation finishes after the fixed receipt-based expiry
- **THEN** no value is returned as current and validation does not renew expiry

### Requirement: Initial delivery remains experimental and point-only
The reader SHALL preserve `operational: false`, no display-primary admission,
no consensus contribution and no Series claim until native inventory and range
delivery have their own verification. Implementation SHALL NOT reuse GFS source
identity, rectilinear assumptions or original-unit labels for HRRR.

#### Scenario: A descriptor exists before successful acquisition
- **WHEN** a source has only a software capability declaration
- **THEN** coverage and current live retrieval remain unproven independently
