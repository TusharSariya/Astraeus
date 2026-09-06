Owned: `web/src/api.ts`, `web/src/types.ts`, `web/src/MapPanel.tsx`,
`web/src/App.tsx`, `web/src/TimelineDock.tsx` (new), `web/src/StoryFlyout.tsx`
(new), `web/src/styles.css`, `web/src/api.test.ts`, `web/src/MapPanel.test.tsx`,
`web/src/App.test.tsx`, `openspec/config.yaml` (context wording only).
Not touched: `api/`, `ingest/`, `registry/`, `compose.yaml`, `docs/specv1`.

## 1. Frame resolution (pure)

- [x] 1.1 `previousFrame`/`nextFrame` and `resolveLayerFrame` in `api.ts`
      returning `exact | snapped | blend | none` per the group rules
      (observed previous-only, never past the session reference; forecast
      nearest; blend only when interpolate && forecast && strictly between
      two frames), plus `drawableFrames` and `describeResolution`.
      Verify: `cd web && npm test -- --run src/api.test.ts`
- [x] 1.2 `unionFrameInstants` and `snapInstant` (nearest, ties earlier,
      identity on empty), tested with a session reference carrying nonzero
      seconds so exact frame instants survive.
      Verify: `cd web && npm test -- --run src/api.test.ts`
- [x] 1.3 Sanity check, no code: the client only requests instants taken
      verbatim from `layer.times`, which server nearest-within-tolerance
      matching (grids.py, satellite.py, GeoMet TimeExtent.nearest) answers
      exactly, so no API change is needed.
      Verify: `cd api && uv run pytest tests/test_api.py -q`

## 2. MapPanel: fallback drawing, blend slots, corner notes

