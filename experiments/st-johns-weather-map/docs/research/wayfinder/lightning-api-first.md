# Lightning exact-frame source seam

Classification: isolated experiment under GOV-SPEC-001/004/005/006. No route,
source activation, sampling-contract acceptance, registry or client change.
The proposed WMS sampling vocabulary in commit `71ede9a` remains a separate
owner decision; this slice does not expose `point_fields`.

## Reuse and API handoff

Repairs the unmerged `1ad1056` query/worker using `GeoMetClient.url`, the existing
bounded child launcher, GeoMet process/request budgets and host pacing.
`lightning_query_service().entry_for(latitude, longitude, aware_selected_time,
refresh=False)` returns `LightningCacheEntry(sample, acquisition,
expires_at_monotonic)`. `cached_entries()` is read-only and never acquires data.
An explicit refresh replaces the selected key. Identical concurrent misses
coalesce; at most four distinct misses run concurrently. Residency is bounded
by 32 entries and 256 KiB including expired metadata. Capabilities and sample
bodies are bounded by 256 KiB and 64 KiB; worker limits are 96 MiB and one CPU
second. Each cold query costs at most two upstream calls, charged to GeoMet's
existing process budget. Failures carry `LightningDemandUnavailable`; expired
values are withheld and bounded prior acquisition metadata is retained.

Private `lightning_models.py` contains the exact typed receipt models for root's
central integration: selected source/product/coordinate/time and both canonical
URLs; two typed receipts with safe effective headers, final-byte completion,
received bytes and SHA-256; native valid time, cached_at and fixed expires_at.
No default response field or closed public model was modified. These private
models should be centrally mapped or moved when root freezes its interface.

Bare `{}` means the accepted no-density response and returns null quantity and
null coordinates. Numeric zero is a real numeric density. An empty features
list, malformed numeric value, boolean, negative/NaN/infinite density, wrong
layer, invalid geometry or mismatched native time fails; none becomes a zero
observed flag. No request coordinate is represented as a sampled coordinate.
No interpolated/nearest-hour frames are constructed. The odd 21 by 21 WMS
image places I=J=10 on the request-centred pixel; the 0.2-degree latitude-first
box and WMS pixel are request geometry, not a claim of native grid precision.

## Official source check (2026-09-07)

[ECCC lightning documentation](https://eccc-msc.github.io/open-data/msc-data/lightning/readme_lightning_en/)
describes a ten-minute aggregation of cloud-to-ground and intra-cloud flashes,
normalized by grid area and ten minutes to flash km-2 min-1 on approximately
2.5 km cells. A mask excludes locations more than 250 km from Canadian borders.
[GeoMet WMS documentation](https://eccc-msc.github.io/open-data/msc-geomet/wms_en/)
describes GetFeatureInfo as querying an image pixel with I/J, dimensions and
BBOX. TIME is pinned to the advertised capabilities dimension; default time
selection is unsuitable for an exact native-frame query. It does not establish
that the returned WMS geometry is a native cell centre. That scientific
precision limitation remains explicit for public provenance approval.

## Verification receipt

- macOS: `uv run --project api pytest -q api/tests/test_lightning_query.py`:
  14 passed, one real-child test skipped because macOS rejects locked RLIMIT_AS.
- Linux: command below: 15 passed, including the actual production `_decode`
  child and cache hit, using exact checkout files mounted read-only. Its fixed
  MockTransport counted two fixture requests and no provider-network requests.
- `uv run --project tools/specs python tools/specs/specctl.py validate`:
  zero errors and warnings.

Prepared image `astraeus-lightning-proof:c88ff83` uses the repository's locked
API dependencies via `uv sync --locked --extra grib`; image digest
`sha256:afbed8d5524a1c28a0bce3874118b6ab7d5e3f9d3ae9a54a8860494da55db3f6`.
Preparation downloads dependencies before the network-disabled proof:

```sh
docker run --rm --network none --memory 512m \
  -v /private/tmp/astraeus-api-first-lightning/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work astraeus-lightning-proof:c88ff83 \
  python -m pytest -q -p no:cacheprovider api/tests/test_lightning_query.py
```

Separate live proof made exactly two anonymous ECCC requests at
2026-09-07T21:09:16Z: 13,096-byte capabilities advertised 19 native frames from
17:50Z through 20:50Z; the exact 20:50Z sample at 47.56,-52.72 returned a
5-byte whitespace-wrapped bare object. Capabilities SHA-256:
`4573a9406f23b6038481ffce1ca454389e46f20c358303ec2a9ea8e5246682d0`;
sample SHA-256:
`8e1d794b49e35ea828279c6a8c95282bbb9a0787cf5c9385256c2cc9d17baeb7`.
Temporary captured bodies and complete receipt are in
`/private/tmp/astraeus-lightning-api-first-proof/`. They are replay evidence,
not committed provider data or a current availability assertion. Live numeric
detection was not encountered; numeric parsing is established by fixed data.

Remaining integration gates: owner WMS sampling decision, public typed point
mapping, source descriptor/optional Series semantics and root-owned API/client
verification. No live-source promotion or native cell-centre claim is authorized
by this receipt.

## Root review correction

The subsequent bounded review correction keeps a still-valid entry resident
while an explicit refresh runs; ordinary reads use that entry until its real
monotonic deadline. A failed refresh caller receives failure without attaching
`expired_acquisition` before expiry. If the deadline passes while refreshing,
the old values are withheld and only then may expired metadata be attached.
Both final-byte monotonic instants are captured by `_get`; the cache deadline
is the minimum of their independent receipt TTL deadlines. Wall-clock rollback
during decoding cannot extend that monotonic deadline. Public UTC expiry
remains the minimum UTC receipt deadline. Decoder failures disclose only their
exception class, not arbitrary provider or child-process error text.

The same network-disabled Linux focused command now passes **20 tests**, adding
fixed-clock rollback, concurrent refresh failure on either side of expiry, and
safe error disclosure cases. The decoder implementation and live captured
bodies are unchanged; no additional provider requests were made.
