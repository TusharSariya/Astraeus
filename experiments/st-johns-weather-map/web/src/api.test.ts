import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_CLOUD_BANDS, LAYER_GROUP_LABELS, LAYER_GROUP_ORDER, cloudBandOf, describeEvidenceBasis, filterCloudLayers, groupLayers, layerGroup, layerRasterUrl, loadLayerRaster, loadStory, loadTimeline, normalizePoint, pointProductFor, type ApiPointResponse } from './api'
import type { CatalogSource, CloudLayerReading, LayerItem, TimelineResponse } from './types'

const rasterLayer: LayerItem = {
  id: 'geomet-live-hrdps-tt',
  title: 'HRDPS air temperature (live proxy)',
  kind: 'raster',
  field: 'air_temperature',
  product: 'HRDPS',
  units: 'degC',
  semantics: 'live-proxied imagery',
  times: ['2026-08-31T04:00:00Z'],
  staleness_tolerance_seconds: 3600,
  evidence_basis: 'live_proxy',
  raster_available: true,
  legend_available: true,
  upstream_wms_layer: 'HRDPS.CONTINENTAL_TT',
}

const bounds = { west: -55.2, south: 46.2, east: -50.8, north: 48.8, widthPx: 1024.4, heightPx: 768.6 }

/** The provenance headers the endpoint actually returns, verified live against
 *  `/layers/geomet-live-hrdps-tt/raster`. */
function rasterHeaders(overrides: Record<string, string> = {}): Record<string, string> {
  return {
    'content-type': 'image/png',
    'X-Weather-Retrieval-Status': 'retrieved',
    'X-Weather-Wms-Layer': 'HRDPS.CONTINENTAL_TT',
    'X-Weather-Evidence-Basis': 'live_proxy',
    'X-Weather-Image-Basis': 'live_proxy',
    'X-Weather-Valid-Time': '2026-08-31T04:00:00+00:00',
    'X-Weather-Reference-Time': '2026-08-30T00:00:00+00:00',
    'X-Weather-Upstream-Url': 'https://geo.weather.gc.ca/geomet/?service=WMS',
    'X-Weather-Attribution': 'Environment and Climate Change Canada - MSC GeoMet',
    'X-Weather-Byte-Size': '45227',
    ...overrides,
  }
}

const pngBody = () => new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: 'image/png' })

describe('raster request contract', () => {
  // The endpoint takes `south`, `west`, `north` and `east` as separate query
  // parameters. A packed `bbox` is not in its signature: FastAPI would ignore it,
  // substitute its default Avalon box, and return a well-formed image of the
  // wrong extent with no error at all. That is invisible on screen, so it is
  // asserted here on the URL itself.
  it('names each bound separately and sends neither a packed bbox nor a crs', () => {
    const url = new URL(layerRasterUrl(rasterLayer, { ...bounds, validTime: '2026-08-31T04:00:00Z' }), 'http://localhost')
    expect([...url.searchParams.keys()].sort()).toEqual(['east', 'height', 'north', 'south', 'valid_time', 'west', 'width'])
    expect(url.searchParams.get('south')).toBe('46.20000')
    expect(url.searchParams.get('west')).toBe('-55.20000')
    expect(url.searchParams.get('north')).toBe('48.80000')
    expect(url.searchParams.get('east')).toBe('-50.80000')
    expect(url.searchParams.get('valid_time')).toBe('2026-08-31T04:00:00Z')
    expect(url.searchParams.has('bbox')).toBe(false)
    expect(url.searchParams.has('crs')).toBe(false)
  })

  it('rounds pixel dimensions and clamps them to the size the endpoint will render', () => {
    const url = new URL(layerRasterUrl(rasterLayer, { ...bounds, widthPx: 4000, heightPx: 768.6 }), 'http://localhost')
    expect(url.searchParams.get('width')).toBe('2048')
    expect(url.searchParams.get('height')).toBe('769')
  })
})

