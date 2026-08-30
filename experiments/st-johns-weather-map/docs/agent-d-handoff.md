# Agent D handoff — web UI truth boundary (`web/src/`)

**State of the tree: TypeScript compiles (`npx tsc -b` exit 0). `npm test -- --run`
fails 3 of 7 tests.** Nothing is half-written or syntactically broken. The three
failures are in `web/src/App.test.tsx`, which I did **not** get to update: the
tests assert copy and a fetch-mock shape that the rewrite changed. Details and
the exact fix in TEST STATUS / NEXT STEPS below.

## 1. DONE — files actually modified on disk

| File | What changed |
|---|---|
| `web/src/types.ts` | Added `FieldDataMode` (`live\|fixture\|mixed\|unavailable`); added `'mixed'` to `DataSource`; `EvidenceSnapshot` now carries `dataMode`, per-field `fieldModes`, `precipitationProbabilityPct`; new `ProvenanceRow` (with `member`, `level`, `dataMode`), `StoryStep` (all values nullable + `dataMode`), `LayersResult`, `CatalogSource`, `CatalogResult`; `LayerItem` gained optional `raster_url` / `legend_url` / `data_mode`. |
| `web/src/api.ts` | `toDataMode()` maps the response `data_mode` and **fails closed to `unavailable`** for missing/unrecognised values; `loadPoint` returns that as its source (a 200 with `data_mode:"fixture"` is fixture, never live) and reports why when it is unavailable; `normalizePoint` now records per-field `provenance.data_mode`, `member`, `vertical_level`, and real alert text; new `loadLayers`, `loadCatalog`, `layerRasterUrl`, `layerLegendUrl`, `loadLayerRaster`, `loadStory`. |
| `web/src/fixtures.ts` | `fixtureSnapshot` / `unavailableSnapshot` updated to the new shape and stamped `dataMode: 'fixture'` / `'unavailable'` field by field. |
| `web/src/MapPanel.tsx` | Rewritten. No procedural field of any kind. Layer list, titles, units and semantics come from `/layers`; one map image per layer/time/viewport is fetched from the API proxy and drawn verbatim; provider legend graphic is shown as an `<img>`; explicit unavailable panel over the basemap otherwise; screen-reader text alternative added. MapLibre basemap, deck.gl station/label/glow layers, click-to-pick, station selection and the `fixtureMode` watermark are all kept. |
| `web/src/App.tsx` | Marine `Math.sin` / `12.5` defaults removed; warnings from real alert evidence; expert selectors wired to `/catalog` + `/layers` + provenance; model strip driven by `/catalog`; data-path indicator distinguishes live/mixed/fixture/unavailable/loading; banner shown whenever `dataSource !== 'live'`; per-field data-mode chips; every empty state is a sentence, not a dash. |
| `docs/agent-d-handoff.md` | This file. |

Not touched: `styles.css`, `App.test.tsx`, `vite.config.ts`, `package.json`,
and everything outside `web/`.

## 2. DELETED — fabrication audit

All **gone**, verified by grep over `web/src/`:

- `generateSmoothWeatherTexture` — gone
- `fbm` — gone
- `smoothNoise` — gone
- `hash2d` — gone
- `generateWindVectors` (and the `WindVector` type / `LineLayer` import) — gone
- `RASTER_BOUNDS` — gone
- The `15 dBZ / 35 dBZ / 55+ dBZ` and `10°C / 14°C / 18°C` legends and the
  hardcoded cloud/radar/temp/wind button row — gone. The legend is now the
  provider's own graphic fetched from `/layers/{id}/legend`; if it fails to load
  the UI says so and draws no ramp.
- `buildForecastStory` in `api.ts` — gone. `normalizePoint` returns `story: []`.
- `App.tsx` marine `Math.round((1.8 + 0.4 * Math.sin(...)))` and `12.5` SST —
  gone; both render `Unavailable` with an explanation.

No "demo mode" copy of any of it was kept.

## 3. INCOMPLETE

