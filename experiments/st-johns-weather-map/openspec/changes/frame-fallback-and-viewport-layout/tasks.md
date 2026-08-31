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
- [ ] 4.2 Browser pass in both themes at 700/900/1050+ widths, in loading,
      unavailable and live states; expert-mode regression check.
      Verify: `make up` then manual checklist in the change proposal
      Status 2026-08-31: verified live at desktop width in both themes and in
      expert mode (snapping, fallback note, display composite, story flyout
      all exercised in the browser); the 700/900 px passes remain to be run.

## 5. Conventions and validation

- [x] 5.1 Amend `openspec/config.yaml` governing-rule sentence and the
      staleness-tolerance hard-won fact for the owner-approved carve-outs.
      Verify: `openspec validate --all`
- [x] 5.2 Full suite.
      Verify: `cd web && npm test -- --run && npm run build; openspec validate --all`