describe('raster retrieval', () => {
  beforeEach(() => {
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => 'blob:image-1')
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('refuses to draw bytes that carry no retrieval provenance', async () => {
    const headers = rasterHeaders()
    delete headers['X-Weather-Retrieval-Status']
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers })))

    const result = await loadLayerRaster(rasterLayer, bounds)
    expect(result.image).toBeNull()
    expect(result.error).toMatch(/no retrieval provenance/i)
  })

  it('refuses bytes that name no upstream layer', async () => {
    const headers = rasterHeaders()
    delete headers['X-Weather-Wms-Layer']
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers })))

    expect((await loadLayerRaster(rasterLayer, bounds)).image).toBeNull()
  })

  it('keeps the budget, the upstream and the missing-imagery failures apart', async () => {
    const reason = async (status: number, detail: string) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status, headers: { 'content-type': 'application/json' } })))
      return (await loadLayerRaster(rasterLayer, bounds)).error ?? ''
    }
    // A budget we spent is not an absence of weather, and neither is an upstream
    // we could not reach; the reader is told which of the two happened.
    expect(await reason(429, 'upstream budget exhausted')).toMatch(/request budget was reached.*not an absence of weather/i)
    expect(await reason(502, 'connection reset')).toMatch(/no image was retrieved from the provider: connection reset/i)
    expect(await reason(501, 'records no upstream WMS layer')).toMatch(/records no upstream imagery/i)
  })

  it('reports a fully transparent image as retrieved with nothing detected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers: rasterHeaders() })))
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 2, height: 1 })))
    vi.stubGlobal('OffscreenCanvas', class {
      constructor(_width: number, _height: number) {}
      getContext() {
        return { drawImage: () => undefined, getImageData: () => ({ data: Uint8ClampedArray.from([0, 0, 0, 0, 0, 0, 0, 0]) }) }
      }
    })

    const result = await loadLayerRaster(rasterLayer, bounds)
    expect(result.image?.coverage).toBe('fully-transparent')
    // It is still a retrieval, with its provenance intact — not an outage.
    expect(result.image?.provenance.retrievalStatus).toBe('retrieved')
    expect(result.image?.provenance.wmsLayer).toBe('HRDPS.CONTINENTAL_TT')
  })

  it('reports an image with drawn pixels as a field', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers: rasterHeaders() })))
    vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 2, height: 1 })))
    vi.stubGlobal('OffscreenCanvas', class {
      constructor(_width: number, _height: number) {}
      getContext() {
        return { drawImage: () => undefined, getImageData: () => ({ data: Uint8ClampedArray.from([0, 0, 0, 0, 12, 40, 80, 255]) }) }
      }
    })

    expect((await loadLayerRaster(rasterLayer, bounds)).image?.coverage).toBe('has-pixels')
  })

  it('says the pixels were not inspected rather than guessing when the runtime cannot decode them', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers: rasterHeaders() })))
    const result = await loadLayerRaster(rasterLayer, bounds)
    expect(result.image?.coverage).toBe('not-inspected')
  })
})

describe('evidence basis wording', () => {
  it('never describes live-proxied imagery as a published artifact', () => {
    const words = describeEvidenceBasis('live_proxy')
    expect(words).toMatch(/live-proxied/i)
    expect(words).toMatch(/not a published artifact/i)
  })

  it('does not call the drawn image a published artifact even for a published layer', () => {
    const words = describeEvidenceBasis('published_artifact')
    expect(words).toMatch(/published artifact/i)
    expect(words).toMatch(/rendered live by the provider/i)
  })

  it('fails closed to unknown for an absent or unrecognised basis', () => {
    expect(describeEvidenceBasis(undefined)).toMatch(/unknown evidence basis/i)
    expect(describeEvidenceBasis('probably_fine')).toMatch(/unknown evidence basis/i)
  })
})

