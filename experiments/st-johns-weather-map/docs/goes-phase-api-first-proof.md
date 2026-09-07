# GOES-19 ACTPF source-local delivery proof

This is isolated experiment implementation under GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-005 and GOV-SPEC-006, using the existing
`experimental-goes-abi-glm/design.md` scientific mapping and the shared source
integration evidence gate. Those experiment documents do not authorize V1
promotion. The accepted V1 corpus supplies governance only. No production
source contract, scheduler registration, route or source activation changes.

The prior `GOESABIL2Adapter` could acquire and crop ACTPF, but had no finite
source-local demand coordinator. `GOESPhaseQueryService.read_native()` now
returns one native cropped NetCDF revision with provenance. It reuses
`PRODUCTS['ABI-L2-ACTPF']` and `crop_product`: native Phase codes exactly {0, 1, 2, 3, 4, 5}, unchanged
code units, producer-readable DQF zero, preserved quality flags and meanings,
file-derived curvilinear latitude/longitude and exact observed scan start.
Source scan end and creation time remain in the receipt metadata. It makes no
fog classification, cloud-percentage conversion, interpolation, parallax
correction, or local uncertainty estimate. A scan with no readable phase cell
fails acquisition and cannot replace the prior revision. Readable finite
fractional phase values are refused before publication; a numeric range check
alone cannot establish categorical validity.

The anonymous transport permits exactly six hourly listings (512 KiB each,
max-keys=1000) and at most one 64 MiB ACTPF granule. No pagination, redirect,
compressed transport, retry or alternate product is used. Streaming checks a
60-second monotonic deadline with a 20-second network-operation timeout. Strict product/key
and object identity checks reject substitution. One inflight request coalesces
concurrent misses. The decoder runs with a 768 MiB address-space limit, 64 MiB
per-file ceiling, 64 MiB stdin, 16 KiB stdout/stderr and a 60-second timeout.
Its temporary native input is removed before the sole output is promoted.
The retained crop is capped at 16 MiB. There is one retained cache entry;
refresh can temporarily coexist with that prior entry until atomic replacement.

Retention expires 300 seconds after acquisition begins, checked against both
UTC and monotonic clocks. Reads never renew it and cache hits issue zero
provider requests. Explicit refresh acquires a new complete revision. Failed
refresh callers receive unavailable; ordinary reads can still use a prior
unexpired revision. Expired evidence is discarded. Retention says nothing
about observation freshness: the actual scan time remains explicit, including
when the six-hour discovery window yields older evidence.

## Evidence and limits

On September 7 at 21:56 UTC, a separate bounded anonymous capture made two
NOAA requests: a 2,172-byte hourly listing and a 3,796,986-byte ACTPF object.
The object scan began at 21:40:20.9Z and ended at 21:49:51.7Z. Receipts and
payloads remain outside Git in `/private/tmp/astraeus-goes-phase-proof/`:
`capture.py`, `capture.json`, `listing.xml`, `native.nc`, `prove.py`,
`proof.json`, and `crop.nc`.

Offline Linux replay passed the actual bounded decoder and source-local
service using those retained bytes. It produced a 186×465 native crop with
44,600 readable cells; native Phase codes 0–4 appeared in readable cells.
Producer DQF codes 0, 5, 9 and 13 were preserved, and nonzero quality cells
remained unreadable. The crop was 1,400,989 bytes. Seven fixture transport
requests and zero provider requests exercised discovery and decode; the repeat
cache read issued zero additional requests. `proof.json` records exact digests,
native metadata, expiry and observations. The live capture and offline replay
are separate evidence classes, not a claim that a public API read occurred.

Verification:

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-satellite/experiments/st-johns-weather-map:/work:ro \
  -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_goes_phase_query.py api/tests/test_adapter_goes_abi_l2.py -q -p no:cacheprovider
uv run --project tools/specs python tools/specs/specctl.py validate
git diff --check
```

Result: 38 tests passed (80 upstream NumPy/netCDF deprecation warnings),
`specctl` reported 0 errors and 0 warnings, and whitespace verification passed.
The actual bounded leaf regressions refuse fractional codes 0.5, 2.5 and 4.999,
and confirm that every native integer category 0 through 5 survives unchanged.
The categorical correction used no provider requests.

Remaining: shared delivery descriptor/point mapping, public API readback,
immutable publication integration and owner acceptance. The new local return
format is NetCDF; existing published ABI adapters continue producing Zarr.
This candidate is not a completed public API integration.

## Native point continuation, September 7

The source-local service now offers `read_point_native(latitude, longitude,
selected_time, refresh=False)` and the cache-only
`native_point_from_entry(entry, latitude, longitude, selected_time)` helper.
These return `NativePhasePoint`, not a shared `EvidenceField`. The existing
point-evidence-sampling contract supplies the one-cell curvilinear metric,
0.75-degree corrected-distance ceiling and one-hour temporal tolerance. The
existing sampler's coordinate and time-selection utilities are reused. The
requested identity and actual cell identity remain separate. A distant cell
returns null phase with its measured distance; unreadable DQF or masked phase
also yields null without searching for a different good cell. Native DQF stays
visible; local scientific QC is unknown and operational remains false.

The bounded ACTPF decoder now retains the exact file geostationary projection
attributes and scan end in the crop, alongside the existing scan start. Old
crops without these attributes cannot satisfy this native point interface and
are refused. Every readable Phase code 0 through 5 remains an integer. Phase
is not interpolated, translated to a cloud percentage, or used as a fog/score
inference. Native flag meanings remain available in the NetCDF artifact.

Mapped experiment verification: the native point category regression covers
one-cell/unmodified values, exact sampled coordinates, missing-value
provenance, temporal/distance refusal, producer DQF readability, unknown QC and
native scan/projection retention. Invalid location/time identity is refused
before acquisition. The retained capture was replayed through the actual Linux
leaf and native point helper with zero provider requests; receipt is
`/private/tmp/astraeus-goes-phase-proof/native-point-proof.json`. It reads
Phase 1 / DQF 0 at 50.487552642822266,-57.983253479003906, distance 0 km,
scan 2026-09-07T21:40:20.9Z through 21:49:51.7Z. This is offline replay evidence,
not a current live point request or public API proof.

Shared wiring is deliberately still outstanding. The shared sampler currently
converts flag-coded categories to meaning strings, and its public evidence
provenance does not carry this complete native point context. A proposed
source descriptor is source `noaa-goes-east`, native product `ABI-L2-ACTPF`,
field `cloud_top_phase`, native observation (no forecast run or Series), wired
to `read_point_native`. The integration owner must preserve `phase_code`,
`dqf_code`, exact scan interval, projection and actual cell context when
representing this in the shared schema. Do not register this as implemented
shared point delivery until that consumer path is present and verified.

Continuation validation: 48 offline Linux tests passed across
`test_goes_phase_query.py` and `test_adapter_goes_abi_l2.py` (104 upstream
NumPy/netCDF deprecation warnings); `specctl validate` reported 0 errors and
0 warnings; `git diff --check` passed. No credentials, new live acquisition,
remote writes or source admission changes were made.
