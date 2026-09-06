## ADDED Requirements

### Requirement: Partial aggregate cache acquisition is refused pending a publication contract
When the restart cache reports both retained and missing requested valid times
for a provider run, the worker SHALL refuse `adapter.fetch` and SHALL preserve
retained revisions. No generic adapter flag SHALL authorize partial publication.
This barrier does not establish field/member completeness and does not prevent
payloads that an adapter already retrieved during discovery; those are explicit
remaining work, not zero-transfer claims.

#### Scenario: GFS full cache
- **WHEN** GFS discovery declares its bounded expected lead times and the cache reports every requested time present
- **THEN** the actual worker reports a no-op success and makes no GRIB range request

#### Scenario: GFS partial aggregate cache
- **WHEN** some requested GFS times are retained and some are missing
- **THEN** the actual worker refuses fetch, reports partial repair unsupported, and publishes nothing

#### Scenario: Retained times do not overlap the request
- **WHEN** same-run retained keys are entirely outside the requested time set
- **THEN** they do not block an otherwise cold-window fetch

#### Scenario: Store state is unknown
- **WHEN** the store cannot answer which run times are present
- **THEN** the worker fails before fetch rather than assuming an empty cache
