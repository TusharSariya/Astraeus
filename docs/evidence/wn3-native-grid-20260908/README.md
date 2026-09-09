# WN3 native Avalon grid evidence

Classification: owner-authorized isolated experiment. No production admission or
normative status transition. Base commit: `34f94803377516595a3d2538e8e953c1441c6261`;
evidence applies to the accompanying working-tree changes.

Spec-Refs: [GOV-SPEC-001](../../specv1/GOVERNANCE.md#gov-spec-001--specifications-are-authoritative),
[GOV-SPEC-004](../../specv1/GOVERNANCE.md#gov-spec-004--behavior-changes-are-spec-traceable),
[GOV-SPEC-006](../../specv1/GOVERNANCE.md#gov-spec-006--verification-is-part-of-the-requirement).
Owning experimental contract:
[bounded native grid and display](../../../experiments/st-johns-weather-map/openspec/changes/weathernext3-surface-point/specs/source-delivery/spec.md#requirement-bounded-native-avalon-cloud-grid).

## Implemented behavior

`GET /api/experiments/weather/v0/sources/google-weathernext-3-statistics/grid`
accepts `product` (`WeatherNext 3 local` or `WeatherNext 3 historical`),
`field=weathernext3_total_cloud_cover_mean`, and offset-aware `selected_time`.
It returns the next native hourly frame with selected/native timestamps,
ensemble-mean percentages, null masks, original axes and midpoint boundaries,
pinned run and generation-specific acquisition receipts. Display rectangles are
clipped to [-55, 46.5, -51, 48.5], including water. The current native axes give
21 × 41 = 861 intersecting cells. No point-per-cell acquisition is used.

Only these two capabilities set `grid=true`; omitted capability remains
unsupported. Existing saved point-only selections and default stacks retain
their behavior. The map uses fixed tint with alpha = cloud fraction × layer
opacity; it is a display mapping, not physical cloud optical opacity. Zero
remains inspectable; a neutral diagonal hatch distinguishes missing cells.
The existing map details show centre, original footprint, percent, statistic,
run, valid time, and frame acquisition provenance.

Grid responses are bounded to 1 MiB; the cache retains four frames/8 MiB with
60-second expiry. Keys separate scope, pinned root generation/ETag, native
hour, field and region. Data chunk generations remain pinned in receipts.
Duplicate frame and matching point reads coalesce. Discovery and science acquisitions
share a process-wide two-slot semaphore, and client point/grid HTTP requests share two
slots. Grid-first acquisition enables the corresponding point to use its frame;
point-only requests keep their direct reader. Expired, canceled and failed
replacement frames are not displayed. Opacity and viewport changes reuse the
frame. Named-run choices unsupported by this endpoint fail closed.

The acquisition receipt model allows up to 30 transfers for bounded multi-chunk
grids; existing point validators retain their narrower limits. Decoder, auth,
discovery, historical cutoff and upstream transfer budgets are unchanged.

## Mapped verification

| Contract scenario | Verification |
| --- | --- |
| Complete grid agrees with points | `api/tests/test_source_grid.py`: 861-cell extraction, ascending/descending axes, longitude conversion, shared boundaries, four unique chunks, boundary/interior point comparisons, valid zero/100/null, cached point identity |
| Grid unavailable or replaced | Same suite: native lead, unit/shape/chunk failure, missing chunk, historical cutoff, scope separation, expiry, four-frame eviction, oversized response, credential disclosure and concurrent grid/point coalescing |
| Display and inspection preserve meaning | `web/src/workbench/sourceGrid.test.ts`: 0/50/100 alpha, adjoining clipped polygons, masks and coordinates; browser missing-cell inspection through existing details |
| Selection survives and remains bounded | Same client suite plus `pointSelections`, `pointRequests`, `MapStack`, `PointDataPanel`, `discovery`, `MapEvidenceDetails`, API normalization and App tests: legacy state, cycle, no Data-only acquisition, two slots, StrictMode cancellation, obsolete response rejection and failed replacement removal |

Verification commands, from `experiments/st-johns-weather-map` unless stated:

- `uv run --project api pytest -o addopts='' -q api/tests/test_source_delivery.py api/tests/test_source_grid.py api/tests/test_weathernext_surface.py api/tests/test_weathernext_delivery.py api/tests/test_weathernext_native.py api/tests/test_weathernext_gcs_bridge.py api/tests/test_weathernext_local_delivery.py api/tests/test_weathernext_shared_delivery.py api/tests/test_weathernext_query.py`: 266 passed, 3 platform skips.
- `npm --prefix web test -- src/workbench/sourceGrid.test.ts src/workbench/pointRequests.test.ts src/workbench/pointSelections.test.ts src/workbench/discovery.test.tsx src/workbench/MapStack.test.tsx src/workbench/PointDataPanel.test.tsx src/workbench/MapEvidenceDetails.test.tsx src/api.test.ts src/App.test.tsx`: 257 passed.
- `uv run --project api python scripts/generate_source_contract.py --check`, `npm --prefix web run check:source-types`, `npm --prefix web run build`, `openspec validate weathernext3-surface-point --strict`: passed. Vite retains its bundle-size advisory.
- From repository root: `uv run --project tools/specs python tools/specs/specctl.py validate`: zero errors/warnings.

## Network-disabled Linux proof

Prepared image: `astraeus-lightning-proof:c88ff83`, digest
`sha256:afbed8d5524a1c28a0bce3874118b6ab7d5e3f9d3ae9a54a8860494da55db3f6`.
Current source was mounted read-only over the image's prepared dependencies.

```sh
docker run --rm --network none --memory 3g \
  -v "$PWD:/work:ro" -w /work -e PYTHONPATH=/work/api:/work \
  -e OPENBLAS_NUM_THREADS=1 astraeus-lightning-proof:c88ff83 \
  python -m pytest -q -o addopts='' -p no:cacheprovider \
  api/tests/test_source_grid.py \
  api/tests/test_weathernext_gcs_bridge.py::test_actual_native_worker
```

17 passed. The actual production child retains its own 2 GiB/80-second CPU
limits. The grid case performed 18 bounded object RPC operations, retrieving
four coordinate objects, root metadata and four unique field chunks. No
provider network was available. This establishes the worker seam, not live
upstream coverage.

## Separate upstream agreement

[Upstream agreement](upstream-agreement.json) records two real, independent
acquisitions using the existing `astraeus` profile, with identical
generation-pinned request URLs. The September 7 18Z run, September 8 12Z valid
frame returned 93.81702542304993% at 47.5 N, 53 W in both grid and point reads.
Each acquisition made 11 HTTP requests and received 21,978,557 response bytes;
the complete grid response was 28,373 bytes. Grid acquisition took 23.22 seconds;
the combined proof took 45.88 seconds. A cached point agreed too.

Raw native receipts remain temporary under
`/private/tmp/astraeus-wn3-grid-proof/`, separate from synthetic browser evidence.
They were acquired before the final descriptive grid adapter/receipt label
change; native extraction, numeric conversion and generation pinning are the
same. No additional forecast sequence was acquired. This does not establish
public redistribution permission, source admission or complete archive coverage.

## Browser replay and layouts

[Browser result](browser/result.json) records one grid followed by one point
request, zero provider weather requests, and zero page errors. Synthetic native
Zarr fixtures deliberately include 0%, 50%, 100% and missing cells. The replay
clock fixes the fixture evidence time; it does not refresh upstream evidence.
Map rendering, native inspection, and viewport/theme reuse were exercised in
Chrome. Layouts cover 1280×720, 1440×900 and 1920×1080, each in light, dark and
red night themes at real browser zoom 100% and 200% (18 captures). Layers and
timeline remain separate; the smallest zoomed view uses the existing scrollable
Layers panel. The compact legend avoids covering the point panel and Evidence
control. [Hashes](capture-hashes.json) cover all captures; representative
1440×900 images and missing-cell inspection are retained in `browser/`. Other
sizes remain in the temporary proof directory.

Reproduce the synthetic replay with a current local Vite server:

```sh
uv run --project api python scripts/wn3_grid_fixture.py --output /tmp/wn3-grid-proof
cd web
WN3_GRID_PROOF_DIR=/tmp/wn3-grid-proof BENCH_URL=http://127.0.0.1:5323 \
  node scripts/prove-wn3-grid.mjs
```

## Runtime and rollback

The local API/web were rebuilt with `compose.yaml` and `compose.weathernext.yaml`.
The selected profile's short-lived token was refreshed into the API's existing
private tmpfs. Local ports remain API 8000 and web 5173. No credentials are
stored in this evidence. Token expiry still needs the existing refresh command.
Rollback is to turn these layers Off/Data only or revert this experimental
slice; there is no schema migration, scheduled ingestion or default-profile
change.
