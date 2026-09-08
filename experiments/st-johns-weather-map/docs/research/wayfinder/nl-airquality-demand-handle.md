# NL provincial air-quality experimental acquisition handle

This is non-normative implementation evidence for issue #118. It does not
accept or promote a production contract.

## Scope and authority

The owning experiment is
`openspec/changes/experimental-nl-air-quality/specs/nl-air-quality-observations/spec.md`.
Its proposal explicitly says the exact source contract is not accepted.
The source-local handle therefore remains an isolated acquisition prerequisite;
it is not registered, routed, scheduled or promoted into point delivery.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Classification: experiment only.

Missing owner contract: accepted production station/time applicability,
native-field delivery schema, QC eligibility and restricted-rights rules.
No nearest-station mapping, concentration aggregation or AQHI derivation is
implemented. `operational: false` and no redistribution remain attached to
native observations. Successful fixture acquisition cannot resolve this gap.

## Reused implementation

`weather_api/nl_airquality_query.py` acquires only the canonical anonymous
`https://www.mae.gov.nl.ca/wrmd/pp_adrs/Data/StJohns_Line.csv` request, without
redirects, under the existing 1 MiB ceiling. Requests bind exact NAPS station
010102 and offset-aware inclusive windows no longer than the rolling 35-day
file. An instant is expressed by equal start and end times. Empty windows fail
closed; there is no nearest-time or latest fallback.

`weather_api/nl_airquality_worker.py` invokes the existing experimental
`ingest.experimental.nl_air_quality._parse` function. It preserves the existing
warning/schema/station validation, DST ambiguity rejection, local and UTC
identity, missing selected cells and rejected malformed values. PM2.5 remains
its native 24-hour running mean in µg/m³; ozone remains ppb. The handle does not
perform another scientific normalization or redefine the adapter's Zarr units.
The six deferred pollutants retain their existing experimental disposition.

One child has 2 GiB address-space, 1 MiB input/output-channel and 64 KiB stderr
ceilings. The higher address-space allowance accommodates the existing
numpy/xarray adapter imports; native thread counts are constrained before
import. The request cache has four exact-window entries and a 2 MiB serialized
backing ceiling. At most four distinct requests may be pending and acquisition
is serialized; matching requests share one future.

Each entry carries canonical/effective URL, SHA-256, received byte count,
final-byte UTC receipt time, selected window and a fixed 60-second local
experiment cache deadline. Expiry removes values. Explicit refresh success
replaces the entry; failure does not extend its prior deadline. These local
acquisition limits do not claim provider freshness or a production SLA.

## Verification

On 2026-09-08 UTC, the exact working-tree source was mounted read-only into the
prepared Linux dependency image `astraeus-lightning-proof:c88ff83`, image ID
`sha256:afbed8d5524a1c28a0bce3874118b6ab7d5e3f9d3ae9a54a8860494da55db3f6`.
The container had networking disabled. Command, from the repository root:

```sh
docker run --rm --network none --memory 4g \
  -v /private/tmp/astraeus-api-first-nl-airquality/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_nl_airquality_query.py \
  api/tests/test_adapter_nl_air_quality.py -o addopts= -q --tb=short -p no:cacheprovider
```

Result: **26 passed**. The default-worker test uses the actual bounded child and
existing trimmed fixture, calls the same query twice, observes one exact-URL
MockTransport request and zero provider-network requests. Other cases cover
native units, provisional/unknown QC, missingness, station/time rejection,
redirect/body/schema failure, fixed expiry, refresh, coalescing and finite cache
retention. The existing adapter suite checks its artifact/API semantics.

`uv run --project tools/specs python tools/specs/specctl.py validate`:
**0 errors, 0 warnings**. No current provider request or browser proof was made.
