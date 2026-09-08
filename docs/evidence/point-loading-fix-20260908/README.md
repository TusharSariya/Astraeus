# Point loading failure repair

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006

Conforming repair within the isolated experiment. Owner requested the loading
fix on 2026-09-08. Owning executable requirements:

- [Exact-request point results and independent failures](../../../experiments/st-johns-weather-map/openspec/changes/selected-layer-point-data/specs/selected-layer-point-data/spec.md#requirement-every-active-point-selection-owns-exact-request-results)
- [Finite decode resources and wall time](../../../experiments/st-johns-weather-map/openspec/changes/free-source-capacity-budgets/specs/capacity-admission/spec.md#requirement-source-budgets-preserve-complete-admitted-products)
- [Kernel-enforced TAF child bound](../../../experiments/st-johns-weather-map/openspec/changes/awc-taf-app-vertical/specs/capacity-admission/spec.md#requirement-cyyt-taf-is-admitted-before-its-payload-bearing-discovery)

## Observed failure

The local API failed health checks and direct health/catalog requests timed out.
The captured native stack shows a SWPC decoder launch blocked in
`blas_thread_shutdown_ -> fork -> subprocess.Popen`, concurrently with astronomy
blocked in NumPy `cblas_matrixproduct`. `preexec_fn` forced the unsafe fork path;
the stall happened before Popen returned, outside the existing exchange deadline.
Python documents that [preexec_fn is unsafe in threaded applications](https://docs.python.org/3/library/subprocess.html#subprocess.Popen).

## Repair

The existing isolation module now also serves as a fresh stdlib-only launcher.
It installs the same locked RLIMIT_AS and RLIMIT_FSIZE before exec of the decoder,
without reading payload input. The parent no longer supplies preexec_fn. Existing
pipe bounds, deadline, process-group cleanup and atomic promotion remain intact.
Unsupported limits still fail closed. No acquisition schedule or scientific
calculation changed.

Point fetches now abort after 30 seconds, including stalled response bodies,
and return explicit unavailable evidence. Caller cancellation stays distinct and
timers/listeners are cleaned up. A timeout does not imply cancellation of work
already running on the server or synthesize a source value.

## Verification

- Linux rebuilt API image: `tests/test_bounded_process.py`: 19 passed, 1 Darwin-only skip.
  The new concurrent-launch regression verifies that parent atfork callbacks do
  not run and the actual decoder inherits both locked hard limits. Existing
  real memory/file/pipe/deadline/cancellation tests pass.
- Frontend focused tests (`pointTimeout`, `pointRequests`, `api`): 110 passed.
  Includes a hung fetch, hung body, caller cancellation and immediate failure.
- Production frontend build passed (existing bundle-size warning).
- `specctl validate`: zero errors and warnings.
- Rebuilt and replaced only the local Compose API service, preserving data volumes
  and the existing WeatherNext override. Health recovered to HTTP 200 in 0.006s.
- Live browser at `http://127.0.0.1:5301`: selected HRDPS cloud row displayed
  `100 percent`, native time `2026-09-08T19:00:00Z`; imagery rendered and the
  API remained healthy while astronomy and decoder work ran concurrently.
- A repeated exact HRDPS point query returned HTTP 200 in 2.985 seconds through
  the Vite proxy; catalog returned HTTP 200 in 0.037 seconds.
- Limitation: the legacy combined-source point route still exceeded 35 seconds
  during a cold live query. It sequentially requests station observations and
  consensus contributors. The browser reports its 30-second timeout while the
  independent selected HRDPS reading remains available. This repair removes
  the deadlock and indefinite spinner; it does not claim every upstream query
  completes within 30 seconds.
- Additional Linux AWC METAR bounds, SWPC Kp and astronomy tests: 26 passed,
  6 environment-dependent skips. Local focused API tests also passed.

## Merge verification

Re-ran the mounted source and bounded-process tests in a fresh Linux container
with provider networking disabled on 2026-09-08: **19 passed, 1 skipped**.
The verification image extends the existing API image with pytest only; running
application containers were unchanged.

```sh
docker run --rm --network none --memory 2g \
  -v "$PWD/experiments/st-johns-weather-map:/work:ro" \
  -w /work -e PYTHONPATH=/work/api:/work \
  --entrypoint /app/api/.venv/bin/python astraeus-point-merge-check \
  -m pytest -o addopts='' -q -p no:cacheprovider api/tests/test_bounded_process.py
```

Verification image manifest digest:
`sha256:a8f0787cc15fb21d21695f47e17aaf2e64ab2f46c172ba13e681899716034e38`.
