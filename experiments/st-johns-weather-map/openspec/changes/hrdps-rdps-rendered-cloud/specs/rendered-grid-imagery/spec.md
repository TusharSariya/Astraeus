## ADDED Requirements

### Requirement: A rotated grid renders by nearest published cell centre, disclosed as such
A stored grid whose latitude/longitude are 2-D coordinates over anonymous
dimensions (the rotated HRDPS/RDPS shape) SHALL be rendered by assigning
every output pixel the stored value of the single nearest published cell
centre, by equirectangular distance with cos(latitude) longitude scaling -
the same rule `/point` sampling discloses as `curvilinear_nearest_cell`. A
pixel farther than half a cell diagonal (median adjacent-centre spacing per
axis) from every centre SHALL be fully transparent: the grid ends where its
cells end. Nothing SHALL be interpolated, regridded, smoothed or averaged;
every painted pixel is exactly one stored value. The response SHALL disclose
the method: `X-Weather-Sample-Method: curvilinear_nearest_cell`, render
semantics naming the nearest-cell-centre rule and its acceptance radius, and
a method-specific derivation version distinct from the rectilinear one. A
curvilinear grid whose coordinate shapes disagree or whose cell pitch cannot
be measured SHALL be refused rather than guessed. The rectilinear
containing-cell rule and its derivation version are unchanged for 1-D-axis
grids.

#### Scenario: A pixel on a cell centre is that cell's value
- **WHEN** a one-pixel render is centred exactly on a stored cell centre of
  a rotated grid
- **THEN** the pixel carries exactly that cell's stored value, and a stored
  NaN cell renders fully transparent

#### Scenario: Beyond the grid edge
- **WHEN** the requested bounds lie more than half a cell diagonal from
  every published cell centre
- **THEN** every pixel is fully transparent; nothing is extrapolated

#### Scenario: The method rides the response
- **WHEN** a rotated-grid raster is served
- **THEN** the headers carry `X-Weather-Sample-Method:
  curvilinear_nearest_cell`, semantics naming the nearest published cell
  centre and the half-cell-diagonal acceptance, and a derivation version
  specific to the curvilinear method

### Requirement: ECCC total-cloud stored grids are offered as rendered layers
The stored `eccc-hrdps` and `eccc-rdps` surface artifacts' `total_cloud`
SHALL be offered as rendered-grid layers (`eccc-hrdps-surface-total-cloud`,
`eccc-rdps-surface-total-cloud`) under the same `grid-cloud-alpha-v1`
colormap, group, disclosure and fail-closed rules as the GFS strata. Layer
semantics SHALL state the product and native resolution read from the
artifact's own provenance, never asserted in code; a provenance without a
declared resolution SHALL be described as undeclared rather than filled in.
An artifact absent, unreadable, or missing the variable SHALL follow the
existing absence rules (no layer plus a notice, 404/502 at the raster, and
nothing substituted). The `geomet-live-hrdps-nt` live proxy remains offered
unchanged in ECCC's own style with ECCC's own legend.

#### Scenario: The layers appear from provenance facts
- **WHEN** a stored `eccc-hrdps` surface artifact carries `total_cloud`
- **THEN** `/layers` offers `eccc-hrdps-surface-total-cloud` in group
  `rendered_grid` with times exactly the ingested valid times and semantics
  naming the provenance product and native grid

#### Scenario: Before the first ingest run carries the field
- **WHEN** the stored ECCC artifacts do not carry `total_cloud`
- **THEN** the layers are absent with a notice naming them, and no imagery
  is invented

### Requirement: The served cloud legend is the ramp over a disclosed backdrop
`/layers/{id}/legend` for a cloud rendered-grid layer SHALL serve the
declared `grid-cloud-alpha-v1` ramp composited over a neutral mid-grey
backdrop, because the ramp is a transparency ramp and a legend graphic that
is itself transparent reads as a blank box. The compositing SHALL change
only the backdrop, never the mapping: the colormap sentence in the headers
remains the exact mapping applied to the stored values, and the legend
semantics header SHALL disclose the backdrop.

#### Scenario: The legend is visible and still honest
- **WHEN** the legend endpoint is read for a cloud rendered-grid layer
- **THEN** the PNG is opaque, running from the bare grey backdrop at 0
  percent to opaque white at 100 percent, with `X-Weather-Legend-Basis:
  renderer_colormap` and a legend-semantics header disclosing the grey
  backdrop as presentation, not part of the mapping
