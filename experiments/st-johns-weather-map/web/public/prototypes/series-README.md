# Series view prototype

Experiment for [Design the Series view](https://github.com/TusharSariya/Astraeus/issues/50), part of the [front-end Wayfinder map](https://github.com/TusharSariya/Astraeus/issues/38). Owner selected A and B as complementary Series modes. C remains an archived alternative.

Run from this directory:

```sh
python3 serve.py
```

Open <http://localhost:5199/series.html?variant=A>. The existing prototype server can be reused if port 5199 is occupied.

Compare three structures using the variant switcher:

- A: stacked field-family charts.
- B: a single-field workbench.
- C: an instant-first comparison ledger.

All variants build on `tokens.json`, variant C Hyperlegible, with provider colours, model line styles, and the settled light, dark, and red night themes.

## Evidence

`series-captures.json` contains retrieved API responses, with capture time, Focus, and request information. `series-data-notes.md` records the observed API limitations. Captured responses are historical evidence, not a claim of current conditions.

The constructed comparison case exists to judge observations, ensembles, provider reductions, and absence states that the live API cannot currently supply together. It is design test data and cannot establish provider capability or forecast quality.

## Owner decision

Keep both A and B:

- **A — Overview:** separate, time-aligned field tracks for scanning the selected data.
- **B — Compare:** a temporary comparison workspace for selecting fields and sources together. Compatible quantities may share an axis; different units or incompatible meanings retain separate aligned axes.
- Both modes retain the same Focus, instant, selections and provenance when switching.
- Comparison selections live in memory for the current page only. No save, restore, shared workspace link, server persistence or scoring is introduced. Reload starts with the defaults. The layout URL parameter identifies the historical prototype variant, not a saved comparison.
- “Comparison workspace” names this exploratory selection; activity profiles keep their existing grading and verdict meaning.

The owner first requested both modes, then explicitly answered “temporary for now” when asked about saving/sharing. This settles the design ticket; production implementation still goes through the map's API/specification handoff gates.

The HTML preserves the three original layout studies as evidence. Its B variant is a single-field exploration with source overlays; it does not implement the entire selected multi-field comparison workspace.

## Review evidence

 Check whether you can compare sources without losing the shared instant, distinguish raw members from provider reductions, identify why a value is absent, and reach the provenance behind a plotted value. The separate outdoor night-theme ticket still needs the owner's device observations.

Spec-Impact: none. This is a throwaway experiment outside the production path; it does not authorize API behavior, scientific rules, or specification status changes. Any selected design must pass the map's specification handoff gates before production implementation.


## Accessibility repair experiment — September 5, 2026

The owner selected the shared evidence-accessibility contract after the issue 69
browser audit. This isolated repair retains Overview A and temporary Compare B;
it does not promote a production implementation or normative specification.

- Explicit reading/chart inspection focuses the named nonmodal inspector heading.
  Close, or Escape from within the inspector, returns to the exact opener or its
  replacement logical control. If it no longer exists, the Series heading is a
  visible focusable fallback. Inspection retains the exact selected evidence
  object if the view changes; its evidence time and opening Focus remain visible.
- Field controls retain logical focus and pressed state after rerendering.
  Native selects and the timestamp slider retain their keyboard behavior.
- Chart marks use native HTML buttons within SVG foreignObject, including native
  Enter and Space. Their name identifies field, source and value; descriptions
  expose class, valid time, freshness and absence. The same evidence identity is
  available in ledger rows and table Inspect actions.
- Each chart has a native sample-table disclosure with actual sampled timestamps,
  sources, values and gaps. Missing returned fields are labelled as such and their
  sampled response can be inspected. Unqueried intervals are not fabricated as
  gaps. Constructed examples remain explicitly constructed.
- Prototype alternatives use explicit buttons; global arrow interception was
  removed. A concise status region reports selected field/time and reading count.
  This does not establish actual spoken-announcement quality.

Run the prototype with `PORT=5211 python3 serve.py` from this directory, then open
`http://localhost:5211/series.html?variant=A` (or `B`). From this directory run:

```sh
node check-series-accessibility.cjs
```

Set `PLAYWRIGHT_MODULE` to an installed Playwright module if this isolated
worktree has no `web/node_modules`; set `PROTOTYPE_ORIGIN` for another port.
The check exercises both native activation keys, heading entry, Close/Escape
return, field-focus retention, slider behavior, semantic sample/gap actions and
fallback when an opener disappears. It captures temporary AX/screenshot evidence
under `/tmp`. Chromium keyboard checks passed; these tests sometimes focus the
target programmatically to isolate behavior. VoiceOver/NVDA and a complete
sequential-keyboard journey remain unverified. SVG foreignObject needs checking
in the chosen browser/reader pairing; the HTML table provides a separate path.

Verification: Chromium script passed; `specctl validate` returned 0 errors and
0 warnings; `git diff --check` passed. No new numeric data or statistics.

Classification: Experiment.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005.
