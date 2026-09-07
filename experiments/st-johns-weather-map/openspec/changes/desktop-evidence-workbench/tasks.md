Accepted for implementation: see [owner authorization](acceptance.md).
Contract acceptance does not check off implementation tasks.

## 1. Shared Focus and shell

- [x] 1.1 Add `web/src/workbench/focusUrl.ts` to parse and serialize site or point, fixed/live instant, active view, dock, and ordered stack; verify invalid, round-trip, omitted-live-time, and fixed-clock cases with `npm test -- --run src/workbench/focusUrl.test.ts`.
- [x] 1.2 Add `web/src/workbench/WorkbenchShell.tsx`, `FocusBar.tsx`, and the embedded semantic view rail with one stage, at most one right dock, full-screen return, data-mode banner, and bottom timeline; verify semantic controls and shared Focus with `npm test -- --run src/workbench/WorkbenchShell.test.tsx`.
- [x] 1.3 Route every existing usable response-backed panel through the shell and add honest unavailable bodies only for absent view capabilities; verify retained panel access and absence wording with `npm test -- --run src/workbench/WorkbenchShell.test.tsx`.

## 2. Map stack

- [x] 2.1 Add `web/src/workbench/MapStack.tsx` and mount the existing `MapPanel` imagery pipeline in the stage; verify top-first order, opacity, visibility, absence retention, and URL replacement with `npm test -- --run src/workbench/MapStack.test.tsx src/MapPanel.test.tsx`.
- [x] 2.2 Add the Nowcast built-in and family legend presentation without changing frame requests; verify missing default members remain explicit and no substitute request occurs with `npm test -- --run src/workbench/MapStack.test.tsx src/api.test.ts`.
- [x] 2.3 Add the one-line Map disclosure and complete detail table using returned draw states; verify generated, partial, nothing-drawn, shader failure and bounded exception count with `npm test -- --run src/MapPanel.test.tsx src/workbench/MapEvidenceDetails.test.tsx`. The disclosure lives in the existing `MapPanel.tsx`; no parallel renderer is introduced.

## 3. Shared provenance and accessibility

- [x] 3.1 Implement shared glyph/row/inspector presentation in `web/src/workbench/EvidenceInspector.tsx` and `ReturnedValue.tsx` with response-owned sentences and explicit missing-property states; verify retrieved, generated, null, blocked, aged-out, refused, and unknown-class fixtures with `npm test -- --run src/workbench/EvidenceInspector.test.tsx`.
- [x] 3.2 Preserve opener and logical focus through inspector open, Close, scoped Escape, rerender, and opener removal; verify keyboard behavior with `npm test -- --run src/workbench/inspectorReturn.test.tsx src/workbench/WorkbenchShell.test.tsx`.
- [x] 3.3 Add Map and timeline semantic alternatives plus concise status announcements; verify accessible names, table content, and live-region updates with `npm test -- --run src/workbench/WorkbenchShell.test.tsx src/workbench/MapStack.test.tsx`.

## 4. Styling and deterministic acceptance

- [x] 4.1 Apply the selected desktop tokens and Bench layout in `web/src/workbench/bench.css`, including visible focus, non-colour state cues, 200% text zoom, dark and red-night themes, and reduced-motion handling; verify Chromium screenshots and keyboard order against fixed fixtures at 1440x900 and 200% zoom.
- [x] 4.2 Run the focused client suite and production build with `npm test -- --run src/workbench src/MapPanel.test.tsx src/api.test.ts && npm run build` from `experiments/st-johns-weather-map/web`.
- [x] 4.3 Run the fixture-backed Chromium procedure with a fixed clock and confirm zero live-provider requests, all controls keyboard-reachable, inspector focus entry/return, and identical visual/text absence reasons; record browser coordinates and results in the issue without claiming a screen-reader pass.
- [x] 4.4 Run `npx -y @fission-ai/openspec@latest validate desktop-evidence-workbench --strict` from `experiments/st-johns-weather-map` and `uv run --project tools/specs python tools/specs/specctl.py validate` from the repository root before implementation handoff.

## 5. Complete the selected view bodies

