# Compact capability-aware Point data amendment

Implemented in the existing dirty workspace based on
`c6544b2ececaade8215679154bb460b527f0ab47`. Pre-existing panel/selection work and
unrelated bounded-process changes were preserved. No commit, merge, source
admission or operational/verified status transition was made.

The owner supplied the compact capability-aware implementation plan on
September 8, 2026. Its explicit replacement of the older image-row and unchanged
point-time clauses is recorded in `proposal.md` and the amended experimental
contract. This evidence supersedes the initial implementation's presentation and
point-time statements, while retaining its other evidence as historical work.

## Result and limits

- Usable readings use source/value/relative-native-time columns; single-line
  rows target 28px. Percentage signs, concise ambiguity qualifiers, separate
  member lines, valid zeros and explicit `0 · no echo` are preserved.
- Loading remains in scientific categories. Completed omissions appear once per
  selected identity in an initially expanded bottom section. Empty groups are
  omitted. Image-only is declared for known satellite image fields; a missing
  numeric mapping is otherwise unsupported, not evidence of image-only support.
- Details retain selected time, native time and offset, run, retrieval time,
  units, provenance and policy. Focus follows a reading when it moves, and
  returns from provenance without stealing focus after the reader leaves.
- The one-minute age clock does not refresh requests. Two slots, 250ms debounce,
  deduplication, cancellation, obsolete-response rejection, timeout behavior,
  minimized refresh and persisted selection/minimization are retained.
- `time_selection=directional` is opt-in. Catalogue metadata declares
  `point_time_kind` and `directional_time_selection`. Native times resolve on the
  backend; selected time remains the response `valid_time`. Policy is included
  in client request identity. There is no new backend selection cache; existing
  native payload caches retain their resolved native time/run keys.
- Directional discovery is enabled for HRDPS, RDPS, GDPS, GFS, GEFS, IFS,
  AIFS Single, radar and the existing before-selection METAR/AQHI readers.
  Forecast plans use published native inventories; GEFS verifies its candidate
  lead through existing control-index discovery. Returned direction, native
  identity, freshness, run staleness, QC and coverage are checked again.
- **Readers without native discovery remain explicitly unsupported under the
  directional policy.** This includes SWOB, CAMS AOD, GFS Wave, OISST, OSTIA,
  GEPS reductions and WeatherNext. Their legacy exact-time interfaces remain
  intact. The agent asked whether to extend those source-specific contracts;
  no reply was received, so the announced conservative default was used.
  No synthetic timestamp inventory, acquisition schedule or new provider
  integration was added. Ordinary point coverage windows remain enforced.
- Radar reuses the shared GeoMet client, native pixel parser, discovery TTL,
  request/process budgets, registry freshness and native units. It samples rain
  and snow at one common published scan. Explicit Undetected zeros produce the
  echo flag, never fabricated zero rates. Empty coverage and source faults stay
  missing; sanitized OGC fault codes survive in provenance quality flags.

## Verification mapping

| Contract scenario | Verification |
| --- | --- |
| Compact selected readings, fields, members, percentages and zero | `web/src/workbench/PointDataPanel.test.tsx` |
| Loading, unavailable, recovery, bottom focus, provenance and no focus stealing | `PointDataPanel.test.tsx`; `web/scripts/prove-point-data.mjs` |
| Real-clock ages and no acquisition on age updates | Controlled-clock panel tests |
| Two requests, exact request identity, debounce, cancellation and obsolete replies | `pointRequests.test.ts`, `pointTimeout.test.ts`, full frontend suite |
| Directional boundaries, exact matches, gaps, freshness, legacy requests | `api/tests/test_point_directional.py` |
| Radar rates, no echo, missing coverage, failure, wrong time/units and budgets | Directional tests plus existing `test_wms_proxy.py` and `test_adapter_eccc_geomet.py` |
| Explicit capability mapping and generated contract | `test_source_delivery.py`, `test_source_point_integration.py`, `test_desktop_layer_identity.py`, generation checks |
| All desktop sizes/themes/zoom, Layers/timeline overlap, details, saved stacks and camera | 18-combination browser proof, 42 captures |

## Commands and evidence

From `experiments/st-johns-weather-map/web`:

```sh
npm test
npm run build
npm run check:source-types
BENCH_URL=http://127.0.0.1:5312 BENCH_CATALOG_API=http://127.0.0.1:8321 BENCH_PROOF_DIR=<repository>/docs/evidence/compact-point-data-20260908/browser node scripts/prove-point-data.mjs
```

Frontend: 627 passed. Production build passed with the existing large-bundle
warning. The first full run encountered the existing NativeSeries expiry test's
timing failure; isolated and subsequent full runs passed without changing it.
Browser proof: all 18 combinations passed (1280×800, 1440×900, 1920×1080;
dark/light/red-night; 100% and actual Chrome 200%). Layout, camera, focus and
scroll assertions passed. Browser weather responses are constructed fixtures;
provider weather requests in that proof: zero. Ports 5312 and 8321 were owned
by this task; unrelated existing servers on 5301 and 8197 were not altered.

From `experiments/st-johns-weather-map`:

```sh
uv run --project api pytest -o addopts='' -q api/tests/test_point_directional.py api/tests/test_source_delivery.py api/tests/test_source_point_integration.py api/tests/test_point_evidence.py api/tests/test_wms_proxy.py api/tests/test_adapter_eccc_geomet.py api/tests/test_desktop_layer_identity.py
uv run --project api pytest -o addopts='' -q api/tests/test_point_directional.py
uv run --project api python scripts/generate_source_contract.py --check
openspec validate selected-layer-point-data --strict
```

Affected API regression suite: 242 passed, 2 existing opt-in live tests skipped.
After the final freshness-reference/fault-code refinement, all 23 focused
radar/time tests passed. Native GeoMet MockTransport proof verifies two cached
capability reads, two native feature requests and zero image sampling requests.
Generated contract/TypeScript checks and strict OpenSpec validation passed.

From repository root:

```sh
uv run --project tools/specs python tools/specs/specctl.py validate
```

Specification validation: 0 errors, 0 warnings.

[Evidence directory](../../../../../docs/evidence/compact-point-data-20260908/)
contains logs, implementation hashes, captures and browser measurements.
[Live radar evidence](../../../../../docs/evidence/compact-point-data-20260908/live-radar.json)
is separate from the browser fixtures: at latitude 47.5615, longitude -52.7126,
selection 2026-09-08T20:44:41.745424Z resolved to native scan 20:42Z and returned
`radar_echo = 0`, with both rates absent. This confirms live no-echo delivery;
numeric rain/snow behavior is fixture-tested, not claimed as live rate evidence.

Suggested commit: `feat(point): compact readings and resolve declared native times`

Spec-Refs: [GOV-SPEC-001](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-001--specifications-are-authoritative), [GOV-SPEC-004](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-004--behavior-changes-are-spec-traceable), [GOV-SPEC-005](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-005--conflicts-fail-closed), [GOV-SPEC-006](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-006--verification-is-part-of-the-requirement).
Verification: exact commands and outcomes above; accepted experimental behavior in [selected-layer-point-data](specs/selected-layer-point-data/spec.md).
