## ADDED Requirements

### Requirement: Cloud state is rendered with one palette, day and night
The cloud-mask layer SHALL render exactly five states from the stored NOAA
Enterprise Cloud Mask values, with the same palette at every hour: clear
fully transparent; probably-clear, probably-cloudy and cloudy as neutral
white whose opacity encodes detection confidence (cloudy scaled by the
stored cloud probability), with opacity capped below full so the basemap
stays readable; and invalid (quality-flagged) as a distinct non-white state
that is never transparent and never white. Opacity SHALL encode detection
confidence only — never cloud thickness — and no value SHALL be
interpolated, smoothed or resampled finer than the stored grid. The palette
and its semantics SHALL NOT vary with local solar time or between visible
and infrared conditions.

#### Scenario: Invalid is not clear
- **WHEN** a pixel carries a bad or missing quality flag
- **THEN** it renders in the distinct invalid state, visually separable from
  both transparent clear and white cloud, and is never rendered transparent

#### Scenario: Midnight looks like noon
- **WHEN** the same stored class and probability values are rendered for a
  daytime scan and a nighttime scan
- **THEN** the two renders are pixel-identical in colour and opacity

#### Scenario: Opacity is confidence, capped
- **WHEN** a pixel is cloudy with stored probability 1.0
- **THEN** its opacity is the declared maximum, which is below fully opaque,
  and a probably-clear pixel renders faint rather than invisible

### Requirement: Frames are observed scans only and staleness fails closed
The cloud-mask layer's frames SHALL be exactly the scan times of published
artifacts within the past window — never a generated range, never a future
instant, never a frame beyond the declared staleness tolerance. A requested
instant SHALL resolve only to the nearest stored scan within half the
cadence; beyond that the answer is 422 naming the nearest stored frame. When
no artifact within the staleness tolerance exists, the layer SHALL declare
itself unavailable in the index; a feed gap SHALL NOT be rendered, and in
particular SHALL never be presented as clear sky. A missing artifact is 404;
an unreadable one is 502 with nothing substituted.

#### Scenario: A feed gap is not a clear sky
- **WHEN** no cloud-mask artifact has been published within the staleness
  tolerance
- **THEN** the layer is reported unavailable with the reason, and no raster
  is served that could be read as an absence of cloud

#### Scenario: No frame within tolerance
- **WHEN** the requested instant is further than half a cadence from every
  stored scan
- **THEN** the response is 422 naming the nearest stored scan, and no older
  frame is silently substituted

#### Scenario: Scan time is authoritative
- **WHEN** a frame is served
- **THEN** the valid-time header carries the granule's own scan time, not
  the request instant and not an object-store timestamp

### Requirement: The rendering is disclosed, including its uncertainty
Every cloud-mask response SHALL carry rendered-grid provenance
(`X-Weather-Image-Basis: rendered_grid`, `X-Weather-Source-Id` naming the
ingested NOAA source) and semantics stating the values are NOAA
Enterprise Cloud Mask cloud probability, regridded nearest-neighbour from
the geostationary fixed grid, rendered by this experiment. The legend SHALL
show the transparent clear state over a labelled backdrop that makes it
visible, and its caption SHALL state: that opacity encodes detection
confidence, not cloud thickness; the provider-published detection accuracy
(approximately 90% day, 88% night) as NOAA's figure, not a local
measurement; that cloudy pixels are parallax-corrected using the
Provisional-maturity GOES-19 cloud-top height product; and that cloudy
pixels lacking a valid height are shown at their uncorrected apparent
position. The layer SHALL be described as satellite cloud probability and
never as a definitive statement of clear sky.

#### Scenario: A served tile names its basis
- **WHEN** a cloud-mask raster is served
- **THEN** it carries image basis `rendered_grid`, the source id, the scan
  time, and semantics naming NOAA cloud probability, nearest-neighbour
  regridding and this experiment as the renderer

#### Scenario: The legend does not hide the clear state
- **WHEN** the legend is served
- **THEN** the clear swatch is drawn over a labelled backdrop, and the
  caption carries the confidence-not-thickness sentence, the provider
  accuracy figures marked as NOAA's, and the Provisional parallax
  disclosures

### Requirement: The cloud mask stands beside the provider composites
The cloud-mask layer SHALL be listed in the same satellite group as the
proxied provider composites, which remain unchanged, so both can be viewed
at the same instant. The cloud mask SHALL be a transparent overlay capable
of being drawn above an opaque provider composite. The interface wording
SHALL distinguish the two truthfully: the composites are provider-rendered
imagery, the cloud mask is drawn by this experiment from stored NOAA
cloud-mask values, and neither description SHALL be applied to the other.

#### Scenario: Five satellite layers
- **WHEN** the layer index is read with the cloud-mask artifact published
- **THEN** the satellite group lists the four provider composites unchanged
  plus the cloud-mask layer

#### Scenario: Side by side at one instant
- **WHEN** a provider composite and the cloud mask are both active at a
  scan-matched instant
- **THEN** each serves its own frame for that instant under its own
  provenance, and the cloud mask renders as a transparent overlay

#### Scenario: The mask is absent, the composites remain
- **WHEN** no cloud-mask artifact is within tolerance
- **THEN** the four provider composites list and render exactly as before,
  and only the cloud-mask layer reports unavailable
