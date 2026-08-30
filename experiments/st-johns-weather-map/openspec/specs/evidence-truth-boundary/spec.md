## Purpose
Define the one boundary the whole experiment exists to hold: a response may only carry what was actually retrieved, so every surface declares an explicit data mode, a configuration mistake fails closed to `unavailable`, and development fixtures are reachable only behind an explicit switch and are watermarked wherever they are shown.

## Requirements

### Requirement: Exactly four data modes, declared on every response
Every API response SHALL carry a `data_mode` of `live`, `fixture`, `mixed` or `unavailable`, and SHALL carry `operational: false`. `unavailable` SHALL mean that nothing was retrieved and nothing was invented, so that a caller can distinguish an outage from a reading without interpreting an HTTP status code. Response models SHALL forbid unknown fields (`StrictModel`, `extra="forbid"`) so an undeclared field cannot enter a response silently.

#### Scenario: A live response declares live
- **WHEN** `WEATHER_DATA_MODE=live` and published artifacts answer the request
- **THEN** the response carries `data_mode: "live"` and `operational: false`

#### Scenario: Source status is mixed when only some sources have retrieved
- **WHEN** `/sources/status` is read in live mode and a live retrieval has been recorded for some but not all registry sources
- **THEN** the response-level `data_mode` is `mixed`, each row carries its own `data_mode` (`live` only where a retrieval was recorded, `unavailable` otherwise), and no row is promoted on the strength of the registry declaration alone

#### Scenario: An extra field is rejected rather than absorbed
- **WHEN** a payload carries a field the model does not declare
- **THEN** validation fails, because `StrictModel` forbids extras

### Requirement: A missing or malformed data mode fails closed
`WEATHER_DATA_MODE` SHALL be read once per process and SHALL resolve to `unavailable` unless it is exactly `live` or `fixture`. An unset, blank or misspelt value SHALL NOT resolve to `fixture`, because a deployment mistake must never silently become synthetic weather. The resolution SHALL be logged as an error.

#### Scenario: The variable is unset
- **WHEN** `WEATHER_DATA_MODE` is not set and `/point` is requested
- **THEN** the response is `data_mode: "unavailable"`, every field value is `null`, and the provenance quality flags include `no_retrieval` and `data_mode_unconfigured`

#### Scenario: The variable is misspelt
- **WHEN** `WEATHER_DATA_MODE` is set to a value such as `LIVE-ish` or an empty string
- **THEN** the deployment resolves to `unavailable` and never serves fixture values

#### Scenario: A refresh cannot be queued in an unconfigured deployment
- **WHEN** `POST /refresh` is called with no valid data mode configured
- **THEN** the request is refused with 503 stating that the deployment fails closed, rather than creating an in-memory fixture job

### Requirement: No path from a live failure to a fixture value
In `live` mode a store error, an unreachable store, an unreadable artifact or an empty artifact set SHALL produce `data_mode: "unavailable"` with null values and provenance saying so. The API SHALL NOT fall back to `fixtures.py` for any reason, and SHALL NOT return a number it did not read from a published artifact.

#### Scenario: The live store raises while sampling
- **WHEN** `/point` is requested in live mode and the artifact store raises
- **THEN** the response is `unavailable` with a `live_store_error` flag and a notice naming the failure, and every field value is `null`

#### Scenario: The live store is reachable but publishes nothing
- **WHEN** `/point` is requested in live mode and no published artifact covers the coordinate and time
- **THEN** the response is `unavailable` with a `no_published_artifact` flag, and no fixture temperature appears

#### Scenario: Layers are unavailable rather than the fixture list
- **WHEN** `/layers` is requested in live mode and nothing is published
- **THEN** the layer list is empty with `data_mode: "unavailable"` and a notice, never the fixture layer catalogue

### Requirement: Fixtures are gated, stamped and watermarked
Synthetic values SHALL be reachable only under `WEATHER_DATA_MODE=fixture` on the API and only under `import.meta.env.DEV && VITE_WEATHER_FIXTURES === 'true'` in the web client. Every fixture field SHALL carry `provenance.data_mode = fixture`, and any interface showing them SHALL display a persistent on-screen watermark naming them as development fixtures rather than live evidence.

#### Scenario: Every field is stamped, not just the response
- **WHEN** `/point` is served in fixture mode
- **THEN** the response `data_mode` is `fixture` and every field's `provenance.data_mode` is also `fixture`

