Accepted for implementation: see [owner authorization](acceptance.md).
Contract acceptance does not check off implementation tasks.

## 1. Shared Focus and shell

- [x] 1.1 Add `web/src/workbench/focusUrl.ts` to parse and serialize site or point, fixed/live instant, active view, dock, and ordered stack; verify invalid, round-trip, omitted-live-time, and fixed-clock cases with `npm test -- --run src/workbench/focusUrl.test.ts`.
- [x] 1.2 Add `web/src/workbench/WorkbenchShell.tsx`, `FocusBar.tsx`, and the embedded semantic view rail with one stage, at most one right dock, full-screen return, data-mode banner, and bottom timeline; verify semantic controls and shared Focus with `npm test -- --run src/workbench/WorkbenchShell.test.tsx`.
- [x] 1.3 Route every existing usable response-backed panel through the shell and add honest unavailable bodies only for absent view capabilities; verify retained panel access and absence wording with `npm test -- --run src/workbench/WorkbenchShell.test.tsx`.

## 2. Map stack

- [x] 2.1 Add `web/src/workbench/MapStack.tsx` and mount the existing `MapPanel` imagery pipeline in the stage; verify top-first order, opacity, visibility, absence retention, and URL replacement with `npm test -- --run src/workbench/MapStack.test.tsx src/MapPanel.test.tsx`.
- [x] 2.2 Add the Nowcast built-in and family legend presentation without changing frame requests; verify missing default members remain explicit and no substitute request occurs with `npm test -- --run src/workbench/MapStack.test.tsx src/api.test.ts`.
- [ ] 2.3 Add the one-line Map disclosure and complete detail table using returned draw states; verify generated, partial, nothing-drawn, and truncation cases with `npm test -- --run src/workbench/MapDisclosure.test.tsx`.

## 3. Shared provenance and accessibility

- [ ] 3.1 Add `web/src/workbench/EvidenceGlyph.tsx`, `EvidenceRow.tsx`, and `EvidenceInspector.tsx` with response-owned sentences and explicit missing-property states; verify retrieved, generated, null, blocked, aged-out, refused, and unknown-class fixtures with `npm test -- --run src/workbench/EvidenceInspector.test.tsx`.
- [ ] 3.2 Preserve opener and logical focus through inspector open, Close, scoped Escape, rerender, and opener removal; verify keyboard behavior with `npm test -- --run src/workbench/evidenceFocus.test.tsx`.
- [ ] 3.3 Add Map and timeline semantic alternatives plus concise status announcements; verify accessible names, table content, and live-region updates with `npm test -- --run src/workbench/WorkbenchShell.test.tsx src/workbench/MapStack.test.tsx`.

## 4. Styling and deterministic acceptance

- [ ] 4.1 Apply the selected desktop tokens and Bench layout in `web/src/styles.css`, including visible focus, non-colour state cues, 200% text zoom, dark and red-night themes, and reduced-motion handling; verify Chromium screenshots and keyboard order against fixed fixtures at 1440x900 and 200% zoom.
- [x] 4.2 Run the focused client suite and production build with `npm test -- --run src/workbench src/MapPanel.test.tsx src/api.test.ts && npm run build` from `experiments/st-johns-weather-map/web`.
- [ ] 4.3 Run the fixture-backed Chromium procedure with a fixed clock and confirm zero live-provider requests, all controls keyboard-reachable, inspector focus entry/return, and identical visual/text absence reasons; record browser coordinates and results in the issue without claiming a screen-reader pass.
- [x] 4.4 Run `npx -y @fission-ai/openspec@latest validate desktop-evidence-workbench --strict` from `experiments/st-johns-weather-map` and `uv run --project tools/specs python tools/specs/specctl.py validate` from the repository root before implementation handoff.

## 5. Complete the selected view bodies

- [ ] 5.1 Implement Series Overview and temporary Compare using the approved bounded API interactions; verify native sparse times, compatible/incompatible axes, unsampled versus checked gaps, and Focus/selection continuity with fixed responses.
- [x] 5.2 Implement Sky Horizon instrument; verify registered/unsurveyed versus arbitrary-point horizons, scalar cloud gauges, missing directional geometry, Kp/outlook separation and explicit camera absence.
- [ ] 5.3 Implement Activity Operational stack using the owning server verdict contract; verify four lanes, one inline expansion, hard-stop ordering, coverage/withholding, provenance and Saved stack absence. Do not implement client scoring.
- [ ] 5.4 Implement Sources Ledger, Family finder and Coverage lanes; verify filters and inspector survive switching, declarations never imply retrieved coverage, and unmapped/unknown/expired evidence stays inspectable.
- [ ] 5.5 Apply canonical #41 tokens across all five views; verify stable provider slots, red-on-black night, non-colour state distinctions and reduced motion.
- [ ] 5.6 Demonstrate all five selected view bodies with fixed-clock browser fixtures, shared Focus and provenance, failure/absence states and keyboard entry/return. Record unavailable backend capabilities separately; do not close full-view obligations on shell-only evidence.

