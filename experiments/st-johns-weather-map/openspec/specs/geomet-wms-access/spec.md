## Purpose
Define how this experiment talks to ECCC GeoMet's OGC WMS endpoint — the source of radar, lightning, hazard and air-quality evidence and of all live-proxied map imagery — and pin the service behaviours that answer a fault with HTTP 200, so a fault is never handed to a reader as a picture or a number.

## Requirements

### Requirement: An OGC fault served as HTTP 200 is a failure, not bytes
Every response from the service SHALL be inspected for an OGC `ServiceException` in its body before its content type is trusted, and SHALL be raised rather than returned. The exception code carries the identity of the fault and SHALL be preserved in the reported reason. Checking the HTTP status code alone is not sufficient.

#### Scenario: An unadvertised TIME
- **WHEN** `GetMap` is asked for a frame the layer does not advertise
- **THEN** the service answers HTTP 200 with `Content-Type: text/xml` carrying `ServiceException code="NoMatch"`, and the client raises rather than returning that XML to a PNG decoder or publishing it as a tile

#### Scenario: An unadvertised DIM_REFERENCE_TIME
- **WHEN** a run the layer does not advertise is pinned
- **THEN** the same HTTP 200 `NoMatch` fault is raised rather than returned

#### Scenario: An unknown layer or style
- **WHEN** `LAYERS` names an unknown or group layer, or `STYLE` names an unknown style
- **THEN** the HTTP 200 `InvalidLayersParameter` or `LayerNotDefined` fault is raised, so a wrong identifier surfaces immediately

#### Scenario: A body that is not the requested image
- **WHEN** the response declares a content type other than the requested image format, or an empty body
- **THEN** it is raised naming what was asked for and what came back, rather than being served as an image

#### Scenario: A body larger than the ceiling
- **WHEN** a render exceeds the byte ceiling
- **THEN** it is refused rather than truncated, because half a PNG is a corrupt picture, not a smaller one

### Requirement: WMS 1.3.0 with EPSG:4326 is latitude-first, and a transposed box fails silently
Every `BBOX` sent with `CRS=EPSG:4326` at WMS 1.3.0 SHALL be ordered `miny,minx,maxy,maxx` — south, west, north, east. Bounds SHALL be carried as a named mapping rather than a bare four-tuple wherever they cross a boundary, and image provenance SHALL record the box by name.

#### Scenario: The correct axis order is used
- **WHEN** a tile is rendered over the Avalon
- **THEN** the bbox is sent latitude-first, and the returned image's provenance records `south`, `west`, `north`, `east` by name

#### Scenario: A transposed box is answered with silence
- **WHEN** the box is sent longitude-first
- **THEN** the service answers HTTP 200 with a roughly 96-byte near-empty PNG and no exception — which is why the order is asserted by test rather than assumed to fail loudly

#### Scenario: A box that is not south-west to north-east
- **WHEN** south is at or above north, or west at or above east
- **THEN** the request is refused client-side with a 422 before any upstream call

### Requirement: A time outside the advertised extent is refused client-side
The advertised `TIME` extent SHALL be read from `GetCapabilities` and a requested instant SHALL be snapped only onto an advertised instant. A time outside the extent SHALL raise before any request is made, because letting the service fall back to the layer default would attach a valid time the value does not have.

#### Scenario: An out-of-extent frame
- **WHEN** a requested instant lies outside the advertised extent
- **THEN** `TimeOutsideExtent` is raised without an upstream request, and the API reports 422 naming the layer — an unadvertised frame is "you asked for a frame that does not exist", never an outage

#### Scenario: A layer with no time dimension
- **WHEN** the layer advertises no time extent
- **THEN** no `TIME` parameter is sent, rather than one being invented

#### Scenario: An explicit value list extent
- **WHEN** the extent is a comma-separated instant list rather than start/end/period
- **THEN** it is parsed as those exact values

### Requirement: `GetFeatureInfo` answers one pixel at one time
`GetFeatureInfo` SHALL be understood as one value for one pixel at one instant. There is no TIME-range form and no multi-layer form; every value costs one polite request. Sample geometry SHALL therefore be a declared bounded set of points and boxes, and a dense gridded field SHALL come from GRIB rather than from the rendering service.

#### Scenario: A vector layer is queried as a box, not a point
- **WHEN** a vector layer such as `AQHI-OBS` or `Current-Alerts` is sampled
- **THEN** the query is sent as a declared box covering the Avalon core, because MapServer resolves a vector `GetFeatureInfo` against a search area derived from the map resolution and a tight probe around a point returns nothing at all

