import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_CLOUD_BANDS, LAYER_GROUP_LABELS, LAYER_GROUP_ORDER, RASTER_CRS, cloudBandOf, describeEvidenceBasis, describeResolution, drawableFrames, filterCloudLayers, frameMarkers, LAYER_TICK_COLORS, layerTickColor, groupLayers, layerGroup, layerRasterUrl, loadLayerRaster, loadSpaceWeather, loadStory, loadTimeline, nextFrame, normalizePoint, pointProductFor, previousFrame, renderPixelSize, resolveLayerFrame, snapInstant, stepInstant, unionFrameInstants, type ApiPointResponse } from './api'
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
  it('names each bound separately, requests web mercator, and sends no packed bbox', () => {
    const url = new URL(layerRasterUrl(rasterLayer, { ...bounds, validTime: '2026-08-31T04:00:00Z' }), 'http://localhost')
    expect([...url.searchParams.keys()].sort()).toEqual(['crs', 'east', 'height', 'north', 'south', 'valid_time', 'west', 'width'])
    expect(url.searchParams.get('south')).toBe('46.20000')
    expect(url.searchParams.get('west')).toBe('-55.20000')
    expect(url.searchParams.get('north')).toBe('48.80000')
    expect(url.searchParams.get('east')).toBe('-50.80000')
    expect(url.searchParams.get('valid_time')).toBe('2026-08-31T04:00:00Z')
    // The canvas is web mercator; a tile rendered in EPSG:3857 corner-pins
    // onto it exactly. An EPSG:4326 tile pinned the same way is warped ~2-3 km
    // through the middle of a 4 degree box at this latitude.
    expect(url.searchParams.get('crs')).toBe('EPSG:3857')
    expect(RASTER_CRS).toBe('EPSG:3857')
    expect(url.searchParams.has('bbox')).toBe(false)
  })

  it('sizes requests in physical pixels with the device pixel ratio capped at 2', () => {
    const originalRatio = globalThis.devicePixelRatio
    try {
      ;(globalThis as { devicePixelRatio: number }).devicePixelRatio = 1.5
      expect(renderPixelSize(512)).toBe(768)
      ;(globalThis as { devicePixelRatio: number }).devicePixelRatio = 3
      expect(renderPixelSize(512)).toBe(1024) // capped: past 2x nothing gains legibility
      ;(globalThis as { devicePixelRatio: number }).devicePixelRatio = 0.5
      expect(renderPixelSize(512)).toBe(512) // never below the CSS size
    } finally {
      ;(globalThis as { devicePixelRatio: number }).devicePixelRatio = originalRatio
    }
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

  it('accepts a rendered-grid image that names its source artifact instead of a WMS layer', async () => {
    // A grid rendered by the API from the stored artifact has no upstream WMS
    // layer; its provenance is the ingested source its pixels were drawn from.
    const headers = rasterHeaders({ 'X-Weather-Image-Basis': 'rendered_grid', 'X-Weather-Source-Id': 'noaa-gfs', 'X-Weather-Evidence-Basis': 'published_artifact' })
    delete headers['X-Weather-Wms-Layer']
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers })))

    const result = await loadLayerRaster(rasterLayer, bounds)
    expect(result.error).toBeNull()
    expect(result.image?.provenance.wmsLayer).toBeNull()
    expect(result.image?.provenance.sourceId).toBe('noaa-gfs')
    expect(result.image?.provenance.imageBasis).toBe('rendered_grid')
  })

  it('still refuses a rendered-grid image that names no source at all', async () => {
    const headers = rasterHeaders({ 'X-Weather-Image-Basis': 'rendered_grid' })
    delete headers['X-Weather-Wms-Layer']
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(pngBody(), { status: 200, headers })))

    const result = await loadLayerRaster(rasterLayer, bounds)
    expect(result.image).toBeNull()
    expect(result.error).toMatch(/no retrieval provenance/i)
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

  it('says a rendered grid was drawn here from stored values, never fetched from a provider', () => {
    const words = describeEvidenceBasis('published_artifact', 'rendered_grid')
    expect(words).toMatch(/rendered by this experiment/i)
    expect(words).toMatch(/nearest-neighbor, never smoothed/i)
    expect(words).not.toMatch(/rendered live by the provider/i)
  })

  it('says the satellite cloud mask was drawn here from stored NOAA values, never attributed to the provider', () => {
    const words = describeEvidenceBasis('published_artifact', 'satellite')
    expect(words).toMatch(/drawn by this experiment from stored NOAA cloud-mask values/i)
    expect(words).toMatch(/nearest-neighbor, never smoothed/i)
    expect(words).not.toMatch(/rendered live by the provider/i)
    // The four provider composites stay live_proxy and keep their own sentence.
    expect(describeEvidenceBasis('live_proxy', 'satellite')).toMatch(/rendered by the provider at request time/i)
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

  it('honours a declared rendered_grid group with its own heading after the published grids', () => {
    const strata: LayerItem = {
      id: 'noaa-gfs-surface-cloud-low', title: 'Global Forecast System (GFS 0.25 deg) low cloud cover (rendered grid)',
      kind: 'raster', field: 'cloud_low', product: 'Global Forecast System (GFS 0.25 deg)', units: 'percent',
      semantics: 'rendered by this experiment from retrieved NOAA GFS GRIB2 fields; nearest-neighbor; never smoothed',
      times: ['2026-08-30T13:00:00Z'], cadence_seconds: 3600, staleness_tolerance_seconds: 1800,
      evidence_basis: 'published_artifact', raster_available: true, legend_available: true, group: 'rendered_grid',
    }
    expect(layerGroup(strata)).toBe('rendered_grid')
    expect(LAYER_GROUP_ORDER.indexOf('rendered_grid')).toBeGreaterThan(LAYER_GROUP_ORDER.indexOf('published_model'))
    expect(LAYER_GROUP_LABELS.rendered_grid).toBe('Rendered grids (drawn here from stored model data)')
    // Without the declaration it stays a published model grid: the group is
    // never inferred from the id.
    expect(layerGroup({ ...strata, group: undefined })).toBe('published_model')
  })

  it('buckets layers in the shared order, omits empty groups and keeps the API order inside a group', () => {
    const second = { ...satellite, id: 'geomet-live-goes-east-nightir-2km' }
    const grouped = groupLayers([rasterLayer, second, satellite])
    expect(grouped.map(({ group }) => group)).toEqual(['satellite', 'forecast_proxy'])
    expect(grouped[0].rows.map((layer) => layer.id)).toEqual([second.id, satellite.id])
    expect(grouped[0].label).toBe('Satellite (observed, past only)')
  })
})

