## MODIFIED Requirements

### Requirement: Raster request extent SHALL be built from the endpoint's own parameter contract

The client SHALL send the map bounds as the four separate parameters the
endpoint declares, plus `crs=EPSG:3857`, and SHALL NOT send a packed `bbox`
string. The canvas is web mercator, so an image rendered in EPSG:3857 over the
visible bounds corner-pins onto it exactly; the EPSG:4326 images previously
pinned the same way were warped ~2-3 km through the middle of the box at this
latitude. Request `width`/`height` SHALL be physical pixels: the CSS size
multiplied by the device pixel ratio capped at 2, because the provider
rasterises server-side and a CSS-pixel request renders soft on high-density
displays, while past 2x nothing gains legibility. A mismatch in this contract
does not fail loudly: the server would fall back to defaults and return a
plausible image of the wrong extent or projection.

#### Scenario: The request names each bound separately
- **WHEN** the client requests imagery for a layer over the visible map bounds
- **THEN** the query carries `south`, `west`, `north` and `east` as individual
  parameters matching the endpoint signature
- **AND** it carries `crs=EPSG:3857` and no comma-packed `bbox`

#### Scenario: Physical-pixel sizing
- **WHEN** the device pixel ratio is 1.5
- **THEN** the requested width and height are 1.5x the CSS pixels
- **AND** at a ratio of 3 they are capped at 2x, and below 1 they are never
  smaller than the CSS size

#### Scenario: Placement is corner-pinned in the shared projection
- **WHEN** a returned EPSG:3857 image is placed on the map
- **THEN** it is corner-pinned at the requested geographic corners, which is
  exact because image and canvas share the mercator projection

#### Scenario: A drifted parameter contract is caught by test, not by eye
- **WHEN** the raster URL builder is changed such that a bound is renamed, packed,
  reordered, or dropped
- **THEN** a test fails naming the expected parameters
- **AND** the failure does not depend on inspecting a rendered image

### Requirement: Imagery SHALL be drawn only where its provenance is established

An image is evidence only if the client can say where it came from, what it is,
and what instant it represents. The response carries that as `X-Weather-*`
headers. A provider-rendered image establishes itself by naming its upstream
WMS layer; a rendered-grid image (`X-Weather-Image-Basis: rendered_grid`) has
no upstream and SHALL instead name the ingested source its pixels were drawn
from in `X-Weather-Source-Id`. Either statement suffices; an image making
neither is refused.

#### Scenario: A layer that declares no raster is never requested
- **WHEN** a layer reports `raster_available: false`
- **THEN** the client does not issue a raster request for it
- **AND** it renders that layer's vector features if it has any, or nothing

#### Scenario: An image without retrieval provenance is refused
- **WHEN** a raster response omits the retrieval status, and names neither an
  upstream layer nor a rendered-grid source
- **THEN** the client does not draw the returned bytes
- **AND** it reports the layer as unavailable with the reason

#### Scenario: A rendered-grid image is accepted on its own provenance
- **WHEN** a raster response carries `X-Weather-Retrieval-Status`,
  `X-Weather-Image-Basis: rendered_grid` and `X-Weather-Source-Id`
- **THEN** the client draws it and its description says the image was drawn by
  this experiment from that stored source, never that it was fetched from a
  provider

### Requirement: The legend SHALL be the provider's own or absent

The interface SHALL NOT synthesize a colour scale of its own invention. A drawn
field with no legend is uninterpretable, so the legend is fetched from the same
origin that rendered the image: the provider's own graphic for
provider-rendered imagery, or — for a rendered-grid layer — the renderer's
declared colormap served by this experiment's API, which is the exact mapping
applied to the stored values. A rendered-grid legend SHALL be captioned as this
experiment's own colormap and SHALL NOT be captioned as a provider graphic. If
no legend is served, the layer is drawn without one and says so.

#### Scenario: Legend accompanies an active raster layer
- **WHEN** a provider-rendered raster layer is active and reports `legend_available: true`
- **THEN** the provider's legend image is displayed with that layer
- **AND** no colour scale is constructed in the client

#### Scenario: A rendered-grid legend is captioned truthfully
- **WHEN** a `rendered_grid` layer is active with `legend_available: true`
- **THEN** the legend shown is the API-served colormap ramp, captioned as the
  exact mapping this experiment applies to the stored values, not as a
  provider legend

#### Scenario: No legend is served
- **WHEN** a raster layer reports `legend_available: false`
- **THEN** the layer is drawn and explicitly noted as carrying no provider legend
