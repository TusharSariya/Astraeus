## 1. Contract and cartography

- [x] 1.1 Add the experiment change and validate it before behavior changes.
- [x] 1.2 Add a locally owned OpenFreeMap vector style with base and reference
      layer groups separated by a stable weather insertion anchor.
- [x] 1.3 Keep reference outlines and labels above every weather raster and
      Deck.gl observations above the MapLibre stack.
- [x] 1.4 Add an independent, announced reference-map failure state.

## 2. Theme and interface

- [x] 2.1 Add system-first light/dark initialization without a theme flash and
      persist explicit choices locally.
- [x] 2.2 Apply shared semantic tokens to the page, panels, controls and map.
- [x] 2.3 Collapse the layer drawer by default, support Escape, and use a narrow
      screen bottom-sheet layout.
- [x] 2.4 Present active exact provider legends in a map-adjacent rail and retain
      the explicit no-provider-legend state.

## 3. Verification

- [x] 3.1 Assert local vector style ownership, weather insertion before the
      reference stack, theme updates, and reference failure behavior.
- [x] 3.2 Assert system theme initialization, manual persistence, drawer state
      and exact-provider-legend labelling.
- [x] 3.3 Run `cd web && npm test -- --run && npm run build`.
- [x] 3.4 Run `openspec validate --all` and repository `specctl validate`.
- [x] 3.5 Inspect light, dark, opaque-cloud, drawer and narrow layouts in a real
      browser with no horizontal page overflow or console errors.
