## 1. Shared Focus and shell

- [ ] 1.1 Add `web/src/workbench/focusUrl.ts` to parse and serialize site or point, fixed/live instant, active view, dock, and ordered stack; verify invalid, round-trip, omitted-live-time, and fixed-clock cases with `npm test -- --run src/workbench/focusUrl.test.ts`.
- [ ] 1.2 Add `web/src/workbench/WorkbenchShell.tsx`, `FocusBar.tsx`, and `ViewRail.tsx` with one stage, at most one right dock, full-screen return, data-mode banner, and bottom timeline; verify semantic controls and shared Focus with `npm test -- --run src/workbench/WorkbenchShell.test.tsx`.
- [ ] 1.3 Route every existing usable response-backed panel through the shell and add honest unavailable bodies only for absent view capabilities; verify retained panel access and absence wording with `npm test -- --run src/workbench/WorkbenchShell.test.tsx`.

## 2. Map stack

- [ ] 2.1 Add `web/src/workbench/MapStack.tsx` and mount the existing `MapPanel` imagery pipeline in the stage; verify top-first order, opacity, visibility, absence retention, and URL replacement with `npm test -- --run src/workbench/MapStack.test.tsx src/MapPanel.test.tsx`.
- [ ] 2.2 Add the Nowcast built-in and family legend presentation without changing frame requests; verify missing default members remain explicit and no substitute request occurs with `npm test -- --run src/workbench/MapStack.test.tsx src/api.test.ts`.
- [ ] 2.3 Add the one-line Map disclosure and complete detail table using returned draw states; verify generated, partial, nothing-drawn, and truncation cases with `npm test -- --run src/workbench/MapDisclosure.test.tsx`.

## 3. Shared provenance and accessibility

- [ ] 3.1 Add `web/src/workbench/EvidenceGlyph.tsx`, `EvidenceRow.tsx`, and `EvidenceInspector.tsx` with response-owned sentences and explicit missing-property states; verify retrieved, generated, null, blocked, aged-out, refused, and unknown-class fixtures with `npm test -- --run src/workbench/EvidenceInspector.test.tsx`.
- [ ] 3.2 Preserve opener and logical focus through inspector open, Close, scoped Escape, rerender, and opener removal; verify keyboard behavior with `npm test -- --run src/workbench/evidenceFocus.test.tsx`.
- [ ] 3.3 Add Map and timeline semantic alternatives plus concise status announcements; verify accessible names, table content, and live-region updates with `npm test -- --run src/workbench/WorkbenchShell.test.tsx src/workbench/MapStack.test.tsx`.

## 4. Styling and deterministic acceptance

- [ ] 4.1 Apply the selected desktop tokens and Bench layout in `web/src/styles.css`, including visible focus, non-colour state cues, 200% text zoom, dark and red-night themes, and reduced-motion handling; verify Chromium screenshots and keyboard order against fixed fixtures at 1440x900 and 200% zoom.
- [ ] 4.2 Run the focused client suite and production build with `npm test -- --run src/workbench src/MapPanel.test.tsx src/api.test.ts && npm run build` from `experiments/st-johns-weather-map/web`.
- [ ] 4.3 Run the fixture-backed Chromium procedure with a fixed clock and confirm zero live-provider requests, all controls keyboard-reachable, inspector focus entry/return, and identical visual/text absence reasons; record browser coordinates and results in the issue without claiming a screen-reader pass.
- [ ] 4.4 Run `npx -y @fission-ai/openspec@latest validate desktop-evidence-workbench --strict` from `experiments/st-johns-weather-map` and `uv run --project tools/specs python tools/specs/specctl.py validate` from the repository root before implementation handoff.
