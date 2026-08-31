import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MapPanel } from './MapPanel'
import { stations } from './fixtures'
import type { LayerItem, SourceStatusItem } from './types'

// `vi.mock` factories are hoisted above imports, so the fake `Map` class must
// be defined inside the factory rather than referenced from module scope.
vi.mock('maplibre-gl', () => {
  /** A minimal stand-in for maplibre-gl's `Map`. Fires `load` synchronously so
   *  MapPanel's setup effect runs without a real WebGL context. */
  // Controls are recorded by constructor name so a test can assert which ones
  // the panel actually installed — the scale bar is only trustworthy if it is
  // MapLibre's own, recomputed from the map, rather than a printed number.
  ;(globalThis as Record<string, unknown>).__mapControls = []
  class FakeMap {
    private handlers: Record<string, Array<(...args: unknown[]) => void>> = {}
    constructor(_options: unknown) {}
    addControl(control: unknown) {
      ;((globalThis as Record<string, unknown>).__mapControls as string[]).push((control as object)?.constructor?.name ?? 'unknown')
      return this
    }
    on(event: string, callback: (...args: unknown[]) => void) {
      this.handlers[event] = this.handlers[event] ?? []
      this.handlers[event].push(callback)
      if (event === 'load') callback()
      return this
    }
    once(event: string, callback: (...args: unknown[]) => void) {
      const wrapped = (...args: unknown[]) => { this.off(event, wrapped); callback(...args) }
      return this.on(event, wrapped)
    }
    off(event: string, callback: (...args: unknown[]) => void) {
      this.handlers[event] = (this.handlers[event] ?? []).filter((handler) => handler !== callback)
      return this
    }
    /** Test hook: fire an event the way MapLibre would once loading settles. */
    fire(event: string, payload?: unknown) { [...(this.handlers[event] ?? [])].forEach((handler) => handler(payload)) }
    getBounds() { return { getWest: () => -55.2, getSouth: () => 46.2, getEast: () => -50.8, getNorth: () => 48.8 } }
    getCanvas() { return { clientWidth: 1024, clientHeight: 768 } }
    // Layers and sources are recorded, not discarded: the raster path is only
    // trustworthy if the image goes on beneath the basemap labels and is torn
    // down again, and that is invisible unless the fake map remembers.
    private layers: Record<string, unknown> = {}
    private sources: Record<string, unknown> = {}
    private record(key: string, entry: unknown) {
      const globals = globalThis as Record<string, unknown>
      const sink = (globals[key] as unknown[] | undefined) ?? []
      sink.push(entry)
      globals[key] = sink
      globals.__mapLayersNow = Object.keys(this.layers)
    }
    addLayer(layer: { id: string }, beforeId?: string) {
      this.layers[layer.id] = { ...layer, beforeId }
      this.record('__mapLayerAdds', { ...layer, beforeId })
    }
    addSource(id: string, source: unknown) {
      // Image sources answer `updateImage` like MapLibre's do, and updates are
      // recorded: the in-place frame swap is only trustworthy if the fake
      // remembers what the source was last told to show.
      const record = this.record.bind(this)
      this.sources[id] = {
        ...(source as Record<string, unknown>),
        updateImage(options: { url: string; coordinates?: unknown }) {
          Object.assign(this, options)
          record('__mapSourceUpdates', { id, ...options })
        },
      }
      this.record('__mapSourceAdds', { id, source })
    }
    getLayer(id: string) { return this.layers[id] }
    getSource(id: string) { return this.sources[id] }
    setPaintProperty(id: string, name: string, value: unknown) {
      const layer = this.layers[id] as { paint?: Record<string, unknown> } | undefined
      if (layer?.paint) layer.paint[name] = value
      this.record('__mapPaintUpdates', { id, name, value })
    }
    removeLayer(id: string) {
      delete this.layers[id]
      // Removals are recorded too: stack stability across a scrub is only
      // provable if a teardown that should not happen leaves a trace.
      this.record('__mapLayerRemovals', id)
      ;(globalThis as Record<string, unknown>).__mapLayersNow = Object.keys(this.layers)
    }
    removeSource(id: string) { delete this.sources[id] }
    // Reports whatever the test says: MapLibre answers false while any source
    // is still loading, which is exactly when a removal used to be dropped.
    isStyleLoaded() { return ((globalThis as Record<string, unknown>).__mapStyleLoaded as boolean | undefined) ?? true }
    setPadding(padding: unknown) { this.record('__mapPaddings', padding) }
    easeTo() {}
    remove() {}
  }
  ;(globalThis as Record<string, unknown>).__fakeMaps = []
  const Recorded = class extends FakeMap {
    constructor(options: unknown) {
      super(options)
      ;((globalThis as Record<string, unknown>).__fakeMaps as FakeMap[]).push(this)
    }
  }
  return {
    default: {
      Map: Recorded,
      NavigationControl: class {},
      AttributionControl: class {},
      ScaleControl: class {},
    },
  }
})

vi.mock('@deck.gl/layers', () => ({
  ScatterplotLayer: class { constructor(_props: unknown) {} },
  // The label layer's props are recorded: whether a glyph outside ASCII renders
  // at all is decided by `characterSet`, and that is invisible without WebGL.
  TextLayer: class { constructor(props: unknown) { (globalThis as Record<string, unknown>).__textLayerProps = props } },
  GeoJsonLayer: class { constructor(_props: unknown) {} },
}))

vi.mock('@deck.gl/extensions', () => ({
  CollisionFilterExtension: class CollisionFilterExtension {},
}))

vi.mock('@deck.gl/mapbox', () => ({
  MapboxOverlay: class { setProps() {} },
}))

const NOW = new Date('2026-08-30T04:00:00Z')

/** The radar row exactly as `/layers` publishes it (verified live 2026-08-30):
 *  an id-derived title, `mixed` units and a stored-feature kind. An earlier
 *  version of this fixture tested against a nicer title and a dBZ unit the API
 *  never produced. */
const radarLayer: LayerItem = {
  id: 'eccc-radar-radar',
  title: 'eccc-radar radar',
  kind: 'point',
  field: 'radar',
  product: 'Canadian radar composite precipitation rate via GeoMet WMS',
  units: 'mixed',
  semantics: 'No echo means no detected precipitating echo, not clear sky.',
  times: ['2026-08-30T03:54:00Z', '2026-08-30T04:00:00Z'],
  cadence_seconds: 360,
  staleness_tolerance_seconds: 180,
}

const selected = [{ id: radarLayer.id, visible: true, opacity: 0.85 }]

