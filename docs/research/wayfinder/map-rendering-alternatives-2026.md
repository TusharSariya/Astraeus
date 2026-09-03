Non-normative research, 2026-09-03. Not a spec, not a design decision.

# Web map rendering alternatives to MapLibre and deck.gl, September 2026

Answers wayfinder ticket
[#56](https://github.com/TusharSariya/Astraeus/issues/56) (part of map
[#38](https://github.com/TusharSariya/Astraeus/issues/38)): which web mapping
and geospatial rendering stacks in September 2026 could replace or sit beside
MapLibre GL JS and deck.gl for the Map view, judged on power and control over
the Layer stack: per-layer blend modes and custom shaders for raster stacks,
native time as a coordinate, independent time steps per layer, GPU-side
compositing of many rasters, swipe, side-by-side and small-multiple compare
without N map instances, WebGPU, vector and raster in one scene graph, and an
escape hatch to raw GPU code. It ends with a ranked shortlist and a
recommendation on the charting stack lock (React, Vite, MapLibre, deck.gl;
the owner reopened the rendering-library half on 2026-09-03).

It builds on ticket [#44](https://github.com/TusharSariya/Astraeus/issues/44)
(`raster-compositing-compare.md`), which already established what the
current stack can do: MapLibre rasters get opacity and colour adjustment but
only normal blending; blend modes come from deck.gl layer `parameters` or a
custom layer owning its `blendFunc` (`FlowBlendLayer`); every (layer, time)
is its own source; swipe and small multiples are N synced maps unless the
raster is deck-drawn. Those findings are not repeated here; this document
asks whether anything else does better.

Sources are each project's official docs, changelogs, GitHub releases API,
npm registry, bundlephobia and licence files, fetched on 2026-09-03. Every
version and capability claim carries its URL. Claims that could not be
checked against a primary source are marked **unverified**. Bundle sizes are
bundlephobia's minified and gzipped figures for the default entry and are
not what a tree-shaken Vite build ships; they are comparable to each other,
not to the experiment's bundle.

## 1. Summary

- **Nothing in 2026 gives raster blend modes, time as a coordinate and
  single-map compare out of the box on an open licence.** The only style-spec
  product that colours rasters client-side, carries multi-band time-series
  tiles and animates particles is Mapbox GL JS v3 (`raster-color`,
  `raster-array`, `raster-particle`), and it is proprietary, billed per map
  load, and its `raster-array` source is tied to Mapbox-hosted MRT tilesets.
- **The nearest open alternative on raster control is OpenLayers 10's WebGL
  tile layer**: a style expression language over bands (`band`, math,
  `interpolate`, `case`) with multiple sources per layer for band math across
  rasters, GeoTIFF and GeoZarr sources read client-side (GeoZarr gained
  non-spatial dimension selection for time series in 10.10), and
  `prerender`/`postrender` hooks that expose the raw `gl` context for scissor
  swipe in one map. It has no WebGPU and no first-party React binding.
- **CesiumJS is the only candidate with time as a first-class coordinate**
  (`Clock`, `TimeIntervalCollection`, WMS `times`) and a built-in
  `splitDirection` swipe on imagery layers, but imagery layers expose only
  alpha, brightness, contrast, hue, saturation, gamma and colour-to-alpha; no
  blend modes and no custom shader on imagery (custom shaders are for models
  and 3D Tiles; `PostProcessStage` is whole-scene). It is Apache-2.0, 1.3 MiB
  gzipped, and WebGPU is "longer term".
- **WebGPU is not production-ready in any map library today.** deck.gl 9.3
  says so explicitly and 9.4 (beta) ports more layers but still not the
  injection extensions or base-map integration; MapLibre GL JS 6 is WebGL2-only
  with a four-phase modernisation plan and no dates; CesiumJS and OpenLayers
  have no WebGPU renderer; three.js `WebGPURenderer` and Babylon.js 9 are
  production WebGPU engines but not map engines. MapLibre Native's WebGPU
  backend runs in the browser through the FFI project as of June 2026, but as
  an experimental wasm build, not a JS map library.
- **The salvaged `FlowBlendLayer` pattern carries over wherever there is a
  raw-GL custom layer with a known matrix**: MapLibre (as is), Mapbox GL JS
  (same interface), OpenLayers (custom WebGL layer renderer or
  `prerender` hooks, different matrix convention), Windy's LeafletGL (same
  MapLibre custom layer), three.js and Babylon.js (as a ShaderMaterial on a
  quad, a port not a copy). It does not carry over to Cesium (no raw GL
  imagery hook), to deck.gl WebGPU (WGSL rewrite), or to any library that
  hides its context.
- **Recommendation: keep the lock.** MapLibre GL JS 6 plus deck.gl 9.3, with
  the raster stack drawn through deck (`BitmapLayer`/`TileLayer` with
  `parameters` blend factors or a custom layer) rather than MapLibre's native
  raster layer, is the strongest open stack on every axis the ticket names
  except native time, and native time is a small store on the client side.
  Move the pin from maplibre-gl 5.7.1 to 6.x (in-place `updateImage`,
  `setWarp`, WebGL2-only) and from deck 9.1 to 9.3 (multi-canvas and
  `@deck.gl/maplibre` arrive in 9.4). The one thing worth a bounded prototype
  is OpenLayers' WebGL tile style expressions for client-side band math on
  COG or GeoZarr; if that experiment shows a decisive gain, OpenLayers is the
  one candidate that could replace MapLibre without losing the raw-GL hatch.

## 2. Comparison table

Legend: **yes** documented and shipped; **partial** achievable with a custom
layer or a documented workaround; **no** not offered; **n/a** not a map
engine. "N maps" means the arrangement needs one map instance per panel.

| Candidate | Current version (date) | Licence | Backend | Raster blend modes | Custom shader on rasters | Native time | Independent time per layer | Many-raster GPU compositing | Swipe in one map | Side by side / small multiples in one instance | WebGPU | Vector + raster in one scene | Raw GPU hatch | React | Bundle (min+gz) | FlowBlendLayer carries over |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MapLibre GL JS | 6.7.0 (2026-09-02) | BSD-3 | WebGL2 only | no (roadmap, unfunded) | partial (custom layer) | no | per source | one draw per tile per layer, fixed blend | no (native raster); partial (custom layer scissor) | N maps | planned, no date | yes | yes, `WebGL2RenderingContext` | react-map-gl (third party) | 263 KB | yes, as is |
| deck.gl | 9.3.11 (2026-08-28); 9.4.0-beta.3 (2026-09-03) | MIT | WebGL2; WebGPU preview | yes (`parameters` blend factors) | yes (custom layer, shader injection) | no | per layer instance | yes, one context | yes for deck-drawn rasters (mask/scissor) | yes, `views` + `layerFilter`; 9.4 adds multi-canvas | preview, not production | overlay on a base map, or GlobeView | yes, luma.gl Device | first party (`@deck.gl/react`) | 182 KB core | yes, as a deck custom layer (WGSL port for WebGPU) |
| CesiumJS | 1.145 (2026-09-01) | Apache-2.0 | WebGL2 | no (alpha, colour adjustments, colour-to-alpha) | no on imagery; `Globe.material` (Fabric), `PostProcessStage` whole-scene | yes (`Clock`, `TimeIntervalCollection`, WMS `times`) | per provider, one clock | yes, all imagery in the globe shader | yes, `splitDirection` | no (one scene) | longer term | yes (3D) | no supported hook for imagery | Resium (third party) | 1.34 MB | no |
| OpenLayers | 10.10.0 (2026-07-27) | BSD-2 | Canvas 2D or WebGL2 per layer | partial (style expressions, band math across sources; CSS `mix-blend-mode` on per-layer elements, unverified) | yes (expression language; custom `WebGLLayerRenderer`) | partial (GeoZarr dimension selection; WMS `TIME` param per source) | per source | partial (per-layer canvases unless `className` shares a context) | yes (`prerender` scissor) | N maps | no | yes (separate layers) | yes, raw `gl` in `prerender`/`postrender` | none first party | 84 KB (tree-shakeable) | port (different matrix, own renderer class) |
| Kepler.gl | 3.2.0 stable (2025-08-21); 3.3.0-alpha.10 (2026-09-02) | MIT | deck.gl | inherits deck | no app-level hook | filters, not a coordinate | no | inherits deck | no | no | inherits deck | via deck | via deck | React app, Redux | large (app) | not applicable, it is an application |
| loaders.gl | 4.4.6 (2026-09-02); 5.0.0-alpha.5 | MIT | n/a (loaders) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | per loader | n/a |
| Mapbox GL JS v3 | 3.30.0 (2026-09-03) | proprietary, token and billing | WebGL2 | partial (`line-blend-mode` only) | partial (custom layer, same interface) | partial (`raster-array` bands, Mapbox-hosted) | per source | as MapLibre | no | N maps | none announced | yes | yes | react-map-gl | 498 KB | yes, same interface |
| Google WebGLOverlayView | Maps JS API, weekly channel | proprietary, billed | WebGL2 (shared with vector basemap) | no | yes (raw context) | no | n/a | your own | no | N maps | no | basemap plus your GL | yes, shared context, must reset state | third party | loads from Google | port, camera from `CoordinateTransformer` |
| Google Photorealistic 3D Tiles | Map Tiles API | proprietary, billed, caching forbidden | any 3D Tiles renderer | n/a (a data source) | n/a | no | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| three.js | r185 / 0.185.1 (2026-07-01) | MIT | WebGL2 and WebGPU (`WebGPURenderer`, TSL) | yes (material blending, `ShaderMaterial`, TSL) | yes | no | your own | yes | yes (scissor, stencil) | yes (viewports in one renderer) | yes, production | you build the map | yes | react-three-fiber | 182 KB | port to `ShaderMaterial` |
| Babylon.js | 9.23.0 (2026-08-27) | Apache-2.0 | WebGL2 and WebGPU | yes | yes | no | your own | yes | yes | yes | yes, production | you build the map | yes | third party | 1.7 MB | port |
| three-geo | 1.4.5 (2022-06-18) | MIT | three.js r138 | via three | via three | no | no | no | no | no | no | terrain from tiles | via three | no | small | port |
| threebox | 2.2.7 (2022-06-04) | MIT | Mapbox custom layer | via three | via three | no | no | no | no | no | no | three inside Mapbox/MapLibre | via three | no | small | already a custom layer |
| Giro3D | 2.0.4 (v2.0.0 2026-03-31) | MIT | three.js r180 + OpenLayers sources | yes (`ColorLayer.blendingMode`, enum values unverified) | partial (three materials) | no | per source | yes (layers composited in the map material) | unverified | unverified | no | yes (OL sources on three meshes, Globe entity) | via three | no | large (three + ol) | port |
| iTowns | 2.46.0 (2025-10-07) | CeCILL-B and MIT | three.js r170 to r182 | no documented | partial | no | per source | yes (texture arrays per layer) | no | no | no | yes | via three | no | large | port |
| Leaflet + WebGL plugins | 1.9.4 (2023-05-18); 2.0.0-alpha.1 (2025-08-16) | BSD-2 | DOM/Canvas; plugins bring WebGL | plugin (`TileLayer.GL`, `GLOperations`) | plugin | no | per layer | no (one context per plugin layer) | plugin | N maps | no | no (raster tiles, or MapLibre inside via maplibre-gl-leaflet) | plugin | react-leaflet | 43 KB | port to a `TileLayer.GL` shader, loses the matrix |
| Tangram | 0.22.0 (2024-12-17) | MIT | WebGL (Leaflet plugin) | no | yes (scene-file GLSL) | no | no | no | no | N maps | no | vector focus | scene GLSL | no | unverified | no |
| harp.gl | archived 2023-03-08 | Apache-2.0 | three.js | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | no |
| Windy LeafletGL | docs public, version unverified | unverified | trimmed MapLibre + Leaflet API | via MapLibre custom layers | `CanvasLayer` to texture | no | per layer | as MapLibre | no | N maps | no | yes | as MapLibre | no | unverified | yes in principle, unverified |
| Ventusky | not documented | n/a | undocumented | unverified | unverified | unverified | unverified | unverified | unverified | unverified | unverified | unverified | unverified | n/a | n/a | n/a |
| maplibre-rs | experimental, no release | Apache-2.0 or MIT | wgpu / WebGPU, wasm | no | no | no | no | vector only | no | no | yes, by design | vector only | Rust | no | unverified | no |
| MapLibre Native in the browser | FFI WebGPU browser build (June 2026 newsletter); maplibre-native-wasm WebGL1 demo | BSD-2 | WebGPU (Dawn/emdawnwebgpu) or WebGL1 via Emscripten | no | no JS custom layer documented | no | per source | as Native | no | N maps | yes, experimental | yes | no | no | unverified | no |
| PMTiles / Protomaps | spec v3 | BSD (code), ODbL (data) | n/a (tile archive) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | small | n/a |
| WeatherLayers GL | commercial | proprietary, trial | WebGL2 on deck.gl | raster, contour, particle layers | no | no | per layer | via deck | via deck | via deck | via deck | via deck | via deck | via deck | unverified | n/a |

## 3. Notes per candidate

### 3.1 MapLibre GL JS 6

- Latest 6.7.0 on 2026-09-02; 6.0.0 shipped July 2026 ("barely eight months
  after v5"). Sources: GitHub releases API
  (<https://api.github.com/repos/maplibre/maplibre-gl-js/releases>), July 2026
  newsletter (<https://maplibre.org/news/2026-08-02-maplibre-newsletter-jul-2026/>).
- v6 breaking changes from the changelog
  (<https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/CHANGELOG.md>):
  "WebGL (v1) support has been removed; WebGL2 is now required"; ESM-only
  distribution, UMD bundles no longer published; `Map` composes a `Camera`
  instead of extending it; `map.transform` removed; events are real classes;
  TypeScript target ES2022. Each is a small migration for the salvaged
  modules (`mapStyle.ts`, the MapPanel reconcile), none touches
  `FlowBlendLayer`.
- What 6.x adds that #44 wanted: `ImageSource.updateImage({image})` accepts
  a pre-decoded image (6.1.0); experimental `ImageSource.setWarp` with
  `auto`, `perspective`, `flat` (6.5.0); `StyleImageInterface`
  `renderWithWebGL` escape hatch for GPU-rendered style images (6.3.0);
  WebGL2 failure throws `GPUInitializationError` (6.7.0). Source: releases
  API above.
- Custom layers: `CustomLayerInterface` receives a `WebGL2RenderingContext`
  and a `modelViewProjectionMatrix`; the blend function on entry is
  `gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)` with premultiplied colours;
  `renderingMode` `2d` or `3d`. Source:
  <https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/>.
  This is exactly the hook `FlowBlendLayer` uses.
- Blend modes: the roadmap lists "Blending Modes" under consideration
  ("per-layer or per-feature blending modes as multiply, add, overlay,
  lighten, darken") with no date and an OpenCollective link
  (<https://maplibre.org/roadmap/maplibre-gl-js/blending-modes/>). The only
  PR found is #1191 "New paint property fill-comp-op for fill type layer",
  closed 2026-05-13 (<https://github.com/maplibre/maplibre-gl-js/pulls?q=is%3Apr+blend+raster>).
  Nothing for raster.
- WebGPU: "Graphics Modernization" is the one in-progress roadmap item
  (<https://maplibre.org/roadmap/maplibre-gl-js/>). Four phases: WebGL2
  texture and shader improvements, a Drawable architecture with uniform
  buffer objects, integer attributes and instancing, then a WebGPU backend
  with WGSL ports and WebGPU render tests
  (<https://maplibre.org/roadmap/maplibre-gl-js/graphics-modernization/>).
  No dates, no status per phase on the page. Tracking issue #2606 is open
  since 2023-05-28 with no linked PR
  (<https://github.com/maplibre/maplibre-gl-js/issues/2606>). The 6.x release
  notes show phase 1 to 3 work landing (`texelFetch` DEM lookups, integer
  vertex attributes, immutable textures implied by "texture leak fixes").
  What a custom layer looks like under a WebGPU backend is not addressed
  anywhere: **unverified** whether `CustomLayerInterface` survives as GL.
- Bundle: 1,012,272 B minified, 263,200 B gzipped for maplibre-gl 6.7.0
  (<https://bundlephobia.com/api/size?package=maplibre-gl>). Licence
  BSD-3-Clause (<https://registry.npmjs.org/maplibre-gl/latest>).
- React: `react-map-gl` (vis.gl) is third party; the experiment drives the
  map imperatively from `MapPanel.tsx`, which is the pattern the salvage
  inventory keeps.

### 3.2 deck.gl 9.3 (and 9.4 beta)

- Stable 9.3.11 (2026-08-28, "Lock luma.gl to 9.3 minor release");
  9.4.0-beta.1 (2026-08-28) and beta.3 (2026-09-03) exist, beta.2 was
  skipped. Source: <https://api.github.com/repos/visgl/deck.gl/releases>.
- What's new (<https://deck.gl/docs/whats-new>): 9.1 (2025-01-21) moved all
  shaders to uniform buffers "for WebGPU readiness" and added `useWidget` for
  React; 9.2 (2025-10-07) WebGPU "early preview" with LineLayer,
  PointCloudLayer, ScatterplotLayer, `PostProcessEffect` in interleaved mode,
  a `TimelineWidget`; 9.3 (2026-04-13) `TileLayer` `visibleMinZoom` and
  `visibleMaxZoom`, terrain-aware controllers, widget redesign.
- 9.4 on master (<https://github.com/visgl/deck.gl/blob/master/docs/whats-new.md>,
  dated July 2026 in the doc, still beta on npm): more WebGPU layers
  (ArcLayer, ColumnLayer, PathLayer, PolygonLayer, TileLayer, Tile3DLayer,
  MVTLayer; "BitmapLayer and GeoJsonLayer also gain partial WebGPU
  support"), `Deck._canvases` which "presents one shared layer stack into
  multiple HTML canvases" with `View.canvasId`, a `ViewLayout` system, and a
  new `@deck.gl/maplibre` module. It is described as the last 9.x before
  "more substantial architectural changes in v10". The `@deck.gl/maplibre`
  docs page returned 404 on fetch: **unverified** beyond the what's-new text.
- WebGPU guide (<https://deck.gl/docs/developer-guide/webgpu>): "WebGPU
  support in deck.gl v9 is still a work in progress and is not production
  ready." Enabled with `deviceProps: {type: 'webgpu', adapters:
  [webgpuAdapter]}`. Not supported on WebGPU: picking, injection-based
  extensions ("the deck.gl's WGSL shader hook list is currently empty"),
  post-processing, base map integration, attribute transitions partially.
  A custom layer needs a WGSL port.
- Compositing: `Deck` `parameters` default to premultiplied alpha
  (`blendColorSrcFactor: 'src-alpha'`, `blendColorDstFactor:
  'one-minus-src-alpha'`) and "individual layers or views can override"
  (<https://deck.gl/docs/api-reference/core/deck>). That is the per-layer
  blend mode #44 relies on. `views` takes several `View`s, so side by side
  and small multiples run in one context; 9.4's multi-canvas removes the
  single-canvas layout constraint. Base map under every panel is still the
  open point from #44.
- Bundle: @deck.gl/core 9.3.11 637,623 B / 182,311 B gzipped
  (<https://bundlephobia.com/api/size?package=@deck.gl/core>); layers,
  extensions and mapbox modules add to that. MIT.

### 3.3 CesiumJS 1.145

- 1.145 on 2026-09-01; monthly cadence (1.144 2026-08-04, 1.143 2026-07-01).
  Source: <https://api.github.com/repos/CesiumGS/cesium/releases>. npm
  `cesium` 1.145.0 depends on `@cesium/engine` ^26.3.0 and `@cesium/widgets`
  ^16.2.0, Node >= 22 (<https://registry.npmjs.org/cesium/latest>). Licence
  Apache-2.0, with issued patents noted
  (<https://github.com/CesiumGS/cesium/blob/main/LICENSE.md>).
- Imagery compositing (<https://cesium.com/learn/cesiumjs/ref-doc/ImageryLayer.html>):
  `alpha`, `dayAlpha`, `nightAlpha`, `brightness`, `contrast`, `hue`,
  `saturation`, `gamma`, `colorToAlpha` and `colorToAlphaThreshold`,
  `splitDirection`, magnification and minification filters. "No custom
  shader or advanced blend mode properties are documented for
  `ImageryLayer`." All imagery layers are composited in the globe surface
  shader in one pass, which is the GPU-side many-raster compositing the
  ticket asks for, but with a fixed normal blend.
- Custom shaders: `CustomShader` applies to `Model` and `Cesium3DTileset`
  (GLSL `vertexMain`/`fragmentMain`, texture uniforms), not to the globe
  (<https://cesium.com/learn/cesiumjs/ref-doc/CustomShader.html>).
  `Globe.material` accepts a Fabric material
  (<https://cesium.com/learn/cesiumjs/ref-doc/Globe.html>) and
  `PostProcessStage` runs a fragment shader over `colorTexture` and
  `depthTexture` with texture uniforms
  (<https://cesium.com/learn/cesiumjs/ref-doc/PostProcessStage.html>). A
  difference-of-two-rasters shader would have to live in a post-process
  stage fed by its own textures, outside the imagery pipeline.
- Time: `WebMapServiceImageryProvider` takes `times: TimeIntervalCollection`
  whose interval data are request parameters, and `clock` "is required when
  the `times` property is specified"
  (<https://cesium.com/learn/cesiumjs/ref-doc/WebMapServiceImageryProvider.html>).
  One clock drives every provider; independent time per layer means one
  provider per (layer, time) again, or a `Clock` per layer that is not the
  scene clock. Preloading adjacent intervals is not documented.
- WebGPU: the June 2025 roadmap says "Longer term, we'll explore using
  WebGPU as a generational advancement in Graphics API"
  (<https://cesium.com/blog/2025/06/23/cesium-roadmap-for-bridging-the-built-and-natural-environment/>);
  issue #4989 is open since 2017. Cesium for Unity Web ships on WebGPU but is
  a Unity build, not CesiumJS.
- Bundle: 4,890,462 B / 1,340,298 B gzipped
  (<https://bundlephobia.com/api/size?package=cesium>), five times MapLibre.
  React through Resium (third party).

### 3.4 OpenLayers 10.10

- 10.10.0 on 2026-07-27: "Text support in the WebGL vector renderers, plus
  stale tile handling for WebGL tile layers", GeoZarr "selection of
  non-spatial dimensions for time series support", WMTS tile matrix limits
  honoured, `TextPath` now requires `Intl.Segmenter`. 10.9.0 (2026-04-15)
  multi-group GeoZarr bands and WebGL precision fixes; 10.8.0 (2026-02-11)
  `OGCMap` and the experimental `GeoZarr` source; 10.7.0 (2025-11-04) full
  `Map` in a Web Worker on `OffscreenCanvas`, instanced WebGL rendering.
  Source: <https://api.github.com/repos/openlayers/openlayers/releases>.
  npm `ol` 10.10.0, BSD-2-Clause, depends on `geotiff` and `zarrita`
  (<https://registry.npmjs.org/ol/latest>,
  <https://github.com/openlayers/openlayers/blob/main/LICENSE.md>).
- Raster control: `WebGLTileLayer` takes a `style` of expressions and a
  `sources` array ("Can either be an array of sources, or a function that
  expects an extent and a resolution ... and returns an array of sources")
  for band math across rasters, with a texture `cacheSize` default 512
  (<https://openlayers.org/en/latest/apidoc/module-ol_layer_WebGLTile-WebGLTileLayer.html>).
  The shaded-relief example samples neighbouring pixels with
  `['band', index, xOffset, yOffset]` and computes slope, aspect and sun
  incidence in the style
  (<https://openlayers.org/en/latest/examples/webgl-shaded-relief.html>).
  This is the closest thing in any open library to a client-side raster
  colour and difference pipeline without writing GLSL; a signed difference
  of two GeoMet fields from two COG sources is a style expression, not a
  custom layer. The `ol/style/webgl` doc page returned 404 on fetch: the
  full operator list is **unverified** here beyond what the examples use.
- Compare: the WebGL layer-swipe example enables `gl.SCISSOR_TEST` in
  `prerender` and disables it in `postrender` on one map
  (<https://openlayers.org/en/latest/examples/webgl-layer-swipe.html>); the
  canvas version clips the 2D context the same way
  (<https://openlayers.org/en/latest/examples/layer-swipe.html>). The same
  example notes that several layers can share one context by giving them the
  same `className` (`canvas3d`), otherwise each WebGL layer has its own
  canvas and context. Per-layer elements mean CSS `mix-blend-mode` between
  layers is plausible but not documented: **unverified**. Side by side
  and small multiples remain N maps.
- Escape hatch: `prerender`/`postrender` hand the layer's raw `gl`;
  `Layer` accepts a custom `render` function returning an element
  (<https://openlayers.org/en/latest/apidoc/module-ol_layer_Layer-Layer.html>);
  the `WebGLLayerRenderer` base class page returned 404 on fetch, so the
  custom-renderer contract is **unverified** from the docs, though the
  `webgl-layer-swipe` example proves the raw context is reachable.
- WebGPU: none. Community experiments (wgpu-layers) only.
- Bundle: 295,764 B / 84,476 B gzipped for the whole package, tree-shakeable
  by module (<https://bundlephobia.com/api/size?package=ol>). No first-party
  React binding.

### 3.5 Kepler.gl and loaders.gl

- Kepler.gl: last stable v3.2.0 on 2025-08-21; 3.3.0-alpha.10 on 2026-09-02
  ("async loaders.gl 4.4 loader registry"). Sources:
  <https://api.github.com/repos/keplergl/kepler.gl/releases>,
  <https://registry.npmjs.org/kepler.gl>. It is a Redux application over
  deck.gl, not a rendering engine; its time is a filter over rows, not a
  layer coordinate. It brings nothing for a raster Layer stack that deck.gl
  alone does not, and it would replace the shell, which the map notes keep
  fresh.
- loaders.gl: 4.4.6 (2026-09-02), 5.0.0-alpha.5 (2026-08-30, GeoArrow
  conversions) (<https://api.github.com/repos/visgl/loaders.gl/releases>).
  Relevant only as the loader layer under deck (`TileLayer`, `_WMSLayer`);
  not a candidate on its own.

### 3.6 Mapbox GL JS v3

- 3.30.0 on 2026-09-03 (terrain extracted from the core ESM module, max
  sources raised to 64); 3.29.0 on 2026-08-20 added `raster-color-scale`
  ("log" for long-tailed data) and `raster-allow-draping`. Source:
  <https://api.github.com/repos/mapbox/mapbox-gl-js/releases>.
- Raster features from the changelog
  (<https://raw.githubusercontent.com/mapbox/mapbox-gl-js/main/CHANGELOG.md>):
  3.0.0 "raster colorization via `raster-color` paint properties"; 3.1.0
  `raster-elevation`; 3.3.0 "`raster-array` source type, representing a new
  experimental Mapbox Raster Tile format which encodes series of tiled raster
  data" and "`raster-particle` layer which animates particles"; 3.21.0
  experimental `line-blend-mode` (`additive`, `multiply`); 3.29.0
  `line-blend-additive-clamp`. No raster blend mode. The style-spec sources
  page describes `raster-array` as for "Mapbox Tiling Service (MTS)
  tilesets" with the format marked experimental
  (<https://docs.mapbox.com/style-spec/reference/sources/>); the particle
  example uses `mapbox://rasterarrayexamples.gfs-winds`
  (<https://docs.mapbox.com/mapbox-gl-js/example/raster-particle-layer/>).
  Whether self-hosted MRT tiles work is **unverified**; the format spec is
  published but the source docs point at MTS.
- Licence: `package.json` says "SEE LICENSE IN LICENSE.txt"
  (<https://registry.npmjs.org/mapbox-gl/latest>); the licence requires "a
  current active Mapbox account", use "only with the relevant Mapbox
  product(s)", forbids modifying billing and data-collection code, and the
  SDK "sends limited de-identified location and usage data"
  (<https://raw.githubusercontent.com/mapbox/mapbox-gl-js/main/LICENSE.txt>).
  Billing is per map load, a session of up to 12 hours
  (<https://docs.mapbox.com/mapbox-gl-js/guides/pricing/>). Using it over
  OpenFreeMap tiles as the experiment does today is outside the licence.
- Bundle 1,817,145 B / 498,408 B gzipped
  (<https://bundlephobia.com/api/size?package=mapbox-gl>). The custom layer
  interface is the same one MapLibre forked, so `FlowBlendLayer` would run
  unchanged; that is the only thing that carries.

### 3.7 Google Maps: WebGLOverlayView and Photorealistic 3D Tiles

- `WebGLOverlayView` gives "direct access to the same WebGL rendering
  context Google Maps Platform uses to render the vector basemap", requires a
  map ID with the vector map enabled, and demands GL state be reset after
  each draw (<https://developers.google.com/maps/documentation/javascript/webgl/webgl-overlay-view>).
  It is a raw-GL hatch under a proprietary basemap; no raster styling, no
  time, no WebGPU mentioned.
- Photorealistic 3D Tiles are OGC 3D Tiles served by the Map Tiles API for
  "your own 3D Tiles renderer, or ... an open source library" (CesiumJS,
  three.js via 3DTilesRendererJS, deck.gl `Tile3DLayer`), EEA billing
  addresses lose some content since 2025-07-08
  (<https://developers.google.com/maps/documentation/tile/3d-tiles-overview>).
  Policies forbid pre-fetching or caching beyond HTTP cache headers and
  require Google attribution; overlaying your own data is allowed if not
  derived from the tiles
  (<https://developers.google.com/maps/documentation/tile/policies>). The
  3D Maps `Map3DElement` API offers markers, polylines and glTF models, with
  no documented raw-GL or raster overlay
  (<https://developers.google.com/maps/documentation/javascript/3d-maps-overview>).
- For a night-sky and marine-fog map over the Avalon Peninsula a
  photorealistic city mesh adds nothing, the no-cache policy fights the
  three-steps-resident playback shape from #44, and both products are billed
  and proprietary. Not a candidate.

### 3.8 three.js and Babylon.js with geospatial plugins

- three.js r185 (2026-07-01; npm 0.185.1): `WebGPURenderer` with clustered
  lighting, TSL `storageTexture3D` and `textureGather`; r184 (2026-04-16)
  TSL compile 3x faster; r183 (2026-02-20) reversed depth
  (<https://api.github.com/repos/mrdoob/three.js/releases>). 725,907 B /
  182,364 B gzipped for the default bundle
  (<https://bundlephobia.com/api/size?package=three>). MIT. React via
  react-three-fiber.
- Babylon.js 9.23.0 (2026-08-27) with WebGPU maintenance items
  (<https://api.github.com/repos/BabylonJS/Babylon.js/releases>); @babylonjs/core
  7,847,776 B / 1,734,304 B gzipped (<https://bundlephobia.com/api/size?package=@babylonjs/core>).
  Apache-2.0.
- Both are production WebGPU engines with full blending, custom materials,
  scissor and multi-viewport in one renderer: every rendering axis in the
  ticket is a yes. Neither is a map. Tiles, projections, label placement,
  attribution, gesture handling and the base map are all yours or a
  plugin's.
- Plugins: three-geo 1.4.5 was published 2022-06-18 against three ^0.138
  (<https://registry.npmjs.org/three-geo/latest>); threebox-plugin 2.2.7 on
  2022-06-04 as "a Three.js plugin for Mapbox GL JS, using the
  CustomLayerInterface" (<https://registry.npmjs.org/threebox-plugin/latest>).
  Both are dormant. Giro3D 2.0.4 (v2.0.0 2026-03-31, v1.0.0 2025-10-27)
  is MIT, peer-depends on three ^0.180 and ol ^10.8, and its `ColorLayer`
  has `opacity`, `blendingMode` (default `BlendingMode.Normal`; the enum's
  other values were not in the fetched source: **unverified**), brightness,
  contrast, saturation and `elevationRange`
  (<https://registry.npmjs.org/@giro3d/giro3d/latest>,
  <https://gitlab.com/giro3d/giro3d/-/raw/main/src/core/layer/ColorLayer.ts>,
  <https://gitlab.com/giro3d/giro3d/-/raw/main/CHANGELOG.md>). It is the one
  three.js geospatial framework with a per-layer blend mode on rasters and
  OpenLayers sources (WMS, WMTS, COG) feeding a three scene, plus a `Globe`
  entity; it has no WebGPU (three r180 WebGL path), no React binding and no
  time model. iTowns 2.46.0 (2025-10-07) packs raster textures into arrays,
  tracks three r170 to r182, CeCILL-B and MIT, no WebGPU
  (<https://api.github.com/repos/iTowns/itowns/releases>,
  <https://github.com/iTowns/itowns>). three-geospatial (Takram) core 0.9.1
  (2026-05-06) is atmosphere, clouds and globe geometry on WebGPU and TSL
  (<https://api.github.com/repos/takram-design-engineering/three-geospatial/releases>);
  it is a sky renderer for Photorealistic tiles, not a map.
- `FlowBlendLayer` on three.js is a `ShaderMaterial` on a screen quad with
  the map's matrix supplied by whichever plugin owns the camera: a port of
  the GLSL, not a reuse of the class, and the eight GPU tests would need a
  new harness.

### 3.9 Leaflet with WebGL plugins

- Leaflet latest is still 1.9.4 (2023-05-18); 2.0.0-alpha.1 (2025-08-16) is
  ESM-only, PointerEvents, no global `L`, factory methods removed; no 2.0
  stable or beta tag on npm (<https://api.github.com/repos/Leaflet/Leaflet/releases>,
  <https://registry.npmjs.org/leaflet>). BSD-2-Clause, 148,515 B / 42,736 B
  gzipped (<https://bundlephobia.com/api/size?package=leaflet>).
- WebGL is plugin territory: `Leaflet.TileLayer.GL` ("custom WebGL shaders
  to each tile"), `Leaflet.TileLayer.GLOperations` ("filter and do
  calculations on multiple layers"), `Leaflet.TileLayer.GLColorScale`,
  `leaflet-velocity`, `Leaflet.glify`, and `maplibre-gl-leaflet` which puts
  a whole MapLibre map in as a layer (<https://leafletjs.com/plugins.html>,
  <https://maplibre.org/maplibre-gl-js/docs/plugins/>). Each plugin layer is
  its own canvas and context; there is no shared scene, so a five-raster
  stack is five contexts and blend between them is CSS. Windy's LeafletGL
  (3.12) is the proof that Leaflet's API on top of MapLibre's renderer is
  the way to get one context, and it is Windy's, not a public library.

### 3.10 Tangram and harp.gl

- Tangram 0.22.0 on 2024-12-17, MIT, a Leaflet plugin whose scene file
  carries GLSL blocks (<https://github.com/tangrams/tangram/releases>,
  <https://registry.npmjs.org/tangram>). No 2025 to 2026 release, no
  WebGPU, no raster compositing beyond tile layers. Maintenance mode.
- harp.gl archived 2023-03-08; HERE "stopping its engagement on Harp.gl
  starting 03/01/2022" in favour of the commercial HERE Maps API
  (<https://github.com/heremaps/harp.gl>). Not a candidate.

### 3.11 Windy and Ventusky

- Windy documents LeafletGL: "a custom mapping library" that combines
  Leaflet and MapLibre GL JS, with MapLibre "trimmed to only the needed
  features" and the Leaflet API "rewritten in TypeScript"; a `CanvasLayer`
  renders with a 2D context and the image "is automatically transferred to a
  WebGL texture and placed inside MapLibre's layer stack", plus
  `CanvasTileLayer`, `TileCache` and `ReferenceCountedCache`
  (<https://windycom.github.io/LeafletGL/docs/>). The GitHub repo returned
  404 on fetch, so licence, npm availability and version are **unverified**;
  the Map Forecast API is Leaflet 1.4.x, free for development only,
  professional tier paid, rendering technology not stated
  (<https://api.windy.com/map-forecast/docs>). The lesson is architectural:
  Windy answers "many weather rasters over a vector base" with MapLibre's
  custom layer stack and CPU-rendered canvases uploaded as textures, which
  is the shape the experiment already has.
- Ventusky publishes model resolutions and nothing about rendering
  (<https://www.ventusky.com/help>). **Unverified** beyond "WebGL" in
  secondary write-ups; not a source of technique.
- Adjacent: WeatherLayers GL is a commercial deck.gl layer pack (raster,
  contour, high/low, grid, particle) on WebGL2, integrating with MapLibre,
  Mapbox, Leaflet, OpenLayers and Google Maps
  (<https://weatherlayers.com/>): evidence that deck.gl is where weather
  raster tooling accumulates. Fluid Earth (Byrd Polar, MIT) is a custom
  WebGL2 app with no map library
  (<https://github.com/byrd-polar/fluid-earth>), an application not a
  dependency.

### 3.12 2025 to 2026 entrants: Rust, WASM, WebGPU-first, PMTiles

- maplibre-rs: "Rust-based WebGPU map renderer", experimental badge, "The
  current implementation serves as a proof-of-concept ... It is unclear
  whether the high-performance requirements of rendering maps using vector
  graphics are achievable using the current stack"; vector tiles only;
  Apache-2.0 or MIT (<https://github.com/maplibre/maplibre-rs>). February
  2026 newsletter: text labels via an SDF plugin
  (<https://maplibre.org/news/2026-03-03-maplibre-newsletter-february-2026/>).
  Not usable.
- MapLibre Native: the WebGPU backend (wgpu and Dawn) released October 2025
  with a web target planned because "a WebGPU backend promises significantly
  better performance" over the WebGL1/2 Emscripten path
  (<https://maplibre.org/roadmap/maplibre-native/webgpu/>); February 2026
  newsletter reports experimental WebGPU backends for Android and iOS; June
  2026 newsletter: "MapLibre Native FFI project now features browser support
  using the WebGPU backend" (<https://maplibre.org/news/2026-07-04-maplibre-newsletter-jun-2026/>).
  birkskyum/maplibre-native-wasm demos a WebGL1 Emscripten build
  (<https://birkskyum.github.io/maplibre-native-wasm/>). None of these
  exposes a JS custom-layer interface, and there is no npm package, bundle
  size or API surface to evaluate: **unverified** as a product. It is the
  most likely route by which MapLibre gets WebGPU in a browser before GL JS
  phase 4, and the least likely to keep a raw-GL hatch.
- No other WebGPU-first map engine with a release was found; searches
  returned only maplibre-rs and general WebGPU articles.
- PMTiles is at spec v3, BSD code, integrates with MapLibre by
  `addProtocol`, and with OpenLayers and Leaflet
  (<https://docs.protomaps.com/pmtiles/>,
  <https://maplibre.org/maplibre-gl-js/docs/plugins/>). It is a base-map and
  static-tile delivery answer, orthogonal to the renderer choice; it would
  let the experiment self-host the OpenFreeMap-style vector base and, if the
  API ever serves raster tiles per time step, publish each step as one
  PMTiles archive. Not a candidate, a tool.

## 4. Ranked shortlist

Ranking is against the ticket's axes for this experiment (five-plus rasters
with independent time, compare arrangements, an open licence, React and Vite,
and keeping the tested salvage), not against general merit.

1. **MapLibre GL JS 6 + deck.gl 9.3, rasters drawn through deck.** Open,
   the only pairing with per-layer blend factors on rasters, one-context
   multi-view compare, a custom-layer hatch on both sides, a first-party React
   binding on the deck side, and the salvage runs unchanged. WebGPU arrives
   through deck's preview first and MapLibre's phase 4 later; neither is
   needed for the Map view. Gaps: no native time, no client-side band math
   without GLSL, no base map under every deck view.
2. **OpenLayers 10 (alone, or as the imagery engine under a MapLibre base
   via maplibre-gl-leaflet-style embedding).** The best open raster styling
   language (band expressions across multiple sources, GeoTIFF and GeoZarr
   client-side, time via GeoZarr dimensions), single-map scissor swipe, raw
   `gl` in hooks, 84 KB. Loses: one context shared across layers is opt-in
   and undocumented for blending, no WebGPU, no React binding, N maps for
   small multiples, and the whole MapLibre style, `mapStyle.ts` and
   `FlowBlendLayer` matrix path are a port.
3. **CesiumJS 1.145.** Native time and split swipe, one-pass imagery
   compositing, Apache-2.0. Loses on the axes that matter most here: no
   blend modes and no shader on imagery, 1.3 MB gzipped, one clock, WebGPU
   "longer term", and a 3D globe is the wrong default for a 2D forecast
   workbench.
4. **Giro3D 2.0 (three.js + OpenLayers sources).** The only framework with a
   raster `blendingMode` on layers and OL sources in a three scene; MIT.
   Small community, three WebGL path only, no React, no time, enum
   unverified.
5. **three.js r185 or Babylon.js 9 with a hand-built map.** Everything the
   GPU can do including production WebGPU; nothing a map needs. Only sensible
   if the Map view were reconceived as a rendered scene without a styled
   vector base.
6. **Mapbox GL JS 3.30.** Technically the best raster feature set
   (`raster-color`, `raster-array`, `raster-particle`) but proprietary,
   billed, token-gated and tied to Mapbox tiling for the array format; the
   experiment's OpenFreeMap base would breach the licence.
7. **Leaflet 1.9 with GL plugins, Tangram, Kepler.gl, Windy LeafletGL.**
   Either one context per plugin, dormant, an application, or not
   published.
8. **Google WebGLOverlayView and Photorealistic 3D Tiles, harp.gl,
   maplibre-rs, MapLibre Native in the browser.** Proprietary, archived, or
   experimental without a JS API.

## 5. Recommendation on the stack lock

**Keep the lock: React, Vite, MapLibre GL JS, deck.gl.** Revise the pins
and the division of labour, not the libraries.

What the experiment would gain by switching, per serious candidate, and what
it would have to port (salvaged modules from
`web-salvage-inventory.md`):

| Switch to | Gain | Port |
|---|---|---|
| OpenLayers 10 | Client-side band math and colour ramps as style expressions; COG and GeoZarr read in the browser (no TiTiler for stored grids); single-map scissor swipe for every raster layer; 84 KB core | `mapStyle.ts` (MapLibre style over OpenFreeMap becomes an `ol-mapbox-style` layer or a raster base), `FlowBlendLayer.ts` (new renderer class, new matrix, 25 tests re-harnessed), the MapPanel imagery pipeline and reconcile (source model differs), station layers (from deck to OL WebGL points), theme repaint. Pure modules (playback, scrubber axis, tier boundary, field families, evidence class, api.ts) unchanged. |
| CesiumJS | Native `Clock` and WMS `times`, `splitDirection` swipe, one-pass imagery compositing | Everything map-side, plus loss of blend modes and the flow shader path entirely; `FlowBlendLayer` has no home. |
| Giro3D | Raster `blendingMode` and OL sources in a three scene | Everything map-side; `FlowBlendLayer` as a three material; no React binding; dependency on two large libraries. |
| Mapbox GL JS 3 | `raster-color`, `raster-array`, `raster-particle` | Nothing in code; everything in licence, billing and base-map hosting. |

None of these gains outweighs the port. The gap the ticket is really about,
blend modes and independent time on rasters, is closed on the current stack
by drawing the rasters through deck.gl (one context, per-layer `parameters`,
`views` for compare) and keeping MapLibre for the vector base, labels and
gestures; that is what #44 concluded and nothing surveyed here changes it.

Concrete adjustments to carry into the front-end proposal:

- Pin `maplibre-gl` to 6.x (ESM-only, WebGL2-only, `updateImage({image})`,
  `setWarp`), and `@deck.gl/*` to 9.3.x now with an eye on 9.4 for
  multi-canvas compare and the `@deck.gl/maplibre` module once it is stable.
- Treat WebGPU as out of scope for the rebuild. deck's own guide says not
  production-ready; MapLibre has no date; a custom layer under either WebGPU
  path is a WGSL rewrite of `FlowBlendLayer`, so the shader should be kept
  small and its pure helpers (`envelopeTerm`, `hermiteDisplacement`,
  `visibilityWeights`, `blendReference`) kept out of the GLSL.
- Time stays a client-side store (the timeline store the salvage inventory
  already names), not a library feature; no candidate's native time model
  handles per-layer cadences and run selection the way the prior-art ticket
  (#45) asks.
- One bounded prototype is worth running before the proposal is final:
  OpenLayers `WebGLTile` with two COG sources and a difference expression
  against the same pair drawn through deck `BitmapLayer` with a two-texture
  shader, to measure whether expression-based band math changes the API
  contract (serving COGs instead of rendered PNGs). If it does not change
  the contract, the case for OpenLayers closes.

## 6. What this leaves open

- Whether `CustomLayerInterface` survives MapLibre's WebGPU phase 4 as a
  GL hook, a WGSL hook, or both; nothing published says.
- The actual contents of deck.gl 9.4's `@deck.gl/maplibre` module and
  whether multi-canvas gives a base map under every compare panel.
- Whether Mapbox's MRT `raster-array` format can be self-hosted under
  MapLibre by an `addProtocol` decoder, which would bring multi-band time
  series tiles to the open stack without the licence.
- Giro3D's `BlendingMode` enum values and OpenLayers' full WebGL style
  operator list, both unfetched.
- Windy LeafletGL's licence and availability.
