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
  /** Every evidence class this provider/product reported, deduplicated in
   *  first-seen order. A row carrying more than one says so. */
  evidenceClasses: ResolvedEvidenceClass[]
}

/** How a value came to exist, as `provenance.evidence_class` declares it.
 *  Required on every served value, with no default (ADR 0001). */
export type EvidenceClass =
  | 'retrieved'
  | 'reprocessed'
  | 'derived_here'
  | 'intermediary_derived'
  | 'generated_display'
  | 'uncalibrated_observation'

/** What the client resolved a declared class to. `unrecognised` covers both a
 *  name outside the six and a provenance that declared none; both are shown
 *  as unavailable with the reason, never as `retrieved`. */
export type ResolvedEvidenceClass = EvidenceClass | 'unrecognised'

/** How a source's values reach this deployment, as the registry declares it.
 *  A separate axis from the evidence class: an `intermediary_derived` value is
 *  still retrieved by this deployment. */
export type DeliveryKind = 'published_cell' | 'reprocessed' | 'intermediary_derived'

/** The declared phase of a humidity value. An attribute of the value, not part
 *  of its key: liquid and mixed differ only below freezing, and two keys would
 *  double every humidity field for a difference that vanishes above zero. */
export type FieldPhase = 'liquid' | 'mixed'

/** Where a field's data sits, as the catalogue's storage rule declares it.
 *  `available-not-stored` and `not-published` are two different upstream facts
 *  and neither is an absent VALUE; both stay distinct from `null`, `blocked`
 *  and `aged_out`. */
export type FieldStorage = 'stored' | 'available-not-stored' | 'not-published'

/** One unordered pair of served members of one family, as `/point` answers it.
 *  `reason` and `detail` are null when the pair is comparable. The client never
 *  computes one of these: the phase rule needs the air temperature and the
 *  catalogue's definitions, which live on the API side. */
export interface ComparabilityPair {
  family: string
  a: string
  b: string
  comparable: boolean
  reason: string | null
  detail: string | null
}

/** One field of a `/catalog` source entry: what the source publishes, under
 *  which catalogue key, and whether this deployment stores it. */
export interface CatalogFieldEntry {
  key: string
  family: string
  storage: FieldStorage | null
  upstream: string | null
  note: string | null
}

/** One input a `derived_here` value was computed from, as the response listed
 *  it. Every field is what the API said; nothing is inferred from the input's
 *  name. */
export interface DerivationInput {
  field: string
  sourceId: string | null
  product: string | null
  validTime: string | null
  /** The run the input came from, where the input had one. */
  runTime: string | null
  units: string | null
  /** The input's own quality status, verbatim. Null when none was declared. */
  quality: string | null
  evidenceClass: ResolvedEvidenceClass
  /** Exactly the class string the response carried for this input, or null. */
  declaredClass: string | null
}