- [x] 5.1 Implement Series Overview and temporary Compare using the approved bounded API interactions; verify native sparse times, compatible/incompatible axes, unsampled versus checked gaps, and Focus/selection continuity with fixed responses.
- [x] 5.2 Implement Sky Horizon instrument; verify registered/unsurveyed versus arbitrary-point horizons, scalar cloud gauges, missing directional geometry, Kp/outlook separation and explicit camera absence.
- [x] 5.3 Implement Activity Operational stack using the owning server verdict contract; verify four lanes, one inline expansion, hard-stop ordering, coverage/withholding, provenance and Saved stack absence. Do not implement client scoring.
- [x] 5.4 Implement Sources Ledger, Family finder and Coverage lanes; verify filters and inspector survive switching, declarations never imply retrieved coverage, and unmapped/unknown/expired evidence stays inspectable.
- [x] 5.5 Apply canonical #41 tokens across all five views; verify stable provider slots, red-on-black night, non-colour state distinctions and reduced motion.
- [x] 5.6 Demonstrate all five selected view bodies with fixed-clock browser fixtures, shared Focus and provenance, failure/absence states and keyboard entry/return. Record unavailable backend capabilities separately; do not close full-view obligations on shell-only evidence.

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


## September 7 layer identity checkpoint

The API now supplies explicit source/field associations and separate imagery
availability. Sources retains source filters/inspection and presents the joins
without populating point coverage from a declaration. Map names supplied sources
and preserves unknown mappings. See the API implementation evidence for exact
scope, tests and the fixed browser procedure. Task 5.4 remains open only for the
remaining assembled Sources/Series cache scope; no view selection is reopened.


## September 7 supported named-run checkpoint

Task 5.1 is complete for the existing bounded native readers: Overview,
temporary field/source Compare, compatible same-field run overlay, actual
latest/previous selection for HRDPS/RDPS/GDPS, explicit GFS latest-only capability,
URL-scoped pins, native gaps and fixed selection lifetime. Sources without a
native reader remain explicitly unavailable; their integration belongs to the
existing #70 queue. Current image delivery cannot request a named run, so Map
preserves the requested stack with a shared inspector refusal instead of drawing
Latest. See the API implementation evidence and `prove-desktop-runs.mjs` for
verification. Full desktop task 5.6 remains open for Activity, shared inspection,
provider tokens and assembled proof; no source integration issue is closed.


## September 7 Sources finite-selection checkpoint

Task 5.4 is complete for currently returned evidence. Sources now shares only
loaded native Series pages at the exact Focus, separately from point readings,
registry declarations and layer/image metadata. Source/family filters apply to
native rows, including explicitly unknown families. Partial pagination is named;
opening Sources does not fetch pages or renew a cache. Expiry withholds native
values in both Sources and an already-open native value inspector while retaining
selection identity/time bounds and filters. Changing Focus cannot expose the old
selection. The same native chart/table and provenance control are reused.

Verification: 491 full client tests, 33 final focused workbench tests, build,
strict desktop OpenSpec and specctl pass. Fixed Chrome proof
`web/scripts/prove-desktop-source-selection.mjs` verifies native source/value
inspection, view-switch reuse without acquisition, three themes, 200% text zoom,
expiry clearing with an open inspector, preserved filters and no automatic
renewal when returning to Series. Screenshots/receipt:
`/tmp/astraeus-source-selection-proof/` outside Git. Separate main-agent review
retained expired selection identity while removing values/provenance; no
independent-agent or physical accessibility review is claimed.
No API, source adapter, registry status, acquisition or scientific rule changes.
Task 5.6 remains open for Activity, shared Map inspection/tokens and assembled
verification. Source completion still belongs to #70 after the desktop milestone.


## September 7 Map native inspection checkpoint

Actual GeoJSON picks and the semantic feature table share one inspector action.
Returned station properties retain native zero, null, units, QC and geometry;
reference location pickers remain distinct from reports. Image receipts expose
actual frame inputs, returned metadata, method/version and capture identity,
with explicit absence. Actual admitted generated display sets the generated
glyph/label independently of the layer catalogue. No raster pixel becomes a
numeric observation, and no generated picture enters a native value path.

Receipts exclude hidden/zero-opacity layers and failed renderers. Open native
feature inspectors withhold old values when the feature disappears or Focus
changes. Exact Focus identity also prevents retained Map receipts from appearing
at a different location/instant when switching views. The one-line disclosure
uses a bounded exception count; its table exposes all requested layers and actual
times without truncating the reasons.