- [x] 2.1 MapPanel consumes `resolveLayerFrame` (new `interpolate` and
      `reference` props); raster state becomes slot-based; blend pairs fetch
      together and commit atomically, falling back to the nearer single
      frame at full opacity when one slot fails; per-frame image reuse keyed
      by layer + frame + extent.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`
- [x] 2.2 `.map-frame-notes` corner block (role=status), one note per
      snapped/blended/none active layer, with the same sentences in the
      text alternative and drawer rows; drawer keeps the jump button for
      `none`.
      Verify: `cd web && npm test -- --run src/MapPanel.test.tsx`

## 3. App: exact instants, snapping, interpolation toggle

- [x] 3.1 Selected time becomes an exact instant; scrubber, quick jumps,
      story cards and `jumpToTime` route through one snapping selector;
      keyboard arrows move across the union when snapping; aria-valuetext
      names the real instant.
      Verify: `cd web && npm test -- --run src/App.test.tsx`
- [x] 3.2 Interpolation toggle in the dock, default off, persisted,
      display-only wording; passed to both MapPanel instances.
      Verify: `cd web && npm test -- --run src/App.test.tsx`

## 4. Layout

- [x] 4.1 Extract `TimelineDock` and `StoryFlyout`; simple mode becomes the
      100dvh shell (explicit rows for banner/masthead/workspace; map stage +
      right conditions strip + bottom dock; flyout over the map with Escape
      and focus return); expert mode unchanged; responsive fallback below
      900 px.
      Verify: `cd web && npm test -- --run && npm run build`
- [x] 4.2 Browser pass in both themes at 700/900/1050+ widths, in loading,
      unavailable and live states; expert-mode regression check.
      Verify: `make up` then manual checklist in the change proposal
      Status 2026-08-31: verified live at desktop width in both themes and in
      expert mode (snapping, fallback note, display composite, story flyout
      all exercised in the browser); the 700/900 px passes remain to be run.
      Status 2026-09-02: 700 px and 900 px run against the stack already up
      (web on 127.0.0.1:5173), in Chrome, in both themes, in the loading,
      unavailable and live states, plus the expert-mode regression check.
      The viewport was established with a same-origin 700/900 px iframe of the
      app, because the window-resize path left the layout viewport at 1728 px
      (the automated tab renders hidden and does not reflow); media queries,
      `innerWidth` and layout inside the iframe are the real narrow ones.
      Verify result: FAILED at both widths, in both themes, in every state.
      One defect, everything else passed.

      FAILURE - the scrubber axis labels overlap. At 700 px the marks
      `-3h (Past)` (x 27-87), `-1h` (x 66-84) and `Now (0h)` (x 75-123) sit on
      one row and overlap each other: `-1h` is drawn entirely inside
      `-3h (Past)`, and `Now (0h)` starts 12 px before `-3h (Past)` ends. At
      900 px it is smaller but still present: `-3h (Past)` 27-87 against `-1h`
      81-99, and `-1h` 81-99 against `Now (0h)` 97-145. Both themes, and in
      loading, unavailable and live alike, so it is pure layout. The cause is
      width of the rail, not the breakpoint: the same collision reproduces at
      a 1200 px viewport, where the right conditions strip leaves the rail
      ~860 px wide, and it disappears around a ~1150 px rail - which is why
      the 2026-08-31 desktop pass did not see it. The first three marks are
      1 h and 3 h apart on a 27 h axis, so they are ~3.7% of the rail apart
      while `-3h (Past)` alone is 60 px wide. Not fixed in this session by
      instruction; reported for the owner.

      Passed at 700 px and 900 px, both themes:
      - No horizontal overflow at any width, theme or state
        (`scrollWidth === clientWidth` throughout).
      - Responsive fallback is active at both (the `max-width: 900px` query
        matches at exactly 900): the shell stacks, map pane 700x570 / 900x570,
        timeline dock immediately under it (700: 662-914; 900: 648-867), so
        map and timeline are visible together inside a 950 px viewport
        without scrolling; the conditions strip scrolls below.
      - Interpolation toggle present and default off, wording
        "Interpolate forecast · display only".
      - Story flyout opens from the dock, takes focus, closes on Escape, and
        returns focus to its toggle - verified at 700 px in both themes.
      - Loading state (a delayed `/point`): banner
        "CHECKING API · NO EVIDENCE SHOWN YET", map caption "Checking the API
        for evidence points", hero "Unknown", no number anywhere.
      - Unavailable state (a rejected `/point`): banner "NO LIVE EVIDENCE
        RETRIEVED", hero "Unknown", no digit in the hero block, dock still
        inside the viewport.
      - Live state: hero 13.7 °C from `eccc-hrdps`, data path "Live API".
      - On-map fallback disclosure: with GOES-East day visible / night IR on
        and the scrub at +6h, `.map-frame-notes` renders inside the map at
        both widths reading "not shown - observed imagery has no frames for
        future instants", and the identical sentence appears in the drawer
        row (with its jump button) and in the text alternative.
      - Expert mode (Workbench) at 700 px and 900 px, both themes: the
        scrolling layout is unchanged, no dock or scrubber, provenance table
        renders, no horizontal overflow.
      - Console: no application errors (only two Chrome extension
        message-channel exceptions, from the automation itself).

      Not exercised: the display-compositing blend note, which needs a
      forecast layer straddling two frames with interpolation on; the
      2026-08-31 desktop pass covered it and this pass did not repeat it.

      Status 2026-09-02 (re-run, PASSED). The label overlap above was fixed
      (task 4.3) and the whole pass repeated against a build of this branch:
      `npm run build`, then a Vite dev server from the worktree on port 5200
      proxying the live API on 8000, driven through the same same-origin
      700/900 px iframe. (`vite preview` was tried first and rejected: its SPA
      fallback answers `/api/...` with `index.html` and a 200, so the app would
      have been read against a dead API that looked alive.)
      Verify result: PASSED at 700 px and 900 px, in both themes.
      - Scale labels: no overlapping pair at any width, theme or state, every
        label inside the rail. At 700 px (rail 646 px) the axis reads
        `-3h · Now (0h) · +6h · +12h · +18h · +24h (Forecast)` with a smallest
        gap of 29.6 px: `-1h` is thinned out and the past boundary sheds its
        "(Past)". At 900 px (rail 846 px) `-3h (Past)` is back in full and the
        smallest gap is 9.7 px. The eight quick jumps and all 16 frame markers
        are unchanged with the layers on.
      - Layout: no horizontal overflow anywhere; map pane 700x570 / 900x570
        with the dock directly beneath (700: 662-880; 900: 648-866), both
        inside a 950 px viewport.
      - Story flyout opens, takes focus, closes on Escape and returns focus, at
        700 px and 900 px in both themes.
      - Loading (delayed `/point`): "CHECKING API · NO EVIDENCE SHOWN YET",
        hero "Unknown". Unavailable (rejected `/point`): "NO LIVE EVIDENCE
        RETRIEVED", hero "Unknown", no digit in the hero block. Dock still at
        889 px, inside the viewport, in both.
      - Fallback disclosure: with GOES-East day visible / night IR on,
        interpolation on and the scrub at +12h, the on-map note reads "not
        shown - observed imagery has no frames for future instants", inside the
        viewport, with the same sentence in the drawer row (plus its jump
        button, naming the 03:00 p.m. frame 12.5 h earlier) and in the text
        alternative. With interpolation OFF the quick jump snaps back onto a
        published frame and resolves exactly, which is the snap rule working,
        not a missing note.
      - Expert mode at 700 px and 900 px, both themes: scrolling layout intact,
        no dock or scrubber, provenance table present, no overflow.
      - Console: no errors.
      - Noted, not a layout fault: this branch also carries
        `evidence-classes-and-derived-here`, and the live API does not yet send
        `provenance.evidence_class`. Every reading therefore renders as
        "Unavailable · unrecognised evidence class - the response declared
        none", and every layer badge as unrecognised. That is the required
        behaviour of a required field with no default, against an API whose own
        tasks (1.1-2.4) have not landed; it changes no geometry, and the
        loading and unavailable states are unaffected by it.

- [x] 4.3 Thin the scrubber's scale labels against the measured rail so none
      is ever drawn over another, keeping the past boundary, `Now` and the
      future boundary; frame markers and quick jumps untouched.
      Verify: `cd web && npm test -- --run scrubberAxis`
      Verify result: 14 passed. `placeScaleMarks` in `web/src/scrubberAxis.ts`
      places marks in priority order (`Now`, future boundary, past boundary,
      then the rest in axis order) and keeps one only when its measured box
      clears every box already placed by 8 px; a boundary tries its long form,
      then its short form, before it would be dropped. Asserted non-overlapping
      at 700, 860, 900 and 1200 px rails and at every integer width from 600 to
      2000 px, with the three orienting marks present throughout. The component
      measures the rail with a `ResizeObserver` and the text with a canvas in
      the rail's own font; an unmeasured rail (first paint, or a runtime with no
      layout) renders every long label, which is the pre-existing behaviour.

## 5. Conventions and validation

- [x] 5.1 Amend `openspec/config.yaml` governing-rule sentence and the
      staleness-tolerance hard-won fact for the owner-approved carve-outs.
      Verify: `openspec validate --all`
- [x] 5.2 Full suite.
      Verify: `cd web && npm test -- --run && npm run build; openspec validate --all`
