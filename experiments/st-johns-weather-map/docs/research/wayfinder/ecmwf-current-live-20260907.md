# ECMWF deterministic current live receipt, September 7

Non-normative experiment evidence. No API route, source admission, ensemble
mapping or normative status changed. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002,
GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

One anonymous acquisition per deterministic product ran at 22:43 UTC against
the existing public Open Data coordinator. Both discovered the September 7
12Z run and selected exactly September 8 00Z, native lead 12 hours. Each made
eight requests: one unavailable 18Z directory (404), two successful directory
listings, one index and four verified HTTP 206 GRIB message ranges. No full
model file, ensemble, credential, alternate endpoint or retry was used.

| Product | Received body bytes | Normalized bytes | Final-byte completion UTC |
|---|---:|---:|---|
| IFS | 3,039,613 | 19,809 | 2026-09-07T22:43:47.038715Z |
| AIFS Single | 3,568,762 | 21,499 | 2026-09-07T22:43:53.574632Z |

Body counts cover streamed successful responses; the rejected 404 bodies were
not consumed. Request counts include those 404s. The default production Linux
child validated the exact native `2t`, `2d`, `msl` and instantaneous `tcc`
messages, grid, source/run/lead/class identity and manifest. Both manifests
reported computed quality passed, no flags, complete coverage and fraction 1.
Temperature/dewpoint native K became degC, pressure Pa became hPa. IFS cloud
native `(0 - 1)` and AIFS Single cloud native `%` both became percent, preserving
the distinct native tokens in point provenance.

The production point sampler queried 47.5615,-52.7126 and returned the actual
47.5,-52.75 cell, rectilinear selection and 7.392 km distance for both products.
Each returned four native fields and the existing explicitly derived liquid
relative humidity. `operational` stayed false and member identity stayed null.
Repeating the query and then reading the point added zero provider requests
and retained the identical cache entry and fixed deadline.

An explicitly synthetic expiry check advanced the injected monotonic clock
beyond the fixed deadline and disabled network transport. Both products refused
expired evidence with ECMWFQueryUnavailable; this added zero provider requests
and did not extend the old deadline. This is an injected failure check, not a
live provider outage or a ten-minute wall-clock waiting claim.

The source-local point sampler currently inherits `storage: stored`, null
`demand_acquisition` and catalogue display-primary flags. Public integration
must attach the demand receipt and represent actual non-stored delivery without
treating this successful acquisition as source admission. This receipt proves
the coordinator and sampler, not assembled API/UI behavior or release readiness.

## Reproducibility

Read-only checkout: `d328ece2599a617a69ca6c9baf69a6c20686475c`.
Locked image: `astraeus-lightning-proof:c88ff83`, digest
`sha256:afbed8d5524a1c28a0bce3874118b6ab7d5e3f9d3ae9a54a8860494da55db3f6`.
The container had a 2 GiB memory ceiling; coordinator request, byte, workspace,
decoder and cache ceilings were unchanged. The harness used an HTTPX streaming
capture transport with automatic retries disabled and the default decoder.

Raw listings, index and selected range bytes, per-source receipts, normalized
payloads and the capture harness remain outside Git at
`/private/tmp/astraeus-ecmwf-current-live-proof/`. `proof.json` SHA-256:
`1cc78a2baa377303b58f27d0b4d9bfe336a2b6cb51877b2958aaa0d46c49d89e`.
Each response receipt includes exact URL/range, safe headers, received bytes,
digest and completion. Original per-message native metadata and full point
readback are retained. Do not reacquire merely to repeat this proof; replay the
captured bytes with network disabled.

Command used (performed once, both products):

```sh
docker run --rm --memory 2g \
  -v /private/tmp/astraeus-api-first-ecmwf-units/experiments/st-johns-weather-map:/work:ro \
  -v /private/tmp/astraeus-ecmwf-current-live-proof:/proof \
  -w /work -e PYTHONPATH=/work/api:/work \
  astraeus-lightning-proof:c88ff83 python /proof/live.py
```
