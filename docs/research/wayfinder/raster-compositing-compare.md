> Historical recovery: restored from `30792afafa1f` during the September 8 unused-work audit. This retains the original September 3 research; version, licensing, performance and product claims have not been revalidated. Current accepted contracts and implemented behavior take precedence over its recommendations.

Non-normative research, 2026-09-03. Not a spec, not a design decision.

# Multi-layer raster compositing and compare on MapLibre and deck.gl

Answers wayfinder ticket
[#44](https://github.com/TusharSariya/Astraeus/issues/44) (part of map
[#38](https://github.com/TusharSariya/Astraeus/issues/38)): the proven
techniques and limits for drawing many raster layers with independent time
steps on MapLibre GL JS and deck.gl, with WMS tiles (GeoMet) and COG tiles
(TiTiler); per-layer opacity and blend modes; swipe and side-by-side compare;
small multiples with synchronised cameras; and smooth playback with a stack
of five or more rasters. Each technique is costed in requests, GPU memory and
frame time, and each compare arrangement is marked feasible or not without
forking the map library.

Sources are the MapLibre GL JS and style-spec docs and source on `main`
(checked against the `v5.7.1` tag the experiment pins), deck.gl docs and
source at 9.3, TiTiler docs, GeoMet WMS docs, and the plugin sources named
inline. Versions in use in `experiments/st-johns-weather-map/web/package.json`:
`maplibre-gl ^5.7.1`, `@deck.gl/* ^9.1.14`. Latest releases on 2026-09-03:
maplibre-gl-js v6.7.0, deck.gl v9.3.11 (GitHub releases API). Where v6
behaviour differs from v5.7.1 it is called out. No experiment code was
changed; the numbers in section 6 are arithmetic on documented texture
formats and tile counts, not measurements.

## 1. Summary

- **Opacity is free; blend modes are not.** MapLibre's raster layer has
  `raster-opacity` (plus brightness, contrast, saturation, hue) but only
  normal premultiplied-alpha blending. Per-layer blend modes are an open
  issue since 2020 ([#48](https://github.com/maplibre/maplibre-gl-js/issues/48));
  the only PR in flight (Aug 2026) covers line and fill, not raster. Blend
  modes for rasters are obtained without forking by drawing the raster
  through deck.gl (`parameters` with luma.gl blend factors, works overlaid
  and interleaved) or a MapLibre custom layer that sets its own `blendFunc`
  (what `FlowBlendLayer.ts` already does).
- **Colour mapping is not a MapLibre feature.** The style spec has no
  `raster-color`; it must come from the server (TiTiler `colormap_name` /
  `rescale`, or the API's own `/raster`) or from a custom shader.
- **Independent time steps are a per-source problem.** Every (layer, time)
  pair is its own MapLibre source or deck `TileLayer` instance. GeoMet WMS
  accepts one `TIME` per request and offers no WMTS, so tile requests go
  through GetMap with a per-tile BBOX. MapLibre loads tiles for any source
  whose layer is not hidden, even at `raster-opacity: 0`, and does not draw
  a layer at opacity 0, which is the cheapest prefetch mechanism the library
  offers. deck.gl keeps a hidden `TileLayer`'s cache when `visible: false`.
- **Swipe without forking:** two `Map` instances with CSS `clip` and
  `syncMove` (maplibre-gl-compare, maplibre-gl-swipe) is the proven
  arrangement, at roughly double the requests and GPU memory. A single-map
  swipe is possible for deck-drawn rasters (MaskExtension, or scissor in a
  custom layer) but not for native MapLibre raster layers.
- **Side by side and small multiples:** N `Map` instances synced by
  `syncMove` (it accepts any number of maps) is the only arrangement that
  keeps a base map under every panel; deck's multi-view can drive N raster
  panels with one context but MapboxOverlay syncs only one view to the base
  map, and reverse-controlled multi-view is the documented path for that.
- **Playback budget:** five rasters, one viewport, 512-px max edge,
  RGBA8 with mipmaps is about 1.4 MiB per frame per layer; 24 time steps
  preloaded for five layers is about 165 MiB of texture, which is too much
  to hold. A ring of three steps per layer (about 20 MiB) plus decoding
  ahead with `createImageBitmap` is the workable shape. Per-frame draw cost
  is one draw call per visible tile per raster layer, fragment-bound, and is
  not what limits playback; request latency and texture upload are.

## 2. MapLibre GL JS raster facts

### 2.1 Paint properties and blending

From the style spec `v8.json` (`paint_raster`): `raster-opacity` (default 1),
`raster-hue-rotate` (0), `raster-brightness-min` (0), `raster-brightness-max`
(1), `raster-saturation` (0), `raster-contrast` (0), `raster-resampling`
(`linear` | `nearest`, default `linear`), `raster-fade-duration` (300 ms).
All are supported since JS 0.10.0. There is no `raster-color*` property in
MapLibre's spec (that family is Mapbox v3 only); the nearest thing is the
`color-relief` layer type (JS 5.6.0), which colours DEM sources, not
arbitrary rasters. The word "blend" appears only in sky and fog properties.
Source: <https://github.com/maplibre/maplibre-style-spec/blob/main/src/reference/v8.json>,
<https://maplibre.org/maplibre-style-spec/layers/>.

Blending is fixed. `draw_raster.ts` draws every visible tile of a layer with
one `program.draw` using `painter.colorModeForRenderPass()` (the normal
premultiplied blend), a depth mode that is read-write only when
`raster-opacity === 1` and read-only otherwise, and returns early when
`raster-opacity` is 0. Opacity, brightness, contrast, saturation, hue and the
parent fade mix are uniforms. Source:
<https://github.com/maplibre/maplibre-gl-js/blob/main/src/webgl/draw/draw_raster.ts>
(v5.7.1: `src/render/draw_raster.ts`, same shape).

Per-layer blend modes are issue
[#48](https://github.com/maplibre/maplibre-gl-js/issues/48), open since
2020-12-28 with a bounty
([maplibre/maplibre#269](https://github.com/maplibre/maplibre/issues/269))
and a roadmap page
<https://maplibre.org/roadmap/maplibre-gl-js/blending-modes/>. The one PR
referencing it, [#8073](https://github.com/maplibre/maplibre-gl-js/pull/8073)
"feat: add `{line,fill}-layer-blend` support" (opened 2026-08-02, open,
awaiting a TSC vote), does not touch raster. The last comment on #48
(2026-05-12) points at the multi-canvas CSS `mix-blend-mode` workaround
(<https://github.com/wipfli/hillshade-multiply-blending>): one MapLibre
instance per blended layer, canvases stacked and synced.

Stacked normal blending composes as `1 - (1-a)(1-b)`, which is what
`MapPanel.tsx` already discloses as "display compositing" for its blend pairs.

### 2.2 Custom layers

`CustomLayerInterface.render` receives the `WebGL2RenderingContext` and the
MVP matrix; MapLibre guarantees the main framebuffer is bound, depth and
clipping are set to let other layers draw over, and blending is
`gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)` expecting premultiplied
colours; the layer "cannot make any other assumptions about the current GL
state". A layer may set its own blend function (the docs show the
non-premultiplied variant). `renderingMode: '2d'` shares no depth buffer;
`prerender` may render to its own framebuffer first. Source:
<https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/>.
`FlowBlendLayer.ts` follows this exactly (`renderingMode = '2d'`, own
`blendFuncSeparate`, own textures). This is the one MapLibre-native route
to any blend mode: a custom layer owns its blend state for its own draw.

### 2.3 Image sources (what the experiment uses today)

`ImageSource.updateImage` replaces the image and optionally the coordinates.
On `main` (v6) it accepts either `url` or a pre-decoded `image`
(`HTMLImageElement`, `HTMLCanvasElement`, `ImageBitmap`, `ImageData`), skips
the network for the decoded case, and updates the existing texture
(`texture.update`). On the pinned v5.7.1 `updateImage` takes `url` only,
reloads through `ImageRequest`, nulls the texture and creates a new one on
next prepare. Both versions carry the note: "To avoid having the image flash
after changing, set the `raster-fade-duration` paint property on the raster
layer to 0". Sources:
<https://maplibre.org/maplibre-gl-js/docs/API/classes/ImageSource/>,
<https://github.com/maplibre/maplibre-gl-js/blob/v5.7.1/src/source/image_source.ts>.
`MapPanel.tsx` already sets `raster-fade-duration: 0` and requests one
viewport image per layer per frame, capped at 1024 px on the long edge
(`RENDERED_REQUEST_MAX_EDGE_PX`) and DPR 2 (`renderPixelSize`).

### 2.4 Raster tile sources, cache and requests

- Source `tileSize` defaults to 512; `volatile: true` disables local tile
  caching; `bounds` limits the tiles requested. Source:
  <https://maplibre.org/maplibre-style-spec/sources/>.
- `RasterTileSource.setTiles(tiles)` swaps the URL template and reloads;
  `setPremultiplyAlpha(false)` keeps exact RGBA when alpha is data. Source:
  <https://maplibre.org/maplibre-gl-js/docs/API/classes/RasterTileSource/>.
- Tile cache per source: `updateCacheSize` sets the out-of-view LRU to
  `floor(approxTilesInView * maxTileCacheZoomLevels)` (default 5), capped by
  `maxTileCacheSize` if given. Evicted tiles have their textures destroyed
  through `TileCache.onRemove`. Sources:
  <https://github.com/maplibre/maplibre-gl-js/blob/main/src/tile/tile_manager.ts>
  (`updateCacheSize`), <https://github.com/maplibre/maplibre-gl-js/blob/main/src/tile/tile_cache.ts>,
  <https://maplibre.org/maplibre-gl-js/docs/API/type-aliases/MapOptions/>.
- A source loads tiles only while `used`, and `used` is set per frame for
  every layer that is not hidden at the current zoom (visibility and zoom
  range, not opacity). Sources: `style.ts` `_updateSources` at v5.7.1
  (<https://github.com/maplibre/maplibre-gl-js/blob/v5.7.1/src/style/style.ts>),
  `tile_manager.ts` `update` (`if (!this.used && !this.usedForTerrain) idealTileIDs = []`).
  Consequence: a raster layer at `raster-opacity: 0` keeps loading and
  caching tiles and costs no draw call; a layer at `visibility: none` stops
  loading and lets its tiles age out of the LRU.
- Image requests are throttled globally: `MAX_PARALLEL_IMAGE_REQUESTS: 16`,
  `MAX_PARALLEL_IMAGE_REQUESTS_PER_FRAME: 8`, adjustable with
  `setMaxParallelImageRequests`. Sources:
  <https://github.com/maplibre/maplibre-gl-js/blob/main/src/util/config.ts>,
  <https://maplibre.org/maplibre-gl-js/docs/API/functions/setMaxParallelImageRequests/>.
- Raster tile textures are uploaded with mipmaps (`useMipmap: true` in
  `raster_tile_source.ts`), so GPU memory is 4/3 of the RGBA8 size.
- Parent/child cross-fade uses `raster-fade-duration` and the tiles'
  `timeAdded`; `fadeDuration === 0` disables all fading (`getFadeProperties`
  in `draw_raster.ts`). For time playback this must be 0 or every new time
  step fades in over 300 ms.
- `addProtocol` registers a custom scheme whose handler receives the request
  and an `AbortController` and returns an `ArrayBuffer`, on the main thread;
  it is how an in-memory or IndexedDB tile cache shared across time steps
  and sources can sit under MapLibre without forking. Source:
  <https://maplibre.org/maplibre-gl-js/docs/API/functions/addProtocol/>.
- `canvasContextAttributes` defaults: `antialias: false`,
  `powerPreference: 'high-performance'`, `preserveDrawingBuffer: false`;
  `maxCanvasSize` `[4096, 4096]`. Source: MapOptions page above.

## 3. deck.gl raster facts (9.1 to 9.3)

### 3.1 BitmapLayer and Layer parameters

`BitmapLayer` takes `image` (URL, data URL, pixel source, luma.gl `Texture`
or a Promise of one), `bounds` (`[left, bottom, right, top]` or four
corners), `desaturate`, `tintColor`, `transparentColor`, `textureParameters`
(`minFilter`/`magFilter` `'nearest'` for pixelated), and picking returns the
`bitmap.pixel` under the cursor. Source:
<https://deck.gl/docs/api-reference/layers/bitmap-layer>.

Every layer has `opacity` (gamma-corrected so it looks linear), `visible`
(preferred over removal, keeps buffers), and `parameters`, "values for GPU
parameters such as blending mode, depth testing etc." applied only while that
layer draws. Sources: <https://deck.gl/docs/api-reference/core/layer>,
<https://deck.gl/docs/developer-guide/performance>. In v9 the names are
luma.gl/WebGPU strings, for example
`blendColorOperation: 'add', blendColorSrcFactor: 'src-alpha', blendColorDstFactor: 'one'`
(additive) from the upgrade guide
<https://deck.gl/docs/upgrade-guide>; the full value sets are
`BlendOperation` `add | subtract | reverse-subtract | min | max` and
`BlendFunction` `zero | one | src | one-minus-src | src-alpha | one-minus-src-alpha | dst | one-minus-dst | dst-alpha | one-minus-dst-alpha | src-alpha-saturated | constant | one-minus-constant`
(<https://luma.gl/docs/api-reference/core/parameters>). That yields
multiply (`dst`, `zero`), screen (`one`, `one-minus-src`), additive, and
`min`/`max` per layer with no shader work. Photoshop-style overlay or soft
light are not fixed-function and need a custom shader with a copy of the
destination.

### 3.2 TileLayer

Defaults from `tile-layer.ts`: `tileSize 512`, `maxCacheSize null` (which
resolves to `5 * selectedTiles.length` in `Tileset2D`), `maxCacheByteSize
null` (needs `byteLength` on the tile data), `refinementStrategy
'best-available'`, `maxRequests 6` concurrent `getTileData` calls per layer,
`debounceTime 0`, `zoomOffset 0`; 9.3 adds `visibleMinZoom`/`visibleMaxZoom`.
`getTileData({index, id, url, bbox, signal})` may be aborted when more than
`maxRequests` are in flight and some are off screen. The cache keeps loaded
tiles in memory when off screen; `onTileUnload` fires on eviction. Image
tiles are drawn by returning a `BitmapLayer` from `renderSubLayers` with
`bounds` from `tile.bbox`. Sources:
<https://deck.gl/docs/api-reference/geo-layers/tile-layer>,
<https://github.com/visgl/deck.gl/blob/master/modules/geo-layers/src/tile-layer/tile-layer.ts>,
<https://github.com/visgl/deck.gl/blob/master/modules/geo-layers/src/tileset-2d/tileset-2d.ts>.

Changing `data` (the URL template) clears the tile set and reloads, which
flickers; the documented mitigations are `refinementStrategy` (shows cached
ancestors or descendants while loading) or keeping the old layer instance
until the new one has loaded. Sources:
<https://github.com/visgl/deck.gl/discussions/5502>,
<https://github.com/visgl/deck.gl/issues/6448>. For time playback that means
one `TileLayer` instance per time step, toggled with `visible`, not one
instance whose URL changes.

### 3.3 WMSLayer (experimental)

`_WMSLayer` fetches a single image covering the viewport per view change,
takes `data`, `serviceType` (`wms` | `template` | `auto`), `layers`, `srs`
(`auto` picks EPSG:3857 under a `MapView`), and reports
`onImageLoadStart/onImageLoad/onImageLoadError/onMetadataLoad`. Limits:
"each instance only supports being rendered in one view", does not work well
with pitch, and not with non-geospatial views. Source:
<https://deck.gl/docs/api-reference/geo-layers/wms-layer>. It is the deck
equivalent of the experiment's current one-image-per-layer approach, and
shares its weakness: every pan or zoom is a fresh full-viewport request.

### 3.4 Views and MapboxOverlay

Multiple views are an array of `View` instances with `x/y/width/height`
(numbers, percentages, and since 9.3 `calc()`), each with its own
`viewState` keyed by id or one shared object; `layerFilter({layer, viewport})`
decides which layers draw in which view. The guide warns that expensive
layers such as `TileLayer` recompute per viewport change and recommends one
layer instance per view rather than sharing. Source:
<https://deck.gl/docs/developer-guide/views>. `MapView` options include
`repeat`, `orthographic`, `fovy`, `altitude` (<https://deck.gl/docs/api-reference/core/map-view>).

`MapboxOverlay` has two modes. Overlaid: a separate deck canvas above the
map. Interleaved: deck layers are inserted into MapLibre's layer stack and
share its `WebGL2RenderingContext`, ordered by `beforeId`; since 9.3 layers
are always grouped by `beforeId`/`slot`, and MaskExtension or
CollisionFilterExtension only work among layers in one group. In both modes
the overlay prepends a reserved `mapbox` view built from the map camera; user
views are allowed but "only one view synchronizes with the base map.
Additional custom views are possible but non-interactive". Interleaved mode
sets `blend: true, blendColorSrcFactor: 'src-alpha', blendColorDstFactor:
'one-minus-src-alpha', depthWriteEnabled: true, depthCompare: 'less-equal'`
as defaults; per-layer `parameters` still apply through deck's normal render
pass. Sources:
<https://deck.gl/docs/api-reference/mapbox/mapbox-overlay>,
<https://github.com/visgl/deck.gl/blob/master/modules/mapbox/src/mapbox-overlay.ts>,
<https://github.com/visgl/deck.gl/blob/master/modules/mapbox/src/deck-utils.ts>.
For multiple maps or a multi-view layout the base-map guide says to use
reverse-controlled mode, where deck owns size and camera and MapLibre
controls are unavailable:
<https://deck.gl/docs/developer-guide/base-maps/using-with-maplibre>.
9.1 made multi-view consistent across overlaid and interleaved and added
MapLibre v5 globe support (<https://deck.gl/docs/whats-new>).

## 4. Tile servers

### 4.1 GeoMet WMS

GetMap needs `SERVICE, VERSION, REQUEST, LAYERS, STYLES, CRS/SRS, BBOX,
FORMAT, HEIGHT, WIDTH`; `TIME` and `DIM_REFERENCE_TIME` are optional ISO
8601 UTC. Without them GeoMet returns the nearest past run's closest
interval. "Queries with time ranges or multiple time values are not
currently supported ... Only single time queries are supported."
GetCapabilities expresses the time dimension as
`start/end/PT3H`-style intervals. The page documents no maximum image size,
no WMTS, no tiled-request or cache-control behaviour. Source:
<https://eccc-msc.github.io/open-data/msc-geomet/wms_en/>.

Consequences: each time step is one GetMap URL family; tiling a WMS layer
means issuing GetMap per tile with a per-tile EPSG:3857 BBOX, which both
MapLibre raster sources (a `tiles` template cannot express a BBOX, so this
goes through `addProtocol` or a proxy) and deck `TileLayer` (`getTileData`
builds the request from `bbox`) can do. Tiling turns each pan into a few
small cacheable requests instead of one full-viewport image, but every
(tile, time) is a distinct request with no server-side tile cache advertised.

### 4.2 TiTiler (COG)

`GET /cog/tiles/{tileMatrixSetId}/{z}/{x}/{y}[@{scale}x][.{format}]` with
`url` plus `bidx`, `expression`, `nodata`, `unscale`, `resampling`,
`reproject`, `rescale`, `color_formula`, `colormap_name`, `colormap`,
`return_mask`, `buffer`, `padding`, `algorithm`; also `/preview`, `/bbox`,
`/point/{lon},{lat}`, `/{tms}/tilejson.json`, and a `WMTSCapabilities.xml`
through the WMTS extension (documented on the mosaic router). Source:
<https://developmentseed.org/titiler/endpoints/cog/>,
<https://developmentseed.org/titiler/endpoints/mosaic/>.
Colour mapping and rescaling are therefore server-side, which fits MapLibre's
lack of `raster-color`. Caching is not built in: `CacheControlMiddleware`
adds a `Cache-Control` header (default none, `exclude_path` regexes) and the
performance guide is GDAL tuning (`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`,
`VSI_CACHE`, `CPL_VSIL_CURL_CACHE_SIZE`, `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES`,
`GDAL_INGESTED_BYTES_AT_OPEN` sized to the COG header). Sources:
<https://developmentseed.org/titiler/api/titiler/core/middleware/>,
<https://developmentseed.org/titiler/advanced/performance_tuning/>.
Each time step is a separate COG `url`; for a NetCDF or Zarr with a time
axis, `titiler.xarray` selects the slice per request with `variable` and
`sel`/`datetime` (<https://developmentseed.org/titiler/packages/xarray/>).
Every tile is one or more HTTP range reads on the COG, so a CDN or reverse
proxy in front of the tiles endpoint is what makes replay of a time step
cheap.

## 5. Compare arrangements

### 5.1 Swipe

- **Two maps, CSS clip (proven, no fork).**
  `@maplibre/maplibre-gl-compare` creates two `Map` instances, syncs them
  with `syncMove` from `@mapbox/mapbox-gl-sync-move`, and clips each
  container with CSS `clip: rect(...)` while translating a divider;
  options `mousemove`, `orientation` (`vertical` | `horizontal`),
  `setSlider(x)`, `slideend`. Last commit 2022-09-28 (21 commits) but the
  code is small and self-contained. `syncMove` listens to `move`, copies
  center, zoom, bearing and pitch with `jumpTo`, and turns the listeners
  off while applying to avoid the loop; it accepts any number of maps
  (last commit 2025-06-17). `maplibre-gl-swipe` (opengeos) does the same on
  one control: it constructs a second `MapLibreMap`, positions it in a
  clip container sized by `left`/`width`, toggles layer `visibility` per
  side, and offers a `layerProvider` hook for deck.gl or custom layers.
  `maplibre-gl-compare-plus` adds a side-by-side mode on the same two-map
  base. Sources:
  <https://github.com/maplibre/maplibre-gl-compare/blob/main/index.js>,
  <https://github.com/mapbox/mapbox-gl-sync-move/blob/master/index.js>,
  <https://github.com/opengeos/maplibre-gl-swipe/blob/main/src/lib/core/SwipeControl.ts>,
  <https://github.com/Willjfield/maplibre-gl-compare-plus>.
  Cost: two contexts, two base maps, two overlays; requests and GPU memory
  double for everything not shared, and `jumpTo` sync lags the leading
  map by one frame.
- **One map, deck-drawn rasters (feasible, prototype needed).** Rasters
  drawn as deck `BitmapLayer`/`TileLayer` can be clipped per layer with
  `MaskExtension` (a screen-half polygon as the mask) or, more cheaply, a
  scissor rectangle set in the layer's draw; in interleaved mode both
  layers must share one `beforeId` group (9.3 grouping rule). Native
  MapLibre raster layers cannot be clipped this way: the style has no clip
  property, and `bounds` on a source is static and geographic.
- **One map, custom layer scissor (feasible).** A MapLibre custom layer
  may enable `SCISSOR_TEST` for its own draw and restore it; this is the
  route for `FlowBlendLayer`-style layers.

### 5.2 Side by side and small multiples

- **N MapLibre maps + `syncMove` (proven, no fork).** Each panel is a full
  map with its own base style, sources and overlay; `syncMove` handles N.
  Cost scales linearly in contexts, base-map tiles, raster requests and
  textures; four panels of five rasters is 20 raster sources. Browsers cap
  the number of live WebGL contexts (unverified figure, commonly cited as
  16 in Chromium), so small multiples beyond about a dozen panels need
  another arrangement.
- **One deck canvas, N `MapView`s, one context (feasible, base map in one
  panel only).** Views laid out with `x/width` percentages or `calc()`,
  one shared `viewState` for locked cameras, `layerFilter` sending each
  raster to its panel, one `TileLayer` instance per panel (the views guide
  says not to share). Under `MapboxOverlay` only the reserved `mapbox` view
  follows the base map and extra views are non-interactive; a base map
  under every panel needs reverse-controlled mode or no base map (a vector
  coastline drawn by deck per view instead). Cost: one context, tile
  requests per panel (each view has its own tileset), one draw pass per
  view.
- **Off-map compare** (cross-source at a point) is not a raster problem and
  is already served by `/point`.

### 5.3 Blend compare (difference, multiply, min/max)

Only through deck (`parameters` on the raster layer) or a custom MapLibre
layer. A true signed difference of two data rasters is not a fixed-function
blend; it needs a two-texture shader (the pattern `FlowBlendLayer` already
implements for its crossfade) fed by exact-value textures
(`setPremultiplyAlpha(false)` on MapLibre, or `textureParameters` nearest
sampling on deck).

## 6. Cost model for a stack of five rasters

Assumptions: 1280 x 800 CSS px viewport, DPR 2, RGBA8 textures.

| Technique | Requests per time step (5 layers) | GPU memory per time step (5 layers) | Per-frame draw |
|---|---|---|---|
| One viewport image per layer (current `/raster`, 1024 px cap) | 5 | 5 x 1024 x 1024 x 4 B = 20 MiB (26.7 MiB with mipmaps on tile sources; image sources upload without mipmaps) | 5 draws |
| Same at a 512 px cap for playback | 5 | 5 MiB (6.7 MiB with mipmaps) | 5 draws |
| WMS or COG tiles, 256 px tiles (`tileSize` 256) | about 5 x 30 = 150 (6 x 5 tiles in view) | 5 x 30 x 256 KiB x 4/3 = 50 MiB | 150 draws |
| WMS or COG tiles, 512 px tiles | about 5 x 12 = 60 | 5 x 12 x 1 MiB x 4/3 = 80 MiB | 60 draws |
| Two-map swipe | 2x the row above | 2x plus two base maps | 2x |
| Four-panel small multiples | 4x | 4x | 4x |

Per-frame draw cost is one draw call per visible tile per raster layer with
two texture binds and a handful of uniforms (`draw_raster.ts`), or one
`BitmapLayer` draw per tile in deck; deck's guidance is that frame time
scales with fragment work, not layer count, and that up to about 100 layers
is routine. Sixty to a hundred and fifty full-screen-fraction quads is well
inside a 16 ms budget on any GPU that runs MapLibre at all; the frame-time
risk is texture upload on the frame a new step appears (1 to 5 MiB per
layer, synchronous `texImage2D`), and the request risk is the 16-parallel
image limit in MapLibre and 6-per-layer in deck when five layers each want
30 tiles.

Playback across 24 steps therefore cannot preload everything at viewport
resolution (5 layers x 24 steps x 5.3 MiB = 636 MiB at 1024 px, 165 MiB
at 512 px). The shapes that fit:

1. **Ring buffer of decoded frames, not textures.** Fetch ahead and decode
   with `createImageBitmap` off the main thread (`MapPanel.tsx` already
   prefetches blend pairs); hold `ImageBitmap`s in JS memory (same byte
   size as the texture, but not GPU memory) and upload one step ahead of
   the play head. On v5.7.1 `updateImage` refetches by URL (browser cache)
   and recreates the texture; on v6 the decoded `image` can be handed over
   directly.
2. **Three time steps resident per layer** (previous, current, next) as
   MapLibre sources with the non-current ones at `raster-opacity: 0`, so
   they load and cache without drawing; promote by setting opacity, with
   `raster-fade-duration: 0`. About 20 MiB for five layers at 512 px.
3. **Tiles only when the camera moves.** Tiled sources win on pan and zoom
   (small, cacheable, partial reloads) and lose on playback (30 to 150
   requests per step). A hybrid, one image per step while playing and tiles
   at rest, is what the current design implicitly does and matches
   `_WMSLayer`'s model.
4. **Cache below the map library.** `addProtocol` (MapLibre) or a custom
   `getTileData` (deck) in front of a shared in-memory or Cache API store
   keyed by (layer, time, tile) lets a scrub back and forth replay steps
   without refetching, independent of MapLibre's per-source LRU (default 5
   viewports per source) and deck's per-layer cache.

## 7. What this leaves open

- Whether the API should serve tiles (TiTiler in front of the artifact
  store, or a `/tiles/{z}/{x}/{y}` route) for the rendered-grid layers;
  the request-count column above is the trade.
- Measured, not computed, frame times for a five-layer stack on the target
  laptops, and the WebGL context ceiling for small multiples.
- A prototype of the single-map swipe for deck-drawn rasters (mask versus
  scissor) against the two-map plugin, on the same layer stack.
- Whether to move to maplibre-gl v6 for `updateImage({image})` and the
  texture-update path, which removes the recreate-and-flash step in
  playback.
