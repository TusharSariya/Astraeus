## Purpose
Define the layer index a map draws from: how a published artifact's stored geometry decides what it may be drawn as, how each layer keeps its own time axis at its native cadence, and how a layer declares the staleness tolerance beyond which it must render nothing rather than misdate an older frame as current.

## Requirements

### Requirement: How a layer may be drawn comes from its stored geometry, never its media type
Layer kind SHALL be derived from the coordinates the artifact actually carries. The media type only decides whether this API can read the artifact at all; an artifact whose geometry cannot be vouched for SHALL NOT be offered as a layer, and SHALL instead produce a notice saying so.

#### Scenario: A single sampled pixel is not a field
- **WHEN** an artifact stores a WMS `GetFeatureInfo` series — one pixel at one time — inside a Zarr container
- **THEN** it is offered as a `point` layer, never a `raster`, because drawing one sampled pixel as an area would spread a single measurement across the Avalon as though it had been measured everywhere

#### Scenario: A station outer product is points
- **WHEN** an artifact carries fewer than 16 distinct values on either coordinate axis, such as three AQHI stations stored on a 3x3 outer product
- **THEN** it is enumerated as sites so the six never-measured placeholder cells can be dropped, rather than drawn as a field

#### Scenario: A real field is a raster
- **WHEN** latitude and longitude both vary over at least 16 values
- **THEN** the layer kind is `raster`

#### Scenario: A vector collection is an alert layer
- **WHEN** the artifact's media type is `application/geo+json`
- **THEN** the layer kind is `alert`

#### Scenario: An unrenderable or unknown-geometry artifact
- **WHEN** the media type is outside the renderable set, or the geometry is neither gridded nor an enumerable site list
- **THEN** the artifact is omitted from the layer index with a notice naming it and its media type, rather than being guessed at

### Requirement: Every layer carries its own time axis at its own cadence
`times` SHALL be exactly the instants read from the artifact's own time coordinate — never a generated range. An empty list SHALL mean the artifact declared no time axis, never that it covers every hour. Cadence SHALL be the modal gap between consecutive frames and SHALL be `null` below two frames. Layers SHALL NOT be collapsed onto a shared hourly axis.

#### Scenario: Native cadences are preserved
- **WHEN** radar publishes every six minutes, lightning every ten and METAR hourly
- **THEN** each layer reports its own frames and its own cadence, so each can be scrubbed at the resolution it actually has and a gap can be shown as a gap

#### Scenario: One missing frame does not redefine the cadence
- **WHEN** a run has one double-length gap because a lead is missing
- **THEN** the reported cadence is the modal gap, not the mean, since averaging would report a cadence the layer never publishes at

#### Scenario: A vector artifact's frames
- **WHEN** a GeoJSON artifact declares valid times in its provenance
- **THEN** those are its frames; with none declared, the run time alone is used, and an artifact declaring neither gets no frames rather than an invented one

### Requirement: A layer declares a staleness tolerance and renders nothing beyond it
Every layer SHALL publish `staleness_tolerance_seconds`. It SHALL be half the derived cadence, floored at 60 seconds; a layer whose cadence cannot be derived SHALL receive a bounded unknown-cadence tolerance of 900 seconds rather than none, so a lone frame cannot answer for the whole window. When the requested time is further from the nearest published frame than the tolerance, the client SHALL render nothing and say why — showing an older frame would misdate the evidence.

#### Scenario: Within tolerance
- **WHEN** the requested time is nearer the resolved frame than to any other, within half a cadence
- **THEN** the frame is drawn, and its signed offset from the requested time is displayed beside it

#### Scenario: Beyond tolerance
- **WHEN** the nearest frame of a six-minute radar layer is an hour from the requested time
- **THEN** no frame resolves, nothing is fetched and nothing is drawn, and the reader is told there is no frame within the layer's tolerance

#### Scenario: A layer that declared no tolerance
- **WHEN** a layer item carries no numeric `staleness_tolerance_seconds`
- **THEN** the client assumes none and resolves no frame, rather than adopting a default

#### Scenario: A layer with no frames
- **WHEN** a layer published no times
- **THEN** no frame resolves and the reason given is that the layer published no frames

### Requirement: Stored values are served for an exact declared frame only
`/layers/{id}/features` SHALL return the stored values for one layer at one exact frame, chosen by the client from the layer's own declared times. It SHALL NOT snap to a neighbouring frame. A time with nothing stored SHALL return an empty collection with `data_mode: "unavailable"` and a notice stating that nothing has been substituted. A layer id that is not currently published SHALL be a 404.

#### Scenario: An exact frame with values
- **WHEN** a frame the layer declared is requested
- **THEN** the stored features are returned with `data_mode: "live"`, their geometry passed through as published and only provenance added

#### Scenario: An exact frame with no stored values
- **WHEN** a declared frame holds no value at the requested instant
- **THEN** the collection is empty with a notice naming the layer and time and stating that nothing was substituted

#### Scenario: A cell with no value
- **WHEN** a stored site's variables are all NaN at that frame
- **THEN** no feature is emitted for that site, because NaN is absence rather than a reading

#### Scenario: A rotated-grid artifact
- **WHEN** features are requested for a curvilinear artifact
- **THEN** no site enumeration is attempted, since such an artifact is a field rather than a set of stations

### Requirement: Draw order keeps observations above fields
Every layer SHALL carry a `z_index` derived from its kind — raster below mask, line, alert, then point on top — so a station reading is never hidden beneath a raster it disagrees with. Layer identifiers SHALL be formed in exactly one place from source id and logical name, so the API and the store cannot disagree.

#### Scenario: An observation over a field
- **WHEN** a point layer and a raster layer are both active
- **THEN** the point layer draws above the raster

#### Scenario: Layer ids are consistent
- **WHEN** a layer id is needed by the layer index, the coverage map or the features endpoint
- **THEN** all three derive it from the same function
