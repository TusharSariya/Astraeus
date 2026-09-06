## ADDED Requirements

### Requirement: SWPC Kp is selected against an aware evidence instant
The experiment SHALL pass the client's aware selected instant to
`/space-weather`. One canonical observed request and one canonical forecast
request SHALL be cached independently of scrub timestamps, and native rows
SHALL be filtered only after the bounded documents validate.

#### Scenario: Observed and forecast rows surround a selection
- **WHEN** the observed document has rows before and after the selected instant
- **THEN** the observed series contains no future row
- **AND** the forecast series contains only entries at or after the selection with the provider's own observed, estimated, or predicted status
- **AND** no nearest row or interpolated Kp is substituted

#### Scenario: Forecast is unavailable
- **WHEN** observed Kp validates and the forecast request fails
- **THEN** observed Kp remains available and forecast is explicitly unavailable with no substituted values

### Requirement: Kp demand reads do not require retained Kp artifacts
The focused `/space-weather` response SHALL obtain Kp from the bounded demand
service without reading `kp_observed` or `kp_forecast` from ArtifactStore.
Solar wind MAY remain a separately labelled retained read until its own source
migration. After cutover, `/space-weather/products` SHALL NOT advertise a
retained `noaa-swpc-kp` artifact as current demand evidence.

#### Scenario: The retained store is unavailable
- **WHEN** demand Kp succeeds and the retained store is absent or raises
- **THEN** the Kp response remains live and solar wind alone is unavailable

### Requirement: Client Kp requests are bounded by completed evidence selection
The client SHALL refresh Kp when the selected evidence instant completes. It
SHALL NOT issue one `/space-weather` request per animation frame.

#### Scenario: Timeline playback advances
- **WHEN** playback changes the display clock between completed evidence reads
- **THEN** no frame-rate Kp request is issued
