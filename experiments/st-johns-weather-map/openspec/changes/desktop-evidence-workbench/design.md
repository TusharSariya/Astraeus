> Current visual authority: the September 8 owner-selected map-first revision in
> [acceptance.md](acceptance.md) and the [desktop contract](specs/desktop-evidence-workbench/spec.md) replaces conflicting historical layout/token choices below.

## Context

See [proposal.md](proposal.md). The current React Workbench already owns the API client, evidence types, MapLibre/deck.gl imagery path, playback and scrubber logic, field families, theme handling, and fixture gate. Owner-selected prototypes define the Bench shell (#39), Map stack (#46), ledger inspector (#40), and repaired keyboard contract (#69). The API remains timestamp-driven and sources may continue changing shared response types in parallel.

## Goals / Non-Goals

**Goals:**

- Introduce the shell and shared Focus as small modules around salvaged, tested data and rendering code.
- Keep API reads in the existing client layer and make every view consume the same normalized Focus/evidence state.
- Make the Map and provenance component usable with the current API's known omissions.
- Prove behavior with fixed fixtures, a fixed clock, and a fixture-backed browser pass.

**Non-Goals:**

- New API routes, response fields, source admission, refresh architecture, Activity scoring, scientific derivations, or live-provider capture.
- Phone layout, band math, screen-reader certification, camera images, or operational promotion.
- Completing all five view bodies in the first implementation slice. The full desktop change still owns their selected designs, enumerated in selected-designs.md and the executable task list. Existing usable panels and views remain reachable during migration; only capabilities with no current response-backed implementation receive bounded unavailable states. A missing body does not complete this change.

## Decisions

### Salvage deep modules and replace the page composition

Keep `api.ts`, response types, playback, scrubber axis, tier boundary, field families, evidence-class parsing, `FlowBlendLayer`, and the tested imagery reconciliation. Replace the page-level composition incrementally with `WorkbenchShell`, `FocusBar`, `ViewRail`, `MapStack`, and `EvidenceInspector`. This follows the #42 inventory and avoids copying prototype scripts into production.

### Use one typed URL adapter for linkable state

Parse and serialize Focus, active view, optional dock, and stack through one module. Invalid coordinates, instants, view names, opacity, or layer IDs fail to documented defaults with a visible notice. History changes come from explicit reader actions; clock or API updates do not churn the URL. Theme remains in browser storage.

### Preserve response ownership at the API boundary

Views receive normalized response objects and request state from the existing API client. Components do not calculate source identity, science, freshness, or provenance. The temporary family/title mapping already present in the client may supply display vocabulary; unknown values remain unknown.

### Use one nonmodal inspector controlled by stable evidence keys

Each provenance opener is a native button identified by a stable evidence key. The shell owns the selected key and opener reference. On open it focuses the inspector heading; on close it restores the opener or a visible view/stack fallback. The inspector stays nonmodal so the staged view remains usable, matching the selected prototype.

### Keep first implementation independent of live source completion

Tests use current checked-in API fixtures and an injected fixed clock. Source migrations can add response cases without changing the shell contract. Shared files under active source work (`api.ts`, `types.ts`, `App.tsx`, `MapPanel.tsx`) are touched only after checking concurrent diffs; new shell modules carry most of the first slice.

## Risks / Trade-offs

- **[Current API omits some layer identity]** → use only existing explicit mappings and show unknown for the rest; do not infer a stronger class or source.
- **[A five-layer built-in may include an unavailable source]** → retain the row and exact absence instead of silently substituting.
- **[Rerenders can strand focus]** → stable keys, opener tracking, and browser keyboard tests cover update and removal paths.
- **[Parallel source PRs touch shared client files]** → isolate shell modules, rebase before integration, and rerun focused deterministic client tests.
- **[Prototype copy can overstate unfinished views]** → unimplemented view bodies state unavailable and expose no inert controls.

## Migration Plan

1. Add URL/Focus state and shell components behind the existing fixture-backed entry point.
2. Mount the existing Map pipeline inside the stage and add the selected stack presentation without changing API requests.
3. Add the shared evidence row and inspector, then migrate Map rows first.
4. Keep existing usable panels reachable from the shell, add explicit unavailable bodies only for absent capabilities, and implement the selected redesigned view bodies in subsequent slices of this change. API/scoring/camera behavior retains its own contract boundary; unavailable placeholders are transitional, not proof of completed view implementation.
5. Replace the old page composition after focused unit, build, accessibility, and fixture-backed browser checks pass. Rollback restores the previous `App` composition while leaving salvaged modules unchanged.
