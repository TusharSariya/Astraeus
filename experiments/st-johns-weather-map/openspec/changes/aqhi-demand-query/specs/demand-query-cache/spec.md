## ADDED Requirements

### Requirement: AQHI demand queries retain actual native station observations
The ECCC AQHI demand query SHALL make one canonical `AQHI-OBS` WMS vector request over the accepted Avalon box and SHALL validate native point geometry, station identity, observation time, numeric AQHI index, and coordinate before cache admission. For a default unselected point request it SHALL discard observations after the selected instant and observations whose age is one hour or greater, then choose the nearest remaining actual station by the accepted latitude-corrected distance. A tie in distance SHALL prefer the newest native observation and then stable station identity. It SHALL NOT construct a rectangular station grid, interpolate, convert AQHI to any concentration or aerosol quantity, or add health interpretation.

#### Scenario: A nearer station observation is older than another applicable station
- **WHEN** two real station point features are less than one hour old and the nearer station has the older observation
- **THEN** the nearer station is served unchanged because spatial selection chooses the nearest applicable published cell before native time breaks a distance tie

#### Scenario: An observation is exactly one hour old
- **WHEN** the newest eligible native observation has age exactly one hour
- **THEN** it is unavailable and no future, older, or more distant observation is substituted

### Requirement: AQHI cache and public acquisition metadata are bounded
The AQHI cache SHALL retain at most one normalized station document under 256 KiB after enforcing a 2 MiB received-body ceiling and bounded decoder resources. A fresh hit SHALL cost zero provider requests and concurrent misses SHALL coalesce. Freshness SHALL be finite and SHALL NOT exceed five minutes. After expiry, failed refresh SHALL discard all station values and retain only typed bounded request/transport identity, body byte count and digest, final-byte time, cache admission and expiry. Public failure metadata SHALL state that values were withheld and SHALL NOT retain raw body bytes, arbitrary headers, exception tracebacks, or stale station values.

#### Scenario: Refresh fails after final-byte expiry
- **WHEN** a cached AQHI response expires and its replacement fails
- **THEN** no AQHI value is served, while the point response exposes the expired bounded acquisition identity and `values_withheld: true`

### Requirement: AQHI default evidence is independent of retained artifacts
The default unselected point response SHALL obtain `eccc-aqhi` evidence from the demand cache without reading a retained AQHI artifact. The field SHALL remain `aqhi` with catalogue key `air_quality_health_index`, native `index` units, observation time, actual station identity and coordinate, corrected sample distance, and unknown local QC unless an accepted mapping defines a provider token. Layer listing SHALL hide retained AQHI layers and advertise the demand observation from fresh source-local cache metadata only, making no provider request. Scheduled `eccc-aqhi` ingestion SHALL fail before discovery.

#### Scenario: Forecast demand and artifact storage are unavailable
- **WHEN** a validated AQHI demand result exists but no forecast demand source or artifact store is reachable
- **THEN** the default point response returns the AQHI observation as evidence-only with its own provenance

#### Scenario: Layer listing has no cache entry
- **WHEN** the layer catalogue is read before AQHI has a fresh cache entry
- **THEN** it performs no AQHI provider request and advertises no invented native observation time
