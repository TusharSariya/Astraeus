# WeatherNext statistics experimental query seam

This is experimental software, authorized by the current API-first execution
plan. It does not accept the draft WeatherNext source contract or enable
production scheduling, registration, consumer mappings or unrestricted serving.

## Reused implementation and evidence

`api/weather_api/weathernext_query.py` reuses
`ingest/adapters/weathernext3_statistics.py::validate_acquisition`, including
all 126 inventory dispositions, source object generation/ETag/read mechanism,
run/lead/time, native units and fill masks. The existing bounded sample scripts
already decode native Zarr chunks; this query does not duplicate that collector.
The injected "acquire(selection) -> bytes" seam supplies a retained or newly
bounded acquisition manifest, and has no default transport. The caller must
bound acquisition before constructing the returned byte string. Query-side
validation rejects manifests above 16 MiB before JSON decoding; this is not
process-isolated decoding or a limit on memory allocated inside the callback.

The explicit selection includes initialization, exact hourly valid time, point
and documented provider statistic fields. Different runs, fields and statistics
have distinct cache keys. Only retained native cell footprints are answerable;
the returned coordinates are actual retained cell centres. Missing selected
fields, unrepresented leads and distant points fail, never use another run or
synthetic cadence. Nulls remain null. No fog, cloud base, pressure level or raw
member is fabricated. Hourly run horizons are capped at 360 hours for 00/06/12/18
UTC and 48 hours for interim initializations.

All 126 arrays are queryable native values when the acquisition contains them.
The default request asks for 24 total/low/medium/high cloud statistics. The
existing six-field box supports only its six acquired statistics. These counts
are decoder capability, not accepted consumer field mappings or successful live
serving. There is no SourceReader registration or frontend activation here.

## Cache and receipt

The source-local cache retains at most eight normalized entries and 2 MiB of
serialized-representation accounting, with a fixed 60-second lifetime from
manifest acquisition completion. It also bounds concurrent distinct acquisitions
to eight. Identical misses/refreshes coalesce; a hit does not invoke acquisition
or renew its receipt. Explicit refresh attempts acquisition; an unchanged unexpired manifest keeps its
original receipt and deadline. Failure is reported
and preserves an unexpired entry for a later ordinary read. Expired entries are
withheld. This cache bounds entry/value cardinality, not Python allocator RSS.

Receipts retain source/product/run/valid time, manifest SHA-256 and byte count,
original source retrieval time, local acquisition completion and fixed expiry.
The evidence class is explicitly retained acquisition manifest replay. Manifest
bytes are not reported as provider payload bytes, and replay completion does
not relabel the source's original retrieval as current. Manifest identity checks
prove structural consistency, not independent authentication of JSON provenance.
The tests use tracked manifests; no provider, authenticated request or new raw
capture occurs. No Linux bounded-child or current live proof is claimed.

## Access and terms remain separate

The only intended acquisition surface is
`gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/`.
Google's [GCS guide](https://developers.google.com/weathernext/guides/gcs), checked
2026-09-07, declares statistics Requester Pays OFF and pre-flattened hourly lead
time, with six reductions over surface fields and no pressure levels. The raw
64-member bucket uses Requester Pays and remains excluded.

The same guide and [current terms PDF](https://storage.googleapis.com/weathernext-public/terms-of-use.pdf)
(last modified 2026-09-03) now distinguish historical valid times at least one
hour old from more recent and future data. Older cached search text describes a
48-hour boundary. This change does not broaden the experiment: the software
retains the explicitly requested conservative strict greater-than-48-hour valid-
time gate. Initialization age alone never establishes historical eligibility.
Recent and future values are refused before acquisition, including cache hits;
there is no boolean configuration switch that grants terms permission.
Restricted serving requires separately established permission and owner-reviewed
scope. Configuration readiness cannot supply that permission.

No WeatherNext API key is required by this seam. A future authenticated collector
must use the existing approved credential-resolution workflow after the required
aws-secrets-manager skill is available; never inspect local gcloud credentials,
print tokens, place credentials in manifests, or add requester billing headers.
The callback must validate the exact statistics bucket/prefix, generation-qualified
object reads and byte counts using the existing acquisition identity contract,
bound metadata and raw payload operations, and return only safe failures.
Authentication, entitlement and terms are independent outcomes. No authentication
or configuration code was added in this slice.

## Verification

`api/tests/test_weathernext_query.py` exercises all126 native values/units/grids,
six SST masks, six-field box selection, run/time/location refusal, strict terms
boundary, manifest size/entry ceilings, zero-acquisition cache hit, expiry,
concurrent misses/refreshes, failed replacement and safe error redaction.
The established adapter regression suite checks experimental isolation and
publication refusal. Tests are fixed retained-fixture replay, not live proof.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006
Classification: experiment; existing WeatherNext draft isolation is preserved.
