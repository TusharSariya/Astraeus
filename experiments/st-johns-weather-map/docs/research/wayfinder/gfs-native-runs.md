# GFS named native runs, September 7, 2026

This implementation evidence is non-normative and does not promote the source.
The accepted [desktop run-selection contract](../../../openspec/changes/desktop-evidence-api-contract/specs/desktop-evidence-api/spec.md)
and [GFS demand contract](../../../openspec/changes/timestamp-demand-query-cache/specs/demand-query-cache/spec.md)
own behavior. Governance references: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

## Source seam

`GFSQueryCoordinator.run_inventory(refresh=False)` exposes at most latest and
previous through `NativeRunInventory` and the existing bounded NOAA f000 index
probes. `run_times(run_id, refresh=False)` reads a bounded exact-key S3 listing
for that producer run. The listing retains only actual native hourly/f120 then
three-hourly keys through f384, rejects truncated or malformed XML, and stores
at most two run listings for a fixed 600 seconds. The existing timeline filters
those native times against each request's evidence window without caching a
previous request's clipped window.

`query`, `point_fields`, and `profile_levels` accept optional `run_id` and
`refresh` keywords. A named run is resolved before native frame matching and
must advertise the chosen frame in its listing. Removed runs and missing native
frames fail without substituting another run. The original less-than-one-hour
GFS selection rule and default latest behavior remain intact.

Explicit refresh revalidates discovery, named-run listing, selected index and
selected payload. Identical concurrent native-frame requests coalesce, including
instants within the same applicable hour. Ordinary reads never renew expiry.
Failed refresh preserves a still-valid cache entry, while expired values remain
unavailable. The four-entry/256 MiB payload bound, exact range/selector/bounds
key, existing native field identities and interval parser, and bounded worker
remain unchanged. No APCP payload or single-card product choice is introduced.

## Verification mapping

From `experiments/st-johns-weather-map`:

```sh
uv run --project api pytest -q api/tests/test_gfs_query.py api/tests/test_native_runs.py
```

46 tests passed. New GFS cases cover named Previous identity, zero additional
traffic on a fresh hit, missing/removed runs, exact listing keys, two-run bounds,
fixed expiry, explicit refresh, latest rollover, eight concurrent native-frame
refresh success/failure outcomes, and shared inventory refresh coalescing with
preservation of its still-unexpired generation. Existing point, profile, cloud
raster, receipt/manifest, cache-budget and timeline tests also pass.

From the repository root, `uv run --project tools/specs python
tools/specs/specctl.py validate` passed with zero errors and warnings.

## Temporary Linux decoder evidence

The existing retained NOAA f006 capture and replay helper were reused without
provider reacquisition. A prepared historical image lacked `jsonschema`, so the
current API Dockerfile and lock prepared a new image before offline execution.
The successful run used Docker `--network none --memory 2g`, a bind mount of the
current API source, and the production default child process with its existing
1 GiB address-space, 64 MiB output and 192 MiB workspace bounds.

- Image: `sha256:aacbd8b2f012e571c45c5a3b88d9935aaa72e6506bbad14bcd970766cb7697ff`.
- Temporary receipt: `/private/tmp/astraeus-api-first-gfs-proof/proof.json`.
- Receipt SHA-256: `da68d9068bb28e2804a6131020ada6fc375d894e70c73961398734e98c94dcf2`.
- Receipt records exact mounted-source hashes and original capture-receipt hash.
- Run `gfs-2026090612`; actual native valid time `2026-09-06T18:00:00Z`.
- 20 local replay requests: one listing, one index, 18 ranges; repeat adds zero.
- Provider-network requests: zero. The listing fixture is synthetic metadata;
  the index and GRIB range bodies are retained actual NOAA bytes.
- Surface and upper-air payloads: 497560 and 68884 bytes.
- Normalized digest: `e0202ed8ced1f20d038933e0114b17de57d4173a62458c018d5350c7c24d619f`.

No proof process remains running. API/Series integration belongs to the shared
interface owner; this source slice does not change the registry or public routes.

## Review correction

The source coordinator admits at most four distinct concurrent selections,
reusing `GFS_CACHE_MAX_ENTRIES`, and rejects saturation before discovery or
payload acquisition. Identical requests still join their admitted operation.
The in-flight identity includes explicit-refresh mode so a refresh cannot join
an ordinary cache-hit read and accidentally skip revalidation.

The targeted command `uv run --project api pytest -q api/tests/test_gfs_query.py
-k 'inflight or concurrent_native_frame_refresh'` passed four tests covering
saturation, refresh separation, and concurrent refresh success/failure. The
previous decoder receipt remains evidence for the unchanged production worker
and payload path; it records the source hash before this admission correction.