describe('timeline mode', () => {
  const items = [{ valid_time_utc: '2026-08-30T04:00:00Z', valid_time_newfoundland: '', available_products: ['eccc-radar'] }]

  it('fails closed when the timeline declares no mode', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ start: '', end: '', items }), { status: 200 })))
    const result = await loadTimeline()
    expect(result.dataMode).toBe('unavailable')
    expect(result.error).toMatch(/declared no data_mode/i)
    expect(result.timeline?.data_mode).toBe('unavailable')
  })

  it('fails closed on an unrecognised mode and keeps its own live reading', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data_mode: 'probably', start: '', end: '', items }), { status: 200 })))
    expect((await loadTimeline()).dataMode).toBe('unavailable')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data_mode: 'live', start: '', end: '', items }), { status: 200 })))
    const live = await loadTimeline()
    expect(live.dataMode).toBe('live')
    expect(live.error).toBeNull()
  })

  it('returns a null timeline, never an empty window, when the endpoint cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const result = await loadTimeline()
    expect(result.timeline).toBeNull()
    expect(result.dataMode).toBe('unavailable')
  })

  it('builds no story hour from an unavailable timeline', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const timeline: TimelineResponse = { data_mode: 'unavailable', start: '', end: '', items }
    const story = await loadStory({ id: 'x', name: 'x', latitude: 47.5, longitude: -52.7, kind: 'station' }, timeline, undefined)
    expect(story).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('product selection predicate', () => {
  const source = (id: string, state: string): CatalogSource => ({
    id,
    producer: 'Environment and Climate Change Canada',
    product: 'HRDPS raw',
    state,
    status_reason: 'Official product is catalogued; ingestion is not implemented yet.',
    role: 'Primary high-resolution deterministic forecast',
    may_enter_consensus: true,
    cadence: '4 runs/day',
    forecast_horizon: 'approximately 48 h',
    geographic_coverage: 'Published native domain',
    licence: 'MSC Open Data licence',
    attribution: 'Credit ECCC',
  })

  // The registry state is a ceiling that never reads `active`, so a source is
  // offered on what `/point` accepts instead — a condition the API can satisfy.
  it('offers a source the point endpoint accepts even though no source is ever active', () => {
    expect(pointProductFor(source('eccc-hrdps', 'implementing'))).toBe('HRDPS')
    expect(pointProductFor(source('eccc-rdps', 'credential_required'))).toBe('RDPS')
  })

  it('offers nothing for a source the point endpoint has no product value for', () => {
    // `/point?product=` answers 422 for these; a button for one could never work.
    expect(pointProductFor(source('eccc-radar', 'implementing'))).toBeNull()
    expect(pointProductFor(source('smartatlantic-st-johns', 'implementing'))).toBeNull()
  })
})

describe('cloud layer normalisation', () => {
  const metar = (field: string, value: unknown, units: string, extra: Record<string, unknown> = {}) => ({
    field, value, provenance: { source_id: 'awc-metar-speci', provider: 'AWC', product: 'CYYT METAR/SPECI', normalized_units: units, data_mode: 'live', ...extra },
  })
  const point = (fields: unknown[]): ApiPointResponse => ({
    data_mode: 'live', valid_time: '2026-08-30T13:00:00Z',
    selection: { mode: 'evidence_only', badge: 'evidence only' },
    fields: fields as ApiPointResponse['fields'],
  })

  it('keeps a slot for any reported field, in provider order, and drops slots nothing was reported for', () => {
    const snapshot = normalizePoint(point([
      metar('cloud_layer_1_cover_code', 'FEW', 'code'),
      metar('cloud_layer_1_base', 365.76, 'm', { original_units: 'ft' }),
      metar('cloud_layer_3_cover_code', 'OVC', 'code'),
    ]))
    expect(snapshot.cloudLayers).toEqual([
      { index: 1, coverCode: 'FEW', coverPct: null, baseM: 365.76 },
      { index: 3, coverCode: 'OVC', coverPct: null, baseM: null },
    ])
    expect(snapshot.fieldSources.cloud_layer_1_cover_code?.sourceId).toBe('awc-metar-speci')
  })

  it('accepts a base only when the response declared metres', () => {
    const feet = normalizePoint(point([metar('cloud_layer_1_cover_code', 'BKN', 'code'), metar('cloud_layer_1_base', 1400, 'ft')]))
    expect(feet.cloudLayers[0]?.baseM).toBeNull()
    const undeclared = normalizePoint(point([metar('cloud_layer_1_cover_code', 'BKN', 'code'), metar('cloud_layer_1_base', 426.72, '')]))
    expect(undeclared.cloudLayers[0]?.baseM).toBeNull()
    const metres = normalizePoint(point([metar('cloud_layer_1_base', 426.72, 'metres')]))
    expect(metres.cloudLayers[0]?.baseM).toBe(426.72)
  })

  it('never turns a bare number into a cover code', () => {
    const snapshot = normalizePoint(point([metar('cloud_layer_1_cover_code', 6, 'code'), metar('cloud_layer_1_base', 609.6, 'm')]))
    expect(snapshot.cloudLayers).toEqual([{ index: 1, coverCode: null, coverPct: null, baseM: 609.6 }])
  })

  it('does not list a slot the API enumerated with null values only', () => {
    // The live API returns every allocated slot; a report with two layers
    // arrives as slots 1-2 with values and slots 3-6 with nulls.
    const snapshot = normalizePoint(point([
      metar('cloud_layer_1_cover_code', 'FEW', 'code'),
      metar('cloud_layer_1_base', 609.6, 'm', { original_units: 'ft' }),
      metar('cloud_layer_2_cover_code', 'BKN', 'code'),
      metar('cloud_layer_2_cover', 75, 'percent'),
      metar('cloud_layer_2_base', 3962.4, 'm', { original_units: 'ft' }),
      metar('cloud_layer_3_cover_code', null, 'code'),
      metar('cloud_layer_3_cover', null, 'percent'),
      metar('cloud_layer_3_base', null, 'm', { original_units: 'ft' }),
      metar('cloud_layer_4_cover_code', null, 'code'),
    ]))
    expect(snapshot.cloudLayers.map((layer) => layer.index)).toEqual([1, 2])
  })

  it('reads fog_state as the API category and nothing else', () => {
    expect(normalizePoint(point([metar('fog_state', 'evidence_present', 'category')])).fogRisk).toBe('evidence_present')
    expect(normalizePoint(point([metar('fog_state', 'probably foggy', 'category')])).fogRisk).toBe('unknown')
    expect(normalizePoint(point([])).fogRisk).toBe('unknown')
  })
})

describe('layer grouping shared by the drawer and the coverage rows', () => {
  const satellite: LayerItem = {
    id: 'geomet-live-goes-east-dayvis-nightir',
    title: 'GOES-East day visible / night IR (1 km, live proxy)',
    kind: 'raster', field: 'satellite_day_visible_night_ir', product: 'GOES-East', units: 'unknown',
    semantics: 'observed imagery relayed by ECCC GeoMet from NOAA GOES-East; frames exist only for the past; never forecast',
    times: ['2026-08-30T13:50:00Z', '2026-08-30T14:00:00Z'], cadence_seconds: 600, staleness_tolerance_seconds: 300,
    evidence_basis: 'live_proxy', raster_available: true, group: 'satellite',
  }

  it('honours a declared satellite group and puts observed evidence first', () => {
    expect(layerGroup(satellite)).toBe('satellite')
    expect(LAYER_GROUP_ORDER.slice(0, 5)).toEqual(['satellite', 'observation', 'alert', 'forecast_proxy', 'published_model'])
    expect(LAYER_GROUP_LABELS.satellite).toBe('Satellite (observed, past only)')
  })

  it('derives a group from basis and kind, never from the id, when none is declared', () => {
    // The id says GOES-East; the declaration says nothing. Proxied imagery
    // with no group is a forecast proxy, exactly like the HRDPS field.
    expect(layerGroup({ ...satellite, group: undefined })).toBe('forecast_proxy')
    expect(layerGroup({ ...satellite, group: 'not-a-group' })).toBe('forecast_proxy')
    expect(layerGroup({ ...rasterLayer, kind: 'alert', evidence_basis: undefined })).toBe('alert')
    expect(layerGroup({ ...rasterLayer, evidence_basis: 'published_artifact' })).toBe('published_model')
    expect(layerGroup({ ...rasterLayer, kind: 'point', evidence_basis: 'published_artifact' })).toBe('observation')
    expect(layerGroup({ ...rasterLayer, evidence_basis: undefined })).toBe('unknown')
  })

  it('buckets layers in the shared order, omits empty groups and keeps the API order inside a group', () => {
    const second = { ...satellite, id: 'geomet-live-goes-east-nightir-2km' }
    const grouped = groupLayers([rasterLayer, second, satellite])
    expect(grouped.map(({ group }) => group)).toEqual(['satellite', 'forecast_proxy'])
    expect(grouped[0].rows.map((layer) => layer.id)).toEqual([second.id, satellite.id])
    expect(grouped[0].label).toBe('Satellite (observed, past only)')
  })
})

describe('cloud band view filter', () => {
  // Today's CYYT report as /point serves it: FEW020 (609.6 m) and BKN130
  // (3962.4 m), plus an OVC slot whose base was not declared in metres.
  const few: CloudLayerReading = { index: 1, coverCode: 'FEW', coverPct: 25, baseM: 609.6 }
  const bkn: CloudLayerReading = { index: 2, coverCode: 'BKN', coverPct: 75, baseM: 3962.4 }
  const ovcNoBase: CloudLayerReading = { index: 3, coverCode: 'OVC', coverPct: null, baseM: null }
  const high: CloudLayerReading = { index: 4, coverCode: 'CI', coverPct: null, baseM: 7000 }

  it('places a base by the aviation convention, at the declared metre boundaries', () => {
    expect(cloudBandOf(few)).toBe('low')
    expect(cloudBandOf(bkn)).toBe('middle')
    expect(cloudBandOf(high)).toBe('high')
    // 6,500 ft is 1,981.2 m: the boundary itself belongs to the band above.
    expect(cloudBandOf({ ...few, baseM: 1981.2 })).toBe('middle')
    expect(cloudBandOf({ ...few, baseM: 1981.1 })).toBe('low')
    expect(cloudBandOf({ ...few, baseM: 6096 })).toBe('high')
    expect(cloudBandOf({ ...few, baseM: 6095.9 })).toBe('middle')
  })

  it('has no band for a layer with no base in metres', () => {
    expect(cloudBandOf(ovcNoBase)).toBeNull()
  })

  it('returns the full as-reported list, in order, with every band on', () => {
    expect(filterCloudLayers([few, bkn, ovcNoBase, high], ALL_CLOUD_BANDS)).toEqual([few, bkn, ovcNoBase, high])
  })

  it('hides only the layers whose base falls in a band switched off', () => {
    expect(filterCloudLayers([few, bkn], { low: false, middle: true, high: true })).toEqual([bkn])
    expect(filterCloudLayers([few, bkn], { low: true, middle: false, high: true })).toEqual([few])
    expect(filterCloudLayers([few, bkn, high], { low: false, middle: false, high: true })).toEqual([high])
  })

  it('never hides a layer whose base is unknown, whatever is switched off', () => {
    expect(filterCloudLayers([few, ovcNoBase, bkn], { low: false, middle: false, high: false })).toEqual([ovcNoBase])
  })

  it('does not alter the readings it lets through', () => {
    const [kept] = filterCloudLayers([bkn], { low: false, middle: true, high: true })
    expect(kept).toBe(bkn)
  })
})