/** The registered derivation method a `derived_here` value names. */
export interface DerivationMethod {
  name: string
  version: string | null
  citation: string | null
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
  /** The catalogue key this value was served under, verbatim. Null when the
   *  response declared none, which is said rather than guessed from the API
   *  field name: a name and a catalogue key are not the same claim. */
  fieldKey: string | null
  /** The family the response put this value in. `ungrouped` when it declared
   *  none — never inferred from how the key is spelled. */
  family: string
  /** The declared phase of a humidity value, or null for every other field and
   *  for a humidity value that declared none. */
  phase: FieldPhase | null
  /** Whether this deployment stores the field. Null means the response
   *  declared nothing, which is a gap in the response, not a fourth state. */
  storage: FieldStorage | null
  /** `uncatalogued_field`: the variable has no catalogue key, so the API
   *  refused to serve a value for it and said so in a notice. */
  uncatalogued: boolean
  /** The API's own description of a derived value (e.g. MetPy RH from dew
   *  point). Null means the field was read from the provider as published. */
  derivation: string | null
  derivationVersion: string | null
  /** The declared class, resolved. `unrecognised` when the response carried a
   *  class this client does not know, or none at all. */
  evidenceClass: ResolvedEvidenceClass
  /** The class string exactly as the response wrote it, for the reason line. */
  declaredClass: string | null
  /** `quality.status` and `quality.flags` as served; `derived` is a flag, not
   *  a fifth status, so the four-status contract holds. */
  qualityStatus: string | null
  qualityFlags: string[]
  /** The method and inputs a `derived_here` value names. Empty and null for
   *  every other class; never synthesised from the derivation sentence. */
  derivationMethod: DerivationMethod | null
  derivationInputs: DerivationInput[]
  /** The registry's delivery kind for the producing record, and the
   *  intermediary it names. Null kind means the record declared none, which
   *  renders no label at all. */
  deliveryKind: DeliveryKind | null
  intermediary: string | null
  /** The intermediary's own method, where the intermediary documents one.
   *  Null is "undocumented", which is said out loud rather than read as
   *  "no transformation". */
  intermediaryMethod: string | null
  /** Whether this value may stand as a field's primary reading. The API
   *  computes it from the class; the client additionally refuses a source the
   *  catalogue marks `display_primary: false`. */
  displayPrimaryEligible: boolean
  /** `derivation_refused`: a derived value the registry conditions refused.
   *  `provenance_unmodelled`: an artifact whose provenance could not be
   *  modelled. Either renders as unavailable with the response's own notice. */
  derivationRefused: boolean
  provenanceUnmodelled: boolean
  /** The response notice that explains this field's refusal, matched at
   *  normalise time where both the field name and the notices are in hand.
   *  Null when the value is a reading rather than a refusal. */
  notice: string | null
}

/** One value for a field that is NOT its primary reading: a reprocessed,
 *  intermediary-derived or uncalibrated value, or one from a source the
 *  catalogue refuses as a primary. Shown beside the reading, never in it. */
export interface FieldAlternative {
  field: string
  /** As rendered, already unit-converted where the metric converts. */
  text: string
  attribution: FieldAttribution
}

/** One value the response served, whatever became of it afterwards.
 *
 *  The metric grid renders a fixed list of field names; the family view must
 *  render everything that was actually served, or a member the response
 *  carried would vanish from the family it belongs to and the reader would see
 *  a family with fewer members than the evidence has. So this is the response's
 *  own list, in response order, primaries and alternatives alike. */
export interface ServedFieldValue {
  /** The API field name, exactly as served. */
  field: string
  /** The value as served, in the unit the response declared. Never converted:
   *  a member is shown to be compared with its siblings, and rewriting its
   *  unit is how a number stops matching the key beside it. */
  text: string
  /** Whether a number or string came back at all. False is not an error — a
   *  field that is `available-not-stored` has no value by definition. */
  hasValue: boolean
  /** The numeric value as served, unconverted, or null for a non-numeric or
   *  absent one. A difference is only ever taken between two of these. */
  value: number | null
  /** The unit the response declared for it, verbatim. Two members with
   *  different declared units are never differenced. */
  units: string | null
  /** Whether this value is the one the interface shows as the field's reading. */
  primary: boolean
  attribution: FieldAttribution
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
  /** Values the same field carried that may not be its primary reading, keyed
   *  by API field name. Rendered as alternative readings with their badge and
   *  delivery label; never promoted into the metric. */
  fieldAlternatives: Record<string, FieldAlternative[]>
  /** Every value the response served, in response order, for the family view. */
  servedFields: ServedFieldValue[]
  /** The response's own `notices`, verbatim. They carry the reason a
   *  derivation was refused or an artifact's provenance was not modelled. */
  notices: string[]
  /** One entry per unordered pair of served members within a family, exactly as
   *  `/point` computed it. Empty against an API that does not serve it yet,
   *  which the interface reads as "no pair is stated", never as "comparable". */
  comparability: ComparabilityPair[]
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
  /** Upper-air seeing/transparency ingredients: jet-level wind speeds
   *  (derived by the API from stored GFS u/v) and column precipitable water
   *  as stored. Interpretation is caption text, never a computed verdict. */
  upperAir: { jet200Kmh: number | null; jet300Kmh: number | null; precipitableWaterKgM2: number | null }
  /** OVATION aurora probability at the sampled grid cell, in percent as
   *  stored — a model nowcast, never an observation. Null when the response
   *  carried none; never defaulted to zero. */
  auroraProbabilityPct: number | null
  marine: { waveHeightM: number | null; sstC: number | null; tide: string }
  warnings: string[]
  story: StoryStep[]
  provenance: ProvenanceRow[]
}