/** `/sources/status` rows shaped as the running API returns them: CYYT's METAR
 *  feed has a recorded retrieval, the SmartAtlantic buoy is catalogued with
 *  none, and Cape Spear claims no source at all. */
const liveStatuses: SourceStatusItem[] = [
  { source_id: 'awc-metar-speci', state: 'implementing', data_mode: 'live', last_retrieval: '2026-08-30T04:23:44Z', detail: 'live retrieval recorded by the ingestion worker' },
  { source_id: 'awc-taf', state: 'implementing', data_mode: 'live', last_retrieval: '2026-08-30T04:28:46Z', detail: 'live retrieval recorded by the ingestion worker' },
  { source_id: 'smartatlantic-st-johns', state: 'implementing', data_mode: 'unavailable', last_retrieval: null, detail: 'no live retrieval recorded' },
]

const panel = (props: Partial<React.ComponentProps<typeof MapPanel>> = {}) => (
  <MapPanel
    label="Test"
    field="Response-backed evidence points"
    validTime={NOW}
    reference={NOW}
    interpolate={false}
    selected={stations[0]}
    onSelect={() => undefined}
    layers={[radarLayer]}
    layersError={null}
    layersLoading={false}
    selections={selected}
    onToggleLayer={() => undefined}
    onSetOpacity={() => undefined}
    onJumpToTime={() => undefined}
    layerNotices={[]}
    evidence={[]}
    sourceStatuses={liveStatuses}
    initialDrawerOpen={true}
    {...props}
  />
)

describe('MapPanel layer stack', () => {
  beforeEach(() => { (globalThis as Record<string, unknown>).__mapControls = [] })
  afterEach(() => vi.unstubAllGlobals())

  it('reports the failure and still surfaces the layer semantics when features cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 404 })))
    render(panel())

    expect((await screen.findAllByText(/could not be read: feature request returned 404/i)).length).toBeGreaterThan(0)
    // The semantics text must reach the user even though the fetch failed — it is
    // where the API explains that "no echo" is not the same as "clear sky".
    expect(screen.getAllByText('No echo means no detected precipitating echo, not clear sky.').length).toBeGreaterThan(0)
  })

  it('draws nothing for an observed layer scrubbed past the reference, and says why on the map', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    // Two hours past the newest frame AND past the session reference: an
    // observed layer never falls forward, and never falls back for a future
    // instant — an old sweep under a future timestamp would misdate it.
    render(panel({ validTime: new Date('2026-08-30T06:00:00Z') }))

    expect((await screen.findAllByText(/observed imagery has no frames for future instants/i)).length).toBeGreaterThan(0)
    // The disclosure is on the map itself, not only in the drawer.
    expect(document.querySelector('.map-frame-notes')?.textContent ?? '').toMatch(/observed imagery has no frames for future instants/i)
    // The guarantee that matters: nothing drawable means nothing requested,
    // so a stale frame cannot arrive and be drawn as though it were current.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('falls back to the previous frame for an observed layer at a past instant, disclosing it on the map', async () => {
    const feature = { type: 'Feature', geometry: { type: 'Point', coordinates: [-52.71, 47.56] }, properties: { radar_echo: 0 } }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ type: 'FeatureCollection', features: [feature] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    // 03:30Z is beyond the 180 s tolerance of both frames but before the
    // reference; only the earlier frame (03:54 is later — the PREVIOUS frame
    // relative to 03:30 does not exist, so use 03:58 style instead). Here the
    // requested instant sits between nothing earlier and the frames later, so
    // shift the reference: ask for 04:10 with reference 04:30 — previous
    // frame is 04:00, 10 minutes earlier.
    render(panel({ validTime: new Date('2026-08-30T04:10:00Z'), reference: new Date('2026-08-30T04:30:00Z') }))

    // The previous frame is fetched and drawn, never the nothing of before.
    expect((await screen.findAllByText(/1 value drawn from frame/i)).length).toBeGreaterThan(0)
    // And the fallback is disclosed on the map, naming the real frame time.
    expect(document.querySelector('.map-frame-notes')?.textContent ?? '').toMatch(/showing .* \(10 min earlier than the selected time\)/i)
  })

  it('names the frame it drew and how far it sits from the requested time', async () => {
    const feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-52.71, 47.56] },
      properties: { radar_echo: 0 },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ type: 'FeatureCollection', features: [feature] }), { status: 200 }),
    ))
    // 03:57Z is three minutes from both frames; the resolver takes 03:54 or 04:00
    // and must state the offset either way rather than implying an exact match.
    render(panel({ validTime: new Date('2026-08-30T03:57:00Z') }))

    expect((await screen.findAllByText(/1 value drawn from frame/i)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/3 min (earlier|later)/i).length).toBeGreaterThan(0)
  })
})

describe('MapPanel scale bar', () => {
  beforeEach(() => {
    ;(globalThis as Record<string, unknown>).__mapControls = []
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200 })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('installs MapLibre\u2019s own ScaleControl and prints no fixed distance of its own', () => {
    const { container } = render(panel())
    expect((globalThis as Record<string, unknown>).__mapControls as string[]).toContain('ScaleControl')
    // The old panel drew a hardcoded "50 km" beside a freely zoomable map. Any
    // distance on this pane must now come from the control, which recomputes it.
    expect(container.querySelector('.map-scale')).toBeNull()
    expect(container.textContent).not.toMatch(/\b50 km\b/)
  })
})