## September 7 Bench implementation checkpoint

The first implementation introduces the shared shell, precise URL state,
versioned registered sites and explicit site adoption, ordered Map controls,
Saved stacks, an actual-draw disclosure, native-value ledger and inspector.
The previous panels remain reachable. Registered-site reads use the existing
site audit and preserve the unsurveyed geometry note. No camera route is added.

Verification: final client suite 467 passed, including actual raster reorder. Two API
registry endpoint cases passed. Build, both changed strict OpenSpec packages and specctl
passed. `node scripts/prove-desktop-bench.mjs` from `web` exercises the real browser against fixed
responses, with external requests blocked. Receipt and screenshots are outside
Git at `/tmp/astraeus-bench-proof/`.

Remaining: full five-view bodies and bounded Series/run/change-check API;
complete family-grouped stack/station/sample inspection and provider palettes;
complete fixed-clock keyboard coverage and screen-reader/outdoor evidence.
The Map renderer, native times and source-specific display restrictions are
retained. This checkpoint does not complete the desktop milestone or #38/#55.

## September 7 native Series checkpoint

The initial native API and two-track Overview/temporary Compare are implemented
with stable cursor pages, selection-specific change checks, explicit refresh and
five-minute expiry. Switching display or stage/dock preserves the same selection.
See [implementation evidence](../desktop-evidence-api-contract/implementation-evidence.md).
Task 5.1 stays open for the full source/run workspace; task 5.6 stays open for
the complete desktop. No other view or source is completed by this slice.

## September 7 Sources and Map-family checkpoint

`SourcesView.tsx` adds Ledger, Family finder and Coverage lanes using the existing
catalogue, acquisition status, current point fields and separate layer records.
App owns its filters, perspective and selected source across stage/dock switches.
A declaration/retrieval timestamp cannot populate a native coverage lane; sparse
returned values and absences retain timestamps and shared inspection. Missing
layer joins remain inspectable and explicitly unmapped.

Map family legends now live with the ordered stack, once per family with separate
provider scales/definitions. The compact Map no longer repeats the floating
legend. Drawn-frame runs are read from the matching frame identity and are distinct
from the newest run in the index. The value inspector shows returned sampled-cell
geometry and distinguishes same-field readings by native time, run and report.

Verification: full client suite 478 passed, build passed;
`node scripts/prove-desktop-sources.mjs` passed in Chrome with fixed responses and
clock and all external requests blocked. The proof covers Sources filters and
inspector persistence, declaration-only empty coverage, native zero/absence,
three themes, and scoped Escape returning to a logical fallback after its opener
is removed. Screenshots and receipt are outside Git at `/tmp/astraeus-sources-proof/`.
No provider-live, screen-reader or outdoor proof is claimed.

Still open: explicit API layer/source-field joins and imagery availability;
complete station/generated-display inspection and stable provider palettes;
Series run/native-reader residuals and the assembled Sources/Series cache view;
Sky and Activity. Task 5.4 remains open for that assembled source-evidence scope,
not because the three perspectives need another owner selection.


## September 7 Sky Horizon checkpoint

Sky now presents registered horizon samples with their unsurveyed/terrain-check
basis, independent scalar cloud-layer gauges, returned astronomy intervals and
altitudes, separate observed Kp and outlook, and native solar-wind measurements.
No azimuth or horizon-adjusted event is invented. Arbitrary points have no
borrowed polygon; unavailable ephemeris values are null, never a zero-altitude
or zero-illumination assertion. Camera eligibility comes from an allowlisted,
versioned read-only registry response; no endpoint, private terms, image or
Focus-to-camera association is supplied.

Exact Focus coordinates and milliseconds drive astronomy and point reads.
Old point/astronomy/space-weather responses are withheld across Focus changes;
playback does not create repeated point or native Series selections. Pausing
reads the exact selected instant. These fixes preserve the finite Series cache.

Verification: 483 client tests, production build, 77 affected API tests pass.
Six existing astronomy geometry tests skip because the checkout has no DE442
kernel; no new ephemeris calculation or live astronomical proof is claimed.
`node scripts/prove-desktop-sky.mjs` uses fixed, explicitly constructed geometry
responses and blocks external traffic. It covers arbitrary/registered horizons,
native cloud zero, missing directions, camera ineligibility, exact-time requests,
failed geometry clearing and three themes. Screenshots and receipt remain at
`/tmp/astraeus-sky-proof/`. Review is a separate main-agent pass.
Activity, assembled desktop/keyboard proof, source/run residuals, provider tokens
and the API layer joins remain open. Screen-reader and outdoor checks are separate.
