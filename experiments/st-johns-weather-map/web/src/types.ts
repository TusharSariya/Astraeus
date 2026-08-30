export type FallbackMode = 'consensus' | 'hrdps' | 'rdps' | 'unavailable'
export type AppMode = 'simple' | 'expert'

/** How a single response, or a single field inside one, was produced.
 *  Anything the API does not explicitly declare is `unavailable`. */
export type FieldDataMode = 'live' | 'fixture' | 'mixed' | 'unavailable'

export interface LocationPoint {
  id: string
  name: string
  latitude: number
  longitude: number
  kind: 'airport' | 'buoy' | 'station' | 'map'
  /** Registry source IDs whose declared coverage names this place. Empty or
   *  absent means no ingested source claims it, which the UI must say out loud:
   *  a pin on a map reads as coverage whether or not anything is behind it. */
  sourceIds?: string[]
}

export interface ProvenanceRow {
  provider: string
  product: string
  run: string
  role: string
  freshness: string
  member: string | null
  level: string
  dataMode: FieldDataMode
  /** Every `provenance.derivation` string this provider/product reported, one
   *  per derived field. Empty means every field of it was a provider value. */
  derivations: string[]
}

/** Who produced the number a metric shows. Carried beside every displayed
 *  reading, because a value without its source is a claim the interface is
 *  making on its own: on the blended response the first `temperature` field is
 *  a METAR observation and the second an HRDPS sample, and which one is shown
 *  has to be said. */
export interface FieldAttribution {
  sourceId: string | null
  product: string | null
  provider: string
  /** The API's own description of a derived value (e.g. MetPy RH from dew
   *  point). Null means the field was read from the provider as published. */
  derivation: string | null
  derivationVersion: string | null
}

export interface StoryStep {
  time: string
  offset: number
  label: string
  dataMode: FieldDataMode
  temperatureC: number | null
  dewPointC: number | null
  precipPct: number | null
  windKmh: number | null
}

/** One METAR/TAF cloud layer as the API served it, in provider order. The
 *  cover code is the retrieved meaning string (`BKN`), the base is metres above
 *  ground and is accepted only when the response declared metres. Layers are
 *  never bucketed into low/middle/high strata here. */
export interface CloudLayerReading {
  index: number
  coverCode: string | null
  coverPct: number | null
  baseM: number | null
}

export interface EvidenceSnapshot {
  mode: FallbackMode
  /** The response's own `selection.badge`, `selected_product_id` and
   *  `selected_source_id`. Null when the response carried none: the header
   *  then falls back to a mode label rather than naming a product it guessed. */
  selectionBadge: string | null
  selectedProductId: string | null
  selectedSourceId: string | null
  /** Response-level `data_mode`. */
  dataMode: FieldDataMode
  /** Per-field `provenance.data_mode`, keyed by the API field name. */
  fieldModes: Record<string, FieldDataMode>
  /** Per-field attribution for the field actually shown, keyed by API field name. */
  fieldSources: Record<string, FieldAttribution>
  issuedAt: string
  validAt: string | null
  temperatureC: number | null
  dewPointC: number | null
  relativeHumidityPct: number | null
  windKmh: number | null
  /** Meteorological "from" direction in degrees, as the API published it. */
  windDirectionDeg: number | null
  gustKmh: number | null
  precipitation: string
  precipitationProbabilityPct: number | null
  cloud: { low: number | null; middle: number | null; high: number | null }
  /** `total_cloud` on its own. It is not a stratum and never fills one. */
  totalCloudPct: number | null
  /** Reported cloud layers, slot by slot, only where the response carried one. */
  cloudLayers: CloudLayerReading[]
  /** Mean sea level pressure in hPa, converted only from a declared unit. */
  pressureHpa: number | null
  visibilityKm: number | null
  fogRisk: 'evidence_present' | 'not_indicated' | 'unknown'
  aqhi: number | null
  marine: { waveHeightM: number | null; sstC: number | null; tide: string }
  warnings: string[]
  story: StoryStep[]
  provenance: ProvenanceRow[]
}

export type DataSource = 'loading' | 'live' | 'mixed' | 'fixture' | 'unavailable'

export interface TimelineItem {
  valid_time_utc: string
  valid_time_newfoundland: string
  available_products: string[]
}

export interface TimelineResponse {
  /** Resolved by the same fail-closed rule as every other response: an absent or
   *  unrecognised mode is `unavailable`, and unavailable hours are not coverage. */
  data_mode: FieldDataMode
  start: string
  end: string
  items: TimelineItem[]
}

