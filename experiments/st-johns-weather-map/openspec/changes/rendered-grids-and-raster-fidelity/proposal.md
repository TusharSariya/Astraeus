## Why

Two defects in how the map shows rasters, both invisible on a quick glance and
both about positional or representational fidelity rather than missing data.

First, every map image was requested from GeoMet in EPSG:4326 and then
corner-pinned onto MapLibre's web-mercator canvas as a `type: 'image'` source.
Corner-pinning a plate-carree image onto a mercator canvas is linear in
latitude where the canvas is linear in mercator-y; at 47.5 N over the ~4
degree box the map shows, that misplaces mid-box pixels by roughly 2-3 km.
GeoMet serves EPSG:3857 `GetMap` correctly (verified live 2026-08-30), and a
3857 tile whose bbox matches the pinned corners is exact by construction. Two
smaller fidelity gaps ride along: the request size was CSS pixels, so forecast
fields rendered soft on high-density displays (GeoMet rasterises server-side),
and the opaque GOES-East satellite frames were fetched as PNG at ~160 kB where
JPEG carries the same picture at ~54 kB with no transparency to lose.

Second, the owner wants low/middle/high cloud toggles in the layer menu, and
no provider publishes strata rasters for this region (ECCC GeoMet has none -
verified). But the worker already ingests the NOAA GFS grids that carry the
provider-declared strata (`cloud_low`/`cloud_middle`/`cloud_high` from GRIB
LCDC/MCDC/HCDC at the provider's own cloud layers, 0.25 degree, leads to
36 h), and `/point` already serves them. The only honest way to put them on
the map is to render them ourselves, from the stored artifact, without
inventing anything: stored values at their native cells, nearest-neighbor,
never smoothed, with the colormap disclosed and the times limited to what was
actually ingested.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **EPSG:3857 renders:** `GeoMetClient.map_image` accepts
  `crs="EPSG:3857"` (default stays `EPSG:4326`), projecting the geographic
  bounds to spherical-mercator metres and sending the bbox in the
  `minx,miny,maxx,maxy` easting/northing order that CRS defines - the
  EPSG:4326 latitude-first rule is untouched. `/layers/{id}/raster` gains a
  `crs` query parameter (422 for anything but the two supported values), the
  response discloses `X-Weather-Crs`, and image provenance records the CRS it
  was really rendered in.
- **Satellite JPEG:** the four GOES-East proxies (product `GOES-East`, group
  `satellite`) are requested and served as `image/jpeg` with
  `transparent=FALSE`; every other layer keeps transparent PNG, where a fully
  transparent tile is itself a reading. The response content type is what the
  upstream actually declared - a mismatch is already refused.
- **Web fidelity:** the client requests every raster with `crs=EPSG:3857`
  sized in physical pixels (device pixel ratio capped at 2) and keeps
  corner-pinning - which is now exact, because image and canvas share a
  projection. "No frame here" behaviour and provenance-header checks are
  unchanged.
- **Rendered cloud-strata grids:** a new `weather_api/grids.py` renders the
  three GFS strata from the published artifact: per-pixel nearest-neighbor
  assignment to the containing native 0.25 degree cell, exact in both CRS,
  NaN and out-of-grid pixels transparent, a declared single-hue colormap
  (percent -> white with linear alpha; 0 percent transparent), and a legend
  endpoint serving exactly that ramp with `X-Weather-Legend-Basis:
  renderer_colormap`. `/layers` lists the three layers with group
  `rendered_grid` (new `Layer.group` literal member), times exactly the
  ingested valid times, `evidence_basis: published_artifact`, and semantics
  stating they are rendered by this experiment from retrieved GFS GRIB2
  fields, provider-declared strata, 0.25 degree native, nearest-neighbor,
  never smoothed. A frame outside half-cadence tolerance is a 422; a missing
  artifact or variable is a 404 plus an index notice; an unreadable one is a
  502. Nothing reaches `/timeline` or `/point` through this path.
- **Web strata layers:** the three layers appear in the drawer and the
  timeline coverage ribbon under a shared `rendered_grid` group heading,
  toggleable like every other layer; the client accepts rendered-grid
  provenance (`X-Weather-Image-Basis: rendered_grid` plus
  `X-Weather-Source-Id`) in place of an upstream WMS layer name, and the
  legend caption and evidence-basis wording say the imagery is drawn here
  from stored values, never "fetched from the provider".

## Capabilities

### New Capabilities

- `rendered-grid-imagery`: map images rendered by this experiment from its own
  stored grid artifacts - the honesty rules for drawing pixels from retrieved
  values (nearest-neighbor only, ingested times only, disclosed colormap and
  provenance).

### Modified Capabilities

- `geomet-wms-access`: `GetMap` may be requested in EPSG:3857 with the axis
  order that CRS defines; opaque satellite imagery is fetched as JPEG while
  transparent layers stay PNG.
- `web-raster-rendering`: the request contract gains `crs=EPSG:3857` and
  physical-pixel sizing; provenance acceptance and the legend rule learn the
  rendered-grid case.
