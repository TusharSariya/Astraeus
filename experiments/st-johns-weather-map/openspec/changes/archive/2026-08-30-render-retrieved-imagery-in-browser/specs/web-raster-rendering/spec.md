## Purpose

How the browser draws imagery the API retrieved from a provider, together with
that provider's own legend, without inventing extent, colour, or time.

## ADDED Requirements

### Requirement: Raster request extent SHALL be built from the endpoint's own parameter contract

The client SHALL send the map bounds as the four separate parameters the endpoint
declares, and SHALL NOT send a packed `bbox` string or a `crs` parameter. A
mismatch here does not fail loudly: the server would fall back to its default
extent and return a plausible image of the wrong place, and a transposed
EPSG:4326 box is answered HTTP 200 with a near-empty tile and no exception.

#### Scenario: The request names each bound separately
- **WHEN** the client requests imagery for a layer over the visible map bounds
- **THEN** the query carries `south`, `west`, `north` and `east` as individual
  parameters matching the endpoint signature
- **AND** it carries neither a comma-packed `bbox` nor a `crs` parameter

#### Scenario: A drifted parameter contract is caught by test, not by eye
- **WHEN** the raster URL builder is changed such that a bound is renamed, packed,
  reordered, or dropped
- **THEN** a test fails naming the expected parameters
- **AND** the failure does not depend on inspecting a rendered image

### Requirement: Imagery SHALL be drawn only where its provenance is established

An image is evidence only if the client can say where it came from, what it is,
and what instant it represents. The response carries that as `X-Weather-*`
headers.

#### Scenario: A layer that declares no raster is never requested
- **WHEN** a layer reports `raster_available: false`
- **THEN** the client does not issue a raster request for it
- **AND** it renders that layer's vector features if it has any, or nothing

#### Scenario: An image without retrieval provenance is refused
- **WHEN** a raster response omits the retrieval status or upstream layer headers
- **THEN** the client does not draw the returned bytes
- **AND** it reports the layer as unavailable with the reason

### Requirement: A transparent image SHALL be reported as a reading, not an outage

A fully transparent tile means the provider was asked and detected nothing. That
is a measurement. Reporting it as "unavailable" would erase a real observation of
absence, and reporting nothing at all would leave the reader unable to tell the
two apart.

#### Scenario: Radar with no echo
- **WHEN** a raster response returns HTTP 200 with
  `X-Weather-Retrieval-Status: retrieved` and a fully transparent image
- **THEN** the layer state reads as retrieved with nothing detected
- **AND** it is visually and textually distinct from a layer that was not retrieved

#### Scenario: The upstream could not be reached
- **WHEN** a raster request returns 502
- **THEN** the layer reports that it was not retrieved, naming the reason
- **AND** no previously drawn image for that layer remains on the map

### Requirement: The legend SHALL be the provider's own or absent

The interface SHALL NOT synthesize a colour scale. A drawn field with no legend is
uninterpretable, so the legend is fetched from the same provider that rendered the
image; if the provider serves none, the layer is drawn without one and says so.

#### Scenario: Legend accompanies an active raster layer
- **WHEN** a raster layer is active and reports `legend_available: true`
- **THEN** the provider's legend image is displayed with that layer
- **AND** no colour scale is constructed in the client

#### Scenario: No legend is served
- **WHEN** a raster layer reports `legend_available: false`
- **THEN** the layer is drawn and explicitly noted as carrying no provider legend

### Requirement: The client SHALL respect the upstream request budget

The proxy permits 16 upstream calls per request and 240 per rolling minute. Nine
proxied forecast layers scrubbed cold at once is 252 calls, which exceeds it.

#### Scenario: Only visible layers are requested
- **WHEN** several layers are toggled on but only some are visible
- **THEN** imagery is requested only for visible layers at the resolved frame

#### Scenario: The budget is exhausted
- **WHEN** a raster request returns 429
- **THEN** the layer reports that imagery was not retrieved because the request
  budget was reached
- **AND** the interface does not present the gap as an absence of weather
