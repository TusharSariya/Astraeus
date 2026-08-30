## 1. Fix the request contract before anything depends on it

- [x] 1.1 Rewrite `layerRasterUrl` in `web/src/api.ts` to send `south`, `west`,
      `north`, `east` as separate parameters; drop the packed `bbox` and the `crs`
      parameter. Verify against `api/weather_api/app.py`'s raster signature.
- [x] 1.2 Add a test asserting the exact parameter set, so a silent drift back to
      a packed bbox fails loudly. Verify: `cd web && npm test`
- [x] 1.3 Extend `LayerItem` in `web/src/types.ts` with `evidence_basis`,
      `raster_available`, `legend_available`, `upstream_wms_layer`.

## 2. Draw the imagery

- [x] 2.1 Add a MapLibre `image` source + `raster` layer per active raster layer in
      `MapPanel.tsx`, inserted beneath `esri-labels-layer` in existing z-order.
- [x] 2.2 Drive extent from `map.getBounds()`, debounced on `moveend`.
- [x] 2.3 Apply the layer's existing opacity to `raster-opacity`.
- [x] 2.4 Extend the `releaseImage` ref to a per-layer map; revoke on layer
      removal, frame change and unmount. Add a test that no object URL leaks
      across a frame change.
- [x] 2.5 Skip the request entirely when `raster_available` is false.
      Verify: `cd api && uv run pytest -q` unaffected; `cd web && npm test`

## 3. Report retrieval honestly

- [x] 3.1 Read `X-Weather-Retrieval-Status`; render "retrieved, nothing detected"
      distinctly from "not retrieved".
- [x] 3.2 Handle 502, 429 and 501 with distinct reasons; clear any previously
      drawn image on failure rather than leaving stale pixels.
- [x] 3.3 Refuse to draw bytes when retrieval provenance headers are absent.
- [x] 3.4 Tests for each of the above states.

## 4. Legend

- [x] 4.1 Display the provider legend beside each active raster layer when
      `legend_available` is true; note its absence when false.
- [x] 4.2 Confirm no colour scale is constructed anywhere in the client.

## 5. Evidence basis disclosure (required by the Gate 2 deviation)

- [x] 5.1 Show `evidence_basis` in words in the layer stack panel and in the map
      text alternative.
- [x] 5.2 Fail closed to "unknown basis" when the field is absent or unrecognised.
- [x] 5.3 Test that a `live_proxy` layer is never described as a published artifact.

## 6. Close the two dead paths found in the backfill

- [x] 6.1 Replace the `source.state === 'active'` predicate for model/product
      controls, or remove the controls. Confirm live that 0 of 59 sources are
      `active` before choosing. Do not leave a permanently disabled affordance.
- [x] 6.2 Apply the fail-closed `data_mode` rule to `loadTimeline`; add
      `data_mode` to `TimelineResponse` in `types.ts`.

## 7. Verify end to end

- [x] 7.1 `cd api && uv run pytest` — must stay at 311 passed / 2 skipped or better.
- [x] 7.2 `cd web && npm test` and `npx tsc -b --force` — both clean.
- [x] 7.3 Browser at :5173 — toggle an HRDPS forecast layer, scrub to +24h, confirm
      a real temperature field draws with ECCC's legend, that it is labelled
      live-proxied, and that scrubbing past coverage draws nothing rather than a
      stale frame.