Verification: 496 full client tests, 71 final focused tests, production build, strict desktop OpenSpec
and specctl; `web/scripts/prove-desktop-map-inspection.mjs` verifies actual feature
inspection, source identity, zero/null, keyboard entry/return and removed-opener
fallback, hide/Focus invalidation, three themes and 200% text zoom. Receipts and
screenshots stay outside Git at `/tmp/astraeus-map-inspection-proof/`. Generated
method/header and shader-failure verification uses fixed component fixtures;
this proof does not claim new live provider retrieval or a live generated raster.
Separate main-agent review corrected hidden/failed draw receipts and preserved
missing version/capture values. Physical screen-reader/outdoor proof, provider
tokens, Activity and the assembled five-view milestone remain open.


## September 7 provider-token checkpoint

The selected #41 C palette now supplies fixed provider slots and source/model
line swatches in Map, native Series, Sources and Sky. Native plot markers use
the same slots without connecting gaps; same-source run overlay retains its
circle/square distinction. Source IDs remain printed in ordinary readable ink;
the colour swatch is redundant. Bindings are the explicit selected prototype
list, copied from `prototype/tokens` commit `58857e38`; unknown/unassigned sources
use Other without inferring a provider from their spelling. Provider PNG legends
and existing scalar-colour calculations are untouched. Evidence glyph colours
use the selected light/dark hues and red-night ink. Timeline UI inherits Next;
times and source tags use Mono, with reduced motion preserved.

497 full client tests, 36 final focused workbench tests, build, strict desktop
OpenSpec and specctl pass. `web/scripts/prove-desktop-provider-tokens.mjs` runs
against a production preview (`npm run build`; `npx vite preview --port 5246`),
asserting loaded Next/Mono fonts, exact palette values in three themes, stable
slots/styles through filtering, unknown Other, native gaps, reduced motion and
200% text zoom. Screenshots/receipt: `/tmp/astraeus-provider-tokens-proof/`.
The development-server proof initially exposed HTTP 403 font requests through
the shared node_modules symlink. Production assets load normally; no server
filesystem allowlist was widened. Earlier development screenshots with fallback
fonts are not evidence of Hyperlegible typography. Map and Sky proofs are rerun
against the production preview; captures remain outside Git.

This completes the shared source-style component, not all of task 5.5: Activity
body/strips and final cross-view token audit remain with the assembled milestone.
No new science, provider acquisition, API or source admission changes. Physical
screen-reader/outdoor verification remains separate.


## Issue #69: direct keyboard access to Map samples

The owner selected the first collaborative repair: a visible “Skip to Map
samples” link at the start of the Map body. It opens the existing disclosure,
focuses its heading and leaves the shared Focus URL unchanged. The next Tab
reaches the first native reading's Inspect action when readings exist. Empty
samples keep their existing explicit absence explanation. This does not inspect
or acquire evidence automatically.

Verification: 9 affected component tests and production build pass. The fixed
Chromium procedure `web/scripts/prove-map-samples-keyboard.mjs` uses keyboard-only
navigation from page entry, including the global skip link, and verifies two
Tabs to the new link, heading focus, unchanged URL, the next reading action,
Enter/Space inspection and Close/Escape return. Captures and receipt remain
outside Git at `/tmp/astraeus-app69-fixed-proof/`. Repository specctl passes.
Separate main-agent review checked that the link is available in stage/dock,
uses the existing focus outline and a 44px target, and does not alter evidence.
This closes only this navigation repair; #69 and the broader accessibility
obligations remain open. No actual screen-reader or outdoor pass is claimed.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006; desktop workbench requirements
“Evidence interactions preserve keyboard context” and “Canvas evidence has a
semantic alternative”.


## Issue #69: readable native Map evidence

The next owner-selected repair presents native Map properties and inspector
metadata as semantic labels and values, with returned properties first. Zero,
false, null, empty text and empty collections remain distinct; provider units
and quality are displayed without inference. Two-coordinate GeoJSON Points name
longitude and latitude; other geometry retains its returned structure. Complete
inspected details remain available in a collapsed JSON disclosure. Raw provider
keys are retained there; visible labels replace underscores with spaces only.
Expired/changed Map evidence removes both readable values and the raw disclosure.
Other evidence views retain their existing rendering in this bounded repair.

