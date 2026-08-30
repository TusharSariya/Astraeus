import { fixtureSnapshot, unavailableSnapshot } from './fixtures'
import type { CatalogResult, CatalogSource, CloudLayerReading, EvidenceSnapshot, FieldAttribution, FieldDataMode, GeoJsonFeature, LayerFeatureCollection, LayerItem, LayersResult, LocationPoint, ProvenanceRow, ResolvedFrame, SourceStatusItem, SourceStatusResult, StoryStep, TimelineResponse, TimelineResult } from './types'

const prefix = '/api/experiments/weather/v0'

export type PointDataSource = Exclude<import('./types').DataSource, 'loading'>

export interface ApiEvidenceField {
  field: string
  value: unknown
  provenance?: Record<string, unknown>
}

export interface ApiPointResponse {
  data_mode?: unknown
  valid_time: string
  selection: {
    mode: 'consensus' | 'fallback' | 'evidence_only'
    badge: string
    reason?: string
    selected_source_id?: string | null
    selected_product_id?: string | null
  }
  fields: ApiEvidenceField[]
}

/** Map a declared `data_mode` onto the UI union. A missing or unrecognised value
 *  fails closed to `unavailable`: an undeclared response is never called live. */
export function toDataMode(value: unknown): FieldDataMode {
  return value === 'live' || value === 'fixture' || value === 'mixed' ? value : 'unavailable'
}

function isPointResponse(value: unknown): value is ApiPointResponse {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ApiPointResponse>
  return typeof candidate.valid_time === 'string' && !!candidate.selection && Array.isArray(candidate.fields)
}

/** The one field of `name` that will be shown.
 *
 *  The blended response carries the same field name once per contributing
 *  source — a METAR observation first, then the HRDPS and RDPS samples — and
 *  "first match" silently made the observation stand in for the model the
 *  header named. When the response says which source it selected, that
 *  source's field is preferred; only when it does not is the first one taken,
 *  and either way the attribution beside the number says whose it is. */
function pickField(fields: ApiEvidenceField[], name: string, preferredSourceId: string | null): ApiEvidenceField | undefined {
  const matches = fields.filter((field) => field.field === name)
  if (preferredSourceId) {
    const preferred = matches.find((field) => field.provenance?.source_id === preferredSourceId)
    if (preferred) return preferred
  }
  return matches[0]
}

function attributionOf(field: ApiEvidenceField | undefined): FieldAttribution | null {
  if (!field) return null
  const provenance = field.provenance ?? {}
  return {
    sourceId: typeof provenance.source_id === 'string' ? provenance.source_id : null,
    product: typeof provenance.product === 'string' ? provenance.product : null,
    provider: String(provenance.provider ?? 'Unknown provider'),
    derivation: typeof provenance.derivation === 'string' && provenance.derivation.trim() ? provenance.derivation : null,
    derivationVersion: typeof provenance.derivation_version === 'string' ? provenance.derivation_version : null,
  }
}