#### Scenario: A multi-layer query
- **WHEN** more than one layer name is passed in `LAYERS`
- **THEN** the service refuses with `InvalidLayersParameter`, so requests are made one layer at a time

#### Scenario: An empty or non-numeric answer
- **WHEN** the response carries an empty `features` array, a bare `{}`, or a non-numeric value
- **THEN** it is read as absence — a real answer meaning no value here — and is never replaced by a substituted value

#### Scenario: A mosaic with no run time
- **WHEN** `dim_reference_time` is the literal string `"N/A"`
- **THEN** it reads as no run time rather than as a parse failure

### Requirement: A fully transparent image is a reading, not an outage
An image the service actually returned SHALL be served with `X-Weather-Retrieval-Status: retrieved`, however few bytes it carries. A transparent PNG means retrieved and nothing detected. Only a failure to retrieve SHALL produce an error status, and it SHALL name which failure.

#### Scenario: Radar with no echo
- **WHEN** a radar tile comes back fully transparent at roughly 334 bytes
- **THEN** it is returned 200 with `X-Weather-Retrieval-Status: retrieved` and a header stating that a fully transparent image means retrieved and nothing detected

#### Scenario: Nothing was retrieved
- **WHEN** the upstream render fails
- **THEN** the API returns 502 naming the reason, and nothing is substituted for the image

### Requirement: Layer names, time axes and colour ramps are retrieved, never invented
The WMS layer for a published artifact SHALL come only from that artifact's own recorded `geomet_layer` provenance — there is no fallback table. Proxied layers' frames SHALL come from `GetCapabilities` at request time. Legends SHALL be the service's own `GetLegendGraphic`.

#### Scenario: An artifact with no recorded layer
- **WHEN** an artifact records no `geomet_layer`
- **THEN** no imagery is attached to it and `/layers/{id}/raster` answers 501 with its reason, rather than a layer name being inferred from the id

#### Scenario: A recorded name that is not a single LAYERS value
- **WHEN** an artifact records a combined name such as `RADAR_1KM_RRAI + RADAR_1KM_RSNO`
- **THEN** the pair is split, the first member alone is drawn, and the caller is told which member is shown — passing the composite through would be refused with `LayerNotDefined`

#### Scenario: Capabilities cannot be read
- **WHEN** `GetCapabilities` does not answer for a proxied layer
- **THEN** the layer is offered with no frames plus a notice, never with a generated hourly range that would scrub into `NoMatch` and look like an outage

#### Scenario: A hand-written colour scale
- **WHEN** a rendered field needs a key
- **THEN** only ECCC's own ramp is served, because a legend drawn here would be a fabricated key over real pixels

### Requirement: Proxied imagery is display evidence and is stamped as such
Imagery rendered upstream at request time SHALL be stamped `evidence_basis: live_proxy` on both the layer and the response, SHALL declare in words that it is not a published artifact, and SHALL NOT be stored, sampled by `/point`, counted in `/timeline`, or used to promote a registry source. Image bytes are always live-proxied, so `X-Weather-Image-Basis` is `live_proxy` even for a layer whose evidence rests on a published artifact.

#### Scenario: A proxied layer in the index
- **WHEN** the HRDPS proxied forecast layers are offered
- **THEN** each carries `evidence_basis: live_proxy`, semantics stating it did not pass this experiment's ingest manifest, QC or atomic publication, and a z-index below every published raster, and the index carries a notice repeating that they are display evidence only

#### Scenario: An artifact-backed layer's tile
- **WHEN** a tile is served for a layer backed by a published artifact
- **THEN** `X-Weather-Evidence-Basis` is `published_artifact` while `X-Weather-Image-Basis` is `live_proxy`, because no artifact in this experiment contains an image

#### Scenario: A layer that was never verified rendering
- **WHEN** a candidate WMS layer's render was not confirmed to carry a field
- **THEN** it is not offered — an unverified layer is absent rather than present and untrusted

### Requirement: Upstream calls are budgeted per request and per process
Upstream calls SHALL be counted at the transport, so cache hits cost nothing, and SHALL be bounded both per incoming request and per process over a rolling window. Exhaustion SHALL be reported as a 429 rather than fanned out.

#### Scenario: One request fans out
- **WHEN** a single API request would cause more than the per-request ceiling of upstream calls
- **THEN** the remainder is refused with `UpstreamBudgetExhausted`, surfaced as 429

#### Scenario: A scrub across the window
- **WHEN** the timeline is scrubbed repeatedly
- **THEN** capabilities and renders are answered from the shared TTL caches, so the same question is not re-asked upstream and the budget is not charged
