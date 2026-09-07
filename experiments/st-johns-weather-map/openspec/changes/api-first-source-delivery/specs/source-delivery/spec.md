## ADDED Requirements

### Requirement: Delivery capability is separate from retrieval
Source catalogue responses SHALL declare implemented point and optional native
Series paths with source, product, field, variant, level and run policy. Reading
the catalogue SHALL perform no provider request. Capability SHALL NOT establish
successful retrieval, coverage, freshness, QC or source admission. An absent
implementation SHALL remain distinguishable from an implemented path with no
applicable reading.

#### Scenario: A configured path has never retrieved data
- **WHEN** its catalogue and status are read
- **THEN** its software capability remains visible while retrieval and coverage
  remain unknown or unavailable

### Requirement: Native source selections preserve complete identity
Explicit selectors SHALL preserve source/product/field/variant/level/run and
requested location/time through request, native planning, response, pagination
and inspection. An unsupported explicit identity SHALL be refused before source
acquisition. Legacy selectors MAY omit newly added identity dimensions and
retain existing behavior. Native readings SHALL retain their actual run, time,
station or sampled cell and source provenance without inferred coordinates or
synthetic cadence. Existing Series ceilings and fixed expiry SHALL remain.

#### Scenario: Same-source runs or statistics differ
- **WHEN** two readings differ by run, member, statistic, threshold or level
- **THEN** their identities remain distinct and continuation cannot substitute
  one for the other

### Requirement: Source read implementation remains local
GFS indexed GRIB and AQHI OGC WMS JSON SHALL implement the same narrow descriptor
and point-read interface while retaining their own acquisition, native timing,
decoding, caches and bounds. Optional native Series planning SHALL return actual
source timestamps only. Explicit refresh SHALL not renew an older selection;
failed revalidation SHALL not label unexpired evidence as expired or expired
evidence as current. Concurrent identical misses or refreshes SHALL coalesce.

#### Scenario: A cached point is read again
- **WHEN** its source-local entry remains valid
- **THEN** the source returns the same native identity without downloading a
  provider payload or extending the fixed lifetime

### Requirement: Selected models may carry the named AQHI observation
A selected forecast product MAY carry only the validated `eccc-aqhi`
`air_quality_health_index` native station observation as an air-quality
companion, with its own station identity, observation time, index units and
provenance. This SHALL NOT admit the whole air_quality category, AQHI forecasts,
PM concentrations or a run-bearing AQHI field. Missing AQHI SHALL not replace or
invalidate the selected model; its typed acquisition failure SHALL remain visible.

#### Scenario: AQHI is available beside a selected model
- **WHEN** a selected model and an applicable AQHI station observation are read
- **THEN** both preserve their own identities and AQHI is never attributed to
  the selected forecast model

### Requirement: Configuration outcomes are safe and independent
Existing status responses SHALL distinguish missing configuration, denied
access, unavailable product, missing compute, failed acquisition, readiness and
unknown assessment. They SHALL return safe reasons and configuration names only,
never credentials, signed URLs, private file contents or raw provider exceptions.
Readiness SHALL NOT assert live verification, entitlement or terms permission.

#### Scenario: An inference model needs deployment
- **WHEN** a client is implemented but its required compute or initialization
  data is absent
- **THEN** status describes that missing prerequisite separately from credentials

### Requirement: Backend and frontend consume one generated contract
Affected OpenAPI and TypeScript definitions SHALL be generated from Pydantic.
Backend contract tests and frontend development SHALL share deterministic fixture
responses. Fixtures SHALL not be described as authenticated or current live
proof. Generic selectors SHALL remain available from capabilities even when
point retrieval returns no values, preserving unsupported retained selections
with an explicit reason.

#### Scenario: An optional field has no current reading
- **WHEN** the catalogue declares its implemented native delivery path
- **THEN** the selector remains visible while the result reports its actual gap