describe('MapPanel station coverage', () => {
  beforeEach(() => {
    ;(globalThis as Record<string, unknown>).__mapControls = []
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200 })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('separates stations with a live ingested source from those without, in text', () => {
    render(panel())
    expect(screen.getByText(/live ingested source awc-metar-speci, awc-taf/i)).toBeInTheDocument()
    expect(screen.getByText(/smartatlantic-st-johns is catalogued but reported no live retrieval/i)).toBeInTheDocument()
    expect(screen.getByText(/no registry source declares coverage of this place/i)).toBeInTheDocument()
  })

  it('reports coverage as unknown, never as absent, when the status endpoint could not be read', () => {
    render(panel({ sourceStatuses: null }))
    expect(screen.getAllByText(/source status could not be read/i).length).toBe(2)
    expect(screen.queryByText(/live ingested source/i)).not.toBeInTheDocument()
  })

  it('declares every glyph the labels use, keeps the apostrophe in place names, and favours the selected station in collisions', () => {
    render(panel())
    const props = (globalThis as Record<string, unknown>).__textLayerProps as {
      characterSet: string[]
      data: Array<{ id: string; name: string }>
      getText: (d: { id: string; name: string }) => string
      getCollisionPriority: (d: { id: string }) => number
      extensions: unknown[]
    }
    // deck.gl's default character set is ASCII; the U+2019 in "St. John’s"
    // and the U+00B7 joiner rendered as blanks until they were declared.
    expect(props.characterSet).toContain('\u2019')
    expect(props.characterSet).toContain('\u00b7')
    const cyyt = props.data.find((d) => d.id === 'cyyt')!
    expect(props.getText(cyyt)).toBe('CYYT \u00b7 live source')
    expect(props.getText(props.data.find((d) => d.id === 'sma-sj')!)).toMatch(/St\. John\u2019s/)
    expect(props.extensions.some((extension) => extension?.constructor?.name === 'CollisionFilterExtension')).toBe(true)
    expect(props.getCollisionPriority(cyyt)).toBeGreaterThan(props.getCollisionPriority({ id: 'cape-spear' }))
  })

  it('pushes every label far enough right that its first glyph clears the marker ring', () => {
    render(panel())
    const props = (globalThis as Record<string, unknown>).__textLayerProps as {
      data: Array<{ id: string; name: string }>
      getText: (d: { id: string; name: string }) => string
      getPixelOffset: (d: { id: string; name: string }) => [number, number]
    }
    // The label is anchored at its middle, so the first glyph sits at the
    // offset minus half the label width. The marker ring is 8 px plus a 2 px
    // stroke; measured in Chrome, IBM Plex Mono at 12 px 600 advances 7.22 px
    // per glyph. The old 3.3 px estimate put the first glyph inside the ring.
    for (const point of props.data) {
      const halfWidth = (props.getText(point).length * 7.22) / 2
      const [dx] = props.getPixelOffset(point)
      expect(dx - halfWidth).toBeGreaterThanOrEqual(9 + 4)
    }
  })
})

/** A proxied HRDPS field: imagery, no stored features, and the evidence basis
 *  the owner made a condition of allowing the proxied route at all. */
const proxiedLayer: LayerItem = {
  id: 'geomet-live-hrdps-tt',
  title: 'HRDPS air temperature (live proxy)',
  kind: 'raster',
  field: 'air_temperature',
  product: 'HRDPS',
  units: 'degC',
  semantics: 'live-proxied imagery: rendered by ECCC GeoMet at request time.',
  times: ['2026-08-30T04:00:00Z', '2026-08-30T05:00:00Z'],
  cadence_seconds: 3600,
  staleness_tolerance_seconds: 1800,
  z_index: 5,
  evidence_basis: 'live_proxy',
  raster_available: true,
  legend_available: true,
  upstream_wms_layer: 'HRDPS.CONTINENTAL_TT',
}

function rasterResponse(overrides: Record<string, string> = {}, drop: string[] = []) {
  const headers: Record<string, string> = {
    'content-type': 'image/png',
    'X-Weather-Retrieval-Status': 'retrieved',
    'X-Weather-Wms-Layer': 'HRDPS.CONTINENTAL_TT',
    'X-Weather-Evidence-Basis': 'live_proxy',
    'X-Weather-Image-Basis': 'live_proxy',
    'X-Weather-Valid-Time': '2026-08-30T04:00:00+00:00',
    'X-Weather-Reference-Time': '2026-08-30T00:00:00+00:00',
    ...overrides,
  }
  drop.forEach((name) => delete headers[name])
  return new Response(new Blob([new Uint8Array([0x89, 0x50])], { type: 'image/png' }), { status: 200, headers })
}

/** Routes by URL so `/features` and `/raster` can answer differently in one test. */
function routedFetch(raster: () => Response, legend?: () => Response, flow?: () => Response, tangents?: () => Response) {
  const notFound = (detail: string) => new Response(JSON.stringify({ detail }), { status: 404, headers: { 'content-type': 'application/json' } })
  return vi.fn(async (url: string) => (url.includes('/raster')
    ? raster()
    : url.includes('/flow')
      // No derived motion (and no Hermite tangents) unless a test provides
      // them: absence is the disclosed fallback at each rung.
      ? (url.includes('texture=tangents')
        ? (tangents ? tangents() : notFound('no tangents'))
        : (flow ? flow() : notFound('no derived motion')))
      : url.includes('/legend') && legend
        ? legend()
        : new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200 })))
}

function flowResponse(overrides: Record<string, string> = {}) {
  return new Response(new Blob([new Uint8Array([0x89, 0x50])], { type: 'image/png' }), {
    status: 200,
    headers: {
      'content-type': 'image/png',
      'X-Weather-Image-Basis': 'derived_motion',
      'X-Weather-Flow-Scale': '12.5000',
      'X-Weather-Frame-From': '2026-08-30T04:00:00+00:00',
      'X-Weather-Frame-To': '2026-08-30T05:00:00+00:00',
      ...overrides,
    },
  })
}

