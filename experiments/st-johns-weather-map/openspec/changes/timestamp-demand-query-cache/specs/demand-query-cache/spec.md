## ADDED Requirements

### Requirement: A source query is driven by the selected timestamp
For the isolated experiment, a source query SHALL resolve the client's aware
selected timestamp to a provider-native valid time and retrieve the smallest
bounded provider-native response capable of answering that selection. It SHALL NOT prefetch a complete run
or substitute a neighbouring timestamp merely to fill a cache.

#### Scenario: A provider publishes on a three-hour cadence
- **WHEN** the selected timestamp is not a native valid time and the source contract does not define interval applicability
- **THEN** the query returns an explicit unsupported-time outcome and does not fetch or interpolate adjacent frames

#### Scenario: GFS answers an ordinary selected instant
- **WHEN** the selected instant has a GFS native frame at or before it with age strictly less than one hour
- **THEN** the query fetches only that frame's required indexed byte ranges and returns the requested instant together with the actual native valid time and age
- **AND** it refuses a future frame, a frame exactly one hour old, and a post-f120 three-hour gap that has no qualifying frame

### Requirement: The query cache prevents duplicate provider traffic
A lookup and coalescing key SHALL identify the canonical provider request:
provider, product, exact endpoint/query, selectors, eligible fields and
geography as applicable. Native source/run/valid/content identity learned from
the response SHALL be stored in the entry and returned provenance rather than
assumed before fetch. A fresh hit SHALL issue zero provider payload requests.
Concurrent identical misses or revalidations SHALL coalesce to one bounded
upstream operation.

#### Scenario: Two clients request the same missing selection
- **WHEN** both requests resolve to the same canonical provider request key
- **THEN** one upstream operation runs and both responses cite the same fetched content identity

#### Scenario: A repeated GFS point query hits the cache
- **WHEN** an identical selected run, lead, field set and geography is queried while its validated entry is fresh
- **THEN** the second `/point` response issues zero additional discovery, index or range requests and preserves the first response's run, native valid time, retrieval completion and content identity

### Requirement: Freshness and failure remain explicit
Each source SHALL derive a finite freshness interval from its provider contract
or recorded evidence. Expired content SHALL NOT be served as current. A failed,
invalid or oversized replacement SHALL NOT overwrite a still-valid entry, and
no stale fallback is permitted unless a later accepted source contract says so.

#### Scenario: Conditional revalidation fails after expiry
- **WHEN** the cached entry is expired and the provider revalidation is unavailable
- **THEN** the response is unavailable with the cached identity and expiry disclosed, and the expired values are not returned as current

### Requirement: Cache use preserves evidence semantics
The normalized cache entry and response SHALL preserve source/product/run,
provider publication and valid times, actual HTTP completion, native units,
geometry, masks, QC, missingness, request identity and content digest. Cache
storage technology is an implementation detail and SHALL NOT imply archive,
two-run retention, source admission or operational status.

#### Scenario: A cached response is served
- **WHEN** a fresh cache entry satisfies the exact canonical request
- **THEN** the response carries the same native evidence identity and retrieval provenance as the validated fill and is labelled experimental

#### Scenario: GFS decoding is isolated and validated before caching
- **WHEN** a GFS cache miss decodes selected indexed ranges
- **THEN** the decode runs under enforced process, output, input, stdout, stderr and workspace limits
- **AND** the parent validates the source, run, native time, manifest completeness, QC result, logical artifact names, ZIP members and aggregate byte size before admitting the entry

#### Scenario: The current client displays a demand-query result
- **WHEN** the user selects GFS and `/point` returns a live GFS response for the selected timestamp
- **THEN** the existing weather interface displays the returned values and source provenance and labels the model `live query at selected time`
- **AND** it does not infer availability from the retained-ingestion status endpoint

#### Scenario: GFS profile uses the selected native frame
- **WHEN** the Workbench requests a GFS profile for its selected timestamp
- **THEN** `/profile` uses the same bounded selected-frame cache entry and returns only pressure levels actually present
- **AND** pressure-level temperature and mixed-phase humidity preserve their native evidence while wind speed and direction identify the registered component derivation
- **AND** the response keeps the requested timestamp at top level and names the actual native timestamp without interpolation

#### Scenario: GFS timeline discovery retrieves metadata only
- **WHEN** the current timeline needs the selected GFS cycle's available native frames
- **THEN** one finite cached provider object listing supplies only validated `.idx` keys on the native hourly then three-hourly cadence inside the evidence window
- **AND** a truncated, malformed, declared or structurally oversized listing fails closed without fetching a GRIB payload

#### Scenario: GFS total geometric cloud renders from the selected cache entry
- **WHEN** a validated selected-frame GFS cache entry contains native `TCDC:entire atmosphere` and the client requests that exact native time through the advertised demand layer
- **THEN** the layer catalogue performs no provider request and advertises `total_cloud_geometric` as a retrieved percent capability only for that cached frame
- **AND** the bounded raster route preserves native missing cells as transparent pixels, applies the registered geometric-cloud percent palette without smoothing, and returns source, run, native-valid, upstream-completion and content-digest provenance
- **AND** a different field, frame, invalid bounds, unsupported CRS or oversized output fails explicitly without substituting an opacity-weighted field or a neighbouring frame
- **AND** this single native field does not complete GFS raster or source coverage under #97 or the residual field issues
