# Holyrood API-first source evidence

Experimental source software only. No route, canonical numeric field, accepted
image contract, source activation or operational status transition is included.

## Endpoint decision

The [ECCC radar index](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_en/)
and [GeoMet radar documentation](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_geomet_en/)
were checked on 2026-09-07. They identify the public radar WMS products as North
American composites, precipitation type and extrapolation. They do not identify
a native Holyrood numerical WMS/WCS product. A composite cannot satisfy CASHR
source identity.

The [Datamart radar documentation](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radarimage-datamart_en/)
documents HTTPS directory discovery and native DPQPE GIF filename syntax. The
selected exact endpoint remains
`https://dd.weather.gc.ca/today/radar/DPQPE/GIF/CASHR/`.
This is the documented data distribution service, not an image-page or
undocumented website endpoint. Only same-time native Rain/Snow filenames qualify;
Contingency products remain excluded. No GIF pixel is interpreted numerically.

Reuse evidence: `holyrood-cashr-20260906.md` records actual native CASHR paired
bytes and hashes; `/tmp/holyrood105-capture/` retains receipts and capability
responses. Its WMS metadata describes DPQPE as a North American mosaic; its WCS
capture contains no radar/CASHR coverage. These are dated observations, not a
claim that no future native radar API can exist. No new provider payload fetch
was needed. The older `astraeus-holyrood-contract` draft remains unaccepted.

## Source-local software

`HolyroodQueryService.read_images(refresh=False)` caches at most one immutable
paired image revision. It retains at most two 512 KiB payloads plus bounded
receipts, with a 128 KiB listing receive ceiling and 1,024-character safe header
values. Each response uses bounded streaming and refuses redirects and encoded
bodies. Only successful complete pairs enter the cache. Expiry withholds previous bytes. Failed explicit refresh raises to all waiting
callers and preserves a still-valid previous pair for later ordinary reads.
Concurrent misses and refreshes share both successful and failed outcomes.

The UTC retention timestamp is listing HTTP completion plus 60 seconds. A
separate monotonic deadline fixed before acquisition caps the total lifetime
at 60 seconds, including a wall-clock rollback. It is an
experimental local memory policy, not source cadence, image freshness, or a
claim that an old image is current. Requests finishing outside that interval
fail. Native valid time remains the filename UTC time; future timestamps are
excluded. Numeric point/grid methods remain unsettled. Original image bytes,
digest, receive time, source quality unknown, and operational false survive hits.

The default worker reuses the existing bounded GIF structural validator under
`run_bounded_process`: 256 MiB address space, 512 KiB stdin, 4 KiB stdout/stderr,
and one-byte unused output-file limit. This proves bounded structural validation,
not pixel decoding, palette calibration, georeferencing or precipitation values.

## Verification

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006

The fixture tests map fail-closed identity/absence and nonactivation to
GOV-SPEC-001/005, preserve normative status under GOV-SPEC-002, and provide this
traceable reproducible evidence under GOV-SPEC-004/006. This is experimental
software rather than a production conformance claim.

From the repository root:

```sh
uv run --project tools/specs python tools/specs/specctl.py validate
```

Result: 0 errors, 0 warnings.

Real production worker proof, exact source read-only mount:

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-holyrood/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work \
  astraeus-lightning-proof:c88ff83 python -m pytest -q -p no:cacheprovider \
  api/tests/test_holyrood_query.py api/tests/test_experimental_holyrood_radar.py
```

Image: `sha256:afbed8d5524a1c28a0bce3874118b6ab7d5e3f9d3ae9a54a8860494da55db3f6`.
Result after the cache review correction: 17 passed. The default worker test uses 3 exact-URL fixture transport
requests (listing and two GIFs), zero provider requests, and zero additional
requests on the cache hit. Additional cases cover concurrent misses, refresh,
expiry, failed replacement, slow acquisition, redirects, malformed/oversize
images, future times and native/contingency separation. Deterministic eight-caller
failure tests prove that both misses and explicit refreshes make one request
and share one failure; a rollback test proves monotonic expiry.

Activation residual: an owner-approved image method/retention contract or a
verified and approved numerical native CASHR product is still required.
