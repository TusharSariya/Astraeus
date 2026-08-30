## Purpose
Define how an arbitrary Avalon coordinate is answered from published artifacts: one nearest published cell, never an interpolation, carrying provenance that says which cell was actually read and how far away it was — plus the consensus, fallback and vertical-profile behaviour, including the parts that are honestly unavailable today.

## Requirements

### Requirement: A value is one published cell, unmodified
Sampling SHALL select exactly one published grid cell per source and variable and SHALL report its value unmodified. No value SHALL be computed from more than one cell: there is no interpolation, no averaging and no regridding. `sample_method` SHALL state how the cell was chosen — `rectilinear` by coordinate label, or `curvilinear_nearest_cell` by index on a 2-D coordinate grid.

#### Scenario: A rotated grid is sampled by index
- **WHEN** an HRDPS or RDPS artifact on a rotated lat/lon grid is sampled
- **THEN** the nearest cell is chosen by index over the 2-D coordinate fields, because selection by latitude/longitude label is invalid there and previously caused every such artifact to answer with nothing

#### Scenario: Longitude distance is corrected for latitude
- **WHEN** nearest-cell distance is computed
- **THEN** the longitude difference is scaled by `cos(latitude)`, since a degree of longitude is about 0.68 of a degree of latitude at 47.5N and a raw degree distance would pick a cell too far east or west

#### Scenario: The reported coordinate is the cell's, not the request's
- **WHEN** a value is returned
- **THEN** provenance carries the sampled latitude and longitude of the cell actually read plus the distance in kilometres from the requested coordinate, because echoing the request back would claim a precision the reading does not have

### Requirement: A cell too far from the request is not evidence about it
When the nearest published cell exceeds the maximum grid distance from the requested coordinate, no value SHALL be taken, and the grid SHALL be reported as read-but-unusable with the cell's coordinates and its distance stated. Returning it silently would relabel weather from somewhere else as local.

#### Scenario: A coordinate far from the published grid
- **WHEN** the nearest cell is beyond the distance ceiling
- **THEN** no field is produced from that artifact, and a skip notice names the cell, the request and the distance in kilometres

#### Scenario: A time with no nearby step
- **WHEN** no published step lies within an hour of the requested time
- **THEN** that artifact yields no evidence, rather than answering with a distant step

### Requirement: A missing value is null with full provenance
An absent value SHALL surface as `null` and SHALL still carry the same complete provenance shape as a present value. NaN SHALL be read as absence rather than as a reading. A response with nothing retrieved SHALL still enumerate every expected field as `null` with `quality.flags` including `no_retrieval` and a reason flag, so a caller can tell absence from a reading without interpreting a status code.

#### Scenario: A NaN grid cell
- **WHEN** the selected cell holds NaN
- **THEN** the field value is `null` and the provenance still names the source, product, run time, valid time, level, units, quality, coverage, freshness, licence, attribution and adapter version

#### Scenario: An unavailable point response
- **WHEN** nothing could be retrieved
- **THEN** all twelve unavailable point fields — temperature, relative humidity, dew point, wind speed, wind gust, visibility, low/middle/high/total cloud, fog state and radar echo — are present with `null` values, `data_mode: "unavailable"` provenance and their declared units

### Requirement: Relative humidity is derived only when it was not published
Relative humidity SHALL be taken directly when a source published it. It SHALL be derived from temperature and dew point only when both are present and the source published no direct value, and the derived field SHALL name its derivation and derivation version. The derivation SHALL use an explicit liquid-water phase, because letting the library choose would silently switch to ice below freezing and change the number.

#### Scenario: A published value is preserved
- **WHEN** a source publishes relative humidity directly
- **THEN** that value is used and nothing is derived for that source

#### Scenario: One input is missing
- **WHEN** temperature or dew point is absent
- **THEN** no relative humidity is derived for that source

#### Scenario: A derived value is labelled
- **WHEN** both inputs are present and no direct value exists
- **THEN** the derived value carries the MetPy liquid-phase derivation name and version in its provenance

