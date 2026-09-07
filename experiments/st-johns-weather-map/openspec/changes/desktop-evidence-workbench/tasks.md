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

## 5. Complete the selected view bodies

- [ ] 5.1 Implement Series Overview and temporary Compare using the approved bounded API interactions; verify native sparse times, compatible/incompatible axes, unsampled versus checked gaps, and Focus/selection continuity with fixed responses.
- [ ] 5.2 Implement Sky Horizon instrument; verify registered/unsurveyed versus arbitrary-point horizons, scalar cloud gauges, missing directional geometry, Kp/outlook separation and explicit camera absence.
- [ ] 5.3 Implement Activity Operational stack using the owning server verdict contract; verify four lanes, one inline expansion, hard-stop ordering, coverage/withholding, provenance and Saved stack absence. Do not implement client scoring.
- [ ] 5.4 Implement Sources Ledger, Family finder and Coverage lanes; verify filters and inspector survive switching, declarations never imply retrieved coverage, and unmapped/unknown/expired evidence stays inspectable.
- [ ] 5.5 Apply canonical #41 tokens across all five views; verify stable provider slots, red-on-black night, non-colour state distinctions and reduced motion.
- [ ] 5.6 Demonstrate all five selected view bodies with fixed-clock browser fixtures, shared Focus and provenance, failure/absence states and keyboard entry/return. Record unavailable backend capabilities separately; do not close full-view obligations on shell-only evidence.
