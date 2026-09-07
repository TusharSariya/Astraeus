## Acceptance

Accepted for implementation under the [owner authorization](acceptance.md).
This is the selected frontend contract; all implementation tasks remain open.

## Why

The existing Workbench proves retrieved weather layers and timestamp-driven reads, but it does not assemble the owner-selected desktop Bench with one shared Focus, five views, a coherent Map stack, or one reusable provenance inspector. The selected prototypes and accessibility repairs now define a bounded frontend contract that can be implemented against fixed existing API fixtures before the remaining source batches.

## What Changes

- Rebuild the desktop shell as the selected Bench: vertical Map, Series, Sky, Activity, and Sources view controls; one stage; at most one right dock; per-view full screen; and one global Focus and timeline.
- Persist the selected site or point, instant, active view, optional dock, and Map stack in the URL while keeping theme as a browser preference.
- Rebuild Map controls around the selected layer-stack contract, including explicit frame alignment, absence states, evidence identity, one-line disclosure, family legends, and Saved stacks.
- Add the selected ledger-and-inspector provenance component with permanent evidence-class glyph and source tag, bounded disclosure, and fail-closed absence wording.
- Carry the already-selected Series Overview/temporary Compare, Sky Horizon instrument, Activity Operational stack, and Sources Ledger/Family finder/Coverage lanes into the desktop contract. These are staged implementation obligations, not deferred design choices.
- Use the selected Hyperlegible tokens and light, dark and red-on-black night themes from #41.
- Require semantic controls, stable focus across rerenders, explicit inspector entry and return, scoped Escape handling, text alternatives, and concise status announcements.
- Preserve the existing API routes and timestamp-demand behavior. This change adds no API route, source admission, science, scoring, interpolation, or synthetic value.
- Keep the phone brief, new API contract, screen-reader certification, Activity scoring, band math, and source completion outside this change.

## Capabilities

### New Capabilities

- `desktop-evidence-workbench`: The shared desktop Bench shell, Focus URL state, five-view navigation, Map stack presentation, provenance inspector, and keyboard/focus contract.

### Modified Capabilities

- `web-evidence-interface`: Replaces the current single-view desktop arrangement while preserving its retrieved-only boundary, frame-exact data paths, layer resolution, text alternatives, data modes, and honest unavailable states.

## Impact

- Affected frontend: `web/src/App.tsx`, `web/src/MapPanel.tsx`, shared timeline/theme/evidence modules, new shell/view/provenance components, and `web/src/styles.css`.
- Verification uses deterministic API fixtures and a fixed clock in Vitest plus a fixture-backed Chromium keyboard pass; it does not reacquire live provider data.
- The implementation salvages the existing API client, types, field families, evidence classes, playback, scrubber, tier boundary, FlowBlendLayer, and tested Map imagery pipeline.
- Owner-selected inputs: Wayfinder #39 (shell/Focus), #40 (provenance), #46 (Map stack), and #69 (accessibility repair contract), under parent #38 and proposal task #55.
- Full-view inputs and existing prototype assets are indexed in [selected-designs.md](selected-designs.md). Existing owner design selections are preserved; no replacement layout is proposed.
