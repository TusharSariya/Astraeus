# Selected-layer Point data implementation

The owner-approved panel and three-state selection workflow are implemented in
the isolated weather-map desktop. No operational or specification `verified`
status is asserted.

## Behavior and existing seams

- `pointSelections.ts` owns explicit source/product/field references, merged
  variant choices, the existing GEFS all-members default, state cycling and the
  shared URL/saved-stack decoder. Legacy visibility maps directly to Map + data
  or Data only. Unknown capabilities remain visible and unavailable.
- `DiscoveryBrowser`, `LayerRow` and `MapStack` expose individual fields,
  keyboard-operable selection, unchanged context-menu details, explicit Remove,
  opacity/order restoration and Open point data focus. Source titles never
  establish a numeric map-to-point association.
- `pointRequests.ts` reuses `loadPoint` and normalization, deduplicates by exact
  transport identity, debounces 250ms, and permits two active selected-point
  requests. Canceled transports retain their slot until settlement. Generation
  checks and render-time identity gating reject obsolete responses.
- `PointDataPanel` stays mounted when minimized, groups selected readings by
  existing family metadata and keeps sources separate. It discloses native
  timestamps, offsets and returned provenance. Fixture fallbacks are withheld
  from current point evidence. Image-only rows retain frame information.
- The map-sized overlay keeps its header visible while contents scroll. Narrow
  effective widths share space with Layers; timeline expansion has a bounded
  height. Nested provenance closes back to its originating reading and scroll.
  Point-only timeline rows use readable field names.

## Verification mapping

| Accepted requirement | Evidence |
| --- | --- |
| Field selection separates map display from point data | `pointSelections.test.ts`, `discovery.test.tsx`, `MapStack.test.tsx`; browser cycles click/Enter/Space, context details and retained opacity |
| Point data persists inside the map | `PointDataPanel.test.tsx`; browser empty state, growth, internal scrolling, minimized reload and refresh, 18 viewport/theme/zoom combinations |
| Point readings preserve selected identity and return context | Panel tests for source separation, selected-only filtering, native-time offset and scroll/focus return; browser layer-to-reading focus and nested provenance |
| Every active point selection owns exact-request results | `pointRequests.test.ts` deferred transports/fake timers prove deduplication, concurrency, cancellation, obsolete rejection, settled playback and independent failures; panel tests cover partial/absent fields and credentials |
| Restored selections retain compatibility | Shared decoder tests, existing URL tests and browser saved-stack/URL round trips, retained point identities, order and opacity; map canvas identity, dimensions and panned-map pixel comparison |

## Commands and results

From `experiments/st-johns-weather-map/web`:

```sh
npm test
npm run build
node scripts/prove-point-data.mjs
```

All 614 frontend tests and the production build pass; exact logs are in the evidence
directory below. The build retains the existing large-bundle warning.
The browser proof passes 18 combinations: 1280×800, 1440×900 and 1920×1080;
dark, light and red night; 100% and actual Chrome 200% zoom. Forty captures
include empty, single-reading, minimized and WeatherNext credentials states,
plus Layers/timeline and provenance/Layers/timeline combinations.

From `experiments/st-johns-weather-map`:

```sh
uv run --project api pytest -q api/tests/test_desktop_layer_identity.py api/tests/test_source_point_integration.py api/tests/test_point_evidence.py
openspec validate selected-layer-point-data --strict
openspec validate desktop-evidence-workbench --strict
```

Affected API checks pass (91 cases). Both OpenSpec changes validate. The desktop
contract previously lacked scenario headings for its existing WeatherNext local
restart requirement; matching scenarios were added without changing that rule.
No API schema or generated source types changed.

From repository root:

```sh
uv run --project tools/specs python tools/specs/specctl.py validate
git diff --check
```

Specification validation passes with zero errors and warnings. Diff checks pass.

## Browser evidence and limits

[Evidence directory](../../../../../docs/evidence/point-data-20260908/)
contains test/build logs, source hashes, `constructed/results.json` and all PNGs.
The browser uses real local catalogue declarations and constructed responses;
all browser weather requests are intercepted, with zero provider-weather
requests. These captures prove client behavior, not successful live WeatherNext
authentication or provider availability. API tests use existing fixed fixtures.
The proof used an owned Vite process on port 5301; it is stopped after handoff
checks. Existing services on ports 5197 and 8197 were not modified or stopped.

## Prepared change metadata

Title: `feat(desktop): add persistent selected-field point data`

Selected map and point fields now retain independent readings at shared Focus
in a persistent, minimizable panel. Rows cycle Off, Map + data and Data only;
point-only rows alternate Off and Data only. The change retains URL/saved-stack
compatibility and uses existing endpoints without new acquisition or science.

Spec-Refs: [GOV-SPEC-001](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-001--specifications-are-authoritative),
[GOV-SPEC-002](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-002--human-approval-controls-normative-status),
[GOV-SPEC-004](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-004--behavior-changes-are-spec-traceable),
[GOV-SPEC-005](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-005--conflicts-fail-closed),
[GOV-SPEC-006](../../../../../docs/specv1/GOVERNANCE.md#gov-spec-006--verification-is-part-of-the-requirement).

Verification: commands and results above; accepted behavior is in
[the selected-layer contract](specs/selected-layer-point-data/spec.md).

Failure behavior: each selected field retains its own loading, refusal, gap or
failure; unavailable identities are retained without substitution. Reverting
the client changes restores the earlier UI; older clients cannot interpret new
point-only selection entries, so existing legacy stacks remain the backward
compatibility boundary.