describe('space weather is read fail-closed', () => {
  const liveBody = {
    data_mode: 'live', operational: false, generated_at: '2026-08-31T02:00:00Z',
    kp_observed: { available: true, source_id: 'noaa-swpc-kp', product: 'Planetary K index (observed)', readings: [{ time: '2026-08-31T00:00:00Z', value: 4.33, status: null }], freshness: { status: 'fresh', age_seconds: 1800, threshold_seconds: 21600 }, notices: [] },
    kp_forecast: { available: true, source_id: 'noaa-swpc-kp', product: 'Planetary K index (3-day outlook, per-value status)', readings: [{ time: '2026-08-31T06:00:00Z', value: 5.0, status: 'predicted' }], freshness: { status: 'fresh', age_seconds: 1800, threshold_seconds: 21600 }, notices: [] },
    solar_wind: { available: true, source_id: 'noaa-swpc-rtsw', product: 'Real-time solar wind magnetic field (1-minute)', bz_gsm_nt: -4.1, bt_nt: 4.3, measured_at: '2026-08-31T01:59:00Z', feed_declared_spacecraft: 'SOLAR1', freshness: { status: 'fresh', age_seconds: 120, threshold_seconds: 900 }, notices: [] },
    notices: [],
  }

  it('returns a live response with the provider status intact', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(liveBody), { status: 200 })))
    const result = await loadSpaceWeather()
    expect(result.error).toBeNull()
    expect(result.spaceWeather?.kp_forecast.readings[0].status).toBe('predicted')
    expect(result.spaceWeather?.solar_wind.bz_gsm_nt).toBe(-4.1)
  })

  it('fails closed on a non-live mode, keeping the API notice as the reason', async () => {
    const unavailable = { ...liveBody, data_mode: 'unavailable', notices: ['no fixture space weather exists; fixture mode answers unavailable rather than inventing planetary indices'] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(unavailable), { status: 200 })))
    const result = await loadSpaceWeather()
    expect(result.spaceWeather).toBeNull()
    expect(result.error).toMatch(/no fixture space weather exists/)
  })

  it('fails closed on a missing or unrecognised mode', async () => {
    const { data_mode: _dropped, ...noMode } = liveBody
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(noMode), { status: 200 })))
    expect((await loadSpaceWeather()).spaceWeather).toBeNull()
  })

  it('returns null with the transport failure, never an invented zero', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const result = await loadSpaceWeather()
    expect(result.spaceWeather).toBeNull()
    expect(result.error).toMatch(/offline/)
  })

  it('refuses an incompatible schema', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data_mode: 'live' }), { status: 200 })))
    const result = await loadSpaceWeather()
    expect(result.spaceWeather).toBeNull()
    expect(result.error).toMatch(/incompatible schema/)
  })
})

