## Why

The experiment currently uses a dark, low-detail raster basemap beneath weather
imagery. Land and sea are both grey, and dense cloud imagery can remove the
coastline, lakes, roads and labels that let a reader locate the evidence. That
is especially harmful in Newfoundland, where coast geometry is an essential
part of reading weather at a point.

This change adopts the reference-map pattern used by mature weather products:
a quiet land/water base below the meteorological field and a separate,
transparent orientation layer above it. The visual redesign improves hierarchy
and contrast without recolouring, smoothing, classifying or otherwise changing
weather evidence.

Classification: Experiment, Spec-Impact: none. This work is confined to
`experiments/st-johns-weather-map`; `docs/specv1` and its proposed client
rendering requirements remain untouched.

## What Changes

- Replace the Esri raster basemap with a locally owned MapLibre style backed by
  OpenFreeMap/OpenMapTiles vector data.
- Draw land and water below weather rasters, then coastlines, lake outlines,
  selected roads, boundaries and place labels above them. Observation markers
  and controls remain uppermost.
- Add light and dark chart themes. The first visit follows the operating-system
  preference and a manual choice is retained locally.
- Keep the provider's raster pixels and provider legend exact. Internal cloud
  imagery keeps its existing neutral white-alpha encoding.
- Collapse the layer drawer by default, group dense controls, expose active
  provider legends beside the map, and present the drawer as a bottom sheet on
  narrow screens.
- If reference tiles fail, keep weather imagery, observations and the textual
  alternative available while announcing that the reference map is unavailable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-evidence-interface`: the basemap/reference sandwich, theme behavior,
  persistent orientation under opaque imagery, progressive disclosure and
  reference-map failure state are specified.
- `web-raster-rendering`: provider pixels and legends remain unchanged while
  cartographic reference information is drawn independently above them.

## Impact

- Web only: `web/index.html`, `web/src/App.tsx`, `web/src/MapPanel.tsx`, a new
  locally owned map-style module, CSS, and mapped tests.
- One runtime network dependency changes from Esri raster tiles to OpenFreeMap
  vector tiles, glyphs and sprites. The source is isolated behind the local
  style module so it can be replaced without changing evidence logic.
- No API, ingestion, registry, provider, data model, scientific calculation or
  normative V1 behavior changes.
