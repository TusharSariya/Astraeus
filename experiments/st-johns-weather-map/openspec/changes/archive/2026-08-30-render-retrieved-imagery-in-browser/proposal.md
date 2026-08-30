## Why

The API now retrieves and serves real weather imagery. The browser cannot see any
of it.

Iteration 1 took the map from 6 layers / 59 frames / **0 future frames** to
15 layers / 308 frames / **216 future frames**, and `/layers/{id}/raster` returns
a genuine 59 KB HRDPS temperature field at +24 h with ECCC's own colour ramp from
`/legend`. Verified live. But `evidence_basis`, `raster_available` and
`legend_available` appear nowhere in `web/src`, and `MapPanel.tsx` draws only
GeoJSON point features. Every one of those 216 forecast frames is invisible.

Two blockers were found during the spec backfill that make this more than a
wiring job:

1. **`layerRasterUrl` is wrong, and wrong silently.** It builds
   `bbox=west,south,east,north` plus a `crs` query parameter; the endpoint takes
   `south`/`west`/`north`/`east` as separate parameters. Wired as-is it would fall
   back to server defaults and draw a plausible image of the wrong extent. Given
   that a transposed EPSG:4326 box is answered 200 with a near-empty tile and no
   error, a coordinate mistake here does not announce itself.
2. **Product selection is a dead control path.** Every forecast-model button and
   product option is gated on `source.state === 'active'`, and
   `_REGISTRY_STATE_CEILING` never emits `active` by design. Confirmed live:
   0 of 59 sources are `active`. So `/point?product=` is fully implemented and
   permanently unreachable from the browser.

## What Changes

- Render `raster` layers as MapLibre image sources beneath the existing deck.gl
  vector overlay, one image per layer per frame, honouring per-layer opacity and
  z-order that already exist in the layer stack.
- Fix `layerRasterUrl` to match the endpoint, and pin the parameter contract with
  a test so it cannot drift back.
- Show the retrieved legend beside each active raster layer.
- Surface `evidence_basis` in the UI. This is **required**, not cosmetic: proxied
  forecast layers bypass the Gate 2 ingest/QC/atomic-publication spine, and the
  owner approved that deviation on the explicit condition that the reader is told.
  A live-proxied layer must not be presentable as a published artifact.
- Distinguish "retrieved, nothing detected" from "not retrieved" in the layer
  state, driven by `X-Weather-Retrieval-Status`. A fully transparent radar tile is
  a reading.
- Replace the `state === 'active'` predicate with one the API can actually satisfy,
  so product selection becomes reachable — or remove the control. It must not stay
  a permanently disabled affordance.
- Apply the fail-closed `data_mode` rule to `loadTimeline`, the one client fetch
  that currently skips it.

## Capabilities

### New Capabilities
- `web-raster-rendering`: how retrieved imagery and its provider legend are drawn
  in the browser, how the request extent is constructed, and how an image whose
  provenance cannot be established is refused rather than drawn.

### Modified Capabilities
- `web-evidence-interface`: layers may now render as imagery, not only vector
  features; the interface must disclose each layer's `evidence_basis`; a disabled
  control must be reachable-in-principle or removed.
- `evidence-truth-boundary`: the client applies the mode rule to every fetch,
  including `/timeline`.

## Impact

`web/src/{MapPanel.tsx,api.ts,types.ts,App.tsx,styles.css}` and their tests.
No API change is required — iteration 1 already serves everything needed.
Read-only dependency on `evidence_basis`, `raster_available`, `legend_available`,
`upstream_wms_layer` and the `X-Weather-*` response headers.

Risk: the per-request upstream budget is 16 calls, 240/minute. A cold scrub of all
9 proxied HRDPS layers at once is 252 calls and would return 429. The UI must
request only visible layers and degrade honestly on 429 rather than showing a gap.