Verification: 10 affected component tests and production build pass. The fixed
keyboard browser proof checks structured accessible values, closed raw disclosure
and retained skip/open/close/return behavior. Existing Map inspection proof covers
hide/Focus invalidation, three themes and 200% text zoom. Captures remain outside
Git. Strict desktop OpenSpec and specctl pass. Separate main-agent review checked
zero/null handling, coordinate order, unchanged evidence and removal semantics.
Actual screen-reader testing and broader #69 work remain outstanding.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006; desktop workbench requirements
“Every listed value uses the shared provenance ledger and inspector”, “Evidence
interactions preserve keyboard context” and “Canvas evidence has a semantic
alternative”.


## Issue #69: Sources filter and inspector focus return

The next collaborative check reproduced a lost local return point: filtering
out an inspected Sources reading removed its opener, and Close returned to the
stage root. App now remembers the Sources search control alongside that opener.
Close and scoped Escape first return to an available opener, otherwise to the
still-visible Sources search, otherwise to the existing stage fallback. Other
views do not inherit a previous Sources fallback. Filtering preserves the selected
inspector evidence as required; hiding a row is not evidence expiry.

Verification: 10 affected Sources/inspector/shell component tests and production
build pass. `web/scripts/prove-sources-keyboard.mjs` reproduces the complete flow
using Tab/Shift+Tab, Enter, Escape and search typing: removed opener returns to
search, unchanged opener wins, Focus URL is unchanged and filter interactions
issue no new data requests. Baseline receipt has returnedToSearch=false; repaired
receipt has true, both outside Git. Existing desktop Sources and Map inspection
browser proofs cover perspective changes, themes, zoom and general focus fallback.
Strict desktop OpenSpec, specctl and diff checks pass. A separate main-agent
review checked fallback lifetime and preserved filter/selection behavior.
Actual screen-reader testing remains outstanding; #69 remains open.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006; desktop workbench requirements
“Evidence interactions preserve keyboard context” and “Sources retains all three
selected perspectives”.


## Issue #69: Series selection and expiry focus return

After the Sources repair merged as #292, the next collaborative keyboard check
confirmed that Series already withholds old provenance on selection change but
returns to the stage root after its opener disappears. Series now marks the
persistent Window from Focus control as its local inspector-return fallback.
An available opener still wins; Sources search and the final stage fallback
retain their roles. No scoring, data, request, cache or native-time semantics
change. The window control persists through temporary run comparison.

Verification: 14 affected NativeSeries/inspector/shell tests and production
build pass. `web/scripts/prove-series-keyboard.mjs` uses Tab/Shift+Tab, native
select type-ahead, Enter and Escape to check window replacement, unchanged-opener
return, fixed expiry, old-provenance removal, unchanged Focus URL and exactly two
Series requests (initial plus changed window; expiry does not reacquire).
Baseline returnedToWindow=false; repaired true. Receipts/screenshots stay outside
Git at `/tmp/astraeus-series-keyboard-before/` and
`/tmp/astraeus-series-keyboard-proof/`. The Sources keyboard proof also passes.
Strict desktop OpenSpec, specctl and diff checks pass. Separate main-agent review
checked control lifetime and fallback precedence. Actual screen-reader output
remains untested; #69 remains open.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006; desktop workbench requirements
“Evidence interactions preserve keyboard context” and “Series implements the
selected Overview and temporary Compare”.


## Issue #69: assembled desktop keyboard and inspection batch

Owner direction: merge passing routine repairs autonomously and work in larger
batches. #291/#292/#293 are merged. This batch completes the selected return-focus
mechanics and current fixture-backed browser procedure (tasks 3.2/4.3), not the
unfinished Activity body or all accessibility work.

Repairs: fullscreen keeps the inspector reachable; scoped Escape closes only
inspection, and fullscreen exit returns to the expansion opener. Closing an
inspector that temporarily replaced a dock restores its unique logical reading
control and disclosure; ambiguous/missing controls use the view's local fallback.
Mounted-view focus returns remain immediate; only remounted docks wait for the
render. Sky inspection now resolves from the same current Sky inputs as the view,
including failed/recovered astronomy, registry and planetary evidence. The point
refresh handler only owns point-field inspection. Native/point inspection names
include their time and source; native comparisons also name run and track. Sky
prints evidence class/source alongside geometry and scalar readings. Sources
result counts announce politely. The noninteractive deck overlay leaves the Tab
order while the keyboard MapLibre canvas and semantic sample table remain.

