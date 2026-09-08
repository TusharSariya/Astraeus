# Dense layer menus - September 8, 2026

The owner requested implementation of the dense, single-line layer-menu plan.
Browse now presents individual declared map layers and one row for each source
without map capabilities. Active uses the same 28px row layout in actual drawing
order. Clicking toggles membership; Active's separate visibility control preserves
membership. Right-click, Shift+F10, Menu key and the trailing details control open
the same shared-space details without changing selections.

Details retain full source/layer identities, failure reasons, actual frame and run
timestamps, imagery-check time, provenance, point and Series actions, visibility,
opacity and reorder controls. Missing catalogue frames retain their declared names.
Subject filters apply to each layer's explicit metadata. Source-level provider,
model and method facets, source Ledger behavior and all existing filters remain.
No backend, acquisition, scientific metadata, saved-stack or URL schema changes.

## Verification

- `cd experiments/st-johns-weather-map/web && npm test`: **597 tests pass** in
  42 files, including existing Map imagery, saved-stack, URL and shell regressions.
- `npm run build`: passes. Existing large-bundle warning remains.
- `npm run check:source-types`: passes.
- `cd ../api && uv run python ../scripts/generate_source_contract.py --check`:
  OpenAPI and response fixtures match.
- From the experiment root,
  `npx -y @fission-ai/openspec validate desktop-evidence-workbench --strict`: passes.
- From the repository root,
  `uv run --project tools/specs python tools/specs/specctl.py validate`:
  zero errors and warnings.
- `BENCH_PROOF_DIR=<output> node web/scripts/prove-dense-menus.mjs`: actual Chrome,
  real declarations for 125 sources, deliberately unavailable weather responses.
  No real provider acquisition or live-weather validation is claimed.

One earlier full run failed an existing asynchronous generated-draw receipt
assertion in `MapPanel.test.tsx`. Its isolated 72-test suite and the subsequent
complete 597-test run passed. No Map rendering or shader implementation changed.

## Mapped evidence

| Contract scenario | Verification |
| --- | --- |
| Dense rows toggle one identity | `discovery.test.tsx`: repeated subjects, hidden selections, Enter/Space and all four details gestures; Chrome URL/membership assertions |
| Per-layer subjects and retained facets | `discovery.test.tsx`: multiple capabilities with different subjects, provider facets, point-only and information-only entries |
| Details preserve list context | Chrome filtered/collapsed group, scroll and focus assertions; unit fallback when catalogue refresh removes the opener |
| Active removal and adjustment | `MapStack.test.tsx`: next/previous/heading focus, visibility, opacity, order, explicit delivery replacement, saved selections; Chrome saved-stack/URL round trip |
| Scientific and failure identity | `MapStack.test.tsx`: actual drawn run versus newest index run, missing/loading/error/empty states and provenance notices; Chrome WeatherNext paths and partial registry failure |
| Dense desktop presentation | 57 screenshots across three sizes, three themes and native 100%/200% zoom; row heights, internal scrolling and end-of-list details access checked |

All measured rows are 28 CSS pixels tall. With Browse ungrouped and details and
filters closed, 1280×800 exposes **16 full rows**, 1440×900 exposes 20 and
1920×1080 exposes 26. At 200% zoom the smaller windows require internal scrolling;
the `*-scrolled.png` captures show the accessible list below its controls. No
unexpected document scrolling was measured. The [receipt](browser/receipt.json)
records viewport geometry, requests and browser errors. A deliberate map pan
changes the image; the panned map pixels remain identical through details and
nested provenance, and the same map canvas survives point and Series navigation.

Representative captures:

- [Browse, 1280×800 dark](browser/1280x800-dark-100-browse.png)
- [Active, 1280×800 dark](browser/1280x800-dark-100-active.png)
- [Browse, native 200% red night, scrolled](browser/1280x800-Red-night-200-browse-scrolled.png)
- [WeatherNext supported paths](browser/weathernext-details.png)
- [Partial catalogue failure](browser/partial-catalogue-failure.png)

The source API supplied the public catalogue declarations, while weather requests
were intercepted with explicit unavailable responses. The partial-failure case
uses a constructed independent layer descriptor and a failed registry response.
Reference tiles are OpenFreeMap. These are interaction and presentation proofs,
not evidence of successful weather delivery or screen-reader certification.

## Authority and handoff

[Owner authorization](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/acceptance.md)
and the amended desktop contract record the selected non-breaking experimental
revision. PR #306 carries implementation and evidence. **#38 remains open for
owner visual acceptance.** No verified specification status is asserted.

Rollback is this frontend/spec revision; it needs no data migration. Runtime
remains the isolated workbench at http://localhost:5197 with API port 8197.
The original dirty checkout was preserved.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-006;
`desktop-evidence-workbench` ordered evidence stack and keyboard context;
`web-evidence-interface` unified discovery and additive stack.
