import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CollisionFilterExtension, type CollisionFilterExtensionProps } from '@deck.gl/extensions'
import { GeoJsonLayer, type GeoJsonLayerProps, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { MapboxOverlay } from '@deck.gl/mapbox'
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { describeEvidenceBasis, describeOffset, groupLayers, layerLegendUrl, loadLayerFeatures, loadLayerRaster, loadLegendFailure, nearestFrame, resolveFrame } from './api'
import type { RasterImage } from './api'
import { stationCoverage, stations } from './fixtures'
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
   *  frames, or declines; nothing is resampled onto a shared clock. */
  validTime: Date
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
 *  is ever presented as an absence of weather. */
type RasterState =
  | { status: 'none'; reason: string }
  | { status: 'requesting'; frame: ResolvedFrame }
  | { status: 'unavailable'; frame: ResolvedFrame; reason: string }
  | { status: 'shown'; frame: ResolvedFrame; image: RasterImage }

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
  return {
    west: bounds.getWest(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    north: bounds.getNorth(),
    widthPx: canvas.clientWidth || 512,
    heightPx: canvas.clientHeight || 512,
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
  label, field, comparison, selected, onSelect, validTime, fixtureMode = false,
  layers, layersError, layersLoading, selections, onToggleLayer, onSetOpacity, onJumpToTime, layerNotices, evidence, sourceStatuses,
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
  const [drawerOpen, setDrawerOpen] = useState(true)
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
  // One object URL per layer, so a scrub across the window releases the frame it
  // replaces instead of leaking one blob per step.
  const objectUrlsRef = useRef<Map<string, string>>(new Map())
  // The map layers this panel owns, so it removes exactly what it added, and
  // what stack they were painted for, so an unchanged stack is left alone.
  const rasterLayerIdsRef = useRef<string[]>([])
  const paintedKeyRef = useRef('')
  // What each layer's held image was requested for, so toggling another layer on
  // does not re-request an image already drawn at the same frame and extent.
  // Every avoided request is one back in the proxy's upstream budget.
  const retrievedKeyRef = useRef<Map<string, string>>(new Map())

  // The drawer body covers the right 300 px of the pane. Padding the map by
  // that much moves the view's centre into the uncovered part, so the initial
  // fit keeps the Avalon and the station labels visible with the drawer open
  // by default, and every later camera move respects the same edge.
  const padForDrawer = useCallback((map: MapLibreMap) => {
    const measured = Math.round(drawerRef.current?.getBoundingClientRect().width ?? 0) || DRAWER_WIDTH_PX
    const right = drawerOpenRef.current ? Math.min(measured, Math.floor(map.getCanvas().clientWidth / 2)) : 0
    map.setPadding({ top: 0, bottom: 0, left: 0, right })
  }, [])

  const retainObjectUrl = useCallback((layerId: string, objectUrl: string | null) => {
    const previous = objectUrlsRef.current.get(layerId)
    if (previous && previous !== objectUrl) URL.revokeObjectURL(previous)
    if (objectUrl) objectUrlsRef.current.set(layerId, objectUrl)
    else objectUrlsRef.current.delete(layerId)
    if (!objectUrl) retrievedKeyRef.current.delete(layerId)
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

  // Each active layer resolves the requested instant against its own frames.
  // A layer with no frame inside its tolerance is not fetched and not drawn.
  const resolved = useMemo(
    () => active.map(({ entry, layer }) => ({ entry, layer, frame: resolveFrame(layer, validTime) })),
    [active, validTime],
  )
  const frameKey = resolved.map(({ layer, frame }) => `${layer.id}@${frame?.time ?? 'none'}`).join('|')

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [-52.9, 47.55],
      zoom: 6.5,
      attributionControl: false,
      style: {
        version: 8,
        sources: {
          'esri-dark': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
          },
          'esri-labels': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: '',
          },
        },
        layers: [
          { id: 'ocean', type: 'background', paint: { 'background-color': '#06171d' } },
          { id: 'esri-dark-layer', type: 'raster', source: 'esri-dark', minzoom: 0, maxzoom: 20 },
        ],
      },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'bottom-right')
    // MapLibre's own scale bar, recomputed from the map's real zoom and centre
    // on every move. The panel used to print a fixed "50 km" beside a freely
    // zoomable map, which is the same fabrication as a fixed temperature: a
    // number that looks measured, is not, and never changes when the thing it
    // describes does.
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-left')
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: 'Experimental evidence · no navigation use' }))

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
      map.addLayer({
        id: 'esri-labels-layer',
        type: 'raster',
        source: 'esri-labels',
        minzoom: 0,
        maxzoom: 20,
        paint: { 'raster-opacity': 0.65 },
      })
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
      paintedKeyRef.current = ''
      // Every retained image is released on unmount; none of them outlives the map.
      objectUrlsRef.current.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
      objectUrlsRef.current.clear()
    }
  }, [label, padForDrawer])

  // One fetch per active layer per frame. A layer whose frame did not resolve is
  // recorded as such and never requested, so nothing is drawn off-time.
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    setStates((previous) => {
      const next: Record<string, LayerState> = {}
      for (const { layer, frame } of resolved) {
        // Layer kind comes from the artifact's stored geometry, so a `raster`
        // layer has no stored features to ask for: /features answers 404 for the
        // proxied ones. Its evidence is the image, reported separately below.
        if (layer.kind === 'raster') {
          next[layer.id] = { status: 'imagery-only' }
          continue
        }
        if (!frame) {
          const tolerance = layer.staleness_tolerance_seconds
          next[layer.id] = {
            status: 'no-frame',
            reason: (layer.times?.length ?? 0) === 0
              ? 'this layer published no frames'
              : `no frame within ${typeof tolerance === 'number' ? `${Math.round(tolerance / 60)} min` : 'its declared tolerance'} of the selected time`,
          }
          continue
        }
        const existing = previous[layer.id]
        next[layer.id] = existing && 'frame' in existing && existing.frame.time === frame.time ? existing : { status: 'loading', frame }
      }
      return next
    })

    for (const { layer, entry, frame } of resolved) {
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

  // One image per visible layer per frame, over the extent the reader is looking
  // at. Nothing is requested for a layer that declares no imagery, and nothing is
  // requested for a frame that did not resolve, so no image can arrive off-time.
  // Requesting only the visible layers is also what keeps a scrub inside the
  // proxy's 16-call-per-request, 240-per-minute upstream budget.
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    if (!extent) return () => controller.abort()

    const requestKey = (frame: ResolvedFrame) => `${frame.time}|${extent.south},${extent.west},${extent.north},${extent.east},${Math.round(extent.widthPx)}x${Math.round(extent.heightPx)}`

    setRasters((previous) => {
      const next: Record<string, RasterState> = {}
      for (const { layer, frame } of resolved) {
        if (layer.raster_available !== true) {
          retainObjectUrl(layer.id, null)
          next[layer.id] = {
            status: 'none',
            reason: layer.raster_available === false
              ? 'this layer declares no map image'
              : 'this layer did not declare whether it has a map image, so none is requested',
          }
          continue
        }
        if (!frame) {
          retainObjectUrl(layer.id, null)
          next[layer.id] = { status: 'none', reason: 'no frame of this layer answers the selected time' }
          continue
        }
        const held = previous[layer.id]
        next[layer.id] = held?.status === 'shown' && retrievedKeyRef.current.get(layer.id) === requestKey(frame)
          ? held
          : { status: 'requesting', frame }
      }
      // A layer toggled off keeps nothing. Its retrieval key in particular
      // must go: with it retained, toggling the layer back on at the same
      // frame skipped the request as already held, and the row sat at
      // "requesting" with no image and no request in flight.
      for (const id of Object.keys(previous)) if (!(id in next)) retainObjectUrl(id, null)
      return next
    })

    for (const { layer, frame } of resolved) {
      if (!frame || layer.raster_available !== true) continue
      // Already held for this exact frame and extent; asking again would spend
      // upstream budget to receive the same image.
      if (retrievedKeyRef.current.get(layer.id) === requestKey(frame)) continue
      void loadLayerRaster(layer, { ...extent, validTime: frame.time }, controller.signal).then((result) => {
        if (cancelled) {
          // The frame moved under this response; release it rather than retain it.
          if (result.image) URL.revokeObjectURL(result.image.objectUrl)
          return
        }
        retainObjectUrl(layer.id, result.image?.objectUrl ?? null)
        if (result.image) retrievedKeyRef.current.set(layer.id, requestKey(frame))
        setRasters((previous) => ({
          ...previous,
          [layer.id]: result.image
            ? { status: 'shown', frame, image: result.image }
            // A failed request clears whatever was drawn: stale pixels under a new
            // timestamp are the fabrication this project forbids.
            : { status: 'unavailable', frame, reason: result.error ?? 'imagery unavailable' },
        }))
      }).catch(() => undefined)
    }

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [frameKey, resolved, extent, retainObjectUrl])

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
    const shown = resolved
      .map(({ layer, entry }) => ({ layer, entry, state: rasters[layer.id] }))
      .filter((row): row is { layer: LayerItem; entry: LayerSelection; state: Extract<RasterState, { status: 'shown' }> } => row.state?.status === 'shown')
      .sort((a, b) => (a.layer.z_index ?? 0) - (b.layer.z_index ?? 0))
    const desiredKey = shown.map(({ layer, entry, state }) => `${layer.id}|${state.image.objectUrl}|${entry.opacity}|${Object.values(state.image.request).join(',')}`).join('\n')

    const reconcile = () => {
      const painted = rasterLayerIdsRef.current
      const consistent = paintedKeyRef.current === desiredKey && painted.every((id) => map.getLayer(id) && map.getSource(id))
      if (consistent) return
      for (const id of painted) {
        if (map.getLayer(id)) map.removeLayer(id)
        if (map.getSource(id)) map.removeSource(id)
      }
      rasterLayerIdsRef.current = []
      for (const { layer, entry, state } of shown) {
        const id = `raster-${layer.id}`
        const { west, south, east, north } = state.image.request
        map.addSource(id, {
          type: 'image',
          url: state.image.objectUrl,
          coordinates: [[west, north], [east, north], [east, south], [west, south]],
        })
        map.addLayer(
          { id, type: 'raster', source: id, paint: { 'raster-opacity': Math.max(0, Math.min(1, entry.opacity)), 'raster-fade-duration': 0 } },
          map.getLayer('esri-labels-layer') ? 'esri-labels-layer' : undefined,
        )
        rasterLayerIdsRef.current.push(id)
      }
      paintedKeyRef.current = desiredKey
    }

    reconcile()
    if (map.isStyleLoaded()) return
    map.once('idle', reconcile)
    return () => { map.off('idle', reconcile) }
  }, [rasters, resolved, extent])

  // Re-pad when the drawer opens or closes. The first application is made by
  // the `load` handler above; before that the map is not ready to be padded.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoadedRef.current) return
    padForDrawer(map)
  }, [drawerOpen, padForDrawer])

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
  const describeRaster = (layer: LayerItem): string => {
    const state = rasters[layer.id]
    if (!state) return 'No map image has been requested.'
    if (state.status === 'none') return `No map image requested: ${state.reason}.`
    if (state.status === 'requesting') return `Requesting map imagery for frame ${new Date(state.frame.time).toISOString()}.`
    // "Not retrieved" and "retrieved, nothing detected" are different sentences
    // on purpose; collapsing them would erase a real observation of absence.
    if (state.status === 'unavailable') return `Imagery not retrieved: ${state.reason}. Nothing has been drawn in its place.`
    const { provenance, coverage } = state.image
    // The alerts image is served untimed (`x-weather-valid-time: none`). It
    // used to be stamped with the scrubbed time, which is a timestamp the
    // provider never gave; it is now called what it is.
    const when = provenance.validTime === 'none'
      ? 'current image, not time-indexed'
      : `valid ${provenance.validTime ?? new Date(state.frame.time).toISOString()}`
    const run = provenance.referenceTime && provenance.referenceTime !== 'none' ? `, model run ${provenance.referenceTime}` : ''
    const head = `Imagery retrieved from ${provenance.wmsLayer}, ${when}${run}`
    const notice = provenance.notice ? ` Notice: ${provenance.notice}.` : ''
    if (coverage === 'fully-transparent') return `${head}. The image is fully transparent: retrieved, and nothing was detected. That is a reading, not an outage.${notice}`
    if (coverage === 'not-inspected') return `${head}. Its pixels were not inspected in this browser, so "nothing detected" cannot be distinguished from a drawn field here.${notice}`
    return `${head}.${notice}`
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
    const frame = on ? resolveFrame(layer, validTime) : null
    const nearest = on && !frame ? nearestFrame(layer, validTime) : null
    const tolerance = layer.staleness_tolerance_seconds
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
              {frame
                // JSX text does not process JavaScript escapes, so the joiner
                // is a real character in a JS expression rather than a
                // "\u00b7" printed on every frame line. A stored-feature layer
                // (points, alert polygons) is fetched at this instant, so the
                // line calls it a retrieval; "Frame" is kept for imagery,
                // whose valid time is the image's own.
                ? <>{layer.kind === 'raster' ? 'Frame' : 'Retrieved'} <time dateTime={frame.time}>{stJohns(frame.time)}</time>{' \u00b7 '}{describeOffset(frame.offsetSeconds)}{lead && <>{' \u00b7 '}{lead}</>}</>
                : nearest
                  ? (
                    // Nothing is drawn: the nearest frame is named with its age
                    // and the tolerance it failed, and the reader may go to it.
                    <span className="stack-noframe">
                      No frame within {typeof tolerance === 'number' ? `${Math.round(tolerance / 60)} min` : 'the declared tolerance'} of this time.
                      {' '}Nearest frame <time dateTime={nearest.time}>{stJohns(nearest.time)}</time> ({describeOffset(nearest.offsetSeconds)}){typeof tolerance === 'number' ? `; tolerance ${Math.round(tolerance / 60)} min` : ''}.
                      {' '}<button type="button" className="stack-jump" onClick={() => onJumpToTime(new Date(nearest.time))}>Jump to nearest frame</button>
                    </span>
                  )
                  : <span className="stack-noframe">No frame at this time: this layer published none.</span>}
            </p>
            {!undrawable && <p className="stack-state">{describeState(layer)}</p>}
            <p className="stack-raster">{describeRaster(layer)}</p>
            {/* The evidence basis is the condition on which the proxied route
                was permitted, so it is rendered as words rather than encoded
                in the swatch beside it. */}
            <p className={`stack-basis basis-${layer.evidence_basis ?? 'unknown'}`}>{describeEvidenceBasis(layer.evidence_basis)}</p>
            {layer.raster_available === true && (layer.legend_available === true
              ? legendFailure
                ? <p className="stack-legend-missing">No legend was retrieved from the provider: {legendFailure}. The layer is drawn without one; none is invented here.</p>
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

      {/* The layer drawer: docked to the right edge, full pane height, and
          absorbing the old chip strip and stack panel. The strip was measured
          at 1321 px wide in an 867 px pane, painting over the caption; nothing
          but the caption is now absolutely positioned in the top band. */}
      <aside ref={drawerRef} className={`map-layer-drawer ${drawerOpen ? 'open' : 'closed'}`} aria-label="Published map layers">
        <button type="button" className="drawer-toggle" aria-expanded={drawerOpen} onClick={() => setDrawerOpen((open) => !open)}>
          Layers ({onCount} on)
        </button>
        {drawerOpen && (
          <div className="drawer-body">
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
          : <ul className="layer-text-list">{active.map(({ layer }) => (
            <li key={layer.id}>
              <strong>{layer.title}</strong>: {describeState(layer)} {describeRaster(layer)} {describeEvidenceBasis(layer.evidence_basis)}
            </li>
          ))}</ul>}
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
