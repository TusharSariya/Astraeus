import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CollisionFilterExtension, type CollisionFilterExtensionProps } from '@deck.gl/extensions'
import { GeoJsonLayer, type GeoJsonLayerProps, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { MapboxOverlay } from '@deck.gl/mapbox'
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { DEFAULT_INTERPOLATION_METHOD, describeEvidenceBasis, describeOffset, describeResolution, drawableFrames, groupLayers, layerGroup, layerLegendUrl, loadLayerFeatures, loadLayerFlow, loadLayerRaster, loadLegendFailure, renderPixelSize, resolveLayerFrame, stJohnsTime } from './api'
import { flowObjectUrls } from './api'
import type { FlowTexture, FrameResolution, RasterImage } from './api'
import { FlowBlendLayer } from './FlowBlendLayer'
import { stationCoverage, stations } from './fixtures'
import { applyWeatherMapTheme, createWeatherMapStyle, REFERENCE_SOURCE_ID, WEATHER_REFERENCE_ANCHOR_ID, type Theme } from './mapStyle'
import type { GeoJsonFeature, LayerItem, LayerSelection, LocationPoint, ResolvedFrame, SourceStatusItem, StationCoverage } from './types'

export interface MapEvidenceRow {
  label: string
  value: string
}

interface MapPanelProps {
  label: string
  field: string
  comparison?: string
  fixtureMode?: boolean
  /** The instant the reader asked for. Each layer answers it from its own
   *  frames, or falls back with a visible disclosure; nothing is resampled
   *  onto a shared clock and nothing is drawn undated. */
  validTime: Date
  /** The session reference instant. Observed layers never fall back for an
   *  instant after it: their frames are of what had already happened. */
  reference: Date
  /** Owner-approved display setting: when true, a forecast layer between two
   *  frames is drawn as both real retrieved frames composited by opacity.
   *  Display derivation only — it never touches features or point data. */
  interpolate: boolean
  /** Which interpolation construction to draw with, from the server's bench.
   *  Named in the disclosure whenever it is not the default, so a screenshot
   *  is never ambiguous about what produced the picture. */
  interpolationMethod?: string
  selected: LocationPoint
  onSelect: (point: LocationPoint) => void
  /** Layer list exactly as published by `/layers`. No layer is invented here. */
  layers: LayerItem[]
  layersError: string | null
  layersLoading: boolean
  /** The stack, in draw order. Empty means basemap only — an explicit choice. */
  selections: LayerSelection[]
  onToggleLayer: (layerId: string) => void
  onSetOpacity: (layerId: string, opacity: number) => void
  /** Move the timeline scrubber to an instant. Offered beside a layer whose
   *  nearest frame is outside its tolerance: the reader may go to the evidence,
   *  but the evidence is never brought to the reader's clock. */
  onJumpToTime: (date: Date) => void
  /** `/layers` notices, verbatim. One naming a layer id lands on that row. */
  layerNotices: string[]
  /** Textual alternative to the canvas for the selected point. */
  evidence: MapEvidenceRow[]
  /** `/sources/status` rows, or `null` when the endpoint could not be read.
   *  The only thing permitted to say a station marker has a live source. */
  sourceStatuses: SourceStatusItem[] | null
  theme?: Theme
  /** Defaults closed in the product. Exposed only so isolated render tests can
   * exercise the dense drawer contents without repeating an opening click. */
  initialDrawerOpen?: boolean
}

/** What one active layer resolved to for the requested instant. A layer is
 *  either drawn at a named frame or explicitly not drawn — there is no third
 *  state in which something appears without a timestamp behind it. */
type LayerState =
  | { status: 'no-frame'; reason: string }
  | { status: 'imagery-only' }
  | { status: 'loading'; frame: ResolvedFrame }
  | { status: 'empty'; frame: ResolvedFrame }
  | { status: 'error'; frame: ResolvedFrame; reason: string }
  | { status: 'drawn'; frame: ResolvedFrame; features: GeoJsonFeature[] }

/** What one layer's imagery resolved to. `none` covers every case where no
 *  request was issued at all, and carries the reason; `unavailable` covers a
 *  request that was issued and did not come back as drawable evidence. Neither
 *  is ever presented as an absence of weather. `shown` holds one slot
 *  normally, or two for a display composite — each slot a real retrieved
 *  image at the fractional opacity weight it is drawn with. */
type RasterSlot = { frame: ResolvedFrame; weight: number; image: RasterImage }
type RasterState =
  | { status: 'none'; reason: string }
  | { status: 'requesting'; frames: ResolvedFrame[] }
  // The previous frame stays drawn, at its own disclosed timestamp, while the
  // newly selected one is retrieved: a scrub never blanks the map, and what is
  // on screen is always a named real frame (`slots`), never the pending one.
  | { status: 'refreshing'; slots: RasterSlot[]; frames: ResolvedFrame[] }
  | { status: 'unavailable'; frame: ResolvedFrame; reason: string }
  | { status: 'shown'; slots: RasterSlot[] }

/** The one frame a stored-feature request may use. A blend never applies to
 *  features — the nearer of its pair answers instead. */
function featureFrame(resolution: FrameResolution): ResolvedFrame | null {
  if (resolution.kind === 'exact' || resolution.kind === 'snapped') return resolution.frame
  if (resolution.kind === 'blend') return resolution.fraction <= 0.5 ? resolution.previous : resolution.next
  return null
}

/** The imagery slots a resolution asks for, with their opacity weights. */
function slotPlan(resolution: FrameResolution): Array<{ frame: ResolvedFrame; weight: number }> {
  if (resolution.kind === 'exact' || resolution.kind === 'snapped') return [{ frame: resolution.frame, weight: 1 }]
  if (resolution.kind === 'blend') return [{ frame: resolution.previous, weight: 1 - resolution.fraction }, { frame: resolution.next, weight: resolution.fraction }]
  return []
}

/** Retrieved images a layer may hold at once. Forty holds a layer's whole
 *  28-hour frame axis at one extent - which is what makes a scrub across the
 *  window instant once the frames are in - plus room for blend pairs. */
const IMAGE_CACHE_PER_LAYER = 40

/** Locally rendered layers (stored-grid renders: cloud grids, satellite mask,
 *  aurora) cost no upstream budget and their sources are far coarser than the
 *  screen, so their rasters are requested at a bounded pixel size and scaled
 *  on the GPU with nearest-neighbor - same cells, far smaller PNGs. */
const RENDERED_REQUEST_MAX_EDGE_PX = 1024

function isLocallyRendered(layer: LayerItem): boolean {
  return layer.evidence_basis === 'published_artifact' && layer.raster_available === true
}

function requestExtentFor(layer: LayerItem, extent: ViewExtent): ViewExtent {
  if (!isLocallyRendered(layer)) return extent
  const scale = RENDERED_REQUEST_MAX_EDGE_PX / Math.max(extent.widthPx, extent.heightPx)
  if (scale >= 1) return extent
  return { ...extent, widthPx: Math.max(1, Math.round(extent.widthPx * scale)), heightPx: Math.max(1, Math.round(extent.heightPx * scale)) }
}

/** The extent and pixel size one image is requested over. Taken from the map
 *  itself, never from a constant: the image has to cover what the reader is
 *  actually looking at, and a stale extent would draw the wrong place at full
 *  confidence. */
interface ViewExtent {
  west: number
  south: number
  east: number
  north: number
  widthPx: number
  heightPx: number
}

function readExtent(map: MapLibreMap): ViewExtent {
  const bounds = map.getBounds()
  const canvas = map.getCanvas()
  // Physical pixels, DPR-capped at 2 (renderPixelSize): the provider
  // rasterises server-side, so a CSS-pixel request is what made forecast
  // fields soft on high-density displays.
  return {
    west: bounds.getWest(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    north: bounds.getNorth(),
    widthPx: renderPixelSize(canvas.clientWidth || 512),
    heightPx: renderPixelSize(canvas.clientHeight || 512),
  }
}

/** Label geometry, in pixels. The marker ring is `radiusMaxPixels` plus half
 *  its 2 px stroke; the advance is IBM Plex Mono at size 12, weight 600, as
 *  Chrome's canvas measures it (7.22 px, and the system monospace it falls
 *  back to advances the same). The earlier 3.3 px figure was half of a 6.6 px
 *  guess, and once the label was anchored at its middle the first glyph of an
 *  18-character label landed 6 px from the marker centre: inside the ring. */
const MARKER_RING_PX = 9
const LABEL_MARGIN_PX = 6
const GLYPH_ADVANCE_PX = 7.22

/** Colours by layer kind. These identify a layer in the stack; they never encode
 *  a value, which is why no colour ramp or dBZ scale appears anywhere. */
const KIND_COLOUR: Record<string, [number, number, number]> = {
  point: [117, 203, 209],
  alert: [255, 138, 96],
  raster: [161, 196, 253],
  mask: [200, 178, 255],
  line: [255, 214, 122],
}

function colourFor(kind: string): [number, number, number] {
  return KIND_COLOUR[kind] ?? [222, 243, 239]
}

function stationLayers(
  label: string,
  selected: LocationPoint,
  onPick: (point: LocationPoint) => void,
  markPick: () => void,
  coverageFor: (point: LocationPoint) => StationCoverage,
) {
  const currentPoints = stations.some((station) => station.id === selected.id) ? stations : [...stations, selected]
  const labelFor = (d: LocationPoint) => `${d.name.replace(/ \/ .*/, '')} \u00b7 ${coverageFor(d).short}`
  return [
    new ScatterplotLayer<LocationPoint>({
      id: `stations-glow-${label}`,
      data: currentPoints,
      getPosition: (d) => [d.longitude, d.latitude],
      getFillColor: (d) => (d.id === selected.id ? [255, 190, 82, 90] : [117, 203, 209, 45]),
      radiusMinPixels: 10,
      radiusMaxPixels: 16,
      pickable: false,
      // deck.gl does not re-run an accessor because a new function was passed;
      // without these triggers the highlight stayed on the first station after
      // another was picked.
      updateTriggers: { getFillColor: [selected.id] },
    }),
    // The marker is a location picker, so every station gets a pin — but a pin
    // reads as coverage. A station with a live ingested source behind it is a
    // filled disc; one without is an open ring. The distinction is a glyph, not
    // a hue, and it is repeated verbatim in the on-canvas label, the picker
    // options and the text alternative below, so it never rests on colour.
    new ScatterplotLayer<LocationPoint>({
      id: `stations-${label}`,
      data: currentPoints,
      getPosition: (d) => [d.longitude, d.latitude],
      getFillColor: (d) => (coverageFor(d).state !== 'live'
        ? [0, 0, 0, 0]
        : d.id === selected.id ? [255, 190, 82, 255] : [222, 243, 239, 235]),
      getLineColor: (d) => (d.id === selected.id ? [255, 190, 82, 255] : [222, 243, 239, 235]),
      lineWidthMinPixels: 2,
      radiusMinPixels: 5,
      radiusMaxPixels: 8,
      pickable: true,
      stroked: true,
      filled: true,
      updateTriggers: { getFillColor: [selected.id, coverageFor], getLineColor: [selected.id] },
      onClick: (info) => {
        if (!info.object) return
        markPick()
        onPick(info.object)
      },
    }),
    new TextLayer<LocationPoint, CollisionFilterExtensionProps<LocationPoint>>({
      id: `stations-labels-${label}`,
      data: currentPoints,
      getPosition: (d) => [d.longitude, d.latitude],
      getText: labelFor,
      // deck.gl rasterises only the glyphs in `characterSet`, and its default is
      // printable ASCII. The apostrophe in "St. John’s" (U+2019) and the joiner
      // (U+00B7) are outside it, so both rendered as blanks — "St. John s",
      // "CYYT  live source". The set is built from the strings actually drawn;
      // the names are not ASCII-folded to fit the default.
      characterSet: [...new Set(currentPoints.flatMap((point) => [...labelFor(point)]))],
      getSize: 12,
      getColor: [240, 248, 255, 240],
      // Anchored at its middle and pushed right by the ring, a margin and half
      // its own width, so the first glyph clears the marker. The anchor
      // matters: the collision test samples the collision map at the anchor,
      // and a label anchored 'start' with a pixel offset leaves no glyph over
      // it, so every label read as occluded and all three vanished. The
      // advance only places the label; it never decides what is shown.
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'center',
      getPixelOffset: (d: LocationPoint) => [MARKER_RING_PX + LABEL_MARGIN_PX + (labelFor(d).length * GLYPH_ADVANCE_PX) / 2, 0],
      fontFamily: 'IBM Plex Mono, monospace',
      fontWeight: 600,
      // The outline was already asked for; deck only draws it from an SDF
      // atlas and warned on every render that it was not doing so.
      fontSettings: { sdf: true },
      outlineWidth: 3,
      outlineColor: [5, 18, 24, 255],
      // An invisible background quad, so the collision map holds a solid
      // rectangle for each label. Glyphs alone leave gaps, and the sample at
      // the anchor falls on the space in the middle of the text.
      background: true,
      getBackgroundColor: [0, 0, 0, 0],
      backgroundPadding: [6, 3, 6, 3],
      // Picking colours are what the collision map is drawn in, and the label
      // is a second, larger target for choosing the station it names.
      pickable: true,
      onClick: (info) => {
        if (!info.object) return
        markPick()
        onPick(info.object)
      },
      // Three stations sit within 35 km of each other; at the default zoom
      // their labels overlapped. The selected station's label always wins.
      // The collision map is drawn centred on the anchor (offset zeroed) so
      // the sample at the anchor lands on the label itself, and at twice the
      // size so a near miss counts. The priorities sit near the ends of the
      // extension's ±1000 range: verified in the browser that 100 vs 0 left
      // the selected label half-faded while these do not.
      extensions: [new CollisionFilterExtension()],
      collisionEnabled: true,
      collisionGroup: 'station-labels',
      collisionTestProps: { getPixelOffset: [0, 0], sizeScale: 2 },
      getCollisionPriority: (d: LocationPoint) => (d.id === selected.id ? 900 : -900),
      updateTriggers: { getCollisionPriority: [selected.id], getText: [coverageFor], getPixelOffset: [coverageFor] },
    }),
  ]
}

/** The drawer's CSS width, used when it cannot be measured (jsdom). */
const DRAWER_WIDTH_PX = 300

/** A stored grid the API will not render: `/raster` answers 501 for it by
 *  design. The row is shown, disabled, with this one sentence. */
const UNDRAWABLE_REASON = 'publishes a stored grid but no map image; read it through the forecast panel'
function isUndrawable(layer: LayerItem): boolean {
  return layer.kind === 'raster' && layer.raster_available === false
}

/** A notice that names a layer belongs on that layer's row. The catalogue
 *  writes them as "<layer id> ..." or "<layer id>: ...". */
function noticesFor(layer: LayerItem, notices: string[]): string[] {
  return notices.filter((notice) => notice.startsWith(`${layer.id} `) || notice.startsWith(`${layer.id}:`))
}

function isLayerNotice(notice: string, layers: LayerItem[]): boolean {
  return layers.some((layer) => noticesFor(layer, [notice]).length > 0)
}

const stJohns = (time: string) => new Date(time).toLocaleTimeString('en-CA', { timeZone: 'America/St_Johns', hour: '2-digit', minute: '2-digit' })

/** A frame later than the wall clock is a forecast, and its lead is stated in
 *  the frame line so a future field is never read as an observation. */
function describeLead(frameTime: string, now: number): string | null {
  const lead = (new Date(frameTime).getTime() - now) / 3600_000
  if (!(lead > 0)) return null
  return `forecast lead +${lead < 1 ? lead.toFixed(1) : Math.round(lead)} h`
}

/** Everything the API returned for one layer, drawn as published. Geometry comes
 *  from the response; only the colour, which carries no value, is chosen here. */
function evidenceLayers(layer: LayerItem, features: GeoJsonFeature[], opacity: number) {
  const [r, g, b] = colourFor(layer.kind)
  const alpha = Math.round(Math.max(0, Math.min(1, opacity)) * 255)
  return [
    new GeoJsonLayer({
      id: `evidence-${layer.id}`,
      // The features are exactly what the API returned; the cast only restates
      // that shape in deck.gl's own prop type, which is narrower than `object`.
      data: { type: 'FeatureCollection', features } as unknown as GeoJsonLayerProps['data'],
      pickable: true,
      stroked: true,
      filled: true,
      pointType: 'circle',
      getFillColor: [r, g, b, alpha],
      getLineColor: [r, g, b, 255],
      lineWidthMinPixels: 2,
      pointRadiusMinPixels: 6,
      pointRadiusMaxPixels: 14,
    }),
  ]
}

export function MapPanel({
  label, field, comparison, selected, onSelect, validTime, reference, interpolate,
  interpolationMethod = DEFAULT_INTERPOLATION_METHOD, fixtureMode = false,
  layers, layersError, layersLoading, selections, onToggleLayer, onSetOpacity, onJumpToTime, layerNotices, evidence, sourceStatuses, theme = 'dark', initialDrawerOpen = false,
}: MapPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const stationPickAtRef = useRef(0)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const [states, setStates] = useState<Record<string, LayerState>>({})
  const [rasters, setRasters] = useState<Record<string, RasterState>>({})
  const [extent, setExtent] = useState<ViewExtent | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(initialDrawerOpen)
  const [referenceMapError, setReferenceMapError] = useState(false)
  const drawerRef = useRef<HTMLElement>(null)
  const drawerOpenRef = useRef(drawerOpen)
  drawerOpenRef.current = drawerOpen
  // Set on the map's `load`. Padding applied before then left both MapLibre and
  // the deck overlay rendering at roughly 2.5x scale on first paint (verified
  // in Chrome; the transform still reported zoom 6.5), so it waits for `load`.
  const mapLoadedRef = useRef(false)
  // Why a legend `<img>` failed, per layer, in the API's words. Set only after
  // the image itself errored; cleared when the layer leaves the stack.
  const [legendFailures, setLegendFailures] = useState<Record<string, string>>({})
  // Retrieved images per layer, keyed by frame time + extent and capped per
  // layer (LRU). A scrub across a blend boundary reuses the frame that moved
  // between slots instead of refetching it, and toggling a layer back on at
  // the same frame reuses its image — every avoided request is one back in
  // the proxy's upstream budget. Eviction revokes the object URL.
  const imageCacheRef = useRef<Map<string, Map<string, RasterImage>>>(new Map())
  // What each layer is currently being fetched for, so a pair of blend images
  // arriving after the selection moved on is cached but never committed.
  const generationRef = useRef<Map<string, string>>(new Map())
  // In-flight requests keyed layer|frame|extent: concurrent wants (a scrub
  // revisit, the prefetcher, a blend pair sharing a frame) share one promise.
  const inflightRef = useRef<Map<string, Promise<{ image: RasterImage | null; error: string | null }>>>(new Map())
  // The abort scope for raster fetches, keyed by viewport: frame changes never
  // abort (results are cacheable); viewport changes and unmount do.
  const fetchScopeRef = useRef<{ key: string; controller: AbortController } | null>(null)
  // Derived motion textures per layer, keyed by frame pair + extent.
  // 'absent' records a 404: the pair has no derived motion and the blend
  // crossfades - cached so the 404 is asked once, not per scrub tick.
  const flowCacheRef = useRef<Map<string, Map<string, FlowTexture | 'absent'>>>(new Map())
  const flowInflightRef = useRef<Set<string>>(new Set())
  // The custom shader layers this panel owns, by map layer id.
  const flowLayersRef = useRef<Map<string, FlowBlendLayer>>(new Map())
  // Bumped when a motion texture lands, so the map-sync effect re-runs.
  const [flowVersion, setFlowVersion] = useState(0)
  // The map layers this panel owns, so it removes exactly what it added, and
  // what stack they were painted for, so an unchanged stack is left alone.
  const rasterLayerIdsRef = useRef<string[]>([])
  // What each painted slot currently shows (url, opacity, coordinates), so an
  // unchanged slot is left alone and a changed one is updated in place.
  const paintedContentRef = useRef<Map<string, string>>(new Map())

  // The drawer body covers the right 300 px of the pane. Padding the map by
  // that much moves the view's centre into the uncovered part, so the initial
  // fit keeps the Avalon and the station labels visible with the drawer open
  // by default, and every later camera move respects the same edge.
  const padForDrawer = useCallback((map: MapLibreMap) => {
    const measured = Math.round(drawerRef.current?.getBoundingClientRect().width ?? 0) || DRAWER_WIDTH_PX
    const right = drawerOpenRef.current ? Math.min(measured, Math.floor(map.getCanvas().clientWidth / 2)) : 0
    map.setPadding({ top: 0, bottom: 0, left: 0, right })
  }, [])

  const cacheGet = useCallback((layerId: string, key: string): RasterImage | null => {
    const held = imageCacheRef.current.get(layerId)
    const image = held?.get(key)
    if (held && image) {
      // Refresh recency: Map iteration order is insertion order.
      held.delete(key)
      held.set(key, image)
    }
    return image ?? null
  }, [])

  const cachePut = useCallback((layerId: string, key: string, image: RasterImage) => {
    let held = imageCacheRef.current.get(layerId)
    if (!held) {
      held = new Map()
      imageCacheRef.current.set(layerId, held)
    }
    const previous = held.get(key)
    if (previous && previous.objectUrl !== image.objectUrl) URL.revokeObjectURL(previous.objectUrl)
    held.delete(key)
    held.set(key, image)
    while (held.size > IMAGE_CACHE_PER_LAYER) {
      const [oldestKey, oldest] = held.entries().next().value as [string, RasterImage]
      held.delete(oldestKey)
      URL.revokeObjectURL(oldest.objectUrl)
    }
  }, [])

  const cacheDropLayer = useCallback((layerId: string) => {
    const flows = flowCacheRef.current.get(layerId)
    if (flows) {
      flows.forEach((entry) => { if (entry !== 'absent') flowObjectUrls(entry).forEach((url) => URL.revokeObjectURL(url)) })
      flowCacheRef.current.delete(layerId)
    }
    const held = imageCacheRef.current.get(layerId)
    if (!held) return
    held.forEach((image) => URL.revokeObjectURL(image.objectUrl))
    imageCacheRef.current.delete(layerId)
    generationRef.current.delete(layerId)
  }, [])

  // Held in a ref as well as a memo: the map setup effect runs once and closes
  // over whatever coverage was known then, which is usually "still loading".
  const coverageFor = useCallback((point: LocationPoint) => stationCoverage(point, sourceStatuses), [sourceStatuses])
  const coverageRef = useRef(coverageFor)
  coverageRef.current = coverageFor
  const pickerCoverage = useMemo(
    () => (stations.some((station) => station.id === selected.id) ? stations : [...stations, selected])
      .map((point) => ({ point, coverage: coverageFor(point) })),
    [selected, coverageFor],
  )

  const byId = useMemo(() => new Map(layers.map((layer) => [layer.id, layer])), [layers])
  const active = useMemo(
    () => selections.filter((entry) => entry.visible).map((entry) => ({ entry, layer: byId.get(entry.id) })).filter((pair): pair is { entry: LayerSelection; layer: LayerItem } => Boolean(pair.layer)),
    [selections, byId],
  )

  // Each active layer resolves the requested instant against its own frames:
  // quietly within tolerance, by disclosed fallback beyond it, and by the
  // opt-in display composite for forecast imagery between two frames.
  const resolved = useMemo(
    () => active.map(({ entry, layer }) => ({ entry, layer, resolution: resolveLayerFrame(layer, validTime, { interpolate, reference }) })),
    [active, validTime, interpolate, reference],
  )
  const frameKey = resolved.map(({ layer, resolution }) => {
    const frames = drawableFrames(resolution).map((frame) => frame.time).join('+') || 'none'
    const fraction = resolution.kind === 'blend' ? `~${resolution.fraction.toFixed(3)}` : ''
    return `${layer.id}@${frames}${fraction}`
  }).join('|')

  // The disclosure sentences for every active layer not drawn at an exact
  // frame, shared verbatim by the on-map notes, the drawer rows and the text
  // alternative. A blend that lost one image mid-pair says so.
  const layerNoteFor = (layer: LayerItem, resolution: FrameResolution): string | null => {
    if (resolution.kind === 'blend') {
      const state = rasters[layer.id]
      if (state?.status === 'shown' && state.slots.length === 1) {
        const slot = state.slots[0]
        return `showing ${stJohnsTime(slot.frame.time)} NT (${describeOffset(slot.frame.offsetSeconds)} than the selected time); the second frame of the display composite was not retrieved`
      }
      if (isLocallyRendered(layer)) {
        // Rendered-grid blends draw through the interpolation shader; the
        // note names the method actually applied to this pair.
        const held = [...(flowCacheRef.current.get(layer.id)?.entries() ?? [])]
          .find(([key]) => key.startsWith(`${resolution.previous.time}->${resolution.next.time}|`))?.[1]
        const construction = held && held !== 'absent'
          ? (held.shader === 'intermediate' && held.backwardUrl
            ? 'advection-corrected along intermediate motion approximated from both the forward and the backward field derived for this pair, dissolving where the two frames say cloud grew or decayed in place rather than moved'
            : held.tangentsUrl
            ? 'advection-corrected along motion fitted through neighbouring published frames (C1 trajectories), dissolving where the two frames say cloud grew or decayed in place rather than moved'
            : 'advection-corrected along a motion field derived from the two published frames, dissolving where cloud grew or decayed in place rather than moved')
          : 'a linear cross-dissolve; no derived motion field for this pair'
        // Any construction other than the default is named outright: an
        // admin menu that silently changes what is drawn is the one thing
        // this map's governing rule does not tolerate.
        const served = held && held !== 'absent' ? held.method : interpolationMethod
        const method = served && served !== DEFAULT_INTERPOLATION_METHOD
          ? `${construction}; interpolation method "${served}"`
          : construction
        return `temporally interpolated for display between the ${stJohnsTime(resolution.previous.time)} and ${stJohnsTime(resolution.next.time)} NT frames (${method}) — display only, not evidence`
      }
    }
    return describeResolution(resolution)
  }
  const fallbackNotes = resolved.flatMap(({ layer, resolution }) => {
    const text = layerNoteFor(layer, resolution)
    return text ? [{ layer, text }] : []
  })

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [-52.9, 47.55],
      zoom: 6.5,
      attributionControl: false,
      style: createWeatherMapStyle(theme),
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'bottom-right')
    // MapLibre's own scale bar, recomputed from the map's real zoom and centre
    // on every move. The panel used to print a fixed "50 km" beside a freely
    // zoomable map, which is the same fabrication as a fixed temperature: a
    // number that looks measured, is not, and never changes when the thing it
    // describes does.
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-left')
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'Experimental evidence · no navigation use' }))

    map.on('error', (event) => {
      const sourceId = 'sourceId' in event && typeof event.sourceId === 'string' ? event.sourceId : null
      if (sourceId === REFERENCE_SOURCE_ID || (!sourceId && !map.isStyleLoaded())) setReferenceMapError(true)
    })

    // The extent every image is requested over. `moveend` is debounced because an
    // in-flight pan has no stable extent to ask about, and because each refetch
    // spends from the proxy's upstream budget.
    let extentTimer: ReturnType<typeof setTimeout> | undefined
    const commitExtent = () => setExtent(readExtent(map))
    map.on('moveend', () => {
      if (extentTimer) clearTimeout(extentTimer)
      extentTimer = setTimeout(commitExtent, 250)
    })

    map.on('load', () => {
      mapLoadedRef.current = true
      map.once('idle', () => padForDrawer(map))
      commitExtent()
      const overlay = new MapboxOverlay({
        interleaved: false,
        layers: stationLayers(label, selectedRef.current, (point) => onSelectRef.current(point), () => { stationPickAtRef.current = performance.now() }, (point) => coverageRef.current(point)),
      })
      overlayRef.current = overlay
      map.addControl(overlay as unknown as maplibregl.IControl)
    })

    map.on('click', (event) => {
      if (performance.now() - stationPickAtRef.current < 120) return
      onSelectRef.current({
        id: `map-${event.lngLat.lat.toFixed(4)}-${event.lngLat.lng.toFixed(4)}`,
        name: `Map point ${event.lngLat.lat.toFixed(3)}°N, ${Math.abs(event.lngLat.lng).toFixed(3)}°W`,
        latitude: event.lngLat.lat,
        longitude: event.lngLat.lng,
        kind: 'map',
      })
    })

    mapRef.current = map
    return () => {
      if (extentTimer) clearTimeout(extentTimer)
      map.remove()
      mapRef.current = null
      overlayRef.current = null
      mapLoadedRef.current = false
      rasterLayerIdsRef.current = []
      paintedContentRef.current.clear()
      // Every retained image is released on unmount; none of them outlives the map.
      fetchScopeRef.current?.controller.abort()
      fetchScopeRef.current = null
      inflightRef.current.clear()
      imageCacheRef.current.forEach((held) => held.forEach((image) => URL.revokeObjectURL(image.objectUrl)))
      imageCacheRef.current.clear()
      generationRef.current.clear()
      flowCacheRef.current.forEach((held) => held.forEach((entry) => { if (entry !== 'absent') flowObjectUrls(entry).forEach((url) => URL.revokeObjectURL(url)) }))
      flowCacheRef.current.clear()
      flowInflightRef.current.clear()
      flowLayersRef.current.clear()
    }
  }, [label, padForDrawer])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => applyWeatherMapTheme(map, theme)
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
    return () => { map.off('load', apply) }
  }, [theme])

  // One fetch per active layer per frame. A layer whose frame did not resolve is
  // recorded as such and never requested, so nothing is drawn off-time.
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setStates((previous) => {
      const next: Record<string, LayerState> = {}
      for (const { layer, resolution } of resolved) {
        // Layer kind comes from the artifact's stored geometry, so a `raster`
        // layer has no stored features to ask for: /features answers 404 for the
        // proxied ones. Its evidence is the image, reported separately below.
        if (layer.kind === 'raster') {
          next[layer.id] = { status: 'imagery-only' }
          continue
        }
        const frame = featureFrame(resolution)
        if (!frame) {
          next[layer.id] = {
            status: 'no-frame',
            reason: resolution.kind === 'none' ? resolution.reason : 'no frame of this layer answers the selected time',
          }
          continue
        }
        const existing = previous[layer.id]
        next[layer.id] = existing && 'frame' in existing && existing.frame.time === frame.time ? existing : { status: 'loading', frame }
      }
      return next
    })

    for (const { layer, entry, resolution } of resolved) {
      const frame = featureFrame(resolution)
      if (!frame || layer.kind === 'raster') continue
      void loadLayerFeatures(layer, frame, controller.signal).then((result) => {
        if (cancelled) return
        setStates((previous) => ({
          ...previous,
          [layer.id]: result.error
            ? { status: 'error', frame, reason: result.error }
            : result.features.length === 0
              ? { status: 'empty', frame }
              : { status: 'drawn', frame, features: result.features },
        }))
        void entry
      }).catch(() => undefined)
    }

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [frameKey, resolved])

  // One image per visible layer per drawable frame, over the extent the reader
  // is looking at. Nothing is requested for a layer that declares no imagery,
  // and nothing is requested for a frame that did not resolve, so no image can
  // arrive off-time. Requesting only visible layers, reusing cached frames,
  // and committing blend pairs atomically is what keeps a scrub inside the
  // proxy's 16-call-per-request, 240-per-minute upstream budget.
  useEffect(() => {
    let cancelled = false
    if (!extent) return

    // One abort scope per viewport, not per frame: a scrub to the next frame
    // must not cancel a request the server is already rendering - its result
    // lands in the cache and a scrub back reuses it. Only a viewport change
    // (new bounds/size make the bytes unusable) or unmount aborts.
    const viewKey = `${extent.south},${extent.west},${extent.north},${extent.east},${Math.round(extent.widthPx)}x${Math.round(extent.heightPx)}`
    if (fetchScopeRef.current?.key !== viewKey) {
      fetchScopeRef.current?.controller.abort()
      fetchScopeRef.current = { key: viewKey, controller: new AbortController() }
    }
    const controller = fetchScopeRef.current.controller

    const frameCacheKey = (layer: LayerItem, frame: { time: string }) => {
      const request = requestExtentFor(layer, extent)
      return `${frame.time}|${request.south},${request.west},${request.north},${request.east},${Math.round(request.widthPx)}x${Math.round(request.heightPx)}`
    }

    // One request per (layer, frame, extent) no matter how many effect runs
    // want it: concurrent wants share the same promise, and every settled
    // image is cached even if the selection has moved on.
    const fetchFrame = (layer: LayerItem, frame: { time: string }): Promise<{ image: RasterImage | null; error: string | null }> => {
      const key = frameCacheKey(layer, frame)
      const held = cacheGet(layer.id, key)
      if (held) return Promise.resolve({ image: held, error: null })
      const inflightKey = `${layer.id}|${key}`
      const pending = inflightRef.current.get(inflightKey)
      if (pending) return pending
      const promise = loadLayerRaster(layer, { ...requestExtentFor(layer, extent), validTime: frame.time }, controller.signal)
        .then((result) => {
          if (result.image) cachePut(layer.id, key, result.image)
          return result
        })
        .finally(() => inflightRef.current.delete(inflightKey))
      inflightRef.current.set(inflightKey, promise)
      return promise
    }

    // One motion texture per (layer, frame pair, extent): fetched once, a 404
    // remembered as the disclosed crossfade fallback. Never blocks a frame.
    // The method is part of the key: two methods are two different published
    // fields for the same pair, so switching must fetch rather than reuse.
    const flowPairKey = (layer: LayerItem, from: string, to: string) => {
      const request = requestExtentFor(layer, extent)
      return `${from}->${to}|${interpolationMethod}|${request.south},${request.west},${request.north},${request.east},${Math.round(request.widthPx)}x${Math.round(request.heightPx)}`
    }
    const ensureFlow = (layer: LayerItem, from: string, to: string): Promise<unknown> => {
      const key = flowPairKey(layer, from, to)
      if (flowCacheRef.current.get(layer.id)?.get(key) !== undefined) return Promise.resolve()
      const inflightKey = `${layer.id}|${key}`
      if (flowInflightRef.current.has(inflightKey)) return Promise.resolve()
      flowInflightRef.current.add(inflightKey)
      return loadLayerFlow(layer, { ...requestExtentFor(layer, extent), from, to }, controller.signal, interpolationMethod)
        .then(({ flow, absent }) => {
          if (!flow && !absent) return
          let held = flowCacheRef.current.get(layer.id)
          if (!held) {
            held = new Map()
            flowCacheRef.current.set(layer.id, held)
          }
          held.set(key, flow ?? 'absent')
          while (held.size > IMAGE_CACHE_PER_LAYER) {
            const [oldestKey, oldest] = held.entries().next().value as [string, FlowTexture | 'absent']
            held.delete(oldestKey)
            if (oldest !== 'absent') flowObjectUrls(oldest).forEach((url) => URL.revokeObjectURL(url))
          }
          if (!cancelled) setFlowVersion((version) => version + 1)
        })
        .catch(() => undefined)
        .finally(() => flowInflightRef.current.delete(inflightKey))
    }

    // A layer toggled off keeps nothing, so toggling it back on at the same
    // frame issues a real request rather than sitting at "requesting" forever.
    const activeIds = new Set(resolved.map(({ layer }) => layer.id))
    for (const id of [...imageCacheRef.current.keys()]) if (!activeIds.has(id)) cacheDropLayer(id)

    setRasters((previous) => {
      const next: Record<string, RasterState> = {}
      for (const { layer, resolution } of resolved) {
        if (layer.raster_available !== true) {
          next[layer.id] = {
            status: 'none',
            reason: layer.raster_available === false
              ? 'this layer declares no map image'
              : 'this layer did not declare whether it has a map image, so none is requested',
          }
          continue
        }
        const plan = slotPlan(resolution)
        if (plan.length === 0) {
          next[layer.id] = { status: 'none', reason: resolution.kind === 'none' ? resolution.reason : 'no frame of this layer answers the selected time' }
          continue
        }
        const held = plan.map(({ frame }) => cacheGet(layer.id, frameCacheKey(layer, frame)))
        if (held.every((image): image is RasterImage => image !== null)) {
          next[layer.id] = { status: 'shown', slots: plan.map((slot, index) => ({ ...slot, image: held[index] as RasterImage })) }
          continue
        }
        // Keep the previous real frame on screen while the wanted one loads:
        // the drawn slots keep their own timestamps, so nothing on the map is
        // ever mislabelled - it is simply the last retrieved frame, disclosed.
        const prior = previous[layer.id]
        const priorSlots = prior && (prior.status === 'shown' || prior.status === 'refreshing') ? prior.slots : null
        next[layer.id] = priorSlots
          ? { status: 'refreshing', slots: priorSlots, frames: plan.map(({ frame }) => frame) }
          : { status: 'requesting', frames: plan.map(({ frame }) => frame) }
      }
      return next
    })

    for (const { layer, resolution } of resolved) {
      if (layer.raster_available !== true) continue
      if (resolution.kind === 'blend' && isLocallyRendered(layer)) {
        void ensureFlow(layer, resolution.previous.time, resolution.next.time)
      }
      const plan = slotPlan(resolution)
      if (plan.length === 0) continue
      const generation = plan.map(({ frame }) => frameCacheKey(layer, frame)).join('+')
      generationRef.current.set(layer.id, generation)
      // Every wanted frame already held: the updater above committed it.
      if (plan.every(({ frame }) => cacheGet(layer.id, frameCacheKey(layer, frame)))) continue
      void Promise.all(plan.map(async ({ frame }) => {
        const result = await fetchFrame(layer, frame)
        return { frame, image: result.image, error: result.error }
      })).then((results) => {
        if (cancelled || generationRef.current.get(layer.id) !== generation) return
        setRasters((previous) => {
          const succeeded = results.filter((row): row is { frame: ResolvedFrame; image: RasterImage; error: string | null } => row.image !== null)
          let state: RasterState
          if (succeeded.length === results.length) {
            state = { status: 'shown', slots: plan.map((slot, index) => ({ ...slot, image: results[index].image as RasterImage })) }
          } else if (succeeded.length > 0) {
            // One frame of a display composite failed. A lone half-opacity
            // slot would present a partial retrieval as a blend, so the
            // nearest retrieved frame is drawn whole and the note says why.
            const nearest = succeeded.reduce((best, row) => (Math.abs(row.frame.offsetSeconds) < Math.abs(best.frame.offsetSeconds) ? row : best))
            state = { status: 'shown', slots: [{ frame: nearest.frame, weight: 1, image: nearest.image }] }
          } else {
            // A failed request clears whatever was drawn: stale pixels under a
            // new timestamp are the fabrication this project forbids.
            state = { status: 'unavailable', frame: plan[0].frame, reason: results.find((row) => row.error)?.error ?? 'imagery unavailable' }
          }
          return { ...previous, [layer.id]: state }
        })
      }).catch(() => undefined)
    }

    // Prefetch the full frame axis of every locally rendered active layer
    // (stored-grid renders only: they cost no upstream budget, so warming
    // them is free of the proxy's spending rules; proxied layers stay
    // strictly on-demand). Two at a time, at idle priority, sharing the
    // viewport abort scope and the in-flight dedupe above.
    const prefetchQueue: Array<() => Promise<unknown>> = resolved
      .filter(({ layer }) => isLocallyRendered(layer))
      .flatMap(({ layer }) => (layer.times ?? []).map((time) => ({ layer, frame: { time } })))
      .filter(({ layer, frame }) => !cacheGet(layer.id, frameCacheKey(layer, frame)))
      .map(({ layer, frame }) => () => fetchFrame(layer, frame))
    if (interpolate) {
      // With display interpolation on, the motion texture of every adjacent
      // pair is warmed too, so a scrub crosses pairs without a crossfade
      // flash while its flow loads. Same idle queue, same budget-free layers.
      for (const { layer } of resolved) {
        if (!isLocallyRendered(layer)) continue
        const times = layer.times ?? []
        for (let index = 0; index + 1 < times.length; index += 1) {
          const from = times[index]
          const to = times[index + 1]
          if (flowCacheRef.current.get(layer.id)?.get(flowPairKey(layer, from, to)) === undefined) {
            prefetchQueue.push(() => ensureFlow(layer, from, to))
          }
        }
      }
    }
    if (prefetchQueue.length > 0) {
      const schedule: (callback: () => void) => number = (window as unknown as { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback
        ? (callback) => (window as unknown as { requestIdleCallback: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback(callback, { timeout: 1500 })
        : (callback) => window.setTimeout(callback, 250)
      schedule(() => {
        if (cancelled || controller.signal.aborted) return
        void Promise.all(Array.from({ length: 2 }, async () => {
          while (!cancelled && !controller.signal.aborted) {
            const task = prefetchQueue.shift()
            if (!task) return
            await task().catch(() => undefined)
          }
        }))
      })
    }

    return () => {
      cancelled = true
    }
  }, [frameKey, resolved, extent, interpolate, cacheGet, cachePut, cacheDropLayer])

  // Sync the map with the images actually held. When the painted stack differs
  // from the held one, every managed layer is removed and re-added in published
  // z-order beneath the basemap labels, so the stack order the API declares is
  // the order the reader sees.
  //
  // This used to return early while `isStyleLoaded()` was false. MapLibre says
  // false whenever any source is still loading, including the image source this
  // effect had just added, so an untoggle landing in that window was skipped
  // and never retried: the temperature field stayed painted under a drawer
  // saying it was off. Removals now run unconditionally, since a layer this
  // panel added is either on the map or not and `getLayer` says which. When the
  // style reports not loaded, the reconcile is also repeated on the next `idle`,
  // so nothing MapLibre dropped mid-load stays wrong.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    // `refreshing` draws its held previous slots exactly like `shown`: the
    // slots name the real frame they carry, so nothing is mislabelled while
    // the newly selected frame loads.
    const shown = resolved
      .map(({ layer, entry }) => ({ layer, entry, state: rasters[layer.id] }))
      .filter((row): row is { layer: LayerItem; entry: LayerSelection; state: Extract<RasterState, { status: 'shown' } | { status: 'refreshing' }> } =>
        row.state?.status === 'shown' || row.state?.status === 'refreshing')
      .sort((a, b) => (a.layer.z_index ?? 0) - (b.layer.z_index ?? 0))
    // One image source per slot: one for a plain frame, two for a display
    // composite, earlier frame below the later. Stacked translucent layers
    // compose as 1-(1-a)(1-b) rather than a linear crossfade, which is why
    // every disclosure calls this display compositing, not blending of values.
    //
    // The exception is a blend of a locally rendered layer: those draw
    // through one custom shader layer that cross-dissolves the two frames
    // linearly and, when the pair's derived motion texture is held, warps
    // them along it (advection-corrected interpolation, disclosed in the
    // layer note). Both inputs are the same two retrieved frames.
    type ImageEntry = {
      kind: 'image'
      id: string
      url: string
      coordinates: [[number, number], [number, number], [number, number], [number, number]]
      opacity: number
      resampling: 'nearest' | 'linear'
    }
    type FlowEntry = {
      kind: 'flowblend'
      id: string
      frame0Url: string
      frame1Url: string
      flowUrl: string | null
      flowScalePixels: number
      tangentsUrl: string | null
      tangentsScalePixels: number
      backwardUrl: string | null
      backwardScalePixels: number
      construction: string
      bounds: { west: number; south: number; east: number; north: number }
      widthPx: number
      heightPx: number
      t: number
      opacity: number
    }
    const desired: Array<ImageEntry | FlowEntry> = shown.flatMap(({ layer, entry, state }): Array<ImageEntry | FlowEntry> => {
      // A locally rendered layer under display interpolation draws through
      // the blend layer even at an exact frame (both inputs the real frame,
      // t = 0: the identity), so the painted stack keeps the same shape on
      // both sides of a real-frame crossing and the reconcile below never
      // tears it down mid-scrub.
      const blendPair = state.slots.length === 2
      if (isLocallyRendered(layer) && (blendPair || (interpolate && state.slots.length === 1))) {
        const previous = state.slots[0]
        const next = blendPair ? state.slots[1] : state.slots[0]
        const request = previous.image.request
        const pairKey = blendPair
          ? [...(flowCacheRef.current.get(layer.id)?.keys() ?? [])]
            .find((key) => key.startsWith(`${previous.frame.time}->${next.frame.time}|`))
          : undefined
        const flow = pairKey ? flowCacheRef.current.get(layer.id)?.get(pairKey) : undefined
        return [{
          kind: 'flowblend',
          id: `flowblend-${layer.id}`,
          frame0Url: previous.image.objectUrl,
          frame1Url: next.image.objectUrl,
          flowUrl: flow && flow !== 'absent' ? flow.objectUrl : null,
          flowScalePixels: flow && flow !== 'absent' ? flow.scalePixels : 0,
          tangentsUrl: flow && flow !== 'absent' ? flow.tangentsUrl : null,
          tangentsScalePixels: flow && flow !== 'absent' ? flow.tangentsScalePixels : 0,
          backwardUrl: flow && flow !== 'absent' ? flow.backwardUrl : null,
          backwardScalePixels: flow && flow !== 'absent' ? flow.backwardScalePixels : 0,
          // Which construction the shader evaluates is the server's answer,
          // read from the headers of the fields it actually served - never
          // inferred from which textures happened to load.
          construction: flow && flow !== 'absent' ? flow.shader : 'hermite',
          bounds: { west: request.west, south: request.south, east: request.east, north: request.north },
          widthPx: request.widthPx,
          heightPx: request.heightPx,
          t: blendPair ? next.weight : 0,
          opacity: entry.opacity,
        }]
      }
      return state.slots.map((slot, index): ImageEntry => {
        const { west, south, east, north } = slot.image.request
        return {
          kind: 'image',
          id: `raster-${layer.id}-${index}`,
          url: slot.image.objectUrl,
          coordinates: [[west, north], [east, north], [east, south], [west, south]],
          opacity: Math.max(0, Math.min(1, entry.opacity * slot.weight)),
          // Locally rendered grids are requested at a bounded pixel size and
          // scaled here with nearest-neighbor, so the blocky stored cells
          // stay blocky instead of smoothed by the GPU's default resampling.
          resampling: isLocallyRendered(layer) ? ('nearest' as const) : ('linear' as const),
        }
      })
    })
    const contentOf = (slot: ImageEntry | FlowEntry) => slot.kind === 'image'
      ? `${slot.url}|${slot.opacity}|${slot.coordinates.flat().join(',')}`
      : `${slot.frame0Url}|${slot.frame1Url}|${slot.flowUrl}|${slot.flowScalePixels}|${slot.tangentsUrl}|${slot.tangentsScalePixels}|${slot.backwardUrl}|${slot.backwardScalePixels}|${slot.construction}|${slot.t}|${slot.opacity}|${Object.values(slot.bounds).join(',')}`

    const updateFlowLayer = (slot: FlowEntry) => {
      flowLayersRef.current.get(slot.id)?.update({
        frame0Url: slot.frame0Url,
        frame1Url: slot.frame1Url,
        flowUrl: slot.flowUrl,
        flowScalePixels: slot.flowScalePixels,
        tangentsUrl: slot.tangentsUrl,
        tangentsScalePixels: slot.tangentsScalePixels,
        backwardUrl: slot.backwardUrl,
        backwardScalePixels: slot.backwardScalePixels,
        construction: slot.construction,
        bounds: slot.bounds,
        widthPx: slot.widthPx,
        heightPx: slot.heightPx,
        t: slot.t,
        opacity: slot.opacity,
      })
    }

    const reconcile = () => {
      const painted = rasterLayerIdsRef.current
      const structureChanged = painted.join(';') !== desired.map((slot) => slot.id).join(';')
        || desired.some((slot) => !map.getLayer(slot.id) || (slot.kind === 'image' && !map.getSource(slot.id)))
      if (structureChanged) {
        for (const id of painted) {
          if (map.getLayer(id)) map.removeLayer(id)
          if (map.getSource(id)) map.removeSource(id)
          flowLayersRef.current.delete(id)
        }
        rasterLayerIdsRef.current = []
        paintedContentRef.current.clear()
        for (const slot of desired) {
          if (slot.kind === 'flowblend') {
            const instance = new FlowBlendLayer(slot.id)
            flowLayersRef.current.set(slot.id, instance)
            map.addLayer(instance as unknown as maplibregl.LayerSpecification & { type: 'custom' }, WEATHER_REFERENCE_ANCHOR_ID)
            updateFlowLayer(slot)
          } else {
            map.addSource(slot.id, { type: 'image', url: slot.url, coordinates: slot.coordinates })
            map.addLayer(
              { id: slot.id, type: 'raster', source: slot.id, paint: { 'raster-opacity': slot.opacity, 'raster-fade-duration': 0, 'raster-resampling': slot.resampling } },
              WEATHER_REFERENCE_ANCHOR_ID,
            )
          }
          rasterLayerIdsRef.current.push(slot.id)
          paintedContentRef.current.set(slot.id, contentOf(slot))
        }
        return
      }
      // Same stack: swap image bytes / uniforms in place. No source or layer
      // churn, no style diff, no texture re-add - this is what makes a scrub
      // over cached frames paint at animation speed, and an interpolation
      // tick within one pair costs only a uniform update.
      for (const slot of desired) {
        const content = contentOf(slot)
        if (paintedContentRef.current.get(slot.id) === content) continue
        if (slot.kind === 'flowblend') {
          updateFlowLayer(slot)
        } else {
          const source = map.getSource(slot.id) as maplibregl.ImageSource
          source.updateImage({ url: slot.url, coordinates: slot.coordinates })
          map.setPaintProperty(slot.id, 'raster-opacity', slot.opacity)
        }
        paintedContentRef.current.set(slot.id, content)
      }
    }

    reconcile()
    if (map.isStyleLoaded()) return
    map.once('idle', reconcile)
    return () => { map.off('idle', reconcile) }
  }, [rasters, resolved, extent, flowVersion, interpolate])

  // Re-pad when the drawer opens or closes. The first application is made by
  // the `load` handler above; before that the map is not ready to be padded.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoadedRef.current) return
    padForDrawer(map)
  }, [drawerOpen, padForDrawer])

  useEffect(() => {
    if (!drawerOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [drawerOpen])

  // Redraw the overlay: stations, then each drawn layer in published order.
  useEffect(() => {
    const drawn = resolved.flatMap(({ layer, entry }) => {
      const state = states[layer.id]
      return state && state.status === 'drawn' ? evidenceLayers(layer, state.features, entry.opacity) : []
    })
    overlayRef.current?.setProps({
      layers: [
        ...stationLayers(label, selected, (point) => onSelectRef.current(point), () => { stationPickAtRef.current = performance.now() }, coverageFor),
        ...drawn,
      ],
    })
  }, [label, selected, states, resolved, coverageFor])

  useEffect(() => {
    if (selected.kind === 'map') mapRef.current?.easeTo({ center: [selected.longitude, selected.latitude], duration: 450 })
  }, [selected])

  const describeState = (layer: LayerItem): string => {
    const state = states[layer.id]
    if (!state) return 'Not requested.'
    // A raster layer has no stored features to ask for. Whether it has an
    // image to draw instead is a separate declaration, and the two published
    // model grids declare none — so that sentence says so rather than
    // promising imagery the raster line then denies.
    if (state.status === 'imagery-only') return isUndrawable(layer) ? `This layer ${UNDRAWABLE_REASON}.` : 'This layer publishes imagery, not stored features; no feature request is made for it.'
    if (state.status === 'no-frame') return `Not drawn: ${state.reason}.`
    const stamp = `${new Date(state.frame.time).toISOString()} (${describeOffset(state.frame.offsetSeconds)})`
    if (state.status === 'loading') return `Requesting frame ${stamp}.`
    if (state.status === 'error') return `Frame ${stamp} could not be read: ${state.reason}.`
    if (state.status === 'empty') return `Frame ${stamp} published no values. Nothing has been drawn in their place.`
    return `${state.features.length} value${state.features.length === 1 ? '' : 's'} drawn from frame ${stamp}.`
  }

  /** One layer's imagery, in words. Every clause here is a retrieved fact: the
   *  upstream layer name, the instant and the run come off the response headers,
   *  and "nothing detected" is only ever said about an image that arrived. */
  /** One retrieved image, in words. Every clause is a retrieved fact off the
   *  response headers; "nothing detected" is only said about an image that
   *  arrived. */
  const describeImage = (slot: RasterSlot): string => {
    const { provenance, coverage } = slot.image
    // The alerts image is served untimed (`x-weather-valid-time: none`). It
    // used to be stamped with the scrubbed time, which is a timestamp the
    // provider never gave; it is now called what it is.
    const when = provenance.validTime === 'none'
      ? 'current image, not time-indexed'
      : `valid ${provenance.validTime ?? new Date(slot.frame.time).toISOString()}`
    const run = provenance.referenceTime && provenance.referenceTime !== 'none' ? `, model run ${provenance.referenceTime}` : ''
    // A rendered-grid image was drawn here from the stored artifact; naming a
    // WMS layer for it would invent an upstream it never had.
    const drawnFrom = provenance.wmsLayer
      ?? (provenance.imageBasis === 'rendered_grid'
        ? `the stored ${provenance.sourceId ?? 'grid'} artifact, rendered by this experiment at its native cells (nearest-neighbor, never smoothed)`
        : 'an unnamed source')
    const head = `Imagery retrieved from ${drawnFrom}, ${when}${run}`
    const notice = provenance.notice ? ` Notice: ${provenance.notice}.` : ''
    if (coverage === 'fully-transparent') return `${head}. The image is fully transparent: retrieved, and nothing was detected. That is a reading, not an outage.${notice}`
    if (coverage === 'not-inspected') return `${head}. Its pixels were not inspected in this browser, so "nothing detected" cannot be distinguished from a drawn field here.${notice}`
    return `${head}.${notice}`
  }

  const describeRaster = (layer: LayerItem): string => {
    const state = rasters[layer.id]
    if (!state) return 'No map image has been requested.'
    if (state.status === 'none') return `No map image requested: ${state.reason}.`
    if (state.status === 'requesting') return `Requesting map imagery for frame${state.frames.length === 1 ? '' : 's'} ${state.frames.map((frame) => new Date(frame.time).toISOString()).join(' and ')}.`
    if (state.status === 'refreshing') {
      return `Requesting map imagery for frame${state.frames.length === 1 ? '' : 's'} ${state.frames.map((frame) => new Date(frame.time).toISOString()).join(' and ')}; until it arrives the last retrieved frame stays drawn at its own instant. ${state.slots.map(describeImage).join(' ')}`
    }
    // "Not retrieved" and "retrieved, nothing detected" are different sentences
    // on purpose; collapsing them would erase a real observation of absence.
    if (state.status === 'unavailable') return `Imagery not retrieved: ${state.reason}. Nothing has been drawn in its place.`
    if (state.slots.length === 2) {
      const [previous, next] = state.slots
      if (isLocallyRendered(layer)) {
        return `Display interpolation between two retrieved frames at fraction ${next.weight.toFixed(2)} — advection-corrected along a derived motion field when one exists for the pair, a linear cross-dissolve otherwise; display derivation, not evidence. ${describeImage(previous)} ${describeImage(next)}`
      }
      return `Display composite of two retrieved frames at ${Math.round(previous.weight * 100)}% and ${Math.round(next.weight * 100)}% opacity — display derivation, not evidence. ${describeImage(previous)} ${describeImage(next)}`
    }
    return describeImage(state.slots[0])
  }

  const onLegendError = (layer: LayerItem) => {
    void loadLegendFailure(layer).then((reason) => {
      setLegendFailures((previous) => ({ ...previous, [layer.id]: reason }))
    }).catch(() => undefined)
  }

  const wallClock = Date.now()
  const onCount = active.length
  // Group order and headings are shared with the timeline coverage rows
  // (`groupLayers` in api.ts), so a layer sits under the same heading in both.
  const grouped = groupLayers(layers)
  const footerNotices = layerNotices.filter((notice) => !isLayerNotice(notice, layers))

  /** One drawer row: the toggle, and when on, everything the stack panel used
   *  to say about the layer. The evidence-basis, state and raster sentences
   *  are the same strings the text alternative carries. */
  const renderRow = (layer: LayerItem) => {
    const entry = selections.find((item) => item.id === layer.id)
    const on = Boolean(entry?.visible)
    const undrawable = isUndrawable(layer)
    const resolution = on ? resolveLayerFrame(layer, validTime, { interpolate, reference }) : null
    const note = resolution ? layerNoteFor(layer, resolution) : null
    const frame = resolution && (resolution.kind === 'exact' || resolution.kind === 'snapped') ? resolution.frame : null
    const state = states[layer.id]
    const status = on ? state?.status ?? 'loading' : 'off'
    const lead = frame ? describeLead(frame.time, wallClock) : null
    const rowNotices = noticesFor(layer, layerNotices)
    const legendFailure = legendFailures[layer.id]
    return (
      <div key={layer.id} className={`drawer-row stack-entry ${status}${undrawable ? ' undrawable' : ''}`}>
        <label className="drawer-row-head">
          <input type="checkbox" checked={on} disabled={undrawable} onChange={() => onToggleLayer(layer.id)} />
          <span className="stack-swatch" style={{ background: `rgb(${colourFor(layer.kind).join(',')})` }} aria-hidden="true" />
          <strong>{layer.title}</strong>
          <small>{layer.units}</small>
        </label>
        {undrawable && <p className="stack-state">This layer {UNDRAWABLE_REASON}.</p>}
        {on && entry && (
          <>
            <p className="stack-frame">
              {frame && (
                // JSX text does not process JavaScript escapes, so the joiner
                // is a real character in a JS expression rather than a
                // "\u00b7" printed on every frame line. A stored-feature layer
                // (points, alert polygons) is fetched at this instant, so the
                // line calls it a retrieval; "Frame" is kept for imagery,
                // whose valid time is the image's own.
                <>{resolution?.kind === 'snapped' ? (layer.kind === 'raster' ? 'Fallback frame' : 'Fallback retrieval') : layer.kind === 'raster' ? 'Frame' : 'Retrieved'} <time dateTime={frame.time}>{stJohns(frame.time)}</time>{' \u00b7 '}{describeOffset(frame.offsetSeconds)}{lead && <>{' \u00b7 '}{lead}</>}</>
              )}
              {resolution?.kind === 'blend' && (
                <>Display composite of <time dateTime={resolution.previous.time}>{stJohns(resolution.previous.time)}</time> and <time dateTime={resolution.next.time}>{stJohns(resolution.next.time)}</time> frames{' \u00b7 '}display only, not evidence</>
              )}
              {resolution?.kind === 'none' && (
                resolution.nearest
                  ? (
                    // Nothing is drawn: the reason is named, so is the nearest
                    // frame with its distance, and the reader may go to it.
                    <span className="stack-noframe">
                      Not shown: {resolution.reason}.
                      {' '}Nearest frame <time dateTime={resolution.nearest.time}>{stJohns(resolution.nearest.time)}</time> ({describeOffset(resolution.nearest.offsetSeconds)}).
                      {' '}<button type="button" className="stack-jump" onClick={() => resolution.nearest && onJumpToTime(new Date(resolution.nearest.time))}>Jump to nearest frame</button>
                    </span>
                  )
                  : <span className="stack-noframe">No frame at this time: this layer published none.</span>
              )}
            </p>
            {/* The same disclosure sentence the on-map note carries, so the
                drawer, the note and the text alternative cannot disagree. */}
            {note && <p className="stack-fallback-note">{note}</p>}
            {!undrawable && <p className="stack-state">{describeState(layer)}</p>}
            <p className="stack-raster">{describeRaster(layer)}</p>
            {/* The evidence basis is the condition on which the proxied route
                was permitted, so it is rendered as words rather than encoded
                in the swatch beside it. */}
            <p className={`stack-basis basis-${layer.evidence_basis ?? 'unknown'}`}>{describeEvidenceBasis(layer.evidence_basis, layerGroup(layer))}</p>
            {layer.raster_available === true && (layer.legend_available === true
              ? legendFailure
                ? <p className="stack-legend-missing">No legend was retrieved from the provider: {legendFailure}. The layer is drawn without one; none is invented here.</p>
                : layerGroup(layer) === 'rendered_grid'
                  ? (
                    <figure className="stack-legend">
                      <img src={layerLegendUrl(layer)} alt={`Colour scale for ${layer.title}: the exact colormap this experiment renders the stored values with, 0 to 100 percent`} onError={() => onLegendError(layer)} />
                      <figcaption>Rendering colormap, served by this experiment&apos;s API: the exact mapping applied to the stored values (0% transparent to 100% opaque). It is presentation, not provider data.</figcaption>
                    </figure>
                  )
                  : (
                  <figure className="stack-legend">
                    <img src={layerLegendUrl(layer)} alt={`Colour scale for ${layer.title}, drawn and served by the provider that rendered the image`} onError={() => onLegendError(layer)} />
                    <figcaption>Provider legend, fetched from the provider. No colour scale is constructed here.</figcaption>
                  </figure>
                )
              : <p className="stack-legend-missing">The provider serves no legend for this layer, so it is drawn without one; none is invented here.</p>)}
            <label className="stack-opacity">
              Opacity
              <input
                aria-label={`${layer.title} opacity`}
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={entry.opacity}
                onChange={(event) => onSetOpacity(layer.id, Number(event.target.value))}
              />
            </label>
            <p className="stack-semantics">{layer.semantics}</p>
            {/* Keyed by position: the catalogue can repeat a notice verbatim. */}
            {rowNotices.map((notice, index) => <p key={`${index}-${notice}`} className="stack-notice">{notice}</p>)}
          </>
        )}
      </div>
    )
  }

  return (
    <section className={`map-pane ${drawerOpen ? 'drawer-open' : 'drawer-closed'}`} aria-label={`${label} map pane`}>
      <div className="map-caption">
        <span>{label}</span>
        <strong>{field}</strong>
        {comparison && <small>{comparison}</small>}
      </div>

      <div ref={containerRef} className="map-canvas" data-testid="map-canvas" />
      {fixtureMode && <span className="surface-watermark">FIXTURE</span>}
      {referenceMapError && <p className="reference-map-status" role="status" aria-live="polite">Reference map unavailable · weather evidence remains available</p>}

      {/* One note per active layer not drawn at an exact frame: the fallback
          frame it shows, the display composite it draws, or why nothing is
          shown. The disclosure the fallback rules require lives here, on the
          map itself, not only in the drawer. */}
      {fallbackNotes.length > 0 && (
        <div className="map-frame-notes" role="status" aria-live="polite" aria-label="Layers not at the selected time">
          {fallbackNotes.map(({ layer, text }) => (
            <p key={layer.id}><b>{layer.title}</b> — {text}</p>
          ))}
        </div>
      )}

      {active.some(({ layer }) => layer.raster_available === true) && (
        <aside className="map-legend-rail" aria-label="Active map legends">
          <strong>Active legends</strong>
          {active.filter(({ layer }) => layer.raster_available === true).map(({ layer }) => {
            const failed = legendFailures[layer.id]
            if (layer.legend_available !== true) return <p key={layer.id}><b>{layer.title}</b> · no provider legend</p>
            if (failed) return <p key={layer.id}><b>{layer.title}</b> · provider legend unavailable</p>
            const rendered = layerGroup(layer) === 'rendered_grid'
            return (
              <figure key={layer.id}>
                <img src={layerLegendUrl(layer)} alt={`${rendered ? 'Rendering colormap' : 'Provider legend'} for ${layer.title}`} onError={() => onLegendError(layer)} />
                <figcaption>{layer.title} · {rendered ? 'exact rendering colormap' : 'provider legend'}</figcaption>
              </figure>
            )
          })}
        </aside>
      )}

      {/* The layer drawer: docked to the right edge, full pane height, and
          absorbing the old chip strip and stack panel. The strip was measured
          at 1321 px wide in an 867 px pane, painting over the caption; nothing
          but the caption is now absolutely positioned in the top band. */}
      <aside ref={drawerRef} className={`map-layer-drawer ${drawerOpen ? 'open' : 'closed'}`} aria-label="Published map layers">
        <button type="button" className="drawer-toggle" aria-controls={`layer-drawer-${label}`} aria-expanded={drawerOpen} onClick={() => setDrawerOpen((open) => !open)}>
          Layers ({onCount} on)
        </button>
        {drawerOpen && (
          <div className="drawer-body" id={`layer-drawer-${label}`}>
            <p className="drawer-status" role="status">
              {layersLoading ? 'Loading published layers\u2026' : layersError ? `No layers: ${layersError}` : layers.length === 0 ? 'No layers are published by the API.' : `${layers.length} published layers \u00b7 each drawn at its own frame`}
            </p>
            {grouped.map(({ group, label: heading, rows }) => (
              <section key={group} className="drawer-group" role="group" aria-labelledby={`drawer-group-${group}-${label}`}>
                <h4 id={`drawer-group-${group}-${label}`}>{heading}</h4>
                {rows.map(renderRow)}
              </section>
            ))}
            {/* A div, not a <footer>: the page footer's global rules
                (uppercase, right-aligned, flex) would apply to it. */}
            {footerNotices.length > 0 && (
              <div className="drawer-notices" role="note" aria-label="Layer catalogue notices">
                {footerNotices.map((notice, index) => <p key={`${index}-${notice}`}>{notice}</p>)}
              </div>
            )}
          </div>
        )}
      </aside>

      <div className="map-text-alternative">
        <h3>Map contents as text</h3>
        {active.length === 0
          ? <p>Basemap only. No meteorological layer is requested.</p>
          : <ul className="layer-text-list">{resolved.map(({ layer, resolution }) => {
            const note = layerNoteFor(layer, resolution)
            return (
              <li key={layer.id}>
                <strong>{layer.title}</strong>: {note ? `${note}. ` : ''}{describeState(layer)} {describeRaster(layer)} {describeEvidenceBasis(layer.evidence_basis, layerGroup(layer))}
              </li>
            )
          })}</ul>}
        <dl aria-label={`Evidence at ${selected.name}`}>
          <div><dt>Selected point</dt><dd>{selected.name} · {selected.latitude.toFixed(3)}, {selected.longitude.toFixed(3)}</dd></div>
          {evidence.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
        </dl>
        {/* The marker glyph carries this same distinction. Repeating it as a
            sentence is what makes it available without sight of the canvas. */}
        <h3>Station markers</h3>
        <ul className="station-coverage-list">
          {pickerCoverage.map(({ point, coverage }) => (
            <li key={point.id} className={`station-coverage ${coverage.state}`}>
              <strong>{point.name}</strong> — {coverage.detail}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
