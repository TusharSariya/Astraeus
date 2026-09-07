## ADDED Requirements

### Requirement: AIWP demand preserves four native producer identities
The proposed operational-false service SHALL distinguish GRAP_v100_GFS, GRAP_v100_IFS, PANG_v100_GFS and PANG_v100_IFS. It SHALL bind namespace, native model_name, initialization_model, native version attribute, run, valid time, object URL, ETag and length. A metadata identity mismatch SHALL refuse the object. It SHALL initially expose only t2 in K and msl in Pa, retaining provider-native names and without inferred QC approval.

#### Scenario: Initializer identity differs
- **WHEN** a GFS request resolves an object declaring IFS
- **THEN** the service returns unavailable and does not substitute that object

#### Scenario: Native version differs from namespace
- **WHEN** namespace v100 contains version attribute 3_2025-02-20
- **THEN** both are preserved separately and neither is represented as a checkpoint hash

### Requirement: AIWP selects one exact native valid time and coordinate
The proposed resolver SHALL require an aware selected timestamp and finite latitude/longitude. It SHALL inspect at most the latest two UTC calendar-date prefixes at or before min(selected time, acquisition clock), using one ListObjectsV2 request per date with max-keys=4 and a 64KiB body cap. A truncated listing SHALL refuse rather than imply completeness. It SHALL consider only canonical objects for the requested identity with run at or before both selected time and acquisition clock, newest run first. At most four candidate metadata checks SHALL occur. It SHALL choose the newest successfully verified candidate containing an exact native valid timestamp, with no temporal interpolation. Missing eligible publication SHALL be unavailable, not latency-based proof of absence beyond that bounded search.

The service SHALL validate quarter-degree rectilinear latitude/longitude coordinates against native arrays and require the requested point within their native coverage. It SHALL select minimum-distance coordinate on each native axis after longitude normalization; equal-distance ties SHALL use lower native array index. Response SHALL include requested and selected native coordinates. It SHALL reject missing/nonfinite selected cells without reconstruction.

#### Scenario: Exact time and nearest point exist
- **WHEN** a fixed fixture has the selected native valid time and finite t2/msl at the selected native point
- **THEN** the response returns those native values, coordinates and units bound to that run

#### Scenario: Time falls between six-hour records
- **WHEN** no inspected candidate contains the exact selected valid time
- **THEN** the result is unavailable without interpolation or another initializer

#### Scenario: Listing cannot establish bounded candidates
- **WHEN** a listing is truncated or the candidate budget is exhausted
- **THEN** the result states bounded discovery unavailable and does not claim complete provider absence

### Requirement: AIWP native ranges have one finite resource envelope
Before I/O the proposed service SHALL reserve memory for two decoded 4,152,960-byte planes, bounded metadata/index/HTTP buffers and normalized output, plus admitted cache backing. A query for one identity SHALL receive no more than 8 MiB total and make no more than 128 HTTP requests across discovery, metadata, payload and retries. It SHALL decode at most two selected surface planes, never a whole forecast horizon. It SHALL inspect native chunk offsets, compressed sizes and filters before fetching payload and refuse a chunk exceeding remaining bounds. Unsupported schema/filter/units SHALL refuse.

Every object range SHALL require 206, exact Content-Range/length and consistent object ETag/length. Reads SHALL use If-Match with the pinned ETag. Missing ETag, changed identity, ignored Range or truncated bytes SHALL invalidate the attempt. Completed-body receipts SHALL preserve final-byte time and body hash separately from publication, run and valid time; completed receipts survive a later decode failure. No client library may bypass the shared capped transport.

#### Scenario: Server ignores Range
- **WHEN** a range request returns 200 with a multi-GB object
- **THEN** the service refuses without consuming the full body or resetting the budget

#### Scenario: Chunk exceeds remaining query allowance
- **WHEN** the native chunk index declares more bytes than remain
- **THEN** the payload request is not issued and the result is resource-unavailable

#### Scenario: Object changes between metadata and data
- **WHEN** If-Match fails or ETag/length differs
- **THEN** mixed bytes are never decoded or cached as one object

### Requirement: AIWP demand uses finite cache freshness and truthful failures
The proposed cache SHALL key resolution by identity, selected timestamp and coordinate and bind data to resolved URL/ETag, native run/time/field selectors and native coordinate. It SHALL coalesce identical misses. Freshness SHALL be less than 600 seconds from completed validation; at exactly 600 seconds revalidation is required. A fresh repeated query SHALL cause zero discovery, range or decode operations. Revalidation SHALL perform bounded discovery and verify selected object identity; successful unchanged validation may start a new 600-second freshness period. Failed revalidation SHALL not serve expired values. Chunk reuse SHALL be object-identity scoped and constrained by admitted finite byte capacity; permanent retention or full-run prefetch is forbidden.

#### Scenario: Fixed-clock repeated request is fresh
- **WHEN** an identical query occurs 599 seconds after completed validation
- **THEN** the same native result is returned with no provider or decode work

#### Scenario: Exact expiry or failed revalidation
- **WHEN** the clock reaches 600 seconds and revalidation fails
- **THEN** the service returns unavailable rather than presenting expired data as live

#### Scenario: Concurrent identical misses
- **WHEN** two requests miss the same canonical query together
- **THEN** one bounded acquisition runs and both responses preserve its provenance
