# WeatherNext profile access and isolated GCS transport

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-006. Draft source isolation and production gates remain unchanged.

The owner explicitly authorized existing Google authentication on September 7
("if you have auth use it"), overriding the previous missing-secret-skill hold
for this path. A runtime token from `gcloud --configuration astraeus` was captured
only in process memory. No credential files, service accounts, tokens or account
identifiers were printed or persisted. No login, deployment or ADC changes were
performed. The selected profile has no configured project. Existing gcloud
profile authentication does not prove Python ADC is configured.

One JSON API list request used the statistics prefix, root-metadata matchGlob,
maxResults=3 and selected response fields, capped at 64 KiB. HTTP 200 returned
3 bytes (`{}`), confirming list access but no matching identity. The known root
from the retained September 5 evidence exceeded the initial 128 KiB limit; no GET
was attempted until the owner expanded metadata permission to 256 KiB.

One generation-pinned root metadata GET then returned HTTP 200, 182,540 bytes:

- Bucket: `weathernext3_statistics_spatial`
- Object: `weathernext_3_0_0_statistics/zarr/2026_to_present/20260801_00hr_01_preds/predictions.zarr/zarr.json`
- Requested and response generation: `1787792319369404`
- Response ETag: `CLyhg7HNv5YDEAE=`
- SHA-256: `a1e1a47514c681be825ca5a5cfac7d0375e6b7d24b3dae201b64989e86724549`
- Zarr format 3, group, 133 consolidated nodes.

Exact-object read access is established for that historical generation. There is
no current science-payload, current run, all-field, serving-permission or raw-member
proof. Requester project headers were absent. Statistics Requester Pays OFF is
from the [official WeatherNext guide](https://developers.google.com/weathernext/guides/gcs),
not a bucket-configuration GET. Root/list receipts and raw metadata remain outside
Git in `/private/tmp/astraeus-weathernext-access-proof/`.

The [official objects.list](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/list)
and [objects.get](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/get)
references were checked September 7 for JSON API endpoint and generation syntax.

## Transport implementation

`api/weather_api/weathernext_gcs.py` implements the existing native reader's
injected describe/read protocol using the official JSON API. Explicit construction
with `GcloudProfileToken("astraeus")` selects existing runtime gcloud auth. There
is no default ADC lookup, login, SDK install, registration, retry, redirect or
requester billing. Only exact statistics per-run root/chunk paths are accepted;
raw-member bucket and foreign URL/path inputs are refused before authentication.
Describe responses are capped at 64 KiB and select only identity fields. Reads
pin the described generation and verify response generation, ETag and byte count.
The transport honors the native reader's per-object byte limit with a fixed
512 MiB outer ceiling; compressed content encoding is refused. Each request has
a caller deadline and bounded socket timeout; a bounded parent process remains
required for hard wall-clock and decoding memory enforcement. Token output is
captured in subprocess memory, validated to at most 16 KiB, never cached/logged.
No exception text, HTTP error body or token is included in public error messages.
401, 403, 404, 412 and 429 remain distinguishable safe categories.

The authenticated probe was an independent bounded script. The production-shaped
transport is tested offline with injected runtime token and HTTP responses; it
has not made live requests. Connecting it to the native reader requires root's
explicit composition. No native/query/shared route files changed in this slice.

## Native metadata finding for integration

The real metadata labels longitude as `units: degrees` with
`standard_name: longitude`, while latitude is `degrees_north`. The strict native
reader introduced earlier accepts longitude only as `degrees_east`, so it will
currently refuse this real root before science chunks. Root was notified to
review a narrow metadata-backed alias (degrees plus standard_name longitude).
This transport does not silently convert or bypass that check. Observed codecs
are bytes plus zstd; the cloud chunk shape is [1,1801,3600]. No science chunk was
fetched to validate actual coordinate values or field decoding.

Verification: 27 offline transport tests exercise generation pinning, partial
metadata fields, absent billing, safe HTTP statuses, redirect refusal, deadline,
byte/header bounds, truncation, wrong identity, raw-path refusal and runtime auth
success/failure. Existing native/query/adapter suites run alongside them; specctl
validation is required at handoff.