export interface TimelineResult {
  /** `null` when `/timeline` could not be read at all — never an empty window in
   *  that case, because "no hour is published" is a claim of its own. */
  timeline: TimelineResponse | null
  dataMode: FieldDataMode
  error: string | null
}

export interface ProfileLevel {
  pressure_hpa: number
  temperature_c: number | null
  dew_point_c: number | null
  relative_humidity_pct: number | null
  wind_speed_ms: number | null
}

export interface ProfileResponse {
  valid_time: string
  levels: ProfileLevel[]
}

export interface LayerItem {
  id: string
  title: string
  kind: string
  field: string
  product: string
  units: string
  semantics: string
  /** Exactly the frames this layer published, at its own cadence. An empty list
   *  means the layer declared no time axis — never that it covers every hour. */
  times?: string[]
  cadence_seconds?: number | null
  /** How far a requested time may sit from a published frame before the layer
   *  must report unavailable. Past this the UI draws nothing rather than
   *  presenting an older frame as though it were current. */
  staleness_tolerance_seconds?: number
  default_opacity?: number
  z_index?: number
  /** Optional absolute/relative overrides published by the API. When absent the
   *  documented `/layers/{id}/raster` and `/layers/{id}/legend` paths are used. */
  raster_url?: string
  legend_url?: string
  data_mode?: FieldDataMode
  /** What this layer's evidence rests on: `published_artifact` passed ingest, QC
   *  and atomic publication; `live_proxy` did not. Absent means unknown, which is
   *  said out loud rather than resolved to the stronger of the two. */
  evidence_basis?: string
  /** Whether the API will render an image for this layer at all. False means no
   *  raster request is issued for it — not that the request would come back empty. */
  raster_available?: boolean
  /** Whether the provider serves a legend for it. The client never draws one. */
  legend_available?: boolean
  /** The upstream WMS layer the imagery is rendered from, as declared. */
  upstream_wms_layer?: string | null
  /** `satellite | forecast_proxy | published_model | observation | alert`, as
   *  the API groups it. `satellite` is observed imagery whose frames exist only
   *  for the past; it is never forecast. Optional: an older API omits it and
   *  the drawer derives a group from `evidence_basis` and `kind` instead —
   *  never from the id. */
  group?: string | null
}

export interface LayersResult {
  layers: LayerItem[]
  dataMode: FieldDataMode
  error: string | null
  /** The catalogue's own caveats, verbatim. The radar one says the imagery is
   *  rain-only; dropping it would show snow-free radar as snow-free weather. */
  notices: string[]
}

/** A `/catalog` source record. Only the fields the UI actually renders are typed;
 *  nothing here is defaulted, so a missing field stays visibly missing. */
export interface CatalogSource {
  id: string
  producer: string
  product: string
  state: string
  status_reason: string
  role: string
  may_enter_consensus: boolean
  cadence: string
  forecast_horizon: string
  geographic_coverage: string
  licence: string
  attribution: string
}

export interface CatalogResult {
  sources: CatalogSource[]
  dataMode: FieldDataMode
  error: string | null
}

/** One layer's presence in the stack. Layers are additive: several may draw at
 *  once, which is what makes radar over a temperature field possible. */
export interface LayerSelection {
  id: string
  visible: boolean
  opacity: number
}

/** Which frame of a layer answers a requested time, if any does. */
export interface ResolvedFrame {
  time: string
  /** Signed seconds from the requested time to this frame. Always displayed:
   *  a frame drawn at the wrong time is worse than no frame at all. */
  offsetSeconds: number
}

/** One `/sources/status` row. Only the fields the UI renders are typed, so a
 *  field the API stops sending stays visibly missing instead of defaulting. */
export interface SourceStatusItem {
  source_id: string
  state: string
  data_mode: FieldDataMode
  last_retrieval: string | null
  detail: string
}

export interface SourceStatusResult {
  /** `null` when the endpoint could not be read at all. Never an empty list in
   *  that case: "no source is live" and "we could not ask" are different claims. */
  statuses: SourceStatusItem[] | null
  dataMode: FieldDataMode
  error: string | null
}

/** Whether a live ingested source stands behind a picker station. */
export type StationCoverageState = 'live' | 'declared-not-live' | 'no-source' | 'unknown'

export interface StationCoverage {
  state: StationCoverageState
  /** Short suffix for the on-canvas label and the picker option text. */
  short: string
  /** One sentence for the text alternative, naming the sources it checked. */
  detail: string
}

export interface LayerFeatureCollection {
  type: 'FeatureCollection'
  data_mode: FieldDataMode
  features: GeoJsonFeature[]
  notices: string[]
}

export interface GeoJsonFeature {
  type: 'Feature'
  geometry: { type: string; coordinates: unknown } | null
  properties: Record<string, unknown>
}
