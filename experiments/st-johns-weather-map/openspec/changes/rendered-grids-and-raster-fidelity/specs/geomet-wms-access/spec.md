## ADDED Requirements

### Requirement: GetMap in EPSG:3857 uses the x,y axis order and mercator-exact bounds
`GetMap` MAY be requested with `CRS=EPSG:3857`. The geographic
south/west/north/east bounds SHALL be projected to spherical-mercator metres
with the standard formulas (`x = R*lon_rad`, `y = R*ln(tan(pi/4+lat_rad/2))`,
`R = 6378137`) and the bbox SHALL be sent `minx,miny,maxx,maxy` — easting then
northing, the axis order that CRS defines. `CRS=EPSG:4326` SHALL keep its
latitude-first order unchanged and SHALL remain the default. A CRS outside the
two supported values SHALL be refused client-side before any upstream call.
Image provenance SHALL record the CRS the render was really requested in,
never a hard-coded constant, while the recorded bbox stays the named
geographic mapping in every case. A tile rendered in EPSG:3857 over given
corners corner-pins exactly onto a web-mercator canvas; a plate-carree tile
pinned the same way is warped ~2-3 km mid-box at 47.5 N, which is why the
projection is offered at all.

#### Scenario: A mercator render over the Avalon
- **WHEN** a tile is requested with `crs="EPSG:3857"` over the Avalon box
- **THEN** the bbox on the wire is the four bounds projected to metres in
  `minx,miny,maxx,maxy` order, `CRS=EPSG:3857` is sent, and the returned
  image's provenance records `crs: EPSG:3857` beside the named geographic
  bounds

#### Scenario: The default is unchanged
- **WHEN** no CRS is named
- **THEN** the request is EPSG:4326 with the latitude-first bbox exactly as
  before, and provenance records `crs: EPSG:4326`

#### Scenario: An unsupported CRS
- **WHEN** `crs="EPSG:26919"` (or any value outside the two supported) is
  requested
- **THEN** a ValueError is raised client-side and no upstream request is made

#### Scenario: A latitude outside the projection
- **WHEN** a bound lies beyond EPSG:3857's ~85.05 degree definition
- **THEN** the request is refused rather than silently clamped, because a
  clamped bound would place the tile edge somewhere the caller did not ask
  about

### Requirement: Opaque satellite imagery is fetched as JPEG; transparent layers stay PNG
The GOES-East satellite proxies (product `GOES-East`, group `satellite`) SHALL
be requested with `FORMAT=image/jpeg` and `TRANSPARENT=FALSE`: the imagery is
opaque, JPEG carries the same picture at roughly a third the bytes (~54 kB vs
~160 kB per tile, measured live 2026-08-30), and there is no transparency to
lose. Every other layer SHALL keep transparent PNG, because for those a fully
transparent tile is itself a reading. The response content type SHALL be the
one the upstream actually declared — the existing rule that a declared type
other than the requested format is raised, not served, applies unchanged — so
the served `image/jpeg` is a retrieved fact, not an assertion.

#### Scenario: A satellite tile
- **WHEN** `/layers/{id}/raster` is requested for a GOES-East proxy
- **THEN** the upstream request carries `FORMAT=image/jpeg` and
  `TRANSPARENT=FALSE`, and the 200 response's content type is `image/jpeg`
  as the upstream declared it

#### Scenario: Everything else
- **WHEN** a forecast proxy, radar or any published-artifact layer is
  requested
- **THEN** the upstream request stays `FORMAT=image/png` with
  `TRANSPARENT=TRUE`, and a fully transparent PNG remains a reading

#### Scenario: The upstream answers the wrong type
- **WHEN** a JPEG was requested and the service declares something else
- **THEN** the response is raised naming what was asked for and what came
  back, never relabelled