- **`web/src/styles.css` — not updated.** New class names are emitted but have no
  rules: `.mode-chip`, `.hero-unknown`, `.map-layer-state`, `.layer-reason`,
  `.layer-semantics`, `.legend-graphic`, `.legend-missing`, `.legend-semantics`,
  `.map-text-alternative`, `.layer-empty`, `.model-unavailable`, `.model-empty`,
  `.warning-list`. Functionally fine, visually unstyled. In particular
  `.map-text-alternative` is intended to be visually hidden (sr-only) inside the
  map pane — right now it will render as visible text over the map pane and look
  wrong. This is the one visual regression to fix first.
- **`web/src/App.test.tsx` — untouched, 3 failures** (see below). No new test
  files were written.
- `loadStory` issues up to 8 `/point` calls (only for hours `/timeline` reports as
  published). It works and is honest, but it has not been exercised against a
  live API.

## 4. NOT STARTED

Nothing on the assigned list was skipped: `data_mode` reading, `mixed` mode,
layer list from `/layers`, provider legend graphics, expert selector wiring,
model-strip claims from `/catalog`, and the map textual alternative are all
implemented. What is missing is the **test extension** (all six required new
cases) and the **CSS pass** above.

Note on the API contract: `/layers/{id}/raster` and `/layers/{id}/legend` do not
exist yet (Agent C/B). The UI therefore renders its explicit "layer unavailable"
state with the reason and the layer's `semantics` text — that is the correct
behaviour, not a stub. `LayerItem.raster_url` / `legend_url` are honoured if the
API later publishes them, so no frontend change is required if Agent C picks
different paths.

## 5. TEST STATUS — observed, verbatim

`npx tsc -b` → exit 0, no output.

`npm test -- --run`:

```
 ✓ shows unavailable unknown evidence on API outage instead of fixtures 32ms
 × clears previous point evidence while a new point is loading 1029ms
   → Unable to find an element with the text: 16.
 × converts response wind m/s to km/h and preserves fog enum semantics 1026ms
   → Unable to find an element with the text: 36 / 45.
 ✓ requests GPS only after action and reports denial with retained location 83ms
 ✓ reports unavailable GPS separately 30ms
 ✓ supports keyboard coordinate entry and validates bounds 162ms
 × labels expert controls and comparison as unwired 35ms
   → Unable to find an element with the text: /Selectors are disabled/i.

 Test Files  1 failed (1)
      Tests  3 failed | 4 passed (7)
```

`npm run build` — **not run.** Do not assume it passes; `tsc -b` (the first half
of the build script) does pass.

Cause of the two "Unable to find" data failures: the tests do
`vi.mocked(fetch).mockResolvedValue(response(...))`, returning **one** `Response`
object for every call. App now fetches `/catalog`, `/layers` and `/timeline`
before `/point`, so by the time `/point` runs, that Response body is already
consumed and `json()` throws → the UI correctly shows unavailable. This is a
test-mock defect, not an app defect. The third failure is copy: the expert panel
no longer says "Selectors are disabled" because the selectors are now wired.

## 6. NEXT STEPS, in order

1. `web/src/App.test.tsx`: replace the blanket `mockResolvedValue` with a
   URL-routed mock — `vi.fn(async (url: string) => ...)` returning a **fresh**
   `new Response(JSON.stringify(body), {status:200})` per call, matching on
   `/point`, `/layers`, `/catalog`, `/timeline`. That alone should fix the two
   data failures.
2. In the same file, update the expert-panel assertion: the panel now reads
   "Every option below comes from a response. A selector with no returned options
   stays disabled and says why." Disabled selectors keep their honest reason text
   (e.g. "No run time in returned provenance").
3. Add the six required cases: `data_mode:"fixture"` → banner + no "Live API";
   no `data_mode` → unavailable, not live; all-null fields → no numeric anywhere;
   single-point response → the empty-story state; marine absent → "Unavailable";
   and a MapPanel case (new file, `vi.mock('maplibre-gl')` + `@deck.gl/*`) where
   the raster fetch returns 404 → unavailable state **and** the layer's
   `semantics` text still visible.
4. `web/src/styles.css`: add the missing rules listed in §3; make
   `.map-text-alternative` visually hidden but screen-reader readable.
5. Re-run `npx tsc -b && npm test -- --run && npm run build`.

Nothing was committed.
