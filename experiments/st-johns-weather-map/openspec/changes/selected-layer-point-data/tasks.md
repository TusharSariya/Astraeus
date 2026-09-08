## Authority

- [x] Obtain owner acceptance of the proposed contract before implementation;
  record the owner statement and required specification review metadata.
- [x] Reconcile the desktop workbench's binary membership, separate visibility,
  point-only details and URL clauses with this accepted replacement.

## Implementation and mapped verification

- [x] Selection requirement: update typed selections, `LayerRow.tsx`,
  `MapStack.tsx`, `DiscoveryBrowser.tsx` and `discovery.ts`; test cycling,
  point-only choices, shared groups, retained settings/order and removal focus.
- [x] Persistent panel requirement: add panel component and `bench.css` layout,
  integrate with `App.tsx` and `WorkbenchShell.tsx`; verify natural growth,
  internal scrolling, empty state, minimized storage and timeline coordination.
- [x] Reading requirement: filter selected fields through explicit capability
  mappings, use existing family metadata and provenance; test multiple sources,
  image-only rows, layer-to-reading focus and provenance return scroll/context.
- [x] Request requirement: reuse `api.ts::loadPoint` and normalization with an
  independent request scheduler; use fake timers and deferred promises to test
  deduplication, two-request limit, 250ms debounce, cancellation, obsolete-result
  rejection, minimized refresh and settled playback steps. Test WeatherNext,
  credentials refusal, partial results and unavailable native times.
- [x] Restoration requirement: update `focusUrl.ts` and saved-stack validation;
  test legacy visible/hidden entries, explicit selectors, unavailable selections,
  opacity, order and camera preservation.

## Required gates after implementation

From `experiments/st-johns-weather-map/web`:

- [x] `npm test` (frontend unit/component and existing configured browser tests).
- [x] `npm run build` (TypeScript and production bundle).
- Not applicable: `npm run check:source-types`; the API capability schema and generated source types are unchanged.
- [x] Extend the existing desktop browser proof for panel growth/scroll,
  minimized refresh/storage, keyboard/provenance focus return, all three desktop
  sizes, every theme, 200% zoom and simultaneous overlays. Record the exact
  command: `node scripts/prove-point-data.mjs`. Captures and results are linked
  in `implementation-evidence.md`.

From `experiments/st-johns-weather-map`:

- [x] `uv run --project api pytest -q api/tests/test_desktop_layer_identity.py api/tests/test_source_point_integration.py api/tests/test_point_evidence.py`
- [x] `openspec validate selected-layer-point-data --strict`

From repository root:

- [x] `uv run --project tools/specs python tools/specs/specctl.py validate`

Contract checks alone do not verify application behavior. Record exact outcomes
and evidence for each gate; leave unperformed gates unchecked.

## Proposal validation, September 8, 2026

Verification: `openspec validate selected-layer-point-data --strict` passed.
Verification: `uv run --project tools/specs python tools/specs/specctl.py validate`
passed with 0 errors and 0 warnings. These results validate the proposed documents
only; application gates were subsequently completed as recorded in
`implementation-evidence.md`.

## Compact capability-aware amendment

The current implementation, mapped tests, exact gate outcomes, live radar check
and remaining directional-discovery limitations are recorded in
[compact implementation evidence](compact-implementation-evidence.md).
