# Sources keyboard and accessibility-tree audit

2026-09-05; read-only experiment audit for Wayfinder69. URLs localhost5202/sources.html?variant=A|B|C, branch prototype/sources. Chromium via Playwright (installed repository package), viewport1512x1000 and900x800. Keyboard events and DOM/ARIA snapshots, not a screen-reader or assistive-technology pass. No repository edits, no API writes. Captured API data only; unavailable-state control exercised. GOV-SPEC-001/002/004/005 apply to experiment evidence, not a conformance claim.

## Findings

1. High: arrow shortcut prevents horizontal keyboard scrolling of the source ledger. At viewport900x800, A `.table-wrap` has clientWidth762/scrollWidth1128. Focus the region and press ArrowRight. Expected scrollable table navigation; observed variant changes A→B and activeElement becomes BODY. The global key handler exempts controls but not the focusable region. AX: `region "Source ledger, scroll for all columns"` containing labelled table. Same pattern applies to B's focusable matrix region by code inspection, but A is the exercised reproduction. Remedy: scope prototype shortcut to explicit switcher or exempt scrollable regions; preserve keyboard scrolling.

2. High: source inspection opens without keyboard entry or an announced relationship. A first `[data-inspect="eccc-hrdps"]`, focus then Enter: inspector visible, focus remains source button; next Tab is `summary MSC Open Data licence`. Reaching `#close-inspector` requires238 successive Tabs from the first opener with the full118-source ledger. Opener lacks aria-controls/aria-expanded and inspector heading receives no focus. AX: `button "Inspect HRDPS raw"`; inspector is `complementary "Docked provenance inspector"`, with separate `heading "HRDPS raw"`. This is a docked nonmodal panel, so modal trapping is not requested; a direct entry/return pattern is needed. Escape did not close panel (observed, not independently classified as failure because Escape contract not established).

3. Medium: close restoration fails if selected source is no longer visible. Open first source; fill `#search` with `no match qwerty`; focus Close and press Enter. Inspector hides, but activeElement remains `button#close-inspector` inside the hidden aside; next Tab jumps to `select#instant` in footer instead of a meaningful visible fallback. Handler tries `#heading.focus()` but h1 has no tabindex. AX after filtering exposes `status: 0 of118 catalogue sources...` and empty-result instructions; no remaining source opener exists. Remedy: give a deliberate visible fallback (heading/search/filtered-results control), focus it successfully.

4. Lower/design gap: source buttons' computed names omit source ID and evidence class. First ledger AX is `button "Inspect HRDPS raw"` with nested `img "Evidence class not supplied"`, strong HRDPS raw, text eccc-hrdps. `aria-label="Inspect [product]"` overrides descendant text in the control name. Evidence class and ID are present in browse-tree descendants and inspector, so this is not total semantic loss. Keyboard focus alone does not expose the shared source/class distinction; decide whether adding those facts to name/description is required for production pattern. Captured catalogue has unknown classes; no generated or positive per-value case was validated here.

## Passed cases

- Initial AX has Skip to Sources link; main has tabindex-1 and source ledger caption, column scope and row scope are present.
- Location, theme, vision, evidence mode, family, registry, search, evidence filter, shared instant, and time slider have explicit accessible names. Range supplies aria-valuetext with timestamp rather than only numeric position.
- Source button activates with Enter; native licence/details summaries are keyboard reachable.
- Inspector close returns focus to original source button when it still exists.
- Family finder tile activates with Enter, changes selected family to air_quality, and deliberately focuses #family. Matrix family buttons expose aria-pressed; storage symbols are aria-hidden with equivalent stored/not-mapped text.
- Data banner and result count use role=status. Selecting unavailable state clears source rows, exposes explicit unavailable catalog/status/timeline/layers, and does not silently substitute saved evidence. Live network completion announcement not exercised.
- Coverage lanes provide native exact-times details as a textual alternative to visual marks; full catalogue remains exposed. Raw timestamps are available inside details (usability of long JSON not accepted as full accessible visualization validation).
- Source dots are aria-hidden and source IDs remain textual in AX; unknown evidence glyph has explicit image name, freshness/absence are visible text.

Artifacts: /tmp/sources-ax-A.txt, /tmp/sources-ax-C.txt; /tmp/sources-audit.cjs and /tmp/sources-audit2.cjs. No actual screen-reader, physical mobile, reduced-motion, contrast or all-key/all-source coverage claim.
