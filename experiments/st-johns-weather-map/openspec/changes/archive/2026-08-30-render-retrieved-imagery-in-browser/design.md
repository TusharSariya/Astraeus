## Context

`MapPanel.tsx` already owns a MapLibre map with a deck.gl `MapboxOverlay` for
vector features, an ordered layer stack with per-layer opacity and z-index, and
per-layer frame resolution through `resolveFrame`. What it has never had is an
image path: `RASTER_SOURCE`/`RASTER_LAYER` were removed when the stack became
multi-layer, and `loadLayerRaster` has sat unused in `api.ts` ever since.

The API side is complete and verified live. A raster response is a PNG plus
`X-Weather-*` headers carrying retrieval status, upstream URL, WMS layer, valid
time, reference time, licence and attribution. `X-Weather-Image-Basis` is always
`live_proxy`, because no artifact in this experiment contains an image — even a
radar tile for a stored layer is rendered live.

## Goals / Non-Goals

**Goals:**
- Draw retrieved imagery under the existing vector overlay, per layer, per frame.
- Make the evidence basis of every layer legible to the reader.
- Make the raster URL contract impossible to get silently wrong.

**Non-Goals:**
- Any API change. Iteration 1 serves everything required.
- Tile pyramids or zoom-dependent requests. One image per layer per frame.
- Building Pane B, Skew-T, or cross-section. Those still have no data.
- Client-side reprojection, resampling, or colour manipulation of the image.

## Decisions

**Image source per layer, keyed by layer id.** MapLibre's `image` source takes
four corner coordinates, which is exactly what a single EPSG:4326 `GetMap` over
the map bounds produces. Requesting one image per layer per frame keeps the
upstream call count equal to the number of visible layers, which is what the
proxy's 16-call-per-request budget assumes. A tile pyramid would multiply that by
the tile count and immediately exhaust the 240/minute ceiling.

Alternative considered: reuse the deck.gl overlay with a `BitmapLayer`. Rejected
because raster layers must sit *beneath* the station and feature overlay in the
existing z-order, and MapLibre's own layer ordering already expresses that
relationship against `esri-labels-layer`.

**Bounds come from the map, not from a constant.** The image must cover what the
reader is looking at. `map.getBounds()` supplies it; the four values are sent as
named parameters. Refetch is debounced on `moveend` rather than on every frame of
a pan, both to respect the budget and because an in-flight pan has no stable
extent to request.

**The URL contract is pinned by test.** The current builder disagrees with the
endpoint and would fail silently — the server would substitute defaults and return
a well-formed image of somewhere else. Because a wrong extent renders as a
perfectly plausible picture, this cannot be caught by looking at it, so it is
asserted directly.

**Object URLs are revoked per layer.** The existing single `releaseImage` ref
becomes a map keyed by layer id, released on layer removal, frame change, and
unmount. Without this a scrub across 28 frames leaks 28 blobs per layer.

**Evidence basis is rendered as words, not a colour.** It is the condition under
which the proxied route was allowed, so it must survive in the text alternative
and be legible to a screen reader, not encoded in a swatch.

## Risks / Trade-offs

**The 429 path is real and reachable.** Nine proxied layers scrubbed cold is 252
upstream calls against a 240/minute ceiling. Requesting only visible layers makes
the common case fine, but a reader who enables everything will hit it. The
honest failure — "imagery was not retrieved because the request budget was
reached" — is specified, but it is a worse experience than raising the ceiling.
Raising it trades politeness to a free public service against that experience;
this change keeps the ceiling and reports honestly, and flags the trade rather
than deciding it unilaterally.

**Fixing the dead product control may widen scope.** The clean fix is a
`publishable` signal distinct from `active`, which is an API concern and would
break the "no API change" goal. The alternative is a client-side predicate over
what the catalogue actually reports. If neither is defensible within this change,
removing the control is preferable to leaving a permanently dead one.

**Curvilinear sampling remains unproven end to end.** Not caused by this change
and not fixed by it: no gridded artifact is published yet, so `/point` still
answers from METAR only. Imagery will show an HRDPS field the point readout
cannot corroborate. Worth stating in the interface rather than letting the two
appear to disagree.
