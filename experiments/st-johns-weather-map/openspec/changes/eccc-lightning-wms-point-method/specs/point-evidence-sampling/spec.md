## MODIFIED Requirements

### Requirement: A value is one published cell, unmodified

Sampling SHALL select exactly one published grid cell per source and variable and SHALL report its value unmodified. No value SHALL be computed from more than one cell: there is no interpolation, averaging or regridding. `sample_method` SHALL state how the cell was selected: `rectilinear` by coordinate label, `curvilinear_nearest_cell` by index on a 2-D coordinate grid, or, only for an exact-frame ECCC `Lightning_2.5km_Density` GeoMet `GetFeatureInfo` query, `wms_getfeatureinfo_pixel` by the provider's WMS pixel operation.

#### Scenario: A rotated grid is sampled by index

- **WHEN** an HRDPS or RDPS artifact on a rotated lat/lon grid is sampled
- **THEN** the nearest cell is chosen by index over the 2-D coordinate fields, because selection by latitude/longitude label is invalid there and previously caused every such artifact to answer with nothing

#### Scenario: Longitude distance is corrected for latitude

- **WHEN** nearest-cell distance is computed
- **THEN** the longitude difference is scaled by `cos(latitude)`, since a degree of longitude is about 0.68 of a degree of latitude at 47.5N and a raw degree distance would pick a cell too far east or west

#### Scenario: The reported coordinate is the cell's, not the request's

- **WHEN** a value is returned with provider cell geometry
- **THEN** provenance carries the sampled latitude and longitude of the cell actually read plus the distance in kilometres from the requested coordinate, because echoing the request back would claim a precision the reading does not have
- **AND** the source-specific accepted lightning no-density response follows the explicit unknown-cell scenario below rather than inventing geometry

#### Scenario: GeoMet returns numeric lightning density with point geometry

- **WHEN** an exact advertised native lightning-frame query returns one finite numeric feature with its provider point geometry and native time
- **THEN** the value is served unmodified with `sample_method: wms_getfeatureinfo_pixel`, the provider-returned sampled latitude and longitude, and latitude-corrected distance from the requested coordinate
- **AND** a returned point beyond the accepted distance ceiling is withheld rather than relabelled as local evidence

#### Scenario: GeoMet reports no lightning density without cell geometry

- **WHEN** the exact advertised native lightning-frame query returns the accepted bare `{}` response
- **THEN** `lightning_observed = 0` is served, `lightning_strike` remains absent, and `sample_method` states `wms_getfeatureinfo_pixel_identity_unavailable`
- **AND** sampled latitude, sampled longitude and sample distance remain null with a `published_cell_coordinate_unavailable` disclosure; the requested coordinate is never echoed as the cell coordinate