function finiteValue(field: ApiEvidenceField | undefined): number | null {
  const value = field?.value
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function numericField(fields: ApiEvidenceField[], name: string, preferredSourceId: string | null = null): number | null {
  return finiteValue(pickField(fields, name, preferredSourceId))
}

function unitsOf(field: ApiEvidenceField | undefined): string {
  return String(field?.provenance?.normalized_units ?? field?.provenance?.original_units ?? '').toLowerCase().replaceAll(' ', '')
}

/** Convert by the unit the response declares, and only by that. A value in a
 *  unit not listed here is returned as null — "Unknown" — rather than shown
 *  raw under a label that names a different unit. */
function convertBy(field: ApiEvidenceField | undefined, table: Record<string, (value: number) => number>): number | null {
  const value = finiteValue(field)
  if (value === null) return null
  const convert = table[unitsOf(field)]
  return convert ? convert(value) : null
}

const tenths = (value: number) => Math.round(value * 10) / 10

function speedKmh(fields: ApiEvidenceField[], name: string, preferredSourceId: string | null = null): number | null {
  return convertBy(pickField(fields, name, preferredSourceId), {
    'm/s': (v) => tenths(v * 3.6), mps: (v) => tenths(v * 3.6), 'ms-1': (v) => tenths(v * 3.6), 'm.s-1': (v) => tenths(v * 3.6),
    'km/h': (v) => v, kmh: (v) => v, 'kmh-1': (v) => v, kph: (v) => v,
  })
}

/** Visibility in km. METAR publishes metres (24140.16 m for "15 SM"), and the
 *  panel used to print that number under a "km" label. */
function distanceKm(fields: ApiEvidenceField[], name: string, preferredSourceId: string | null = null): number | null {
  return convertBy(pickField(fields, name, preferredSourceId), {
    m: (v) => tenths(v / 1000), metre: (v) => tenths(v / 1000), metres: (v) => tenths(v / 1000), meter: (v) => tenths(v / 1000), meters: (v) => tenths(v / 1000),
    km: (v) => tenths(v), kilometre: (v) => tenths(v), kilometres: (v) => tenths(v),
  })
}

function pressureHpa(fields: ApiEvidenceField[], name: string, preferredSourceId: string | null = null): number | null {
  return convertBy(pickField(fields, name, preferredSourceId), {
    hpa: (v) => tenths(v), mbar: (v) => tenths(v), mb: (v) => tenths(v),
    pa: (v) => tenths(v / 100),
  })
}

const ALERT_FIELDS = ['alerts', 'alert', 'warnings', 'weather_alerts', 'cap_alerts']

/** Alert text is taken verbatim from alert evidence fields. No alert evidence
 *  means no warnings — the empty state, never a placeholder hazard. */
function alertTexts(fields: ApiEvidenceField[]): string[] {
  const texts: string[] = []
  fields.filter((field) => ALERT_FIELDS.includes(field.field)).forEach((field) => {
    if (typeof field.value === 'string' && field.value.trim()) texts.push(field.value.trim())
    else if (Array.isArray(field.value)) field.value.forEach((entry) => {
      if (typeof entry === 'string' && entry.trim()) texts.push(entry.trim())
    })
  })
  return texts
}

/** The per-slot METAR/TAF cloud-layer fields `/point` may carry, in provider
 *  order. Six slots is the adapter's ceiling; a report with more refuses
 *  publication rather than dropping a layer. */
const MAX_CLOUD_LAYERS = 6
const CLOUD_LAYER_FIELDS = Array.from({ length: MAX_CLOUD_LAYERS }, (_, index) => index + 1)
  .flatMap((slot) => [`cloud_layer_${slot}_cover_code`, `cloud_layer_${slot}_cover`, `cloud_layer_${slot}_base`])

/** Fields the panel displays, so their attribution can be recorded field by field. */
const DISPLAYED_FIELDS = [
  'temperature', 'dew_point', 'relative_humidity', 'wind_speed', 'wind_direction', 'wind_gust',
  'precipitation_probability', 'cloud_low', 'cloud_middle', 'cloud_high', 'total_cloud',
  'mean_sea_level_pressure', 'visibility', 'fog_state', 'aqhi', 'wave_height', 'sea_surface_temperature',
  ...CLOUD_LAYER_FIELDS,
]

/** A cloud base in metres, and only from a response that declared metres. A
 *  base in any other unit - or none - is null rather than a number under the
 *  wrong label. */
function cloudBaseMetres(field: ApiEvidenceField | undefined): number | null {
  return convertBy(field, { m: (v) => v, metre: (v) => v, metres: (v) => v, meter: (v) => v, meters: (v) => v })
}

/** The reported layers, slot by slot. A slot is kept when the response
 *  carried any of its three fields - a cover code with no base is still a
 *  reported layer - and is absent otherwise, so nothing enumerates six empty
 *  slots as though six layers had been observed. */
function cloudLayersOf(fields: ApiEvidenceField[], preferredSourceId: string | null): CloudLayerReading[] {
  const layers: CloudLayerReading[] = []
  for (let slot = 1; slot <= MAX_CLOUD_LAYERS; slot += 1) {
    const code = pickField(fields, `cloud_layer_${slot}_cover_code`, preferredSourceId)
    const cover = pickField(fields, `cloud_layer_${slot}_cover`, preferredSourceId)
    const base = pickField(fields, `cloud_layer_${slot}_base`, preferredSourceId)
    const coverCode = typeof code?.value === 'string' && code.value.trim() ? code.value : null
    const coverPct = finiteValue(cover)
    const baseM = cloudBaseMetres(base)
    // The API enumerates every slot it allocated, with null values where the
    // report had no such layer. A slot whose three values are all null is a
    // retrieved absence, not a layer, and is never listed.
    if (coverCode === null && coverPct === null && baseM === null) continue
    layers.push({ index: slot, coverCode, coverPct, baseM })
  }
  return layers
}

export function normalizePoint(point: ApiPointResponse): EvidenceSnapshot {
  // The response names the product it answered with. The old code inferred the
  // mode from whichever `temperature` field came first, which on the blended
  // response is the METAR observation, so the header and the number disagreed.
  const selectedProductId = typeof point.selection.selected_product_id === 'string' ? point.selection.selected_product_id : null
  const selectedSourceId = typeof point.selection.selected_source_id === 'string' ? point.selection.selected_source_id : null
  const selectedProduct = (selectedProductId ?? '').toUpperCase()
  const selectionMode = point.selection.mode === 'consensus' ? 'consensus'
    : point.selection.mode === 'evidence_only' ? 'unavailable'
      : selectedProduct === 'HRDPS' ? 'hrdps'
        : selectedProduct === 'RDPS' ? 'rdps' : 'unavailable'
  const fields = point.fields
  const pick = (name: string) => pickField(fields, name, selectedSourceId)
  const fogValue = pick('fog_state')?.value
  const fogRisk = fogValue === 'evidence_present' || fogValue === 'not_indicated' ? fogValue : 'unknown'
  const uniqueProvenance = new Map<string, ProvenanceRow>()
  fields.forEach((field) => {
    const provenance = field.provenance ?? {}
    const provider = String(provenance.provider ?? 'Unknown provider')
    const product = String(provenance.product ?? field.field)
    const freshness = provenance.freshness as { status?: unknown; age_seconds?: unknown } | undefined
    const member = provenance.member === null || provenance.member === undefined ? null : String(provenance.member)
    const key = `${provider}/${product}`
    const derivation = attributionOf(field)?.derivation ?? null
    const existing = uniqueProvenance.get(key)
    uniqueProvenance.set(key, {
      provider,
      product,
      run: String(provenance.run_time ?? 'Unknown run'),
      role: String(provenance.forecast_centre ?? 'Evidence'),
      freshness: freshness ? `${String(freshness.status ?? 'unknown')} · ${String(freshness.age_seconds ?? '?')} s` : 'Unknown',
      member,
      level: String(provenance.vertical_level ?? 'Unknown level'),
      dataMode: toDataMode(provenance.data_mode),
      derivations: derivation && !existing?.derivations.includes(derivation) ? [...(existing?.derivations ?? []), derivation] : existing?.derivations ?? [],
    })
  })
  // Mode and attribution are recorded for the field that is shown, not for
  // whichever copy of the name happened to come last in the list.
  const fieldModes: Record<string, FieldDataMode> = {}
  const fieldSources: Record<string, FieldAttribution> = {}
  DISPLAYED_FIELDS.forEach((name) => {
    const field = pick(name)
    if (!field) return
    fieldModes[name] = toDataMode(field.provenance?.data_mode)
    const attribution = attributionOf(field)
    if (attribution) fieldSources[name] = attribution
  })
  return {
    mode: selectionMode,
    selectionBadge: typeof point.selection.badge === 'string' && point.selection.badge.trim() ? point.selection.badge : null,
    selectedProductId,
    selectedSourceId,
    dataMode: toDataMode(point.data_mode),
    fieldModes,
    fieldSources,
    issuedAt: new Date().toISOString(),
    validAt: point.valid_time,
    temperatureC: numericField(fields, 'temperature', selectedSourceId),
    dewPointC: numericField(fields, 'dew_point', selectedSourceId),
    relativeHumidityPct: numericField(fields, 'relative_humidity', selectedSourceId),
    windKmh: speedKmh(fields, 'wind_speed', selectedSourceId),
    windDirectionDeg: numericField(fields, 'wind_direction', selectedSourceId),
    gustKmh: speedKmh(fields, 'wind_gust', selectedSourceId),
    precipitation: 'Precipitation interval unavailable from point response',
    precipitationProbabilityPct: numericField(fields, 'precipitation_probability', selectedSourceId),
    cloud: {
      low: numericField(fields, 'cloud_low', selectedSourceId),
      middle: numericField(fields, 'cloud_middle', selectedSourceId),
      high: numericField(fields, 'cloud_high', selectedSourceId),
    },
    totalCloudPct: numericField(fields, 'total_cloud', selectedSourceId),
    cloudLayers: cloudLayersOf(fields, selectedSourceId),
    pressureHpa: pressureHpa(fields, 'mean_sea_level_pressure', selectedSourceId),
    visibilityKm: distanceKm(fields, 'visibility', selectedSourceId),
    fogRisk,
    aqhi: numericField(fields, 'aqhi', selectedSourceId),
    marine: { waveHeightM: numericField(fields, 'wave_height', selectedSourceId), sstC: numericField(fields, 'sea_surface_temperature', selectedSourceId), tide: 'Tide feed unavailable' },
    warnings: alertTexts(fields),
    story: [],
    provenance: [...uniqueProvenance.values()],
  }
}

export async function loadPoint(location: LocationPoint, validTime?: string, product?: string, signal?: AbortSignal): Promise<{ snapshot: EvidenceSnapshot; source: PointDataSource; error?: string }> {
  try {
    const params = new URLSearchParams({ latitude: String(location.latitude), longitude: String(location.longitude) })
    if (validTime) params.set('valid_time', validTime)
    if (product && product !== 'consensus') params.set('product', product)
    const response = await fetch(`${prefix}/point?${params}`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`weather API returned ${response.status}`)
    const body: unknown = await response.json()
    if (!isPointResponse(body)) throw new Error('weather API returned an incompatible point schema')
    const snapshot = normalizePoint(body)
    const declared = (body as ApiPointResponse).data_mode
    // The mode is stated first, because that is what fails the response closed.
    // The response's own `selection.reason` is appended when it gives one: a
    // product the API accepts but has no artifact for says so itself, and that
    // sentence belongs to the reader rather than being restated here.
    const reason = typeof (body as ApiPointResponse).selection.reason === 'string' ? (body as ApiPointResponse).selection.reason : undefined
    const mode = declared === undefined
      ? 'Response declared no data_mode, so it is treated as unavailable'
      : `Response declared data_mode "${String(declared)}"`
    const error = snapshot.dataMode === 'unavailable' ? (reason ? `${mode} · ${reason}` : mode) : undefined
    return { snapshot, source: snapshot.dataMode, error }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    if (import.meta.env.DEV && import.meta.env.VITE_WEATHER_FIXTURES === 'true') {
      return { snapshot: fixtureSnapshot, source: 'fixture', error: 'API unavailable; explicit development fixture enabled' }
    }
    return { snapshot: unavailableSnapshot, source: 'unavailable', error: error instanceof Error ? error.message : 'weather API unavailable' }
  }
}

export async function loadProfile(location: LocationPoint, validTime?: string, signal?: AbortSignal): Promise<import('./types').ProfileResponse | null> {
  try {
    const params = new URLSearchParams({ latitude: String(location.latitude), longitude: String(location.longitude) })
    if (validTime) params.set('valid_time', validTime)
    const response = await fetch(`${prefix}/profile?${params}`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return null
    const data: unknown = await response.json()
    if (!data || typeof data !== 'object') return null
    const profile = data as { valid_time: string; levels: Array<{ pressure_hpa: number; fields: ApiEvidenceField[] }> }
    const levels = profile.levels.map((lvl) => ({
      pressure_hpa: lvl.pressure_hpa,
      temperature_c: numericField(lvl.fields, 'temperature'),
      dew_point_c: numericField(lvl.fields, 'dew_point'),
      relative_humidity_pct: numericField(lvl.fields, 'relative_humidity'),
      wind_speed_ms: numericField(lvl.fields, 'wind_speed'),
    }))
    return { valid_time: profile.valid_time, levels }
  } catch {
    return null
  }
}

/** The published hours, with the mode they were declared under.
 *
 *  The timeline says which hours carry evidence, so it is held to the same rule
 *  as every other fetch: a response that does not declare `live`, `fixture` or
 *  `mixed` resolves to `unavailable`, and its hours are not presented as
 *  coverage. `timeline` is null when the endpoint could not be read at all —
 *  "no hour is published" is a claim of its own and is not made on a failure. */
export async function loadTimeline(signal?: AbortSignal): Promise<TimelineResult> {
  try {
    const response = await fetch(`${prefix}/timeline`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { timeline: null, dataMode: 'unavailable', error: `timeline returned ${response.status}` }
    const body: unknown = await response.json()
    if (!body || typeof body !== 'object' || !Array.isArray((body as { items?: unknown }).items)) {
      return { timeline: null, dataMode: 'unavailable', error: 'timeline returned an incompatible schema' }
    }
    const declared = (body as { data_mode?: unknown }).data_mode
    const dataMode = toDataMode(declared)
    const timeline = { ...(body as TimelineResponse), data_mode: dataMode }
    if (dataMode === 'unavailable') {
      return {
        timeline,
        dataMode,
        error: declared === undefined
          ? 'The timeline declared no data_mode, so its hours are not presented as published coverage'
          : `The timeline declared data_mode "${String(declared)}", so its hours are not presented as published coverage`,
      }
    }
    return { timeline, dataMode, error: null }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { timeline: null, dataMode: 'unavailable', error: error instanceof Error ? error.message : 'timeline unavailable' }
  }
}

/** Products the `/point` endpoint will actually accept, keyed by the catalogue
 *  source id that names them.
 *
 *  The catalogue reports `state`, which is a registry CEILING: no source is ever
 *  `active`, by design. Gating the product control on `state === 'active'` made
 *  it permanently dead while `/point?product=` is fully implemented. The
 *  catalogue's own `product` text ("HRDPS raw") is not the accepted token
 *  either — the endpoint answers 422 to it. Source id is the one thing the
 *  catalogue reports that maps onto the endpoint's declared vocabulary, so a
 *  source is offered when, and only when, its id appears here. */
export const POINT_PRODUCT_BY_SOURCE_ID: Record<string, string> = {
  'eccc-hrdps': 'HRDPS',
  'eccc-rdps': 'RDPS',
  'eccc-reps': 'REPS',
  'noaa-gfs': 'GFS',
  'ecmwf-ifs': 'IFS',
  'dwd-icon-global': 'ICON',
}

/** The product token `/point` accepts for a catalogue source, or null when the
 *  endpoint has no parameter value for it and the control must not be offered. */
export function pointProductFor(source: { id: string }): string | null {
  return POINT_PRODUCT_BY_SOURCE_ID[source.id] ?? null
}

/** The layer groups, in the order every grouped list shows them, with their
 *  headings. Shared by the drawer and the timeline coverage rows so the two
 *  never disagree about where a layer sits. Observed evidence comes first
 *  because it is the part that cannot be forecast: satellite frames exist only
 *  for the past. */
export const LAYER_GROUP_ORDER = ['satellite', 'observation', 'alert', 'forecast_proxy', 'published_model', 'rendered_grid', 'unknown'] as const
export type LayerGroup = typeof LAYER_GROUP_ORDER[number]
export const LAYER_GROUP_LABELS: Record<LayerGroup, string> = {
  satellite: 'Satellite (observed, past only)',
  observation: 'Observations',
  alert: 'Alerts',
  forecast_proxy: 'Forecast · live proxy',
  published_model: 'Published model grids',
  rendered_grid: 'Rendered grids (drawn here from stored model data)',
  unknown: 'Undeclared group',
}

/** The API's `group` is used when it is one of the known groups; otherwise the
 *  group is derived from `evidence_basis` and `kind`, which the API also
 *  publishes — never from the layer id, whose text is a storage key rather
 *  than a declaration. A layer that declares nothing usable is `unknown`,
 *  which is said out loud rather than resolved to a stronger group. */
export function layerGroup(layer: LayerItem): LayerGroup {
  const declared = layer.group
  if (declared === 'satellite' || declared === 'forecast_proxy' || declared === 'published_model' || declared === 'observation' || declared === 'alert' || declared === 'rendered_grid') return declared
  if (layer.kind === 'alert') return 'alert'
  if (layer.evidence_basis === 'live_proxy') return 'forecast_proxy'
  if (layer.evidence_basis === 'published_artifact') return layer.kind === 'raster' ? 'published_model' : 'observation'
  return 'unknown'
}

/** Layers bucketed by group in the shared order, empty groups omitted, and the
 *  API's order kept inside each group. */
export function groupLayers(layers: LayerItem[]): Array<{ group: LayerGroup; label: string; rows: LayerItem[] }> {
  return LAYER_GROUP_ORDER
    .map((group) => ({ group, label: LAYER_GROUP_LABELS[group], rows: layers.filter((layer) => layerGroup(layer) === group) }))
    .filter(({ rows }) => rows.length > 0)
}

/** The three cloud bands of the aviation convention (FAA AC 00-6B / NAV CANADA):
 *  low below 6,500 ft, middle 6,500-20,000 ft, high from 20,000 ft, in the
 *  metres the API declares. These bound a VIEW FILTER over the as-reported
 *  layers. Nothing is computed per band, no stratum value is derived, and
 *  `cloud_low` / `cloud_middle` / `cloud_high` stay whatever the API returned. */
export type CloudBand = 'low' | 'middle' | 'high'
export type CloudBands = Record<CloudBand, boolean>
export const CLOUD_BAND_LOW_CEILING_M = 1981.2
export const CLOUD_BAND_MIDDLE_CEILING_M = 6096
export const ALL_CLOUD_BANDS: CloudBands = { low: true, middle: true, high: true }

/** Which band a reported layer's base falls in, or null when it has no base
 *  in metres (SKC/CLR/CAVOK/NSC, or a base the response did not declare in
 *  metres). A null band is not a band: such a layer is never filterable. */
export function cloudBandOf(layer: CloudLayerReading): CloudBand | null {
  if (layer.baseM === null) return null
  if (layer.baseM < CLOUD_BAND_LOW_CEILING_M) return 'low'
  if (layer.baseM < CLOUD_BAND_MIDDLE_CEILING_M) return 'middle'
  return 'high'
}

/** The reported layers whose base falls in a band that is switched on, in the
 *  order they were reported. A layer with no base is always kept: hiding it
 *  would claim a band for it that nothing retrieved supports. */
export function filterCloudLayers(layers: CloudLayerReading[], bands: CloudBands): CloudLayerReading[] {
  return layers.filter((layer) => {
    const band = cloudBandOf(layer)
    return band === null || bands[band]
  })
}

function isLayer(value: unknown): value is LayerItem {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<LayerItem>
  return typeof candidate.id === 'string' && typeof candidate.title === 'string' && typeof candidate.semantics === 'string'
}

export async function loadLayers(signal?: AbortSignal): Promise<LayersResult> {
  try {
    const response = await fetch(`${prefix}/layers`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { layers: [], dataMode: 'unavailable', error: `layer catalogue returned ${response.status}`, notices: [] }
    const body: unknown = await response.json()
    if (!body || typeof body !== 'object' || !Array.isArray((body as { layers?: unknown }).layers)) {
      return { layers: [], dataMode: 'unavailable', error: 'layer catalogue returned an incompatible schema', notices: [] }
    }
    const layers = (body as { layers: unknown[] }).layers.filter(isLayer)
    // The catalogue's notices are part of the catalogue. The radar one records
    // that the imagery is drawn from the rain layer alone, and a reader shown
    // radar without it would read a snow band as dry air.
    const rawNotices = (body as { notices?: unknown }).notices
    const notices = Array.isArray(rawNotices) ? rawNotices.filter((notice): notice is string => typeof notice === 'string' && notice.trim().length > 0) : []
    return { layers, dataMode: toDataMode((body as { data_mode?: unknown }).data_mode), error: null, notices }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { layers: [], dataMode: 'unavailable', error: error instanceof Error ? error.message : 'layer catalogue unavailable', notices: [] }
  }
}

function isCatalogSource(value: unknown): value is CatalogSource {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<CatalogSource>
  return typeof candidate.id === 'string' && typeof candidate.product === 'string' && typeof candidate.producer === 'string' && typeof candidate.state === 'string'
}

export async function loadCatalog(signal?: AbortSignal): Promise<CatalogResult> {
  try {
    const response = await fetch(`${prefix}/catalog`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { sources: [], dataMode: 'unavailable', error: `catalog returned ${response.status}` }
    const body: unknown = await response.json()
    if (!body || typeof body !== 'object' || !Array.isArray((body as { sources?: unknown }).sources)) {
      return { sources: [], dataMode: 'unavailable', error: 'catalog returned an incompatible schema' }
    }
    const sources = (body as { sources: unknown[] }).sources.filter(isCatalogSource)
    return { sources, dataMode: toDataMode((body as { data_mode?: unknown }).data_mode), error: null }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { sources: [], dataMode: 'unavailable', error: error instanceof Error ? error.message : 'catalog unavailable' }
  }
}

function isSourceStatus(value: unknown): value is SourceStatusItem {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<SourceStatusItem>
  return typeof candidate.source_id === 'string' && typeof candidate.state === 'string'
}

/** Registry state and recorded retrieval, one row per source. This is the only
 *  thing that may say a source is live: an unreadable response returns a null
 *  list, never an empty one, because "nothing is live" is a claim of its own and
 *  must not be made on a failed request. */
export async function loadSourceStatus(signal?: AbortSignal): Promise<SourceStatusResult> {
  try {
    const response = await fetch(`${prefix}/sources/status`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { statuses: null, dataMode: 'unavailable', error: `source status returned ${response.status}` }
    const body: unknown = await response.json()
    if (!body || typeof body !== 'object' || !Array.isArray((body as { statuses?: unknown }).statuses)) {
      return { statuses: null, dataMode: 'unavailable', error: 'source status returned an incompatible schema' }
    }
    const statuses: SourceStatusItem[] = (body as { statuses: unknown[] }).statuses.filter(isSourceStatus).map((row) => ({
      source_id: row.source_id,
      state: row.state,
      // A row that does not declare its own data_mode is not treated as live.
      data_mode: toDataMode((row as { data_mode?: unknown }).data_mode),
      last_retrieval: typeof row.last_retrieval === 'string' ? row.last_retrieval : null,
      detail: typeof row.detail === 'string' ? row.detail : '',
    }))
    return { statuses, dataMode: toDataMode((body as { data_mode?: unknown }).data_mode), error: null }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { statuses: null, dataMode: 'unavailable', error: error instanceof Error ? error.message : 'source status unavailable' }
  }
}

export interface RasterRequest {
  west: number
  south: number
  east: number
  north: number
  widthPx: number
  heightPx: number
  validTime?: string
}

/** The largest edge the endpoint will render. Asking for more is refused, so the
 *  request is clamped here rather than discovering it as a 422. */
const MAX_RENDER_PIXELS = 2048

/** Every raster is requested in web mercator. The map canvas IS web mercator,
 *  so a tile rendered in EPSG:3857 over the visible bounds corner-pins onto it
 *  exactly; the EPSG:4326 tiles this client used to pin the same way were
 *  warped by ~2-3 km through the middle of a 4 degree box at this latitude. */
export const RASTER_CRS = 'EPSG:3857'

/** Physical pixels for a CSS-pixel length, with the device pixel ratio capped
 *  at 2. The provider rasterises server-side, so a DPR-sized request is what
 *  keeps a forecast field sharp on a high-density display; past 2x nothing
 *  gains legibility and the bytes only grow. */
export function renderPixelSize(cssPx: number): number {
  const ratio = Math.min(Math.max(globalThis.devicePixelRatio || 1, 1), 2)
  return Math.round(cssPx * ratio)
}

/** Documented map-image contract: the API proxies one WMS `GetMap` per request so
 *  no upstream URL is ever hardcoded in the bundle. A layer may override the path.
 *
 *  The four bounds are sent as the four separate parameters the endpoint
 *  declares, plus `crs=EPSG:3857` so the tile is rendered in the projection the
 *  canvas displays. A packed `bbox` is not in that signature: FastAPI would
 *  ignore it, fall back to its default Avalon box, and answer 200 with a
 *  perfectly plausible image of the wrong extent. Nothing about that failure is
 *  visible, which is why `api.test.ts` asserts the parameter set directly. */
export function layerRasterUrl(layer: LayerItem, request: RasterRequest): string {
  const params = new URLSearchParams({
    south: request.south.toFixed(5),
    west: request.west.toFixed(5),
    north: request.north.toFixed(5),
    east: request.east.toFixed(5),
    width: String(Math.min(MAX_RENDER_PIXELS, Math.max(1, Math.round(request.widthPx)))),
    height: String(Math.min(MAX_RENDER_PIXELS, Math.max(1, Math.round(request.heightPx)))),
    crs: RASTER_CRS,
  })
  if (request.validTime) params.set('valid_time', request.validTime)
  const base = layer.raster_url ?? `${prefix}/layers/${encodeURIComponent(layer.id)}/raster`
  return `${base}${base.includes('?') ? '&' : '?'}${params}`
}

/** The provider's own legend graphic. The UI never draws a colour ramp of its own. */
export function layerLegendUrl(layer: LayerItem): string {
  return layer.legend_url ?? `${prefix}/layers/${encodeURIComponent(layer.id)}/legend`
}

/** What a layer's evidence rests on, in words.
 *
 *  A live-proxied layer bypassed ingestion, QC, manifest validation and atomic
 *  publication; a published artifact did not. Both were retrieved, but they do
 *  not carry the same assurance, and the reader cannot weigh what they are shown
 *  without being told which is which. An absent or unrecognised basis fails
 *  closed to unknown — never to the stronger of the two. */
export function describeEvidenceBasis(basis: string | undefined | null, group?: string): string {
  if (basis === 'live_proxy') return 'Live-proxied imagery, rendered by the provider at request time. Not a published artifact: it has not passed ingest, QC or atomic publication.'
  if (basis === 'published_artifact' && group === 'rendered_grid') {
    // The one case where the drawn pixels come from the artifact itself: the
    // API paints the stored cells, nearest-neighbor, and fetches nothing.
    return 'Published artifact: this layer\u2019s evidence passed ingest, QC and atomic publication. Its imagery is rendered by this experiment from the stored grid values at their native cells - nearest-neighbor, never smoothed - not fetched from a provider.'
  }
  // Even here the image itself is live-rendered, so the drawn pixels are never
  // described as the published artifact.
  if (basis === 'published_artifact') return 'Published artifact: this layer\u2019s evidence passed ingest, QC and atomic publication. Any imagery shown for it is still rendered live by the provider.'
  return 'Unknown evidence basis: the layer did not declare one, so no assurance is claimed for it.'
}

/** Whether anything was drawn in a retrieved image.
 *
 *  A fully transparent tile is a reading — the provider was asked and detected
 *  nothing — so it must not be reported as an outage. `not-inspected` is the
 *  honest third answer for a runtime that cannot decode the bytes: it says the
 *  image was retrieved without claiming to know whether it is empty. */
export type RasterCoverage = 'has-pixels' | 'fully-transparent' | 'not-inspected'

async function inspectCoverage(blob: Blob): Promise<RasterCoverage> {
  const decode = (globalThis as { createImageBitmap?: (blob: Blob) => Promise<ImageBitmap> }).createImageBitmap
  const Canvas = (globalThis as { OffscreenCanvas?: new (width: number, height: number) => OffscreenCanvas }).OffscreenCanvas
  if (typeof decode !== 'function' || typeof Canvas !== 'function') return 'not-inspected'
  try {
    const bitmap = await decode(blob)
    const canvas = new Canvas(bitmap.width, bitmap.height)
    const context = canvas.getContext('2d') as OffscreenCanvasRenderingContext2D | null
    if (!context) return 'not-inspected'
    context.drawImage(bitmap, 0, 0)
    const { data } = context.getImageData(0, 0, bitmap.width, bitmap.height)
    for (let index = 3; index < data.length; index += 4) {
      if (data[index] !== 0) return 'has-pixels'
    }
    return 'fully-transparent'
  } catch {
    return 'not-inspected'
  }
}

/** The retrieval facts the response carries about one image. Every field here is
 *  read from an `X-Weather-*` header; none of it is inferred from the bytes. */
export interface RasterProvenance {
  retrievalStatus: string
  /** The upstream WMS layer the image was drawn from, or null for a
   *  rendered-grid image, which has no upstream: its pixels are the stored
   *  artifact's own cells and `sourceId` names where they came from. */
  wmsLayer: string | null
  /** `X-Weather-Source-Id`: the ingested source a rendered-grid image was
   *  drawn from. Null for provider-rendered imagery. */
  sourceId: string | null
  evidenceBasis: string | null
  imageBasis: string | null
  validTime: string | null
  referenceTime: string | null
  upstreamUrl: string | null
  attribution: string | null
  byteSize: number | null
  notice: string | null
}

export interface RasterImage {
  objectUrl: string
  request: RasterRequest
  provenance: RasterProvenance
  coverage: RasterCoverage
}

/** Why an image is not being drawn, in the reader's words rather than a code.
 *  429 and 502 are kept apart deliberately: a budget the client spent is not the
 *  same claim as an upstream that could not be reached, and neither is an
 *  absence of weather. */
function rasterFailure(status: number, detail: string | null): string {
  const because = detail ? `: ${detail}` : ''
  if (status === 429) return `imagery was not retrieved because the upstream request budget was reached${because}. This is a limit on our requests, not an absence of weather`
  if (status === 502) return `no image was retrieved from the provider${because}`
  if (status === 501) return `this layer records no upstream imagery to draw${because}`
  if (status === 422) return `the image request was refused as malformed${because}`
  if (status === 404) return `no such layer is published${because}`
  return `map image request returned ${status}${because}`
}

async function failureDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.clone().json()
    const detail = (body as { detail?: unknown } | null)?.detail
    return typeof detail === 'string' ? detail : null
  } catch {
    return null
  }
}

/** Fetch one map image. Anything that is not an image response is an explicit
 *  unavailability, reported with its reason; nothing is drawn in its place.
 *
 *  Bytes without provenance are refused outright. An image is only evidence if
 *  the client can say what it is and where it came from, and the one failure this
 *  project cannot tolerate is a plausible picture with nothing behind it. */
export async function loadLayerRaster(layer: LayerItem, request: RasterRequest, signal?: AbortSignal): Promise<{ image: RasterImage | null; error: string | null }> {
  try {
    const response = await fetch(layerRasterUrl(layer, request), { signal, headers: { Accept: 'image/png,image/*' } })
    if (!response.ok) return { image: null, error: rasterFailure(response.status, await failureDetail(response)) }
    const contentType = response.headers.get('content-type') ?? ''
    if (!contentType.startsWith('image/')) return { image: null, error: `map image request returned ${contentType || 'an unlabelled body'}, not an image` }
    const retrievalStatus = response.headers.get('X-Weather-Retrieval-Status')
    const wmsLayer = response.headers.get('X-Weather-Wms-Layer')
    const imageBasis = response.headers.get('X-Weather-Image-Basis')
    const sourceId = response.headers.get('X-Weather-Source-Id')
    // Provenance is what makes bytes drawable. A provider-rendered image names
    // its upstream WMS layer; a rendered-grid image has no upstream and names
    // the ingested source its pixels were drawn from instead. Either statement
    // suffices; neither is a 404-shaped guess.
    const renderedGrid = imageBasis === 'rendered_grid' && !!sourceId
    if (!retrievalStatus || (!wmsLayer && !renderedGrid)) {
      return { image: null, error: 'the image carried no retrieval provenance (X-Weather-Retrieval-Status plus X-Weather-Wms-Layer or a rendered-grid X-Weather-Source-Id), so its bytes are not drawn' }
    }
    const blob = await response.blob()
    if (blob.size === 0) return { image: null, error: 'map image request returned an empty body' }
    if (typeof URL.createObjectURL !== 'function') return { image: null, error: 'this browser cannot display the returned map image' }
    const byteSize = Number(response.headers.get('X-Weather-Byte-Size'))
    return {
      image: {
        objectUrl: URL.createObjectURL(blob),
        request,
        coverage: await inspectCoverage(blob),
        provenance: {
          retrievalStatus,
          wmsLayer,
          sourceId,
          evidenceBasis: response.headers.get('X-Weather-Evidence-Basis'),
          imageBasis,
          validTime: response.headers.get('X-Weather-Valid-Time'),
          referenceTime: response.headers.get('X-Weather-Reference-Time'),
          upstreamUrl: response.headers.get('X-Weather-Upstream-Url'),
          attribution: response.headers.get('X-Weather-Attribution'),
          byteSize: Number.isFinite(byteSize) && byteSize > 0 ? byteSize : null,
          notice: response.headers.get('X-Weather-Wms-Layer-Notice'),
        },
      },
      error: null,
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { image: null, error: error instanceof Error ? error.message : 'map image unavailable' }
  }
}

export const STORY_OFFSETS = [-3, -1, 0, 3, 6, 12, 18, 24]

function hourIso(reference: Date, offsetHours: number): string {
  const target = new Date(reference.getTime() + offsetHours * 3600 * 1000)
  target.setUTCMinutes(0, 0, 0)
  return target.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/** Build the 28-hour story from the hours the API actually served.
 *  Every card is one real `/point` response; nothing is interpolated between
 *  them, and an hour the timeline does not publish is simply not requested. */
export async function loadStory(location: LocationPoint, timeline: TimelineResponse | null, product: string | undefined, signal?: AbortSignal): Promise<StoryStep[]> {
  // An undeclared or unavailable timeline names no published hour, so no card is
  // built from it. Its hours would otherwise read as coverage on the strength of
  // a response that never claimed any.
  if (!timeline || timeline.data_mode === 'unavailable') return []
  const published = new Set(
    timeline.items
      .filter((item) => item.available_products.length > 0)
      .map((item) => new Date(item.valid_time_utc).getTime()),
  )
  const reference = new Date()
  reference.setUTCMinutes(0, 0, 0)
  const wanted = STORY_OFFSETS
    .map((offset) => ({ offset, iso: hourIso(reference, offset) }))
    .filter((candidate) => published.has(new Date(candidate.iso).getTime()))
  const results = await Promise.all(wanted.map(async (candidate) => {
    const result = await loadPoint(location, candidate.iso, product, signal)
    if (result.source === 'unavailable') return null
    const snapshot = result.snapshot
    const step: StoryStep = {
      time: candidate.offset === 0 ? 'Now' : candidate.offset > 0 ? `+${candidate.offset}h` : `${candidate.offset}h`,
      offset: candidate.offset,
      label: snapshot.mode === 'consensus' ? 'Consensus response' : snapshot.mode === 'unavailable' ? 'Evidence only' : `${snapshot.mode.toUpperCase()} response`,
      dataMode: snapshot.dataMode,
      temperatureC: snapshot.temperatureC,
      dewPointC: snapshot.dewPointC,
      precipPct: snapshot.precipitationProbabilityPct,
      windKmh: snapshot.windKmh,
    }
    const hasValue = step.temperatureC !== null || step.dewPointC !== null || step.windKmh !== null
    return hasValue ? step : null
  }))
  return results.filter((step): step is StoryStep => step !== null)
}

/** Which frame of a layer answers `at`, or null if none may.

 *  Nearest wins, but only inside the layer's own declared tolerance. Outside it
 *  the answer is null and the caller draws nothing: silently showing the closest
 *  older frame is how a six-minute radar sweep ends up presented as the weather
 *  an hour later, which is exactly the fabrication this project forbids. */
export function resolveFrame(layer: LayerItem, at: Date): ResolvedFrame | null {
  const best = nearestFrame(layer, at)
  if (!best) return null
  const tolerance = layer.staleness_tolerance_seconds
  // A layer that did not declare a tolerance does not get an assumed one.
  if (typeof tolerance !== 'number' || Math.abs(best.offsetSeconds) > tolerance) return null
  return best
}

/** The published frame closest to `at`, with no tolerance applied. This is
 *  what the drawer names when nothing may be drawn: the reader is told how far
 *  away the nearest evidence is and offered a jump to it, instead of being
 *  shown it as though it were current. Never used to draw. */
export function nearestFrame(layer: LayerItem, at: Date): ResolvedFrame | null {
  const times = layer.times ?? []
  const target = at.getTime()
  let best: { time: string; distance: number } | null = null
  for (const time of times) {
    const stamp = new Date(time).getTime()
    if (Number.isNaN(stamp)) continue
    const distance = Math.abs(stamp - target)
    if (!best || distance < best.distance) best = { time, distance }
  }
  if (!best) return null
  return { time: best.time, offsetSeconds: Math.round((new Date(best.time).getTime() - target) / 1000) }
}

/** The 502 body the legend endpoint returns when the provider served nothing.
 *  Fetched only after the `<img>` has already failed, so the reason shown is
 *  the API's own sentence rather than a broken-image icon under alt text that
 *  claims a legend exists. */
export async function loadLegendFailure(layer: LayerItem, signal?: AbortSignal): Promise<string> {
  try {
    const response = await fetch(layerLegendUrl(layer), { signal, headers: { Accept: 'application/json,image/*' } })
    if (response.ok) return 'the provider returned a legend the browser could not display'
    const detail = await failureDetail(response)
    return detail ?? `legend request returned ${response.status}`
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return error instanceof Error ? error.message : 'legend request failed'
  }
}

/** Human wording for a frame offset. Always shown beside the layer, so the
 *  reader can see the frame is not the instant they asked for. */
export function describeOffset(offsetSeconds: number): string {
  if (offsetSeconds === 0) return 'exact frame'
  const magnitude = Math.abs(offsetSeconds)
  const amount = magnitude < 90 ? `${magnitude} s` : magnitude < 5400 ? `${Math.round(magnitude / 60)} min` : `${(magnitude / 3600).toFixed(1)} h`
  return offsetSeconds < 0 ? `${amount} earlier` : `${amount} later`
}

/** Fetch one layer's stored features at one exact frame. Anything that is not a
 *  feature collection is an explicit unavailability, never an empty map. */
export async function loadLayerFeatures(
  layer: LayerItem,
  frame: ResolvedFrame,
  signal?: AbortSignal,
): Promise<{ features: GeoJsonFeature[]; error: string | null }> {
  try {
    const url = `${prefix}/layers/${encodeURIComponent(layer.id)}/features?valid_time=${encodeURIComponent(frame.time)}`
    const response = await fetch(url, { signal, headers: { Accept: 'application/geo+json,application/json' } })
    if (!response.ok) return { features: [], error: `feature request returned ${response.status}` }
    const body = (await response.json()) as Partial<LayerFeatureCollection>
    if (!Array.isArray(body.features)) return { features: [], error: 'feature request returned an incompatible schema' }
    return { features: body.features, error: null }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { features: [], error: error instanceof Error ? error.message : 'features unavailable' }
  }
}