#### Scenario: The browser cannot reach fixtures in a production build
- **WHEN** the API request fails and the build is not a development build with `VITE_WEATHER_FIXTURES === 'true'`
- **THEN** the client renders the unavailable snapshot with the failure reason, and never the fixture snapshot

#### Scenario: A non-live screen is watermarked
- **WHEN** the resolved data source is anything other than `live`
- **THEN** a status banner naming that state is displayed (`DEVELOPMENT FIXTURE · NOT LIVE EVIDENCE` for fixture), and the map surface additionally carries a `FIXTURE` watermark in fixture mode

### Requirement: The browser trusts the declared mode, not the status code
The web client SHALL derive its data mode from the response body's declared `data_mode` and SHALL treat any missing or unrecognised value as `unavailable`. An HTTP 200 SHALL NOT by itself be read as live evidence, and a schema that does not match SHALL be reported as unavailable with its reason rather than partially rendered.

#### Scenario: A 200 with no declared mode
- **WHEN** `/point` returns HTTP 200 with no `data_mode` key
- **THEN** the client reports `unavailable` with the message that the response declared no `data_mode`, and shows no values

#### Scenario: An incompatible schema
- **WHEN** `/layers`, `/catalog` or `/sources/status` returns a body whose shape does not match
- **THEN** the client reports unavailable with an "incompatible schema" reason instead of rendering a partial list

#### Scenario: "Could not ask" is not "nothing is live"
- **WHEN** `/sources/status` cannot be read at all
- **THEN** the client holds `statuses = null` rather than an empty array, because an empty array would assert that no source is live

### Requirement: An empty retrieved answer is distinct from no retrieval
A result that was retrieved and is genuinely empty SHALL be represented as evidence, not as an outage, and SHALL be distinguishable from a retrieval that did not happen. Adapters SHALL publish an explicit observed flag alongside the absent quantity so the two cases can never collapse into one another.

#### Scenario: Radar detected nothing
- **WHEN** the radar mosaic answers `{"value": 0, "class": "Undetected"}` at a sampled pixel
- **THEN** the artifact records `radar_echo = 0` (mandatory, unit `flag`) and omits `precipitation_rate` entirely; `0 mm/h` never appears as a rate

#### Scenario: The radar did not answer at all
- **WHEN** the service refuses the scan
- **THEN** `radar_echo` is missing rather than `0`, and the run fails validation rather than publishing an "everything clear" artifact

#### Scenario: Lightning returns a bare empty object
- **WHEN** the lightning layer answers `{}` with no `features` key
- **THEN** `lightning_observed = 0` is published as a flag and `lightning_strike` is absent

#### Scenario: No alert is in force
- **WHEN** the CAP alerts query returns a valid empty `FeatureCollection` for every declared box
- **THEN** that is a publishable answer with `alerts_in_force = 0` per box, and the empty collection is published byte-for-byte; a box that was never successfully queried leaves `alerts_in_force` missing instead

#### Scenario: A partly queried domain cannot claim the all-clear
- **WHEN** some of the declared alert query boxes failed
- **THEN** the run cannot report that no alert is in force over the Avalon

### Requirement: A skipped artifact is reported, never silently dropped
When a published artifact cannot be read, the store SHALL record the skip with its source id, revision id and reason, and the API SHALL surface those skips as response notices. Other artifacts SHALL continue to answer. A skip SHALL NOT be represented as an absence of evidence.

#### Scenario: One corrupt artifact among several
- **WHEN** one artifact fails to open and others read normally
- **THEN** the readable artifacts still produce fields, and the response carries a notice naming the skipped artifact, its revision and the failure type

#### Scenario: A vector artifact is not a failed sample
- **WHEN** a GeoJSON artifact is encountered during gridded point sampling
- **THEN** it is skipped as a category difference with no skip notice, because reporting it would tell every caller that evidence had been lost when none had

### Requirement: Every client fetch SHALL apply the declared data mode

The client SHALL resolve `data_mode` on every fetch, including `/timeline`, by the same fail-closed rule. The fail-closed mode rule is applied to point, layers, catalogue and source
status, but not to the timeline, which is returned raw. A timeline served in
`unavailable` mode is currently indistinguishable from a live one, and it drives
which hours the reader is told carry evidence.

#### Scenario: The timeline declares a mode
- **WHEN** the client reads `/timeline`
- **THEN** it resolves the response's `data_mode` by the same rule as every other
  fetch
- **AND** an absent or unrecognised mode resolves to unavailable

#### Scenario: An unavailable timeline is not presented as coverage
- **WHEN** `/timeline` resolves to `unavailable`
- **THEN** the interface does not present its hours as published coverage