describe('MapPanel imagery', () => {
  let created = 0
  beforeEach(() => {
    created = 0
    ;(globalThis as Record<string, unknown>).__mapControls = []
    ;(globalThis as Record<string, unknown>).__mapLayerAdds = []
    ;(globalThis as Record<string, unknown>).__mapSourceAdds = []
    ;(globalThis as Record<string, unknown>).__mapLayersNow = []
    ;(globalThis as Record<string, unknown>).__mapLayerRemovals = []
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => `blob:image-${++created}`)
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
  })
  afterEach(() => vi.unstubAllGlobals())

  const proxiedPanel = (props: Partial<React.ComponentProps<typeof MapPanel>> = {}) => panel({
    layers: [proxiedLayer],
    selections: [{ id: proxiedLayer.id, visible: true, opacity: 0.6 }],
    ...props,
  })

  it('draws the retrieved image beneath the basemap labels and names what it retrieved', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(proxiedPanel())

    expect((await screen.findAllByText(/Imagery retrieved from HRDPS\.CONTINENTAL_TT/i)).length).toBeGreaterThan(0)
    const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string; beforeId?: string; paint?: Record<string, unknown> }>
    const raster = adds.find((add) => add.id === `raster-${proxiedLayer.id}-0`)
    expect(raster).toBeDefined()
    // Beneath the labels, and at the opacity the stack already carries.
    expect(raster?.beforeId).toBe('reference-water-casing')
    expect(raster?.paint?.['raster-opacity']).toBe(0.6)
    // The extent is the map's own bounds, sent as four separate parameters.
    const sources = (globalThis as Record<string, unknown>).__mapSourceAdds as Array<{ id: string; source: { coordinates: number[][] } }>
    expect(sources.find((entry) => entry.id === `raster-${proxiedLayer.id}-0`)?.source.coordinates)
      .toEqual([[-55.2, 48.8], [-50.8, 48.8], [-50.8, 46.2], [-55.2, 46.2]])
  })

  it('requests the map bounds as named parameters, never a packed bbox', async () => {
    const fetchMock = routedFetch(() => rasterResponse())
    vi.stubGlobal('fetch', fetchMock)
    render(proxiedPanel())
    await screen.findAllByText(/Imagery retrieved/i)

    const requested = fetchMock.mock.calls.map(([url]) => String(url)).find((url) => url.includes('/raster')) ?? ''
    expect(requested).toMatch(/south=46\.20000/)
    expect(requested).toMatch(/west=-55\.20000/)
    expect(requested).toMatch(/north=48\.80000/)
    expect(requested).toMatch(/east=-50\.80000/)
    expect(requested).not.toMatch(/bbox=/)
  })

  it('never requests imagery for a layer that declares none', async () => {
    const fetchMock = routedFetch(() => rasterResponse())
    vi.stubGlobal('fetch', fetchMock)
    render(proxiedPanel({ layers: [{ ...proxiedLayer, raster_available: false, legend_available: false }] }))

    expect((await screen.findAllByText(/No map image requested: this layer declares no map image/i)).length).toBeGreaterThan(0)
    expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes('/raster'))).toBe(false)
  })

  it('draws a layer whose provider serves no legend, and says it carries none', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(proxiedPanel({ layers: [{ ...proxiedLayer, legend_available: false }] }))

    expect((await screen.findAllByText(/Imagery retrieved from HRDPS\.CONTINENTAL_TT/i)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/serves no legend for this layer/i).length).toBeGreaterThan(0)
    // The client never fetches or invents a scale of its own in that case.
    expect(document.querySelector('.stack-legend img')).toBeNull()
  })

  it('composites a forecast layer as two real frames at fractional opacities when interpolation is on', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    // 04:30 sits exactly halfway between the layer's 04:00 and 05:00 frames.
    render(proxiedPanel({ interpolate: true, validTime: new Date('2026-08-30T04:30:00Z') }))

    await screen.findAllByText(/Display composite of two retrieved frames/i)
    const findSlots = () => {
      const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string; paint?: Record<string, unknown> }>
      return [adds.find((add) => add.id === `raster-${proxiedLayer.id}-0`), adds.find((add) => add.id === `raster-${proxiedLayer.id}-1`)]
    }
    await waitFor(() => expect(findSlots().every(Boolean)).toBe(true))
    const [previous, next] = findSlots()
    // Each slot is the stack opacity (0.6) times its time-fraction weight (0.5).
    expect(previous?.paint?.['raster-opacity']).toBeCloseTo(0.3, 5)
    expect(next?.paint?.['raster-opacity']).toBeCloseTo(0.3, 5)
    // The on-map note calls it display compositing, naming both frames.
    expect(document.querySelector('.map-frame-notes')?.textContent ?? '').toMatch(/display compositing of the .* and .* NT frames — display only, not evidence/i)
  })

  it('never shows a half blend: one failed frame falls back to the nearer whole frame', async () => {
    let call = 0
    // The 05:00 frame request fails; the 04:00 one succeeds.
    vi.stubGlobal('fetch', routedFetch(() => (call++ === 0
      ? rasterResponse()
      : new Response(JSON.stringify({ detail: 'connection reset' }), { status: 502, headers: { 'content-type': 'application/json' } }))))
    // 04:12 is nearer the 04:00 frame.
    render(proxiedPanel({ interpolate: true, validTime: new Date('2026-08-30T04:12:00Z') }))

    await screen.findAllByText(/Imagery retrieved/i)
    const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string; paint?: Record<string, unknown> }>
    const shown = adds.filter((add) => add.id.startsWith(`raster-${proxiedLayer.id}`))
    // One slot, at the full stack opacity — never a lone fractional slot
    // presenting a partial retrieval as a blend.
    expect(shown).toHaveLength(1)
    expect(shown[0].paint?.['raster-opacity']).toBeCloseTo(0.6, 5)
    expect(document.querySelector('.map-frame-notes')?.textContent ?? '').toMatch(/the second frame of the display composite was not retrieved/i)
  })

  const strataBlend: LayerItem = {
    id: 'noaa-gfs-surface-cloud-low', title: 'Global Forecast System (GFS 0.25 deg) low cloud cover (rendered grid)',
    kind: 'raster', field: 'cloud_low', product: 'Global Forecast System (GFS 0.25 deg)', units: 'percent',
    semantics: 'rendered by this experiment; nearest-neighbor; never smoothed',
    times: ['2026-08-30T04:00:00Z', '2026-08-30T05:00:00Z'], cadence_seconds: 3600, staleness_tolerance_seconds: 1800,
    evidence_basis: 'published_artifact', raster_available: true, legend_available: true, group: 'rendered_grid',
  }
  const renderedRaster = () => rasterResponse(
    { 'X-Weather-Image-Basis': 'rendered_grid', 'X-Weather-Source-Id': 'noaa-gfs', 'X-Weather-Evidence-Basis': 'published_artifact' },
    ['X-Weather-Wms-Layer'],
  )
  const strataPanel = (props: Partial<React.ComponentProps<typeof MapPanel>> = {}) => panel({
    layers: [strataBlend],
    selections: [{ id: strataBlend.id, visible: true, opacity: 0.85 }],
    ...props,
  })

  it('interpolates a rendered-grid blend through one shader layer, crossfading when no motion exists', async () => {
    const fetchMock = routedFetch(() => renderedRaster())
    vi.stubGlobal('fetch', fetchMock)
    render(strataPanel({ interpolate: true, validTime: new Date('2026-08-30T04:30:00Z') }))

    await waitFor(() => {
      const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string; type?: string; beforeId?: string }>
      expect(adds.some((add) => add.id === `flowblend-${strataBlend.id}` && add.type === 'custom')).toBe(true)
    })
    const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string; beforeId?: string }>
    // One shader layer under the labels; never the stacked opacity pair whose
    // composite is 1-(1-a)(1-b) rather than a linear cross-dissolve.
    expect(adds.find((add) => add.id === `flowblend-${strataBlend.id}`)?.beforeId).toBe('reference-water-casing')
    expect(adds.some((add) => add.id.startsWith(`raster-${strataBlend.id}`))).toBe(false)
    // The flow endpoint was asked; its 404 is the disclosed crossfade fallback.
    await waitFor(() => {
      expect(fetchMock.mock.calls.map(([url]) => String(url)).some((url) => url.includes('/flow'))).toBe(true)
      const note = document.querySelector('.map-frame-notes')?.textContent ?? ''
      expect(note).toMatch(/temporally interpolated for display between the .* and .* NT frames/i)
      expect(note).toMatch(/linear cross-dissolve; no derived motion field for this pair/i)
      expect(note).toMatch(/display only, not evidence/i)
    })
  })

  it('keeps the same painted stack while scrubbing across a real frame with interpolation on', async () => {
    vi.stubGlobal('fetch', routedFetch(() => renderedRaster()))
    // Exactly on the 04:00 frame: the layer still draws through the shader
    // layer (both inputs the real frame, t = 0 — the identity), never a
    // raster slot, so the stack has the same shape as a between-frames blend.
    const { rerender } = render(strataPanel({ interpolate: true, validTime: new Date('2026-08-30T04:00:00Z') }))
    await waitFor(() => {
      expect((globalThis as Record<string, unknown>).__mapLayersNow as string[]).toContain(`flowblend-${strataBlend.id}`)
    })
    const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string }>
    expect(adds.some((add) => add.id.startsWith(`raster-${strataBlend.id}`))).toBe(false)
    // An exact frame carries no blend disclosure: nothing is composited.
    expect(document.querySelector('.map-frame-notes')?.textContent ?? '').not.toMatch(/temporally interpolated/i)

    // Scrub into the pair and across to the next real frame: the shader layer
    // is updated in place — nothing is ever torn down, so nothing can flash.
    ;(globalThis as Record<string, unknown>).__mapLayerRemovals = []
    rerender(strataPanel({ interpolate: true, validTime: new Date('2026-08-30T04:30:00Z') }))
    await waitFor(() => {
      expect(document.querySelector('.map-frame-notes')?.textContent ?? '').toMatch(/temporally interpolated for display/i)
    })
    rerender(strataPanel({ interpolate: true, validTime: new Date('2026-08-30T05:00:00Z') }))
    await waitFor(() => {
      expect(document.querySelector('.map-frame-notes')?.textContent ?? '').not.toMatch(/temporally interpolated/i)
    })
    expect((globalThis as Record<string, unknown>).__mapLayerRemovals as string[]).toEqual([])
    expect((globalThis as Record<string, unknown>).__mapLayersNow as string[]).toContain(`flowblend-${strataBlend.id}`)
  })

  it('names the advection-corrected method when the pair has a derived motion field', async () => {
    vi.stubGlobal('fetch', routedFetch(() => renderedRaster(), undefined, () => flowResponse()))
    render(strataPanel({ interpolate: true, validTime: new Date('2026-08-30T04:30:00Z') }))
    await waitFor(() => {
      expect(document.querySelector('.map-frame-notes')?.textContent ?? '').toMatch(/advection-corrected along a motion field derived from the two published frames/i)
    })
  })

  it('names the C1 trajectory method when the pair also has Hermite tangents', async () => {
    vi.stubGlobal('fetch', routedFetch(() => renderedRaster(), undefined, () => flowResponse(), () => flowResponse({ 'X-Weather-Flow-Texture': 'tangents' })))
    render(strataPanel({ interpolate: true, validTime: new Date('2026-08-30T04:30:00Z') }))
    await waitFor(() => {
      const note = document.querySelector('.map-frame-notes')?.textContent ?? ''
      expect(note).toMatch(/advection-corrected along motion fitted through neighbouring published frames \(C1 trajectories\)/i)
      expect(note).toMatch(/display only, not evidence/i)
    })
  })

  it('keeps the previous frame drawn, at its own instant, while the next one loads', async () => {
    let resolveSecond: (response: Response) => void = () => undefined
    let rasterCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/raster')) {
        rasterCalls += 1
        if (rasterCalls === 1) return rasterResponse()
        return new Promise<Response>((resolve) => { resolveSecond = resolve })
      }
      if (url.includes('/flow')) return new Response('{}', { status: 404 })
      return new Response(JSON.stringify({ type: 'FeatureCollection', features: [] }), { status: 200 })
    }))
    const { rerender } = render(proxiedPanel())
    await screen.findAllByText(/Imagery retrieved/i)

    rerender(proxiedPanel({ validTime: new Date('2026-08-30T05:00:00Z') }))
    // The map never blanks: the last retrieved frame stays painted while the
    // newly selected one is in flight, and the text says exactly that.
    await screen.findAllByText(/until it arrives the last retrieved frame stays drawn at its own instant/i)
    expect((globalThis as Record<string, unknown>).__mapLayersNow as string[]).toContain(`raster-${proxiedLayer.id}-0`)

    resolveSecond(rasterResponse({ 'X-Weather-Valid-Time': '2026-08-30T05:00:00+00:00' }))
    await waitFor(() => expect(screen.queryAllByText(/stays drawn at its own instant/i)).toHaveLength(0))
  })

  it('prefetches every frame of a locally rendered layer without touching proxied budgets', async () => {
    const fetchMock = routedFetch(() => renderedRaster())
    vi.stubGlobal('fetch', fetchMock)
    render(strataPanel())
    // The 04:00 frame draws now; the 05:00 frame is warmed at idle priority
    // so a scrub to it costs nothing.
    await waitFor(() => {
      const requested = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/raster'))
      expect(requested.some((url) => url.includes('2026-08-30T05'))).toBe(true)
    }, { timeout: 3000 })
  })

  it('exposes the frame notes as a polite status region', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(proxiedPanel({ interpolate: true, validTime: new Date('2026-08-30T04:30:00Z') }))
    await screen.findAllByText(/Display composite/i)
    const notes = document.querySelector('.map-frame-notes')
    expect(notes?.getAttribute('role')).toBe('status')
    expect(notes?.getAttribute('aria-live')).toBe('polite')
  })

  it('reuses a recently retrieved frame instead of refetching it, and releases every frame on unmount', async () => {
    const fetchMock = routedFetch(() => rasterResponse())
    vi.stubGlobal('fetch', fetchMock)
    const { rerender, unmount } = render(proxiedPanel())
    await screen.findAllByText(/Imagery retrieved/i)
    const rasterCalls = () => fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/raster')).length
    const afterFirst = rasterCalls()

    rerender(proxiedPanel({ validTime: new Date('2026-08-30T05:00:00Z') }))
    await waitFor(() => expect(rasterCalls()).toBe(afterFirst + 1))

    // Scrubbing back to the first frame reuses its retained image: no third
    // request is spent from the upstream budget for bytes already held.
    rerender(proxiedPanel({ validTime: NOW }))
    await screen.findAllByText(/Imagery retrieved/i)
    expect(rasterCalls()).toBe(afterFirst + 1)

    // On unmount every retained frame is released; none outlives the map.
    unmount()
    const revoked = (URL as unknown as { revokeObjectURL: ReturnType<typeof vi.fn> }).revokeObjectURL.mock.calls.flat()
    expect(revoked).toContain('blob:image-1')
  })

  it('reports a transparent image as a reading rather than an outage', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 1, height: 1 })))
    vi.stubGlobal('OffscreenCanvas', class {
      constructor(_width: number, _height: number) {}
      getContext() {
        return { drawImage: () => undefined, getImageData: () => ({ data: Uint8ClampedArray.from([0, 0, 0, 0]) }) }
      }
    })
    render(proxiedPanel())

    expect((await screen.findAllByText(/retrieved, and nothing was detected/i)).length).toBeGreaterThan(0)
    expect(screen.queryAllByText(/Imagery not retrieved/i).length).toBe(0)
  })

  it('names a spent request budget as a limit on our requests, not as missing weather', async () => {
    vi.stubGlobal('fetch', routedFetch(() => new Response(JSON.stringify({ detail: 'upstream budget exhausted' }), { status: 429, headers: { 'content-type': 'application/json' } })))
    render(proxiedPanel())

    expect((await screen.findAllByText(/request budget was reached/i)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/not an absence of weather/i).length).toBeGreaterThan(0)
    // Nothing was drawn, so no image layer was ever put on the map.
    const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string }>
    expect(adds.some((add) => add.id.startsWith('raster-'))).toBe(false)
  })

  it('says the upstream could not be reached, and leaves no image behind', async () => {
    let call = 0
    vi.stubGlobal('fetch', routedFetch(() => (call++ === 0
      ? rasterResponse()
      : new Response(JSON.stringify({ detail: 'connection reset' }), { status: 502, headers: { 'content-type': 'application/json' } }))))
    const { rerender } = render(proxiedPanel())
    await screen.findAllByText(/Imagery retrieved/i)

    rerender(proxiedPanel({ validTime: new Date('2026-08-30T05:00:00Z') }))
    expect((await screen.findAllByText(/no image was retrieved from the provider: connection reset/i)).length).toBeGreaterThan(0)
    // The previously drawn frame is removed rather than left under a new time.
    await waitFor(() => {
      expect((globalThis as Record<string, unknown>).__mapLayersNow as string[]).not.toContain(`raster-${proxiedLayer.id}-0`)
    })
    expect(screen.queryAllByText(/Imagery retrieved from/i).length).toBe(0)
  })

  it('removes the image of a layer toggled off while the style is still loading, and again once it has loaded', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    const globals = globalThis as Record<string, unknown>
    const { rerender } = render(proxiedPanel())
    await screen.findAllByText(/Imagery retrieved/i)
    await waitFor(() => expect(globals.__mapLayersNow as string[]).toContain(`raster-${proxiedLayer.id}-0`))

    // MapLibre reports the style as not loaded while the image source it was
    // just handed is still being read. An untoggle landing in that window used
    // to be skipped, and the image stayed painted under a drawer saying "0 on".
    globals.__mapStyleLoaded = false
    rerender(proxiedPanel({ selections: [] }))
    expect(globals.__mapLayersNow as string[]).not.toContain(`raster-${proxiedLayer.id}-0`)
    expect(screen.queryAllByText(/Imagery retrieved from/i).length).toBe(0)

    globals.__mapStyleLoaded = true
    const maps = globals.__fakeMaps as Array<{ fire: (event: string) => void }>
    maps[maps.length - 1].fire('idle')
    expect(globals.__mapLayersNow as string[]).not.toContain(`raster-${proxiedLayer.id}-0`)
  })

  it('draws nothing when the response carries no retrieval provenance', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse({}, ['X-Weather-Retrieval-Status'])))
    render(proxiedPanel())

    expect((await screen.findAllByText(/carried no retrieval provenance/i)).length).toBeGreaterThan(0)
    const adds = (globalThis as Record<string, unknown>).__mapLayerAdds as Array<{ id: string }>
    expect(adds.some((add) => add.id.startsWith('raster-'))).toBe(false)
  })

  it('states the evidence basis in words, in the panel and in the text alternative', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(proxiedPanel())
    await screen.findAllByText(/Imagery retrieved/i)

    // Once in the layer stack, once in the map-contents-as-text list.
    expect(screen.getAllByText(/Not a published artifact: it has not passed ingest, QC or atomic publication/i).length).toBeGreaterThan(1)
  })

  it('describes a layer with no declared basis as unknown rather than as published', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(proxiedPanel({ layers: [{ ...proxiedLayer, evidence_basis: undefined }] }))

    expect((await screen.findAllByText(/Unknown evidence basis/i)).length).toBeGreaterThan(0)
    expect(screen.queryAllByText(/passed ingest, QC and atomic publication/i).length).toBe(0)
  })
})

