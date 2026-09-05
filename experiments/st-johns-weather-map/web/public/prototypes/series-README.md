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