export type DataSource = 'loading' | 'live' | 'mixed' | 'fixture' | 'unavailable'

export interface AstronomyInterval { kind: string; start: string; end: string }

export interface AstronomyMoon {
  rise: string | null
  set: string | null
  above_horizon: AstronomyInterval[]
  phase_deg: number
  illuminated_fraction: number
}

export interface AstronomyResponse {
  data_mode: FieldDataMode
  operational: false
  latitude: number
  longitude: number
  window_start: string
  window_end: string
  valid_time: string
  sun_altitude_deg: number
  moon_altitude_deg: number
  core_altitude_deg: number
  twilight_bands: AstronomyInterval[]
  moon: AstronomyMoon
  milky_way_core: { windows: AstronomyInterval[]; max_altitude_deg: number; caption: string }
  provenance: { source_id: string; kernel_id: string; kernel_sha256: string; derivation: string; derivation_version: string; operational: false } | null
  notices: string[]
}

export interface AstronomyResult { astronomy: AstronomyResponse | null; error: string | null }

/** `/space-weather` shapes. Planetary quantities: no coordinates, no sample
 *  distance, nothing localized. A null value is a gap in the feed, never zero. */
export interface SpaceWeatherFreshness {
  status: 'fresh' | 'stale' | 'unknown'
  age_seconds: number | null
  threshold_seconds: number | null
}

export interface SpaceWeatherReading {
  time: string
  value: number | null
  /** The provider's own per-value label on the Kp forecast series
   *  (`observed` | `estimated` | `predicted`); null where none was declared. */
  status?: string | null
}

export interface SpaceWeatherSeries {
  available: boolean
  source_id: string
  product: string
  readings: SpaceWeatherReading[]
  freshness: SpaceWeatherFreshness
  notices: string[]
}

export interface SolarWindLatest {
  available: boolean
  source_id: string
  product: string
  bz_gsm_nt: number | null
  bt_nt: number | null
  /** The instant the served Bz was actually measured. */
  measured_at: string | null
  /** Whatever the feed's own source field declared, verbatim; never a guess. */
  feed_declared_spacecraft: string | null
  freshness: SpaceWeatherFreshness
  notices: string[]
}

export interface SpaceWeatherResponse {
  data_mode: FieldDataMode
  operational: false
  generated_at: string
  kp_observed: SpaceWeatherSeries
  kp_forecast: SpaceWeatherSeries
  solar_wind: SolarWindLatest
  notices: string[]
}

export interface SpaceWeatherResult { spaceWeather: SpaceWeatherResponse | null; error: string | null }

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
  /** How the layer's values came to exist, as `/layers` declares it. Absent or
   *  unknown is `unrecognised`, said out loud in the drawer rather than read
   *  as `retrieved`. */
  evidence_class?: string
  /** The field family this layer's quantity belongs to, as `/layers` declares
   *  it. Optional: an older API omits it and the layer groups under
   *  `ungrouped` rather than under a family guessed from `field`. */
  family?: string
  /** The catalogue key the layer draws, where the API names one separately
   *  from its display `field`. */
  field_key?: string
  /** Whether this deployment stores the field behind the layer. */
  storage?: string
  /** The declared phase, for a humidity layer. */
  phase?: string | null
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
  /** How this record's values reach the deployment. Optional until every
   *  record declares one; absent renders no label rather than a doubt. */
  delivery_kind?: string
  /** Named where the kind is `reprocessed` or `intermediary_derived`. */
  intermediary?: string | null
  /** False means the registry refuses this source as any field's primary
   *  reading. Absent is not false: an undeclared record is not yet refused. */
  display_primary?: boolean
  /** What this source publishes, key by key, and whether this deployment
   *  stores it. Optional until the API serves it; absent renders no field list
   *  rather than an empty one, because "publishes nothing" is its own claim. */
  fields?: CatalogFieldEntry[]
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