describe('the aurora layer files under the rendered-grid group', () => {
  const auroraLayer: LayerItem = {
    id: 'noaa-swpc-aurora-oval', title: 'Aurora probability (OVATION model nowcast)',
    kind: 'raster', field: 'aurora_probability', product: 'OVATION aurora probability nowcast', units: 'percent',
    semantics: 'rendered by this experiment from the stored NOAA SWPC OVATION aurora nowcast grid; a model nowcast, not an observation',
    times: ['2026-08-31T02:50:00Z'], cadence_seconds: null, staleness_tolerance_seconds: 3600,
    evidence_basis: 'published_artifact', raster_available: true, legend_available: true, group: 'rendered_grid',
  }

  it('sits in the rendered-grid group by declaration, never by id', () => {
    expect(layerGroup(auroraLayer)).toBe('rendered_grid')
    const grouped = groupLayers([auroraLayer])
    expect(grouped).toHaveLength(1)
    expect(grouped[0].group).toBe('rendered_grid')
    expect(grouped[0].label).toBe(LAYER_GROUP_LABELS.rendered_grid)
  })

  it('is treated as a forecast-type layer: its future frame resolves with disclosure, never refused as observed', () => {
    const reference = new Date('2026-08-31T02:00:00Z')
    const resolution = resolveLayerFrame(auroraLayer, new Date('2026-08-31T04:00:00Z'), { interpolate: false, reference })
    expect(resolution.kind).toBe('snapped')
    if (resolution.kind === 'snapped') {
      expect(resolution.frame.time).toBe('2026-08-31T02:50:00Z')
      expect(describeResolution(resolution)).toMatch(/showing/)
    }
  })

  it('normalizes the sampled aurora probability, null when the response carried none', () => {
    const withValue = normalizePoint({
      valid_time: '2026-08-31T02:50:00Z',
      selection: { mode: 'evidence_only', badge: 'evidence' },
      fields: [{ field: 'aurora_probability', value: 12, provenance: { source_id: 'noaa-swpc-ovation', provider: 'NOAA Space Weather Prediction Center', product: 'OVATION aurora probability nowcast', data_mode: 'live' } }],
    } as ApiPointResponse)
    expect(withValue.auroraProbabilityPct).toBe(12)
    expect(withValue.fieldSources.aurora_probability?.sourceId).toBe('noaa-swpc-ovation')
    const without = normalizePoint({ valid_time: '2026-08-31T02:50:00Z', selection: { mode: 'evidence_only', badge: 'evidence' }, fields: [] } as unknown as ApiPointResponse)
    expect(without.auroraProbabilityPct).toBeNull()
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

describe('frame fallback resolution (resolveLayerFrame)', () => {
  // The reference deliberately carries nonzero seconds: exact frame instants
  // must survive it, because a whole-minute offset never lands on them.
  const reference = new Date('2026-08-30T04:00:37.421Z')
  const opts = { interpolate: false, reference }
  const forecast: LayerItem = {
    id: 'forecast', title: 'Forecast', kind: 'raster', field: 'tt', product: 'HRDPS', units: 'degC',
    semantics: 'live-proxied imagery',
    times: ['2026-08-30T03:00:00Z', '2026-08-30T04:00:00Z', '2026-08-30T05:00:00Z'],
    cadence_seconds: 3600, staleness_tolerance_seconds: 1800, evidence_basis: 'live_proxy', group: 'forecast_proxy',
  }
  const observed: LayerItem = {
    id: 'radar', title: 'Radar', kind: 'point', field: 'radar', product: 'radar', units: 'mixed',
    semantics: 'no echo is not clear sky',
    times: ['2026-08-30T03:54:00Z', '2026-08-30T04:00:00Z'],
    cadence_seconds: 360, staleness_tolerance_seconds: 180, group: 'observation',
  }

  it('resolves an exact frame quietly inside the tolerance', () => {
    const resolution = resolveLayerFrame(observed, new Date('2026-08-30T04:01:00Z'), opts)
    expect(resolution.kind).toBe('exact')
    expect(describeResolution(resolution)).toBeNull()
  })

  it('keeps the tolerance meaning even a hair past the reference', () => {
    // 04:02 is after the reference but within the 180 s tolerance of 04:00:
    // effectively the same instant, drawn quietly exactly as before.
    expect(resolveLayerFrame(observed, new Date('2026-08-30T04:02:00Z'), opts).kind).toBe('exact')
  })

  it('never pulls an observed frame backward to stand for an earlier instant', () => {
    const resolution = resolveLayerFrame(observed, new Date('2026-08-30T03:30:00Z'), { interpolate: false, reference: new Date('2026-08-30T05:00:00Z') })
    // 03:54 is the nearest frame, but it observed weather AFTER 03:30.
    // Previous-only fallback finds nothing at or before 03:30, so nothing
    // resolves and the reason says exactly that.
    expect(resolution.kind).toBe('none')
    if (resolution.kind === 'none') expect(resolution.reason).toMatch(/no earlier frame/)
  })

  it('falls back to the previous frame, disclosed, for an observed layer', () => {
    const resolution = resolveLayerFrame(observed, new Date('2026-08-30T04:10:00Z'), { interpolate: false, reference: new Date('2026-08-30T04:30:00Z') })
    expect(resolution).toMatchObject({ kind: 'snapped', direction: 'previous', frame: { time: '2026-08-30T04:00:00Z' } })
    expect(describeResolution(resolution)).toMatch(/10 min earlier than the selected time/)
  })

  it('never draws an observed layer by fallback for a future instant', () => {
    const resolution = resolveLayerFrame(observed, new Date('2026-08-30T06:00:00Z'), opts)
    expect(resolution.kind).toBe('none')
    if (resolution.kind === 'none') {
      expect(resolution.reason).toMatch(/no frames for future instants/)
      expect(resolution.nearest?.time).toBe('2026-08-30T04:00:00Z')
    }
  })

  it('falls back to the nearest frame in either direction for a forecast layer', () => {
    // A gap in the published frames: 04:00 is missing, so 05:37 sits beyond
    // the half-cadence tolerance of both neighbours and must fall back.
    const gappy = { ...forecast, times: ['2026-08-30T03:00:00Z', '2026-08-30T06:00:00Z'] }
    // 04:20 is 80 minutes past 03:00 and 100 before 06:00 — outside the
    // 30-minute tolerance of both, so the nearer one is a disclosed fallback.
    const resolution = resolveLayerFrame(gappy, new Date('2026-08-30T04:20:00Z'), opts)
    expect(resolution).toMatchObject({ kind: 'snapped', direction: 'nearest', frame: { time: '2026-08-30T03:00:00Z' } })
    expect(describeResolution(resolution)).toMatch(/80 min earlier than the selected time/)
  })

  it('composites a forecast layer between two frames when interpolation is on', () => {
    const resolution = resolveLayerFrame(forecast, new Date('2026-08-30T04:15:00Z'), { interpolate: true, reference })
    expect(resolution.kind).toBe('blend')
    if (resolution.kind === 'blend') {
      expect(resolution.previous.time).toBe('2026-08-30T04:00:00Z')
      expect(resolution.next.time).toBe('2026-08-30T05:00:00Z')
      expect(resolution.fraction).toBeCloseTo(0.25, 5)
      expect(describeResolution(resolution)).toMatch(/display compositing .* display only, not evidence/)
    }
  })

  it('never composites an observed layer, whatever the setting says', () => {
    const resolution = resolveLayerFrame(observed, new Date('2026-08-30T03:57:00Z'), { interpolate: true, reference })
    expect(resolution.kind).not.toBe('blend')
  })

  it('resolves none with the reason when a layer published no frames', () => {
    const bare = { ...forecast, times: [] }
    expect(resolveLayerFrame(bare, reference, opts)).toMatchObject({ kind: 'none', reason: 'this layer published no frames' })
  })

  it('exposes 0, 1 or 2 drawable frames per resolution kind', () => {
    expect(drawableFrames(resolveLayerFrame(forecast, new Date('2026-08-30T04:00:00Z'), opts))).toHaveLength(1)
    expect(drawableFrames(resolveLayerFrame(forecast, new Date('2026-08-30T04:15:00Z'), { interpolate: true, reference }))).toHaveLength(2)
    expect(drawableFrames(resolveLayerFrame({ ...forecast, times: [] }, reference, opts))).toHaveLength(0)
  })

  it('finds directional neighbours exactly', () => {
    const at = new Date('2026-08-30T04:30:00Z')
    expect(previousFrame(forecast, at)?.time).toBe('2026-08-30T04:00:00Z')
    expect(nextFrame(forecast, at)?.time).toBe('2026-08-30T05:00:00Z')
    expect(nextFrame(forecast, new Date('2026-08-30T06:00:00Z'))).toBeNull()
    expect(previousFrame(forecast, new Date('2026-08-30T02:00:00Z'))).toBeNull()
  })
})

describe('scrubber snapping helpers', () => {
  const windowStart = new Date('2026-08-30T01:00:37.421Z').getTime()
  const windowEnd = new Date('2026-08-31T04:00:37.421Z').getTime()
  const layerA: LayerItem = {
    id: 'a', title: 'A', kind: 'raster', field: 'a', product: 'a', units: 'a', semantics: 'a',
    times: ['2026-08-30T03:00:00Z', '2026-08-30T04:00:00Z'],
  }
  const layerB: LayerItem = {
    id: 'b', title: 'B', kind: 'point', field: 'b', product: 'b', units: 'b', semantics: 'b',
    times: ['2026-08-30T03:54:00Z', '2026-08-30T04:00:00Z', '2026-09-05T00:00:00Z'],
  }

  it('unions only visible layers, inside the window, sorted and deduplicated', () => {
    const instants = unionFrameInstants([layerA, layerB], [{ id: 'a', visible: true }, { id: 'b', visible: true }], windowStart, windowEnd)
    expect(instants).toEqual([
      new Date('2026-08-30T03:00:00Z').getTime(),
      new Date('2026-08-30T03:54:00Z').getTime(),
      new Date('2026-08-30T04:00:00Z').getTime(),
    ])
    expect(unionFrameInstants([layerA, layerB], [{ id: 'b', visible: false }], windowStart, windowEnd)).toEqual([])
  })

  it('snaps to the nearest exact frame instant, ties resolving earlier', () => {
    const instants = unionFrameInstants([layerB], [{ id: 'b', visible: true }], windowStart, windowEnd)
    // 03:57 is equidistant from 03:54 and 04:00: the earlier one wins.
    expect(snapInstant(instants, new Date('2026-08-30T03:57:00Z').getTime())).toBe(new Date('2026-08-30T03:54:00Z').getTime())
    // The snapped value is the frame's exact epoch instant, seconds and all.
    expect(snapInstant(instants, new Date('2026-08-30T03:58:30Z').getTime())).toBe(new Date('2026-08-30T04:00:00Z').getTime())
  })

  it('is the identity on an empty axis, inventing no instant', () => {
    expect(snapInstant([], 12345)).toBe(12345)
  })

  it('steps to the neighbouring instant and stays put at the ends', () => {
    const instants = [100, 200, 300]
    expect(stepInstant(instants, 200, 1)).toBe(300)
    expect(stepInstant(instants, 200, -1)).toBe(100)
    expect(stepInstant(instants, 300, 1)).toBe(300)
    expect(stepInstant(instants, 100, -1)).toBe(100)
    // From between instants, either direction lands on a real one.
    expect(stepInstant(instants, 250, 1)).toBe(300)
    expect(stepInstant(instants, 250, -1)).toBe(200)
    expect(stepInstant([], 250, 1)).toBe(250)
  })
})

describe('published-frame markers', () => {
  const windowStart = new Date('2026-08-30T01:00:37.421Z').getTime()
  const windowEnd = new Date('2026-08-31T04:00:37.421Z').getTime()
  const layerA: LayerItem = {
    id: 'a', title: 'A', kind: 'raster', field: 'a', product: 'a', units: 'a', semantics: 'a',
    times: ['2026-08-30T03:00:00Z', '2026-08-30T04:00:00Z'],
  }
  const layerB: LayerItem = {
    id: 'b', title: 'B', kind: 'raster', field: 'b', product: 'b', units: 'b', semantics: 'b',
    times: ['2026-08-30T03:54:00Z', '2026-08-30T04:00:00Z', '2026-09-05T00:00:00Z'],
  }
  const axisless: LayerItem = {
    id: 'c', title: 'C', kind: 'raster', field: 'c', product: 'c', units: 'c', semantics: 'c',
  }
  const all = [layerA, layerB, axisless]
  const visible = [{ id: 'a', visible: true }, { id: 'b', visible: true }, { id: 'c', visible: true }]

  it('marks each published instant once, carrying every layer that published it', () => {
    const { markers } = frameMarkers(all, visible, windowStart, windowEnd)
    expect(markers.map((marker) => marker.time)).toEqual([
      '2026-08-30T03:00:00Z', '2026-08-30T03:54:00Z', '2026-08-30T04:00:00Z',
    ])
    // 04:00 belongs to both layers: one tick, two colours - never two ticks
    // stacked with one of them unclickable.
    const shared = markers[2]
    expect(shared.layers.map((layer) => layer.id)).toEqual(['a', 'b'])
    expect(new Set(shared.layers.map((layer) => layer.color)).size).toBe(2)
    // The 2026-09-05 frame is outside the window and carries no tick.
    expect(markers.every((marker) => marker.ms >= windowStart && marker.ms <= windowEnd)).toBe(true)
  })

  it('names a layer that published no frame axis instead of dropping it silently', () => {
    const { markers, axisless: reported } = frameMarkers(all, visible, windowStart, windowEnd)
    expect(reported).toEqual(['C'])
    expect(markers.flatMap((marker) => marker.layers.map((layer) => layer.id))).not.toContain('c')
  })

  it('marks nothing for hidden layers, and nothing at all when none is visible', () => {
    const { markers } = frameMarkers(all, [{ id: 'a', visible: true }, { id: 'b', visible: false }], windowStart, windowEnd)
    expect(markers.flatMap((marker) => marker.layers.map((layer) => layer.id))).toEqual(['a', 'a'])
    expect(frameMarkers(all, [], windowStart, windowEnd)).toEqual({ markers: [], axisless: [] })
  })

  it('keeps a layer colour stable when another layer is toggled off', () => {
    const both = frameMarkers(all, visible, windowStart, windowEnd)
    const alone = frameMarkers(all, [{ id: 'b', visible: true }], windowStart, windowEnd)
    const colorOfB = (result: ReturnType<typeof frameMarkers>) =>
      result.markers.flatMap((marker) => marker.layers).find((layer) => layer.id === 'b')?.color
    expect(colorOfB(alone)).toBe(colorOfB(both))
    expect(layerTickColor('b', all)).toBe(colorOfB(both))
    expect(LAYER_TICK_COLORS).toContain(layerTickColor('unknown-layer', all))
  })

  it('ignores an unreadable timestamp rather than placing a tick at NaN', () => {
    const broken: LayerItem = { ...layerA, id: 'x', title: 'X', times: ['not a time', '2026-08-30T03:00:00Z'] }
    const { markers, axisless: reported } = frameMarkers([broken], [{ id: 'x', visible: true }], windowStart, windowEnd)
    expect(markers).toHaveLength(1)
    expect(markers[0].time).toBe('2026-08-30T03:00:00Z')
    expect(reported).toEqual([])
  })
})
