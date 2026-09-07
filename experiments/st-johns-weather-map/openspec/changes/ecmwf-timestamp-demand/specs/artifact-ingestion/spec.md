## MODIFIED Requirements

### Requirement: An unresolved provider stays non-publishing with a stated reason
An adapter whose endpoint contract, grid geometry or field assembly is unresolved SHALL raise `AdapterUnavailable` with that reason and SHALL NOT publish. Its registry record SHALL stay at its declared non-active status. No regridding, no guessed listing contract and no assumed cycle mapping SHALL be invented to make it publish.

#### Scenario: DWD ICON Global
- **WHEN** ICON Global ingestion is attempted
- **THEN** both entry points raise `AdapterUnavailable` stating that the native icosahedral mesh cannot be cropped to a bbox or sampled at a coordinate without a documented regrid, and nothing is published

#### Scenario: ECMWF Open Data IFS
- **WHEN** IFS discovery lacks verified advertised product/run/lead identity
- **THEN** it raises `AdapterUnavailable` and publishes nothing

#### Scenario: Verified ECMWF timestamp-demand access
- **WHEN** an owner-accepted ECMWF demand product resolves exact native identity under the ecmwf-timestamp-demand contract
- **THEN** bounded demand retrieval may serve its verified native values through finite cache without activating the legacy scheduled artifact publisher