### Requirement: Consensus requires ECCC regional, an independent centre and an ensemble
A consensus value SHALL be produced only when the eligible, fresh, QC-passing candidates include ECCC regional evidence, at least one independent deterministic centre, and at least one applicable ensemble family. One representative per centre SHALL contribute; ensembles prove the minimum evidence but remain distributions and SHALL NOT be averaged into the deterministic mean. Falling short SHALL produce no consensus and a stated reason.

#### Scenario: Minimum evidence not met
- **WHEN** any of the three required evidence classes is absent
- **THEN** consensus is unavailable with the reason `minimum evidence not met`, and no blended value is emitted

#### Scenario: Two models from one family
- **WHEN** two eligible candidates share a forecast centre
- **THEN** they cast one vote between them, not two

#### Scenario: Fewer than two centres survive
- **WHEN** representatives resolve to a single centre
- **THEN** consensus is unavailable with the reason `fewer than two independent centres`

### Requirement: Product selection may never borrow another source's values
When a specific product is requested, only fields whose provenance names that product's registry source SHALL be returned. A product with nothing published for the coordinate and time SHALL return `unavailable` naming that source, rather than another source's numbers under that product's badge. An unknown product name SHALL be a 422.

#### Scenario: A product with no published artifact
- **WHEN** `product=HRDPS` is requested and `eccc-hrdps` published nothing covering the request
- **THEN** the response is `unavailable` with a `no_published_artifact:eccc-hrdps` flag and a notice naming the product and source

#### Scenario: An unknown product
- **WHEN** a product name outside the known mapping is requested
- **THEN** the request is refused with 422

### Requirement: Display selection falls back explicitly and says which it used
The displayed selection SHALL be consensus when consensus is available, otherwise fresh HRDPS, otherwise fresh RDPS, otherwise evidence-only. Each state SHALL carry a badge and a reason naming why the higher option was not used, and evidence-only SHALL name no selected source or product.

#### Scenario: Consensus unavailable but HRDPS fresh
- **WHEN** consensus fails and HRDPS has published evidence
- **THEN** the badge is `HRDPS primary - consensus unavailable` with the reason `minimum consensus evidence not met`

#### Scenario: Neither model available
- **WHEN** neither HRDPS nor RDPS has published evidence and consensus fails
- **THEN** the mode is `evidence_only` with the badge `forecast unavailable`, both selected ids are null, and any observation evidence that was retrieved still stands on its own

### Requirement: The vertical profile is honest about being empty
`/profile` SHALL return a level for each of the standard pressures (1000, 850, 700, 500, 300 hPa), each carrying temperature, dew point, relative humidity and wind speed. When no published artifact carries a pressure-level profile at the coordinate, every field SHALL be `null` with `data_mode: "unavailable"`, a `no_published_artifact` flag and a notice — the sounding structure is present, and every value in it is honestly absent.

#### Scenario: No pressure-level artifact today
- **WHEN** `/profile` is requested against the current live store
- **THEN** the response is `unavailable`, all five levels and all four fields per level are present with `null` values, and provenance reports source, provider, product and units all `unavailable` with `quality.flags` including `no_retrieval`

#### Scenario: A store error
- **WHEN** the store raises while sampling a profile
- **THEN** the same all-null structure is returned with a `live_store_error` flag, not a synthetic sounding

#### Scenario: A published profile
- **WHEN** an artifact carries a pressure-level profile at the coordinate
- **THEN** the levels are returned in descending pressure order with their sampled values and full provenance

### Requirement: Cross-section is unavailable until normalized spatial arrays exist
`POST /cross-section` SHALL validate its request — a path of 2 to 100 coordinates, all inside the Avalon core, a valid time inside the window, and only the supported field names — and SHALL then refuse with 501 stating that cross-section is unavailable until normalized spatial arrays are implemented. It SHALL NOT return sampled values.

#### Scenario: A well-formed request
- **WHEN** a valid path, time and supported fields are posted
- **THEN** the response is 501 with the reason that normalized spatial arrays are not implemented

#### Scenario: An unsupported field
- **WHEN** a field outside temperature, dew point, relative humidity and wind speed is requested
- **THEN** the request is refused with 422 naming the unsupported fields, before the 501

#### Scenario: A path outside coverage or the window
- **WHEN** any coordinate is outside the Avalon core or the valid time is outside the window
- **THEN** the same space and time boundaries as `/point` and `/profile` apply and the request is refused with 422
