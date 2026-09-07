# Isolated CAMS AOD finite delivery, 2026-09-07

Classification: experiment. This extends the existing
`experimental-openmeteo-composition` experiment under the owner's API-first
execution plan. It does not accept source contracts, register routes, schedule
retrieval, activate the source, or assert V1 conformance.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

The selected gap was `openmeteo-cams-aod`: the named `cams_global` adapter
already acquired and validated composition artifacts, but lacked a source-local
finite query/cache seam. The query now reuses that adapter's discovery,
normalization, zipped-Zarr writer and completeness/QC gate. Configurable adapter
coordinates preserve the previous St John's defaults. No alternative model,
particulate/AQHI substitution, or pressure-profile assumption was added.

`OpenMeteoCamsAodQueryService.query(latitude, longitude, start, end=None,
refresh=False)` returns an immutable tuple of actual intermediary timestamps
and dimensionless total AOD at 550 nm. It accepts 1–24 exact hourly selections,
retains absent hours and returned nulls, and adds no interpolation. The
Open-Meteo hourly product itself is reprocessed from CAMS; neither its cadence
nor its returned 0.1-degree cells are represented as the producer's native
three-hour / 0.4-degree grid. The latest metadata initialization remains context;
per-value run identity stays unknown.

`point_fields(latitude, longitude, selected, refresh=False)` is the proposed
root-owned delivery hook. Both field and key are
`aerosol_optical_depth_550nm`, matching existing immutable-artifact readback.
It retains producer, intermediary, sampled coordinates, units, transformations,
response digest and unknown run identity. The finite entry provides Series
input; public contract identity and integration remain root-owned.

Acquisition permits two concurrent distinct selections, coalesces identical
misses, makes two anonymous requests with one attempt each through `PoliteClient`,
and caps each JSON response at 16 KiB with 1 KiB transport chunks. Default acquisition runs both requests and artifact
validation in the existing cancellable Linux isolation process with a 60-second
total wall-clock budget, 2 GiB address-space ceiling, 1 MiB per-file ceiling and
32 KiB stdout/stderr ceilings. Coalesced callers wait at most 65 seconds. The
injected-client fixture seam additionally checks the total budget before and
after downloads and validation; it is not the default transport path. Canonical
shape admits at most 24 values before artifact creation. Temporary response and
artifact files are removed after validation. Cache retention is capped at 32
entries and 256 KiB of conservatively accounted normalized data. Five-minute
expiry is fixed when acquisition completes; reads never extend it. Explicit
refresh replaces only after success. Failure preserves any old entry only until
its original deadline; expiration during validation refuses admission.

Official documentation checked on 2026-09-07:
[Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api)
documents anonymous latitude/longitude requests, the explicit `cams_global`
domain, AOD and hourly selection. Upstream CAMS's three-hour cadence is distinct
from intermediary hourly delivery. This inspection did not capture a live
provider response or establish current source coverage, commercial eligibility,
production admission, or a new science contract.

Verification maps GOV-SPEC-004/006 to
`api/tests/test_openmeteo_cams_aod_query.py`: exact named transport, real
`PoliteClient` with mock HTTP, adapter/Zarr readback, identity/units, native
gaps/nulls, invalid coordinates/times, field inventory and QC refusal, HTTP
429/503 failure, bounded acquisition, concurrent coalescing, successful/failed
refresh, fixed expiry, eviction, and expiry during validation. Existing
`test_adapter_openmeteo.py` verifies regression of the reused source adapter.

Executed offline Linux proof (actual image, no provider network):

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-openmeteo/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_openmeteo_cams_aod_query.py \
  api/tests/test_adapter_openmeteo.py -q -p no:cacheprovider
```

Result: 66 tests passed. Source-specific tests number 32; existing adapter tests
number 34. This is fixture-backed software evidence, with zero provider calls.
`uv run --project tools/specs python tools/specs/specctl.py validate` passed with
0 errors / 0 warnings; `git diff --check` passed.

## Root review corrections

Root review reproduced two P2 defects in the first implementation: acquisition
could take arbitrarily long before its freshness clock started, and longitude
differences across the antimeridian produced a nearly global sample distance.
The follow-up adds the full-operation cancellable child above, preserves a
separate fixed cache deadline after bounded transport completion, and uses
wrapped-longitude haversine distance. The 179.99 to -179.95 degree equatorial
regression measures approximately 6.672 km while retaining literal sampled
coordinates.

New verification exercises a fake 600-second first download (refused before
request two), bounded coalesced waits, actual offline child adapter/Zarr
readback, and actual child timeout/cancellation with no cache or inflight
residue. These fixtures make zero external provider reads. Default process
execution depends on the existing Linux isolation capability; unsupported
platforms fail closed.

## One current-hour live proof

On 2026-09-07 at 22:23:44Z, one default Linux acquisition selected St John's
22:00Z. It completed in **1.820 seconds**, under the 60-second total budget.
The existing default child and `PoliteClient` made exactly two anonymous
requests with no retries: 302 bytes for the point response and 594 bytes for
CAMS metadata, 896 bytes total. A proof-only `sitecustomize` observer copied
the original download receipt and already-received body; it did not replace
transport, request another payload, or change adapter validation.

The point response returned literal hour label `2026-09-07T22:00`, AOD **0.07**,
original unit `""` normalized to dimensionless `1`, and cell
**47.600006, -52.699997** (4.385 km from the request). There were **zero nulls**
in this one-value live response; null/gap behavior remains fixture evidence.
22:00Z is an exact intermediary hourly label, not a claim of a native CAMS
three-hour producer sample. Evidence stayed `reprocessed`, non-primary and
`operational: false`. Producer run time remained null; metadata's 12:00Z
initialization was retained only as context.

Acquisition retrieval time was 22:23:46.262173Z and fixed expiry
22:28:46.262173Z. A point read and repeat query on the same service returned the
same cache entry and unchanged expiry with **zero additional provider
requests/payloads**. Expiry passage, failure and refresh remain the separately
recorded offline fixture proofs.

Outside-Git bundle: `/private/tmp/astraeus-api-first-cams-aod-live-proof/` contains
`proof.json`, both raw JSON bodies and original transport receipts, the download
log, and the observer/proof scripts. Retained body SHA-256 values:

- Point: `824d806aa024b231ca858230d8f3342c571146a13b35b5b5fc74f4422d13061f`.
- Metadata: `6d7a769b98853e4f11fa6d6c3a94ee33444102acb26039fc80aa366e584448db`.

Command used for the single live attempt:

```sh
docker run --rm --memory 1g \
  -v /private/tmp/astraeus-api-first-openmeteo/experiments/st-johns-weather-map:/work:ro \
  -v /private/tmp/astraeus-api-first-cams-aod-live-proof:/proof \
  -e PYTHONPATH=/proof:/work/api:/work -w /work \
  astraeus-lightning-proof:c88ff83 python /proof/proof.py
```

All acquisition and comparison assertions passed and persisted before the final
console summary failed to serialize a datetime. A local read-only verifier then
confirmed the saved successful receipt, download counts, body sizes and hashes;
the live command was not rerun. The proof script's summary formatting was fixed
outside Git.

The live field exposed a separate truthful-storage defect: the generic evidence
model default labeled this memory-cached reading `stored`. The source now sets
`available-not-stored` explicitly, verified by the existing point test and the
66-test offline Linux suite. The retained live field faithfully preserves its
original pre-correction label; no corrected live output is claimed. Shared
routing and public API delivery remain separate root integration work.
