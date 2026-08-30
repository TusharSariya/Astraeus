## ADDED Requirements

### Requirement: A rendered grid shows only stored values at their native cells
A map image rendered by this experiment from a stored grid artifact SHALL
assign every output pixel the stored value of the single native grid cell that
geographically contains the pixel's centre — pure nearest-neighbor. Nothing
SHALL be interpolated between cells, smoothed, resampled onto a finer grid, or
extrapolated past the outermost cell edge. A pixel outside the grid, over a
cell with no stored value (NaN), or over a stored cover of 0 percent SHALL be
fully transparent. Positioning SHALL be exact in the requested CRS (EPSG:4326
or EPSG:3857): pixel centres are computed in that CRS and converted to the
geographic coordinate they represent before the cell lookup, so the same
stored cell answers regardless of projection. A grid whose coordinate axes are
not uniformly spaced SHALL be refused rather than placed by guesswork.

#### Scenario: Block-uniform pixels
- **WHEN** a 3x3-cell grid is rendered at 6x6 pixels over exactly its cell
  extent
- **THEN** every 2x2 pixel block is uniform at its cell's stored value and no
  pixel carries a value between two cells

#### Scenario: A cell boundary is a boundary
- **WHEN** pixels straddle the edge between two cells
- **THEN** each pixel takes the value of the cell containing its centre, with
  no blended pixel in between

#### Scenario: Outside the grid
- **WHEN** the requested bounds extend past the outermost cell edges
- **THEN** the pixels beyond the edge are fully transparent; nothing is
  extrapolated

#### Scenario: EPSG:3857 rows are mercator-linear
- **WHEN** the same grid is rendered in EPSG:3857 and EPSG:4326 over a tall
  box
- **THEN** the row where a cell edge falls matches the mercator position of
  that edge in the 3857 render and the linear-latitude position in the 4326
  render

#### Scenario: A non-uniform axis
- **WHEN** the stored latitude or longitude axis is not uniformly spaced
- **THEN** the render is refused with a stated reason rather than guessed

### Requirement: Rendered-grid frames are exactly the ingested valid times
The frames offered for a rendered-grid layer SHALL be exactly the valid times
the published artifact carries for that variable — never a generated range. A
requested instant SHALL resolve to the nearest stored frame only within half
the layer's own modal cadence (floored at 60 s; 900 s when the cadence cannot
be derived); beyond that the request SHALL be answered 422 naming the nearest
stored frame, never with a silently reused older frame. The response SHALL
carry the resolved frame's real instant, not the requested one. A layer whose
artifact is not published, or does not carry the variable, SHALL be 404 at the
raster endpoint and absent from the layer index (with a notice where the
artifact exists but the variable does not); an unreadable artifact SHALL be
502 with nothing substituted.

#### Scenario: A stored frame answers
- **WHEN** an instant within half a cadence of a stored valid time is
  requested
- **THEN** that frame is rendered and `X-Weather-Valid-Time` carries the
  frame's own instant

#### Scenario: No stored frame within tolerance
- **WHEN** the nearest stored frame is further than the tolerance
- **THEN** the response is 422 stating the tolerance, the nearest stored frame
  and that frames are only what was ingested

#### Scenario: The variable was not ingested
- **WHEN** the published artifact does not carry the layer's variable
- **THEN** the raster endpoint answers 404, and the layer index omits the
  layer with a notice naming it

#### Scenario: The artifact cannot be read
- **WHEN** the stored artifact raises on open
- **THEN** the response is 502 saying no grid was read, and nothing is
  substituted

### Requirement: The rendering is disclosed end to end
Every rendered-grid response SHALL carry provenance headers in the
`X-Weather-*` pattern: `X-Weather-Image-Basis: rendered_grid`,
`X-Weather-Evidence-Basis: published_artifact` (the values come from a
published artifact; the bytes are rendered here and never stored),
`X-Weather-Source-Id`, the product, the model run in
`X-Weather-Reference-Time`, the CRS, the colormap in words, render semantics
stating the nearest-neighbor rule, and disclosed `derivation` /
`derivation_version` strings for the rendering step. The colormap SHALL be a
declared single-hue ramp with 0 percent fully transparent; it is presentation
and SHALL never alter a value. `/layers/{id}/legend` for such a layer SHALL
serve exactly that ramp with `X-Weather-Legend-Basis: renderer_colormap` and
headers stating it is the renderer's own mapping, not provider data.
`X-Weather-Operational` SHALL be `false` and `operational: false` SHALL hold
on every related response.

#### Scenario: A rendered tile's headers
- **WHEN** a strata raster is served
- **THEN** the response carries image basis `rendered_grid`, evidence basis
  `published_artifact`, source id, model run, CRS, the colormap sentence, the
  nearest-neighbor render semantics, a derivation version, and
  `X-Weather-Operational: false`

#### Scenario: The legend is the ramp actually applied
- **WHEN** the legend endpoint is read for a rendered-grid layer
- **THEN** it serves the declared colormap ramp (0 to 100 percent) with
  `X-Weather-Legend-Basis: renderer_colormap`, never a provider graphic and
  never an undocumented scale

### Requirement: Rendered-grid layers are indexed truthfully and reach nothing else
The layer index SHALL list a rendered-grid layer only where the artifact and
variable are actually published, with group `rendered_grid`,
`evidence_basis: published_artifact`, times exactly the ingested valid times,
truthful `legend_available`, no upstream WMS layer, and semantics stating that
the layer is rendered by this experiment from retrieved GFS GRIB2 fields,
provider-declared strata at the provider's own cloud layers, 0.25 degree
native resolution, displayed nearest-neighbor and never smoothed. The
rendering path SHALL NOT feed `/timeline` or `/point`: those read the artifact
store directly, exactly as before. The interface SHALL file the three layers
under a shared `rendered_grid` group in the drawer and the timeline coverage
rows, toggleable like any other layer, and its wording SHALL never describe
the imagery as fetched from or rendered by a provider.

#### Scenario: The layers appear with ingested times
- **WHEN** the GFS artifact is published carrying the three strata variables
- **THEN** `/layers` lists `noaa-gfs-surface-cloud-low/-middle/-high` with
  group `rendered_grid`, the artifact's valid times, and the required
  semantics text

#### Scenario: Nothing is published
- **WHEN** no GFS artifact is current
- **THEN** no strata layer is listed and none is invented

#### Scenario: The drawer and the ribbon agree
- **WHEN** the three layers are listed
- **THEN** the layer drawer and the timeline coverage rows both file them
  under the shared `rendered_grid` heading, and toggling works as for any
  other layer