Verification: full client suite 504 passed, including eight GPU shader cases;
production build passed. `web/scripts/prove-desktop-access.mjs` checks all four
implemented views in fullscreen, three restored docks, distinct same-field/time
comparison controls, Sky failure/recovery, three themes, loaded Hyperlegible,
200% text zoom and reduced motion. With fixture disclosures opened as test setup,
actual Tab traversal reaches 100 Map, 55 Series, 61 Sources and 54 Sky controls;
Chromium accessibility trees report no unnamed tested interactive controls.
These counts are fixture-specific, not a claim about every provider catalogue.

Existing Map inspection, Sources keyboard, Series keyboard and assembled Sky
browser regressions also pass against the final production build. Fixed clocks
and explicitly constructed fixtures; provider traffic is blocked. Captures and
receipts remain at `/tmp/astraeus-desktop-access-proof/` and
`/tmp/astraeus-access-*-regression/` outside Git. Review was a separate main-agent
pass. Initial regression failures identified delayed focus return and a startup
request crossing the filter-proof baseline; mounted returns remain synchronous
and the fixed clock settles startup before acquisition-count assertions.

Strict changed OpenSpec and repository specctl pass. No API, science, provider,
cache or registry admission changes. Unknown, absent, expired and failed evidence
retain their meanings. Activity remains explicitly unwired; tasks 5.3/5.5/5.6 and
#69 remain open for their outstanding scope.

Actual screen-reader procedure (not performed): use VoiceOver with Safari or
NVDA with Firefox; record browser/reader versions and verbatim relevant output.
At a fixed fixture Focus, read the evidence table and source/class/value/absence;
open inspection, verify its heading is announced, move to Close and return to the
reading. Repeat after filter removal, native expiry and a dock remount. Verify
source/run/track names distinguish Compare actions, Sources result counts announce
without moving focus, and failed Sky geometry is announced as absence. Record
what was heard separately from the Chromium tree and keyboard receipts. Physical
outdoor/red-night testing remains #65, and Activity gets its own audit when wired.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006; accepted desktop requirements
for shared provenance, keyboard context, semantic alternatives, native Series,
Sky, Sources and the Bench shell.


## September 7 Activity and assembled five-view checkpoint

Activity now uses the server-owned versioned evaluator across all four selected
lanes, one inline expansion, hard stops before grades, native strips, geometry
windows, profile Saved stacks, Series jumps and shared readable inspection.
Overrides remain browser-local unless explicitly shared; invalid replacements,
Focus changes and fixed expiry withhold old scores and provenance. Planning
uses bands and each profile's actual driving-source native cadence. Missing
current evidence retains its fixed profile weight and reduces coverage.

Tasks 3.1/3.3/4.1 reconcile the existing shared implementation and prior keyboard
proofs, rather than requiring redundant files. Tasks 5.3/5.5/5.6 now have body-level
fixed-clock browser evidence across all five views, including Activity entry and
return, fullscreen/dock remount, native holes, three themes, 200% text zoom,
reduced motion, failed replacement and expiry without automatic reacquisition.
The evaluator fixture is generated from actual v2 profiles and synthetic inputs;
external traffic is blocked. This demonstrates the assembled desktop, not every
live provider or an operational safety product.

Verification: 2,251 API tests passed and 53 skipped; 510 client tests passed
(including eight GPU cases), production build and runtime import passed. Both
changed strict OpenSpec packages and repository specctl pass. Browser procedures:
`web/scripts/prove-desktop-activity.mjs` and `prove-desktop-access.mjs`; receipts
and screenshots remain outside Git at `/tmp/astraeus-desktop-activity-proof/`
and `/tmp/activity-desktop-regression/`. Review was a separate main-agent pass.
The API implementation evidence records finite bounds and field dispositions.

Remaining: missing live lightning/rain/CAP point evidence, named replacement
fields, sector queries and Sun azimuth; DE442 requires its configured kernel.
Selected PM2.5 stack membership remains declared/unserved until #172. No new
source admission is claimed. Actual screen-reader testing remains #69 and outdoor
red-night testing #65; camera placement, phone and deferred science remain separate.
The source Wayfinder #70 remains the subsequent queue.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006; accepted Activity verdict
contract and desktop workbench shared Focus/provenance/five-view requirements.
