# ECMWF deterministic demand candidate, September 7, 2026

This is callable, unregistered experiment software for #270, not source
admission. The accepted legacy scheduled IFS refusal remains untouched.
[Draft #275](https://github.com/TusharSariya/Astraeus/pull/275) still needs the
verified-demand serving exception; its ensemble control/member extension is
outside this slice. Governance references: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-005 and GOV-SPEC-006.

## Native scope and primary-source verification

The constructor accepts only `ecmwf-ifs` and `ecmwf-aifs-single`. Each query
selects native `2t`, `2d`, `msl`, and instantaneous `tcc`, with original record
identity and units preserved. ENS, precipitation, wind, cloud strata and
profiles are not implemented by this candidate.

ECMWF's [Open Data description](https://www.ecmwf.int/en/forecasts/datasets/open-data)
identifies the free public subset, CC BY 4.0 attribution, distributed 0.25-degree
GRIB2 products, and IFS Cycle 50r1 `oper:fc` cycles. The 00/12 cycles offer
three-hour steps through 144 and six-hour steps through 360; 06/18 stop at 144.
The [AIFS description](https://www.ecmwf.int/en/forecasts/datasets/aifs-machine-learning-data)
independently dates AIFS Single v2 to May 12, 2026, and describes six-hour output
through 15 days on four daily cycles. Version labels retain these dated official
bases and are not inferred from hostname or internal model resolution. Runs
before the respective verified upgrade dates are refused.

The retained September 5 native bytes reveal an exact draft-contract correction:
IFS `tcc` is `(0 - 1)` while AIFS Single `tcc` is `%`. Both are instantaneous
entire-atmosphere fields. The candidate validates those distinct native units
and uses existing normalization; the serving contract must not label AIFS
percent as fraction. Both products' 2-m temperature/dewpoint are K and MSL is
Pa. An IFS lead-zero index also advertises unrelated step-three products; these
are not selected or allowed to change the four instantaneous record identities.

## Existing seams and limits

`ECMWFQueryCoordinator(source_id, ...)` in `api/weather_api/ecmwf_query.py`
provides `query(selected_time, run_id=None, refresh=False)` and
`point_fields(latitude, longitude, selected_time, run_id=None, refresh=False)`.
No singleton, public route, registry row or scheduler is changed. The point
sampler also preserves its existing, explicitly derived temperature/dewpoint
relative-humidity result; no new scientific formula is added.

The candidate reuses the Open Data bounded metadata/range helpers, native
`_refusing_reader`, unit normalization, exact-grid check, manifest validation,
process isolation and existing point-evidence sampler. It does not add the SDK
or another dependency, bulk ingestion or retained ArtifactStore delivery.

- At most seven source directory attempts establish up to two actual runs.
- Only exact listed selected steps are read; no nearest-step or run substitution.
- Metadata: 2 MiB/document and 10,000 index records.
- Payload: exactly four selected messages, each at most 8 MiB; exact 206 and
  Content-Range/length checks, no redirect or content-encoding substitution.
- Acquisition deadline: 120 seconds checked before requests and during receives,
  with at most the active 30-second transport timeout beyond that check.
- Decoder: 1 GiB address space, 120 seconds, 128 KiB stdin, 16 MiB output,
  64 MiB workspace allowance, bounded stdout/stderr.
- Cache: four entries, 64 MiB aggregate, four in-flight selections, fixed 600-second
  expiry. Decode elapsed time counts toward advertised expiry. Refresh is a
  distinct operation and identical callers coalesce; expired values are withheld.
- Receipts retain exact requests/ranges, safe headers, digests and final-byte
  completion separately from native run/valid times and fixed expiry.

## Verification

From the experiment root:

```sh
uv run --project api pytest -q api/tests/test_ecmwf_query.py
```

32 fixed tests pass, including product/run/step/class/member/index bounds,
source-specific refusal, malformed range responses, redirects, cache hit,
refresh, expiry, concurrent success/failure, saturation, decoder identity/output
bounds, acquisition deadline and nonrenewing expiry across decode time.

The actual default Linux child and point sampler were also exercised with
retained real IFS/AIFS Single September 5 06Z/f000 index and GRIB bytes. Discovery
HTML is synthetic, HTTP uses an exact fixed `MockTransport`, clocks are fixed,
and Docker uses `--network none --memory 2g`. This is offline replay, not a
new live/provider-availability claim. Each source makes 12 fixture transport
requests (seven discovery attempts, index, four ranges), zero provider-network
requests, and zero additional requests for repeated query plus point sampling.
IFS/AIFS normalized payloads are 19,474/20,747 bytes.

Temporary evidence: `/private/tmp/astraeus-api-first-ecmwf-proof/proof.json`,
SHA-256 `7c3698585a4abed81490ac8cba5b0bf58e9ea45b6bf3801d6ce4eee11ea71b73`.
It contains original input hashes, mounted source hashes, native metadata and
point readback. Image:
`sha256:aacbd8b2f012e571c45c5a3b88d9935aaa72e6506bbad14bcd970766cb7697ff`.
The later source-only typed-error wrapper leaves the decoder and successful
replay path unchanged. No proof process remains running.

`uv run --project tools/specs python tools/specs/specctl.py validate` from the
repository root passes with zero errors and warnings. Public API wiring and
resolution of the serving exception/AIFS native-cloud wording remain root-owned.

### Native unit provenance correction (2026-09-07)

The point sampler now copies each decoded variable's `original_units` into the
artifact provenance consumed by `live_point_fields`, without mutating the cached
entry. Previously the response fell back to normalized units. This changes
metadata only: native temperature/dew point remain `K` with output `degC`,
pressure remains `Pa` with output `hPa`, and IFS cloud `(0 - 1)` remains distinct
from AIFS cloud `%`, both with output `percent`.

The focused regression uses synthetic values and a one-cell Zarr payload with
unit tokens verified by the retained native receipts above. Both product cases
failed before the correction and pass afterward:
`uv run --project experiments/st-johns-weather-map/api pytest -q experiments/st-johns-weather-map/api/tests/test_ecmwf_query.py -k point_sampler_preserves_verified_native_units`
(2 passed). No new provider requests or decoder replay were performed for this
metadata correction. The pending serving exception is unchanged.