describe('MapPanel layer drawer', () => {
  beforeEach(() => {
    ;(globalThis as Record<string, unknown>).__mapControls = []
    ;(globalThis as Record<string, unknown>).__mapLayerAdds = []
    ;(globalThis as Record<string, unknown>).__mapSourceAdds = []
    ;(globalThis as Record<string, unknown>).__mapLayersNow = []
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => 'blob:image-1')
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
  })
  afterEach(() => vi.unstubAllGlobals())

  /** The two published-model grids as `/layers` really lists them: a stored
   *  artifact, `kind: raster`, and `raster_available: false` because the API
   *  answers 501 to any image request for them. */
  const storedGrid: LayerItem = {
    id: 'eccc-hrdps-surface', title: 'eccc-hrdps surface', kind: 'raster', field: 'surface', product: 'ECCC-HRDPS', units: 'mixed',
    semantics: 'published HRDPS surface grid', times: ['2026-08-30T04:00:00Z'], staleness_tolerance_seconds: 1800,
    evidence_basis: 'published_artifact', raster_available: false, legend_available: false,
  }

  it('collapses to a toggle that still says how many layers are on, and reopens', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(panel())
    const toggle = screen.getByRole('button', { name: /Layers \(1 on\)/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('checkbox', { name: /eccc-radar radar/ })).toBeChecked()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('checkbox', { name: /eccc-radar radar/ })).not.toBeInTheDocument()
    // The text alternative is not part of the drawer and does not collapse with it.
    expect(screen.getByRole('heading', { name: 'Map contents as text' })).toBeInTheDocument()

    fireEvent.click(toggle)
    expect(screen.getByRole('checkbox', { name: /eccc-radar radar/ })).toBeInTheDocument()
  })

  it('starts closed in the product and closes an open drawer with Escape', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    const { rerender } = render(panel({ initialDrawerOpen: false }))
    expect(screen.getByRole('button', { name: /Layers \(1 on\)/ })).toHaveAttribute('aria-expanded', 'false')
    rerender(panel({ initialDrawerOpen: true }))
    fireEvent.click(screen.getByRole('button', { name: /Layers \(1 on\)/ }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByRole('button', { name: /Layers \(1 on\)/ })).toHaveAttribute('aria-expanded', 'false')
  })

  it('announces a reference source failure without removing the weather text alternative', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(panel())
    const map = ((globalThis as Record<string, unknown>).__fakeMaps as Array<{ fire: (event: string, payload?: unknown) => void }>).at(-1)
    act(() => map?.fire('error', { sourceId: 'openfreemap' }))
    expect(screen.getByText(/Reference map unavailable/)).toHaveAttribute('role', 'status')
    expect(screen.getByText('Map contents as text')).toBeInTheDocument()
  })

  it('groups rows under headings from the layer group, deriving one only when the API gave none', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(panel({
      layers: [
        { ...radarLayer, group: 'observation' },
        { ...proxiedLayer, group: undefined },
        { ...storedGrid, group: undefined },
        { ...radarLayer, id: 'eccc-cap-alerts-alerts_features', title: 'CAP alert polygons', kind: 'alert', group: 'alert' },
        // Satellite imagery is observed and past-only, so it heads the list:
        // the shared order (api.ts) puts what cannot be forecast first.
        { ...proxiedLayer, id: 'geomet-live-goes-east-naturalcolor', title: 'GOES-East natural color (1 km, live proxy)', product: 'GOES-East', group: 'satellite' },
      ],
      selections: [],
    }))
    const headings = screen.getAllByRole('heading', { level: 4 }).map((heading) => heading.textContent)
    expect(headings).toEqual(['Satellite (observed, past only)', 'Observations', 'Alerts', 'Forecast · live proxy', 'Published model grids'])
    expect(within(screen.getByRole('group', { name: 'Observations' })).getByRole('checkbox', { name: /eccc-radar radar/ })).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Forecast · live proxy' })).getByRole('checkbox', { name: /HRDPS air temperature/ })).toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Satellite (observed, past only)' })).getByRole('checkbox', { name: /GOES-East natural color/ })).toBeInTheDocument()
    // A satellite layer that declares no group is not guessed from its id: it
    // falls back to the basis-derived group like any other proxied layer.
    expect(within(screen.getByRole('group', { name: 'Forecast · live proxy' })).queryByRole('checkbox', { name: /GOES-East/ })).not.toBeInTheDocument()
  })

  it('files a rendered-grid layer under its own heading with its own legend caption', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    const strata: LayerItem = {
      id: 'noaa-gfs-surface-cloud-low', title: 'Global Forecast System (GFS 0.25 deg) low cloud cover (rendered grid)',
      kind: 'raster', field: 'cloud_low', product: 'Global Forecast System (GFS 0.25 deg)', units: 'percent',
      semantics: 'rendered by this experiment from retrieved NOAA GFS GRIB2 fields; nearest-neighbor at the native 0.25 deg cells; never smoothed',
      times: ['2026-08-30T04:00:00Z'], cadence_seconds: 3600, staleness_tolerance_seconds: 1800,
      evidence_basis: 'published_artifact', raster_available: true, legend_available: true, group: 'rendered_grid',
    }
    render(panel({ layers: [strata], selections: [{ id: strata.id, visible: true, opacity: 0.85 }] }))
    const group = screen.getByRole('group', { name: 'Rendered grids (drawn here from stored model data)' })
    expect(within(group).getByRole('checkbox', { name: /low cloud cover/ })).toBeChecked()
    // The legend is OUR colormap and must not be captioned as a provider's.
    expect(screen.getByText(/Rendering colormap, served by this experiment/)).toBeInTheDocument()
    expect(screen.queryByText(/Provider legend, fetched from the provider/)).not.toBeInTheDocument()
    // The basis sentence says the imagery was drawn here from stored values.
    expect(screen.getAllByText(/rendered by this experiment from the stored grid values/i).length).toBeGreaterThan(0)
    expect(screen.queryByText(/rendered live by the provider/)).not.toBeInTheDocument()
  })

  it('shows a stored grid that has no map image as a disabled row with the one reason, and no contradicting sentence', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(panel({ layers: [storedGrid], selections: [{ id: storedGrid.id, visible: true, opacity: 0.85 }] }))
    const checkbox = screen.getByRole('checkbox', { name: /eccc-hrdps surface/ })
    expect(checkbox).toBeDisabled()
    expect(screen.getAllByText(/publishes a stored grid but no map image; read it through the forecast panel/i).length).toBeGreaterThan(0)
    // The old state line said "publishes imagery, not stored features" about a
    // layer whose raster line said it declares no map image.
    expect(screen.queryByText(/publishes imagery, not stored features/i)).not.toBeInTheDocument()
  })

  it('lands the radar rain-only notice on the radar row and the rest in the footer', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    const radarNotice = 'eccc-radar-radar records "layers=[\'RADAR_1KM_RRAI\', \'RADAR_1KM_RSNO\']", which names 2 WMS layers and is not a valid LAYERS value; imagery is drawn from RADAR_1KM_RRAI alone'
    const generalNotice = 'layers marked evidence_basis=live_proxy are rendered by ECCC GeoMet at request time.'
    render(panel({ layerNotices: [radarNotice, generalNotice] }))
    const row = screen.getByRole('checkbox', { name: /eccc-radar radar/ }).closest('.drawer-row') as HTMLElement
    expect(within(row).getByText(/drawn from RADAR_1KM_RRAI alone/)).toBeInTheDocument()
    const footer = screen.getByRole('note', { name: 'Layer catalogue notices' })
    expect(within(footer).getByText(/rendered by ECCC GeoMet at request time/)).toBeInTheDocument()
    expect(within(footer).queryByText(/RADAR_1KM_RRAI alone/)).not.toBeInTheDocument()
  })

  it('names the reason and the nearest frame when nothing may be drawn, and offers a jump to it', () => {
    const fetchMock = routedFetch(() => rasterResponse())
    vi.stubGlobal('fetch', fetchMock)
    const onJumpToTime = vi.fn()
    // Two hours past the newest frame AND past the reference: an observed
    // layer resolves nothing there, and the drawer names why plus how far
    // away the nearest real evidence sits.
    render(panel({ validTime: new Date('2026-08-30T06:00:00Z'), onJumpToTime }))
    expect(screen.getAllByText(/observed imagery has no frames for future instants/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Nearest frame/)).toHaveTextContent(/2\.0 h earlier/)
    fireEvent.click(screen.getByRole('button', { name: /Jump to nearest frame/ }))
    expect(onJumpToTime).toHaveBeenCalledWith(new Date('2026-08-30T04:00:00Z'))
    // Still nothing requested: the jump is the reader's choice, not an auto-draw.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('labels an untimed image as current rather than stamping the scrubbed time on it', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse({ 'X-Weather-Valid-Time': 'none', 'X-Weather-Reference-Time': 'none' })))
    render(panel({ layers: [proxiedLayer], selections: [{ id: proxiedLayer.id, visible: true, opacity: 0.6 }] }))
    expect((await screen.findAllByText(/current image, not time-indexed/i)).length).toBeGreaterThan(0)
    expect(screen.queryAllByText(/valid 2026-08-30T04:00:00/i).length).toBe(0)
  })

  it('renders the notice the image response carries', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse({ 'X-Weather-Wms-Layer-Notice': 'imagery is drawn from RADAR_1KM_RRAI alone' })))
    render(panel({ layers: [proxiedLayer], selections: [{ id: proxiedLayer.id, visible: true, opacity: 0.6 }] }))
    expect((await screen.findAllByText(/Notice: imagery is drawn from RADAR_1KM_RRAI alone/i)).length).toBeGreaterThan(0)
  })

  it('replaces a legend that failed to load with the API\u2019s own reason, never a broken image', async () => {
    vi.stubGlobal('fetch', routedFetch(
      () => rasterResponse(),
      () => new Response(JSON.stringify({ detail: 'no legend was retrieved upstream: Current-Alerts: LayerNotDefined' }), { status: 502, headers: { 'content-type': 'application/json' } }),
    ))
    render(panel({ layers: [proxiedLayer], selections: [{ id: proxiedLayer.id, visible: true, opacity: 0.6 }] }))
    await screen.findAllByText(/Imagery retrieved/i)
    const img = document.querySelector('.stack-legend img') as HTMLImageElement
    expect(img).not.toBeNull()
    fireEvent.error(img)
    expect(await screen.findByText(/No legend was retrieved from the provider: no legend was retrieved upstream: Current-Alerts: LayerNotDefined/)).toBeInTheDocument()
    expect(document.querySelector('.stack-legend img')).toBeNull()
  })

  it('says a future frame is a forecast lead in the frame line', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    const soon = new Date(Date.now() + 6 * 3600 * 1000)
    const iso = soon.toISOString().replace(/\.\d{3}Z$/, 'Z')
    render(panel({
      validTime: soon,
      layers: [{ ...proxiedLayer, times: [iso] }],
      selections: [{ id: proxiedLayer.id, visible: true, opacity: 0.6 }],
    }))
    expect(await screen.findByText(/forecast lead \+6 h/)).toBeInTheDocument()
  })

  it('renders the middle dot in the frame line as a glyph, not as an escape sequence', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(panel({ layers: [proxiedLayer], selections: [{ id: proxiedLayer.id, visible: true, opacity: 0.6 }] }))
    await screen.findAllByText(/Imagery retrieved/i)
    const line = document.querySelector('.stack-frame')?.textContent ?? ''
    // JSX text does not process JavaScript escapes, so the six characters
    // "\\u00b7" were rendered verbatim on every frame line.
    expect(line).toContain('\u00b7')
    expect(line).not.toContain('\\u00b7')
    expect(line).toMatch(/^Frame /)
  })

  it('calls a stored-feature frame a retrieval, and keeps calling an imagery frame a frame', async () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse({ 'X-Weather-Valid-Time': 'none', 'X-Weather-Reference-Time': 'none' })))
    const alerts: LayerItem = { ...proxiedLayer, id: 'eccc-cap-alerts-alerts_features', title: 'CAP alert polygons', kind: 'alert', group: 'alert' }
    render(panel({
      layers: [alerts, proxiedLayer],
      selections: [{ id: alerts.id, visible: true, opacity: 0.6 }, { id: proxiedLayer.id, visible: true, opacity: 0.6 }],
    }))
    await screen.findAllByText(/current image, not time-indexed/i)
    // The polygons were fetched at that instant, so the tolerance is honest;
    // only "Frame" conflated the retrieval with the untimed image's valid time.
    const alertRow = screen.getByRole('checkbox', { name: /CAP alert polygons/ }).closest('.drawer-row') as HTMLElement
    expect(within(alertRow).getByText(/^Retrieved /, { selector: '.stack-frame' })).toBeInTheDocument()
    expect(within(alertRow).getByText(/current image, not time-indexed/)).toBeInTheDocument()
    const rasterRow = screen.getByRole('checkbox', { name: /HRDPS air temperature/ }).closest('.drawer-row') as HTMLElement
    expect(within(rasterRow).getByText(/^Frame /, { selector: '.stack-frame' })).toBeInTheDocument()
  })

  it('pads the map for the open drawer so the stations stay in the visible part, and unpads on close', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    ;(globalThis as Record<string, unknown>).__mapPaddings = []
    render(panel())
    const paddings = () => (globalThis as Record<string, unknown>).__mapPaddings as Array<{ right: number }>
    // Open by default: the drawer body covers the right 300 px of the pane.
    expect(paddings().at(-1)?.right).toBe(300)
    fireEvent.click(screen.getByRole('button', { name: /Layers \(1 on\)/ }))
    expect(paddings().at(-1)?.right).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: /Layers \(1 on\)/ }))
    expect(paddings().at(-1)?.right).toBe(300)
  })

  it('holds the loading sentence in the drawer header rather than an empty list', () => {
    vi.stubGlobal('fetch', routedFetch(() => rasterResponse()))
    render(panel({ layers: [], selections: [], layersLoading: true }))
    expect(screen.getByRole('status')).toHaveTextContent('Loading published layers…')
  })
})
