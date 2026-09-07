## ADDED Requirements

### Requirement: SWOB demand selection retains one complete native MSC station report
The `eccc-swob` demand reader SHALL issue one bounded canonical GeoMet OGC API
Features `swob-realtime` request for the exact selected UTC instant. It SHALL
admit a feature only when its native `data_pvdr-value` is exactly `MSC` and its
`dataset` begins `msc-observation-atmospheric-surface_weather-`. It SHALL refuse
a response with a next page, mismatched `numberMatched` or `numberReturned`, or
a feature-ceiling response without a count proving completeness. It SHALL retain
the provider feature id as `provider_report_id` separately from the native
station id whenever both are published.

Among identity-valid, exact-time reports it SHALL choose the nearest actual
station within 0.75 latitude-corrected degrees. Its request longitude envelope
SHALL cover that corrected-distance radius. This is station point selection:
`sample_method: nearest_published_cell` means one actual native station report,
not a rectilinear or curvilinear grid cell and never interpolation.

#### Scenario: A shared collection contains a nearer non-MSC station
- **WHEN** a canonical response contains an MSC report and a nearer NAV CANADA
  or other-provider report
- **THEN** only the MSC report is eligible and no partner value is served

#### Scenario: The collection advertises another page
- **WHEN** the bounded response has a `rel=next` link or a count that differs
  from the returned feature count
- **THEN** the selected-time point is unavailable and no first-page station is
  represented as the nearest actual station

### Requirement: SWOB native fields, provenance and expiry remain bounded
The reader SHALL preserve exact report time, station coordinates, station/report
identity, native units, and field-quality tokens for temperature, dew point,
relative humidity, mean-sea-level pressure, wind speed and wind direction.
Absent fields SHALL be null individually. No accepted per-field SWOB
quality-token-to-validity mapping currently exists, so every present numeric
value SHALL remain value-bearing with local QC `unknown`; its token is retained
verbatim and is not locally certified, reinterpreted, or used to null a value. It SHALL preserve only bounded canonical/effective request
identity, safe headers, body byte count/digest, final-byte completion and finite
expiry metadata. Identical misses SHALL coalesce and a fresh hit SHALL make zero
provider requests. After expiry a failed refresh SHALL withhold every SWOB value
and may expose typed bounded expired metadata with `values_withheld: true`.

### Requirement: SWOB default composition is cache-only and evidence-only
The default unselected `/point` response SHALL compose validated `eccc-swob`
station fields as `available-not-stored` evidence without a retained SWOB
artifact or consensus contribution. Layer listing SHALL advertise the SWOB
point layer from fresh source-local cache metadata only and SHALL make no
provider request. Scheduled SWOB ingestion SHALL be disabled after the demand
cache-to-API, default Linux child and fixed-live browser checks complete.
