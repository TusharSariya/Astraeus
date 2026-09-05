# Keyboard and evidence accessibility audit

For [Validate keyboard and screen-reader access to evidence controls](https://github.com/TusharSariya/Astraeus/issues/69). Result: **baseline defects repaired in isolated prototypes and browser keyboard rechecks passed; actual screen-reader verification remains pending**. This is experimental design evidence and implementation handoff, not WCAG certification or a normative status transition.

## Scope and method

Tested September 5, 2026 with Playwright Chromium (main run: 151.0.7922.34), native keyboard events and browser accessibility snapshots. Some reproductions programmatically focus the target to isolate its activation behavior; this is not a claim that the entire journey was completed using sequential Tab. Sources inspector reachability was additionally measured by sequential Tab. Main Map skip-link navigation began with Tab from page load.

| Selected study | Artifact | Tested URL |
| --- | --- | --- |
| Layer-led station/point Map | `prototype/station-points` at `f5a602e` | http://localhost:5203/map.html?stationStudy=1&variant=A |
| Series Overview and Compare | `prototype/series` at `d81be17` | http://localhost:5205/series.html?variant=A and B |
| Sky Horizon instrument | `prototype/sky` at `4125ea1` | http://localhost:5206/sky.html?variant=A |
| Sources Ledger, Family finder, Coverage lanes | `prototype/sources` at `7127d64` | http://localhost:5202/sources.html?variant=A, B and C |

The initial audit did not modify prototype sources. Owner-authorized repairs and their rechecks are recorded below. Map coverage here is the selected non-raster study; the original raster route was only inspected during initial loading and is not counted as a complete keyboard test. Activity's canvas and the assembled production shell were not browser-tested. VoiceOver, NVDA, JAWS, touch readers, outdoor night use and physical-device verification were not run.

## Reproduced findings

| ID | Priority | Evidence and user consequence |
| --- | --- | --- |
| A11Y-01 | High | Station Map: focus GFS layer button, Enter; 12 readings appear but active element becomes BODY. Space on its checkbox changes state then also loses focus. Enter on Move up reorders the layer then loses focus. Series B field selection similarly rebuilds the focused button and drops focus. Repeated keyboard operations lose their location |
| A11Y-02 | High | Explicit provenance opening lacks a useful focus path. Station reading Enter opens inspector but focus becomes BODY; next Tab reaches Full provenance instead of inspector. Series/Sky keep focus behind and their Close leaves focus on a hidden button. Sources first source Enter leaves the opener focused; 238 Tabs were needed to reach inspector Close in the tested full catalogue |
| A11Y-03 | High | Sources: after opening an inspector then filtering its source out, Close attempts to focus a nonfocusable heading; active focus remains on hidden Close. Station close returns to generic layer Inspect, not necessarily the actual reading that opened it |
| A11Y-04 | Medium | Names do not consistently identify the target. Station has eight buttons named only Inspect; Series has repeated Inspect field buttons. Chart marks name source/value/unit/time but omit the field/class/freshness; surrounding ledger evidence contains more context. Sources product-button names omit source id/class although descendants retain them |
| A11Y-05 | Medium | Series SVG marks expose role=button and Enter activation, but Space does not activate. This is inconsistent with native button convention; Enter provides a keyboard path, so this finding alone is not a claim that all keyboard operation is absent |
| A11Y-06 | Prototype shortcut hazard | Sources horizontally scrollable ledger: ArrowRight switches to another variant and focus becomes BODY. Sky: ArrowRight on an Inspect button switches variant and loses focus. These are prototype-switcher shortcuts, not approved product navigation. Do not carry them into the product |
| A11Y-07 | Incomplete alternative | The isolated station Map has no coordinate-entry inputs, so its arbitrary-point map-click operation has no demonstrated keyboard equivalent on that route. The original shell has coordinate controls, but an assembled keyboard path still needs validation |

Reproduction/source anchors: station `station-study.js:39,92–95`; Series `series.html:78–90`; Sky `sky.js:64,92–94`; [Sources detailed audit](evidence-accessibility/sources-audit.md). These are pinned prototype artifacts, not line references to a future product implementation.

## Positive evidence

- Station skip link receives initial Tab and moves focus to `main` on Enter.
- Native station checkbox and reorder actions change their intended state; their defect is focus loss after rendering. Native Location select arrow keys do not change study variant.
- Station reading accessibility name includes `retrieved cloud middle 0 % noaa-gfs stale … Valid …`. Numeric zero remains explicit and distinguishable from unavailable text. Unknown class is labelled as not supplied.
- Series ledger and Sky evidence buttons expose class/source and absence reasons. Series time slider updates its timestamp and `aria-valuetext` while preserving the chosen variant.
- Sky Kp native disclosure opens with Enter and exposes a semantic nine-row UTC/Kp/Status table.
- Sources filters and time slider are labelled; family keyboard selection and native details work. Result/banner status regions exist; restoration to an opener that remains visible works.
- Stylesheets contain visible-focus treatments. This is not a full contrast, clipping or screen-reader announcement pass.

## Owner-selected shared interaction contract

The owner approved this contract and prototype repairs with “yes as subagents” on September 5, 2026. This selects experimental design behavior; it does not promote normative specifications.

1. Explicit Inspect activation moves focus to the docked inspector's named heading or first appropriate control. The inspector remains nonmodal: normal navigation can return to the rest of the view. Close, and Escape while focus is within that inspector, restore the actual opener; if it disappeared, use a visible focusable fallback in its original view. Do not apply a page-wide Escape handler that conflicts with existing fullscreen or native controls.
2. Changing a layer, field, checkbox or order retains focus on the corresponding logical control after rendering. Expose selected/expanded state where meaningful, and give repeated actions target-specific names. A chart button gets the same relevant evidence identity as its corresponding row, without duplicating every detail into an enormous label.
3. Keep a semantic row/table alternative for chart samples and gaps, with an inspection action for each reading. Use native button behavior for actions; chart shortcuts must not steal native select, slider or scrolling keys. Coordinate controls provide the equivalent of map-click Focus placement.
4. Announce concise completion, result-count, absence and error changes where they otherwise occur without focus movement. Avoid re-announcing the entire catalogue/inspector on every update. Marked live regions alone do not prove useful spoken behavior.

## Prototype repairs and browser recheck

Three subagents repaired Sources, Series and Sky while the main agent repaired the station Map, each in an isolated worktree. All four repair branches are published:

| Study | Repair artifact | Passing browser checks |
| --- | --- | --- |
| Station Map | [c3222bc](https://github.com/TusharSariya/Astraeus/commit/c3222bc), `prototype/a11y-station`, localhost:5213 | Rerender focus, layer state/order, named inspection, actual opener/fallback, keyboard coordinate entry, zero/absence, native keys, narrow viewport |
| Sources | [45909aa](https://github.com/TusharSariya/Astraeus/commit/45909aa), `prototype/a11y-sources`, localhost:5210 | Rerender and filtered-opener fallback, scoped Escape, horizontal scrolling, refresh failure focus, names/status |
| Series | [1a870db](https://github.com/TusharSariya/Astraeus/commit/1a870db), `prototype/a11y-series`, localhost:5211 | A/B field and time controls, native chart buttons, semantic sample/gap table, inspector restoration and disappeared-opener fallback |
| Sky | [1dc8364](https://github.com/TusharSariya/Astraeus/commit/1dc8364), `prototype/a11y-sky`, localhost:5212 | Inspector entry/return, nonmodal navigation, scoped Escape, native arrow behavior, night-theme focus, nine-row Kp table |

An independent [cross-view recheck](evidence-accessibility/repair-recheck.cjs) passed Enter and Space opening, inspector heading focus, scoped Escape and Close returning to the actual opener for all four repaired artifacts. Per-study scripts are included in the Station, Sources and Series repair commits. JavaScript syntax, diff checks and specctl validation passed in all four worktrees (zero spec errors/warnings).

These are browser keyboard checks, not spoken-output tests. Series native buttons inside SVG foreignObject still need reader/browser verification; the HTML table supplies an independent sample/gap inspection path. Station coordinate entry preserves typed precision but retains the study's existing geographic bounds; it does not resolve the API bounds mismatch. Captured weather evidence and scientific calculations were not changed. The original raster route, Activity canvas, assembled production shell, full contrast/zoom coverage and physical-device behavior remain outside this recheck.

## Actual screen-reader procedure still required

Use a recorded browser/reader/OS pairing on the built or corrected artifact. This is a proposed manual procedure, not performed evidence:

1. Navigate by landmarks/headings and reach a view without traversing every catalogue row. Verify visible keyboard focus throughout.
2. Inspect one retrieved zero, one derived reading and one explicit absence. Confirm spoken field, units, source, evidence class and status distinguish them; inspect full provenance without losing the origin.
3. Open/close inspector from a reading, chart and source. Filter the opener away before closing. Confirm the focus fallback remains usable and is announced meaningfully.
4. Change time, field, source filter, layer state/order and comparison mode. Verify control state and concise changes are conveyed without repeated speech or focus loss.
5. Read a chart via the row/table alternative, including a gap; distinguish unqueried intervals from evaluated absence.
6. Enter an arbitrary coordinate through keyboard controls and exercise an explicit geographic refusal separately from an API/network error. Old readings must not be spoken as the new Focus's evidence.
7. Record actual utterances, steps, success/failure and artifact commit. Repeat after fixes; do not infer a pass from this browser audit.

The outdoor red-night task remains separate. The issue stays open for actual reader verification; no incomplete checks are marked passed.

## Standards used to interpret findings

Pointer operations need a usable keyboard equivalent; Enter-only custom activation is therefore distinguished here from complete keyboard inaccessibility. See [W3C Keyboard guidance](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html).

Focus order must support meaningful operation, and controls need programmatically determinable identity/state. The inspector and rerender findings are assessed against [W3C Focus Order](https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html) and [Name, Role, Value](https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html).

Status updates need appropriate programmatic exposure when they do not take focus; actual announcement quality still needs reader testing. See [W3C Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html). These Understanding documents are explanatory guidance, not an independent certification.

## Reproduction artifacts and validation

[Station script](evidence-accessibility/station-audit.cjs), [station observations](evidence-accessibility/station-results.json), [Series/Sky script](evidence-accessibility/series-sky-audit.cjs), [follow-up script](evidence-accessibility/series-sky-followup.cjs), and [Sources detailed findings](evidence-accessibility/sources-audit.md). Scripts use this workspace's installed Playwright and running prototype servers; temporary screenshot paths are inspection aids, not required handoff assets.

Classification: no spec impact. Documentation/reproduction artifacts only; no product or normative status change. Specctl validation is required before handoff. Baseline browser checks found the failures above; the separate repaired-prototype recheck passed its bounded assertions. No overall accessibility conformance is claimed.
