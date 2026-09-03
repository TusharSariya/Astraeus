import { fixtureSnapshot, unavailableSnapshot } from './fixtures'
import { declaredEvidenceClass, resolveEvidenceClass } from './evidenceClass'
import { resolveDeliveryKind } from './deliveryKind'
import { groupByFamily, resolveFamily, resolveFieldKey, resolvePhase, resolveStorage, type FamilyGroup } from './fieldFamily'
import type { CatalogResult, CatalogSource, CloudLayerReading, ComparabilityPair, DerivationInput, DerivationMethod, EnsembleMemberSet, EnsembleProvenance, EvidenceSnapshot, FieldAlternative, FieldAttribution, FieldDataMode, GeoJsonFeature, LayerFeatureCollection, LayerItem, LayersResult, LocationPoint, ProvenanceRow, ResolvedEvidenceClass, ResolvedFrame, ServedFieldValue, SourceStatusItem, SourceStatusResult, StoryStep, TimelineResponse, TimelineResult, AstronomyResponse, AstronomyResult, SpaceWeatherResponse, SpaceWeatherResult,
} from './types'

const prefix = '/api/experiments/weather/v0'

export type PointDataSource = Exclude<import('./types').DataSource, 'loading'>

export interface ApiEvidenceField {
  field: string
  value: unknown
  /** The catalogue key, family, declared phase and storage state the response
   *  carries for this value. Every one is optional here so the page renders
   *  against an API that does not serve them yet; each absence is shown as an
   *  absence rather than filled in. They are read from the value object and,
   *  failing that, from `provenance`, because both placements are in use. */
  key?: unknown
  family?: unknown
  phase?: unknown
  storage?: unknown
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
  /** One entry per unordered pair of served members within a family. Optional:
   *  an API that does not serve it yet leaves every pair unstated, and an
   *  unstated pair is refused a difference exactly as a non-comparable one is. */
  comparability?: unknown
  /** The response's own notices. They carry the reason a derivation was
   *  refused or an artifact's provenance could not be modelled, which is the
   *  only place that reason exists. */
  notices?: unknown
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
function pickField(fields: ApiEvidenceField[], name: string, preferredSourceId: string | null, nonPrimarySources: ReadonlySet<string> = EMPTY_SOURCES): ApiEvidenceField | undefined {
  const matches = fields.filter((field) => field.field === name)
  // A reprocessed, intermediary-derived or uncalibrated value, or one from a
  // source the catalogue refuses, is never the reading — not even when the
  // response selected its source, and not even when it is the only value the
  // field has. It is offered as an alternative instead (`alternativesOf`).
  const eligible = matches.filter((field) => isDisplayPrimary(field, nonPrimarySources))
  if (preferredSourceId) {
    const preferred = eligible.find((field) => field.provenance?.source_id === preferredSourceId)
    if (preferred) return preferred
  }
  return eligible[0]
}

const EMPTY_SOURCES: ReadonlySet<string> = new Set<string>()

/** An alternative reading in words: the value as served, in the unit the
 *  response declared for it. Deliberately NOT unit-converted — an alternative
 *  is shown to be compared with the primary, and silently rewriting its unit
 *  is how a number stops matching the source it names. */
function describeValue(field: ApiEvidenceField): string {
  const value = field.value
  const units = String(field.provenance?.normalized_units ?? field.provenance?.original_units ?? '').trim()
  if (typeof value === 'number' && Number.isFinite(value)) {
    const shown = Number.isInteger(value) ? String(value) : value.toFixed(1)
    return units ? `${shown} ${units}` : shown
  }
  if (typeof value === 'string' && value.trim()) return value
  return 'no value'
}

/** The values of `name` that may not be the reading, in response order. */
function alternativesOf(fields: ApiEvidenceField[], name: string, nonPrimarySources: ReadonlySet<string>): ApiEvidenceField[] {
  return fields.filter((field) => field.field === name && !isDisplayPrimary(field, nonPrimarySources))
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

/** `quality` as `{ status, flags }`. A response that carries neither reports
 *  null and an empty flag list rather than a status this client made up. */
function qualityOf(provenance: Record<string, unknown>): { status: string | null; flags: string[] } {
  const quality = provenance.quality
  if (!quality || typeof quality !== 'object') return { status: null, flags: [] }
  const record = quality as Record<string, unknown>
  const flags = Array.isArray(record.flags) ? record.flags.filter((flag): flag is string => typeof flag === 'string') : []
  return { status: text(record.status), flags }
}

/** The inputs a `derived_here` value names, as `provenance.derivation_inputs`.
 *  Each entry keeps its own declared class, so an input that is not
 *  `retrieved` is visible to the reader rather than folded into the result. */
function derivationInputsOf(provenance: Record<string, unknown>): DerivationInput[] {
  const raw = provenance.derivation_inputs
  if (!Array.isArray(raw)) return []
  return raw.filter((entry): entry is Record<string, unknown> => !!entry && typeof entry === 'object').map((entry) => {
    // The API publishes `quality` as the same `{ status, flags }` object a
    // value's own provenance carries; a bare status string is accepted too so
    // that a hand-written or older response still reads as a status rather
    // than as "[object Object]".
    const quality = entry.quality
    const status = typeof quality === 'string' ? quality
      : quality && typeof quality === 'object' ? text((quality as Record<string, unknown>).status)
        : null
    return {
      field: String(entry.field ?? 'unnamed input'),
      sourceId: text(entry.source_id),
      product: text(entry.product),
      validTime: text(entry.valid_time),
      runTime: text(entry.run_time),
      units: text(entry.units),
      quality: status,
      evidenceClass: resolveEvidenceClass(entry.evidence_class),
      declaredClass: declaredEvidenceClass(entry.evidence_class),
    }
  })
}

/** The registered method a derived value names.
 *
 *  The API's shape is flat — `derivation`, `derivation_version`,
 *  `derivation_citation` — and that is the contract. The nested
 *  `derivation_method: { name, version, citation }` object is still accepted
 *  first because it costs three lines and lets a response that groups them
 *  read correctly; nothing produces it today. */
function derivationMethodOf(provenance: Record<string, unknown>): DerivationMethod | null {
  const method = provenance.derivation_method
  if (method && typeof method === 'object') {
    const record = method as Record<string, unknown>
    const name = text(record.name)
    if (name) return { name, version: text(record.version), citation: text(record.citation) }
  }
  const name = text(provenance.derivation)
  if (!name) return null
  return { name, version: text(provenance.derivation_version), citation: text(provenance.derivation_citation) }
}

/** Flags the API sets when a value exists as a refusal rather than a reading. */
const DERIVATION_REFUSED = 'derivation_refused'
const PROVENANCE_UNMODELLED = 'provenance_unmodelled'
/** Set on a variable that has no catalogue key. The API serves `value: null`
 *  and `data_mode: "unavailable"` for it and explains it in a notice. */
const UNCATALOGUED_FIELD = 'uncatalogued_field'

/** The three classes that are served but never a field's primary reading
 *  (`point-evidence-sampling`: "Values of class `reprocessed`,
 *  `intermediary_derived` and `uncalibrated_observation` SHALL be sampled and
 *  served as non-primary"). */
const NON_PRIMARY_CLASSES: readonly ResolvedEvidenceClass[] = ['reprocessed', 'intermediary_derived', 'uncalibrated_observation']

/** Whether a value may occupy a field's reading slot.
 *
 *  `unrecognised` deliberately MAY: a class the client cannot read is a
 *  failure to be shown in the reading's place, with its reason, and demoting
 *  it to an alternative instead would hide the fault behind a disclosure
 *  panel — the opposite of what the class field is for. The API's own
 *  `display_primary_eligible` is authoritative for the six it knows; when it
 *  says nothing the class is read directly, so a reprocessed value never
 *  becomes a reading merely because a field was missing from the response. */
function displayPrimaryEligibleOf(provenance: Record<string, unknown>, evidenceClass: ResolvedEvidenceClass): boolean {
  if (evidenceClass === 'unrecognised') return true
  if (typeof provenance.display_primary_eligible === 'boolean') return provenance.display_primary_eligible
  return !NON_PRIMARY_CLASSES.includes(evidenceClass)
}

/** `provenance.ensemble.member_set`, as Seam D declares it. Null when the
 *  entry is missing a family or source id — the two identities a member set
 *  cannot be read without. */
function ensembleMemberSetOf(raw: unknown): EnsembleMemberSet | null {
  if (!raw || typeof raw !== 'object') return null
  const record = raw as Record<string, unknown>
  const family = text(record.family)
  const sourceId = text(record.source_id)
  if (!family || !sourceId) return null
  const membersMissing = Array.isArray(record.members_missing)
    ? record.members_missing.filter((entry): entry is string => typeof entry === 'string')
    : []
  return {
    family,
    sourceId,
    runTime: text(record.run_time),
    membersDeclared: typeof record.members_declared === 'number' ? record.members_declared : 0,
    membersUsed: typeof record.members_used === 'number' ? record.members_used : 0,
    membersMissing,
    controlIncluded: typeof record.control_included === 'boolean' ? record.control_included : null,
    partial: record.partial === true,
  }
}

/** `provenance.ensemble`, as Seam D declares it. Null when the entry is
 *  missing a family — the identity every ensemble number is named by. */
function ensembleProvenanceOf(raw: unknown): EnsembleProvenance | null {
  if (!raw || typeof raw !== 'object') return null
  const record = raw as Record<string, unknown>
  const family = text(record.family)
  if (!family) return null
  return {
    family,
    statistic: text(record.statistic),
    computedHere: record.computed_here === true,
    memberSet: ensembleMemberSetOf(record.member_set),
    refusal: text(record.refusal),
    quantile: typeof record.quantile === 'number' ? record.quantile : null,
    threshold: typeof record.threshold === 'number' ? record.threshold : null,
    thresholdUnits: text(record.threshold_units),
    comparison: text(record.comparison),
    averagingWindowHours: typeof record.averaging_window_hours === 'number' ? record.averaging_window_hours : null,
  }
}

function attributionOf(field: ApiEvidenceField | undefined): FieldAttribution | null {
  if (!field) return null
  const provenance = field.provenance ?? {}
  const quality = qualityOf(provenance)
  const evidenceClass = resolveEvidenceClass(provenance.evidence_class)
  const deliveryKind = resolveDeliveryKind(provenance.delivery_kind)
  return {
    sourceId: typeof provenance.source_id === 'string' ? provenance.source_id : null,
    product: typeof provenance.product === 'string' ? provenance.product : null,
    provider: String(provenance.provider ?? 'Unknown provider'),
    // The catalogue axis. Read from the value first, then from provenance;
    // never from `field.field`, which is an API field name and not a promise
    // that a catalogue key of the same spelling exists.
    fieldKey: resolveFieldKey(field.key ?? provenance.key),
    family: resolveFamily(field.family ?? provenance.family),
    phase: resolvePhase(field.phase ?? provenance.phase),
    storage: resolveStorage(field.storage ?? provenance.storage),
    uncatalogued: quality.flags.includes(UNCATALOGUED_FIELD),
    derivation: typeof provenance.derivation === 'string' && provenance.derivation.trim() ? provenance.derivation : null,
    derivationVersion: typeof provenance.derivation_version === 'string' ? provenance.derivation_version : null,
    evidenceClass,
    declaredClass: declaredEvidenceClass(provenance.evidence_class),
    qualityStatus: quality.status,
    qualityFlags: quality.flags,
    // Optional on the wire, like every other field of the catalogue and window
    // contracts: an API that does not serve it yet leaves it null, and a null
    // last valid time downgrades an aged-out claim rather than filling one in.
    lastValidTime: text(provenance.last_valid_time),
    // Inputs and method are read only for the one class that is defined by
    // them. A reprocessed value naming a `derivation` is the intermediary's
    // sentence, not a registered method this deployment can cite.
    derivationMethod: evidenceClass === 'derived_here' ? derivationMethodOf(provenance) : null,
    derivationInputs: evidenceClass === 'derived_here' ? derivationInputsOf(provenance) : [],
    deliveryKind,
    intermediary: text(provenance.intermediary),
    intermediaryMethod: text(provenance.intermediary_method),
    displayPrimaryEligible: displayPrimaryEligibleOf(provenance, evidenceClass),
    member: provenance.member === null || provenance.member === undefined ? null : String(provenance.member),
    memberControl: typeof provenance.member_control === 'boolean' ? provenance.member_control : null,
    ensemble: ensembleProvenanceOf(provenance.ensemble),
    derivationRefused: quality.flags.includes(DERIVATION_REFUSED),
    provenanceUnmodelled: quality.flags.includes(PROVENANCE_UNMODELLED),
    // Filled in by `normalizePoint`, which is where the field name and the
    // response's notices are both in hand.
    notice: null,
  }
}

/** The response notice that explains one field's refusal.
 *
 *  The API writes a notice per skipped artifact,
 *  "artifact from <source> (revision <id>) was skipped: <reason>", and the
 *  reason for a refused derivation names the field. So a notice naming the
 *  field is preferred, and a notice naming only the source is the fallback —
 *  an unmodelled artifact's notice names the artifact, not each field it
 *  would have carried. Null when nothing in the response explains it, which
 *  the interface says out loud rather than inventing a reason. */
export function noticeForField(fieldName: string, attribution: FieldAttribution, notices: string[]): string | null {
  // `uncatalogued` joins the two refusals: the API serves no value for a
  // variable with no catalogue key and puts the reason in a notice, which is
  // the only place that reason exists.
  if (!attribution.derivationRefused && !attribution.provenanceUnmodelled && !attribution.uncatalogued) return null
  const named = notices.find((notice) => notice.includes(fieldName))
  if (named) return named
  const sourceId = attribution.sourceId
  return (sourceId && notices.find((notice) => notice.includes(sourceId))) ?? null
}

/** Whether a value may stand as a field's primary reading.
 *
 *  Two gates, both refusing: the value's own provenance (the class), and the
 *  catalogue record for its source (`display_primary: false`). Either one is
 *  enough to keep it out of the reading, because they refuse for different
 *  reasons — what the value is, and what the registry says the source is. */
function isDisplayPrimary(field: ApiEvidenceField, nonPrimarySources: ReadonlySet<string>): boolean {
  const attribution = attributionOf(field)
  if (!attribution?.displayPrimaryEligible) return false
  return !(attribution.sourceId && nonPrimarySources.has(attribution.sourceId))
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
  'wind_speed_200hPa', 'wind_speed_300hPa', 'precipitable_water', 'aurora_probability',
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

/** Options a caller may narrow the reading with. `nonPrimarySources` are the
 *  catalogue records whose `display_primary` is false; the catalogue is
 *  fetched separately, so a point normalised before it arrives simply applies
 *  the provenance gate alone and re-normalises when the catalogue lands. */
export interface NormalizeOptions {
  nonPrimarySources?: ReadonlySet<string>
  /** Seam D request parameters. Read only by `loadPoint`, which puts them on
   *  the query string; `normalizePoint` ignores them, because the response is
   *  self-describing and does not need to be told what was asked for. A
   *  member of `null` or `undefined` requests nothing narrower than the
   *  default; `'all'` is a provider identifier value like any other. */
  member?: string | null
  statistic?: string | null
  quantile?: number | null
  threshold?: number | null
  comparison?: string | null
}

/** The comparability list as the response served it.
 *
 *  Only entries naming a family and both members are kept, and `comparable`
 *  must be a real boolean: an entry that half-states a pair states nothing, and
 *  reading a missing `comparable` as `true` would be the one failure this list
 *  exists to prevent. A comparable pair's `reason` and `detail` are null. */
export function parseComparability(raw: unknown): ComparabilityPair[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((entry): entry is Record<string, unknown> => !!entry && typeof entry === 'object')
    .map((entry) => {
      const family = text(entry.family)
      const a = text(entry.a)
      const b = text(entry.b)
      if (!family || !a || !b || typeof entry.comparable !== 'boolean') return null
      return { family, a, b, comparable: entry.comparable, reason: text(entry.reason), detail: text(entry.detail) }
    })
    .filter((entry): entry is ComparabilityPair => entry !== null)
}

/** The source ids a catalogue refuses as any field's primary reading. */
export function nonPrimarySourceIds(sources: CatalogSource[]): ReadonlySet<string> {
  // `display_primary` absent is NOT false: a record that has not declared one
  // is undeclared, not refused, and refusing it here would blank a reading on
  // the strength of a field the registry has not filled in yet.
  return new Set(sources.filter((source) => source.display_primary === false).map((source) => source.id))
}

export function normalizePoint(point: ApiPointResponse, options: NormalizeOptions = {}): EvidenceSnapshot {
  const nonPrimarySources = options.nonPrimarySources ?? EMPTY_SOURCES
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
  const allFields = point.fields
  // Every metric reads from the values that MAY be a reading. A reprocessed,
  // intermediary-derived or uncalibrated value, or one from a source the
  // catalogue refuses, is filtered out here rather than at each call site, so
  // no converter, stratum or cloud-layer reader can promote one by accident.
  const fields = allFields.filter((field) => isDisplayPrimary(field, nonPrimarySources))
  const pick = (name: string) => pickField(fields, name, selectedSourceId, nonPrimarySources)
  const fogValue = pick('fog_state')?.value
  const fogRisk = fogValue === 'evidence_present' || fogValue === 'not_indicated' ? fogValue : 'unknown'
  const uniqueProvenance = new Map<string, ProvenanceRow>()
  // The provenance table lists every source that answered, primary or not:
  // it is the record of what was retrieved, not of what was displayed.
  allFields.forEach((field) => {
    const provenance = field.provenance ?? {}
    const provider = String(provenance.provider ?? 'Unknown provider')
    const product = String(provenance.product ?? field.field)
    const freshness = provenance.freshness as { status?: unknown; age_seconds?: unknown } | undefined
    const member = provenance.member === null || provenance.member === undefined ? null : String(provenance.member)
    const key = `${provider}/${product}`
    const derivation = attributionOf(field)?.derivation ?? null
    const existing = uniqueProvenance.get(key)
    // Every class this provider/product reported, deduplicated. A row that
    // mixes classes says so rather than showing the first one it saw.
    const evidenceClass = resolveEvidenceClass(provenance.evidence_class)
    const evidenceClasses = existing?.evidenceClasses.includes(evidenceClass)
      ? existing.evidenceClasses
      : [...(existing?.evidenceClasses ?? []), evidenceClass]
    uniqueProvenance.set(key, {
      evidenceClasses,
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
  const notices = Array.isArray(point.notices)
    ? point.notices.filter((notice): notice is string => typeof notice === 'string' && notice.trim().length > 0)
    : []
  const fieldModes: Record<string, FieldDataMode> = {}
  const fieldSources: Record<string, FieldAttribution> = {}
  const fieldAlternatives: Record<string, FieldAlternative[]> = {}
  DISPLAYED_FIELDS.forEach((name) => {
    const field = pick(name)
    if (field) {
      fieldModes[name] = toDataMode(field.provenance?.data_mode)
      const attribution = attributionOf(field)
      if (attribution) fieldSources[name] = { ...attribution, notice: noticeForField(name, attribution, notices) }
    }
    // Recorded whether or not the field has a primary: a field whose only
    // value is reprocessed reads as Unknown with that value beside it, which
    // is the whole point of the rule.
    const alternatives = alternativesOf(allFields, name, nonPrimarySources)
      .map((entry) => {
        const attribution = attributionOf(entry)
        return attribution ? { field: name, text: describeValue(entry), attribution } : null
      })
      .filter((entry): entry is FieldAlternative => entry !== null)
    if (alternatives.length > 0) fieldAlternatives[name] = alternatives
  })
  // Every served value, in response order, whether or not a metric renders it
  // and whether or not it may be a reading. The family view is built from
  // this: a member the response carried must appear under its family even when
  // no metric on the page has a slot for it.
  const servedFields = allFields
    .map((entry) => {
      const attribution = attributionOf(entry)
      if (!attribution) return null
      const hasValue = (typeof entry.value === 'number' && Number.isFinite(entry.value))
        || (typeof entry.value === 'string' && entry.value.trim().length > 0)
      return {
        field: entry.field,
        text: describeValue(entry),
        hasValue,
        value: finiteValue(entry),
        units: text(entry.provenance?.normalized_units ?? entry.provenance?.original_units),
        primary: fields.includes(entry),
        attribution: { ...attribution, notice: noticeForField(entry.field, attribution, notices) },
      }
    })
    .filter((entry): entry is ServedFieldValue => entry !== null)
  return {
    fieldAlternatives,
    servedFields,
    notices,
    comparability: parseComparability(point.comparability),
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
    upperAir: {
      jet200Kmh: speedKmh(fields, 'wind_speed_200hPa', selectedSourceId),
      jet300Kmh: speedKmh(fields, 'wind_speed_300hPa', selectedSourceId),
      precipitableWaterKgM2: numericField(fields, 'precipitable_water', selectedSourceId),
    },
    auroraProbabilityPct: numericField(fields, 'aurora_probability', selectedSourceId),
    marine: { waveHeightM: numericField(fields, 'wave_height', selectedSourceId), sstC: numericField(fields, 'sea_surface_temperature', selectedSourceId), tide: 'Tide feed unavailable' },
    // Alerts read from every field, not only the display-primary ones. An
    // alert is a published hazard text rather than a reading to be outranked,
    // and withholding one because its source is not a display primary would
    // drop a warning to satisfy a rule about numbers.
    warnings: alertTexts(allFields),
    story: [],
    provenance: [...uniqueProvenance.values()],
  }
}

export async function loadPoint(location: LocationPoint, validTime?: string, product?: string, signal?: AbortSignal, options: NormalizeOptions = {}): Promise<{ snapshot: EvidenceSnapshot; source: PointDataSource; error?: string }> {
  try {
    const params = new URLSearchParams({ latitude: String(location.latitude), longitude: String(location.longitude) })
    if (validTime) params.set('valid_time', validTime)
    if (product && product !== 'consensus') params.set('product', product)
    // Seam D: member and statistic are request parameters, sent only when the
    // caller named one, so a request that narrows nothing looks exactly like
    // it did before this axis existed.
    if (options.member) params.set('member', options.member)
    if (options.statistic) params.set('statistic', options.statistic)
    if (typeof options.quantile === 'number') params.set('quantile', String(options.quantile))
    if (typeof options.threshold === 'number') params.set('threshold', String(options.threshold))
    if (options.comparison) params.set('comparison', options.comparison)
    const response = await fetch(`${prefix}/point?${params}`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`weather API returned ${response.status}`)
    const body: unknown = await response.json()
    if (!isPointResponse(body)) throw new Error('weather API returned an incompatible point schema')
    const snapshot = normalizePoint(body, options)
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
/** Computed darkness/moon geometry over the window. Same fail-closed rule:
 *  a response that is not `live` keeps its notices as the reason, and a
 *  transport failure yields null — an empty band is a claim ("no darkness"),
 *  so it is never synthesized from a failure. */
export async function loadAstronomy(signal?: AbortSignal): Promise<AstronomyResult> {
  try {
    const response = await fetch(`${prefix}/astronomy`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { astronomy: null, error: `astronomy returned ${response.status}` }
    const body: unknown = await response.json()
    if (!body || typeof body !== 'object' || !Array.isArray((body as { twilight_bands?: unknown }).twilight_bands)) {
      return { astronomy: null, error: 'astronomy returned an incompatible schema' }
    }
    const astronomy = body as AstronomyResponse
    if (toDataMode(astronomy.data_mode) !== 'live') {
      const reason = astronomy.notices?.[0] ?? `astronomy declared data_mode "${String(astronomy.data_mode)}"`
      return { astronomy: null, error: reason }
    }
    return { astronomy, error: null }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { astronomy: null, error: error instanceof Error ? error.message : 'astronomy fetch failed' }
  }
}

/** Planetary space weather: latest Bz, observed Kp, and the provider's Kp
 *  outlook with its own per-value status. Same fail-closed rule as astronomy:
 *  only a response declaring `live` is shown, the API's own notices are the
 *  reason otherwise, and a transport failure yields null — a Kp card showing
 *  zero on an outage would be an invented reading. */
export async function loadSpaceWeather(signal?: AbortSignal): Promise<SpaceWeatherResult> {
  try {
    const response = await fetch(`${prefix}/space-weather`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { spaceWeather: null, error: `space-weather returned ${response.status}` }
    const body: unknown = await response.json()
    if (!body || typeof body !== 'object' || !(body as { kp_observed?: unknown }).kp_observed || !(body as { solar_wind?: unknown }).solar_wind) {
      return { spaceWeather: null, error: 'space-weather returned an incompatible schema' }
    }
    const spaceWeather = body as SpaceWeatherResponse
    if (toDataMode(spaceWeather.data_mode) !== 'live') {
      const reason = spaceWeather.notices?.[0] ?? `space-weather declared data_mode "${String(spaceWeather.data_mode)}"`
      return { spaceWeather: null, error: reason }
    }
    return { spaceWeather, error: null }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return { spaceWeather: null, error: error instanceof Error ? error.message : 'space-weather fetch failed' }
  }
}

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

/** A layer's declared evidence class. `/layers` declares it per layer the way
 *  `/point` declares it per value; an absent or unknown declaration resolves
 *  to `unrecognised`, which the drawer says out loud. It is never inferred
 *  from `evidence_basis` or the group: a published artifact can hold values of
 *  any class, and guessing here is exactly what the class field replaces. */
export function layerEvidenceClass(layer: LayerItem): ResolvedEvidenceClass {
  return resolveEvidenceClass(layer.evidence_class)
}

/** Layers bucketed by group in the shared order, empty groups omitted, and the
 *  API's order kept inside each group. */
export function groupLayers(layers: LayerItem[]): Array<{ group: LayerGroup; label: string; rows: LayerItem[] }> {
  return LAYER_GROUP_ORDER
    .map((group) => ({ group, label: LAYER_GROUP_LABELS[group], rows: layers.filter((layer) => layerGroup(layer) === group) }))
    .filter(({ rows }) => rows.length > 0)
}

/** A layer's field family, as `/layers` declares it and only as it declares it.
 *  An older API declares none and the layer groups under `ungrouped`: reading a
 *  family off `field` would put HRDPS opacity-weighted cloud and GFS geometric
 *  cloud in one group on the strength of a shared spelling, which is the
 *  collision the catalogue exists to remove. */
export function layerFamily(layer: LayerItem): string {
  return resolveFamily(layer.family)
}

/** The catalogue key a layer draws. `field_key` where the API names one, else
 *  its `field`, which is the name it publishes the layer's quantity under. */
export function layerFieldKey(layer: LayerItem): string | null {
  return resolveFieldKey(layer.field_key) ?? resolveFieldKey(layer.field)
}

/** Layers bucketed by field family, in catalogue order, ungrouped last. */
export function groupLayersByFamily(layers: LayerItem[]): Array<FamilyGroup<LayerItem>> {
  return groupByFamily(layers, layerFamily)
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

/** The server-derived motion texture between two adjacent published frames of
 *  a rendered-grid layer. Display-support for the opt-in interpolation
 *  shader; requested over exactly the frame rasters' extent so its pixels
 *  align with theirs. */
/** The texture variants /flow serves. Two of them belong to one method each
 *  and are requested only for that method. */
export type FlowTextureName = 'motion' | 'tangents' | 'visibility' | 'residual'

export interface FlowTexture {
  objectUrl: string
  /** Max displacement in output pixels encoded at channel value 255. */
  scalePixels: number
  /** The pair's Hermite knot velocities (start | end, side by side), or null
   *  when the artifact predates them - the shader then advects linearly. */
  tangentsUrl: string | null
  tangentsScalePixels: number
  /** The pair's per-frame visibility weights (R = frame 0, G = frame 1), or
   *  null when the served method derives none - the fusion is then the
   *  symmetric (1-t, t) every other construction uses. */
  visibilityUrl: string | null
  /** The pair's development envelope coefficients (R = a, G = b, signed
   *  around 128, in cloud percent at `residualScalePixels` per 255), or null
   *  when the served method publishes none - the shader then draws the
   *  advection mix alone, never an envelope the client made up. */
  residualUrl: string | null
  /** The cloud-percent value encoded at channel value 255 of the residual
   *  texture (`X-Weather-Flow-Scale` on that response); 0 when absent. */
  residualScalePixels: number
  frameFrom: string
  frameTo: string
  request: RasterRequest
  /** The client construction the server says these fields are meant for, from
   *  its own registry: 'hermite' | 'visibility' | 'residual-advection'. */
  shader: string
  /** The interpolation method these fields were derived by, as the server
   *  named it back. Carried so the on-map disclosure can say which
   *  construction produced the picture. */
  method: string
}

/** One entry of the interpolation bench, exactly as `/methods` declares it.
 *  The registry is the server's: the menu can never offer a construction the
 *  derivation does not publish. */
export interface InterpolationMethodScore {
  layerId: string
  sourceId: string
  variable: string
  heldOutFrames: number
  /** The motion veto's number. Decides only whether motion is displayed; it
   *  ranks nothing in the menu and is never printed there. */
  improvementOverReversedFlow: number
  /** Skill against the FIXED control: a plain crossfade of the same frames. */
  improvementOverCrossfade: number
  /** Skill against the second fixed control: linear advection of the pair. */
  improvementOverAdvection: number
  midpointMaePercent: number
  midpointSsim: number | null
  /** Gradient energy of the midpoint composite over the real frame's; 1.0 is
   *  as sharp as real, below it is blurred. */
  midpointSharpnessRatio: number | null
  midpointSpectralRatioError: number | null
  midpointMaeGrew: number | null
  midpointMaeDecayed: number | null
  /** Which of the method's options the derive actually applied on this
   *  layer, by option name. All false means the method reduced to the default
   *  construction there. */
  applied: Record<string, boolean>
  reducedToDefault: boolean
}

export interface InterpolationMethodItem {
  id: string
  title: string
  summary: string
  /** Reader copy (plan 0b): one plain sentence, one "gap" sentence, and the
   *  science note with its citations - all the server's words. */
  plain: string
  gap: string
  notes: string
  shader: string
  enabled: boolean
  generative: boolean
  /** True when the deployment's kill switch (WEATHER_GENERATED_DISPLAY=off)
   *  refused this generative construction: shown, never selectable. */
  generationDisabled: boolean
  published: boolean
  /** Unmet requirements are why a selected method may draw the same picture
   *  the baseline does. */
  requirements: Array<{ name: string; met: boolean; detail: string }>
  scores: InterpolationMethodScore[]
}

export const DEFAULT_INTERPOLATION_METHOD = 'baseline'

/** The bench, or an empty list. A method list that could not be read is never
 *  guessed at: the map then draws the default construction and the menu says
 *  the registry was unreadable. */
export async function loadMethods(signal?: AbortSignal): Promise<{ methods: InterpolationMethodItem[]; defaultMethod: string; notices: string[]; error: string | null }> {
  try {
    const response = await fetch(`${prefix}/methods`, { signal, headers: { Accept: 'application/json' } })
    if (!response.ok) return { methods: [], defaultMethod: DEFAULT_INTERPOLATION_METHOD, notices: [], error: `the interpolation bench returned ${response.status}` }
    const payload = await response.json()
    const optional = (value: unknown): number | null => (value === null || value === undefined ? null : Number(value))
    const methods: InterpolationMethodItem[] = (payload.methods ?? []).map((item: Record<string, unknown>) => ({
      id: String(item.id),
      title: String(item.title ?? item.id),
      summary: String(item.summary ?? ''),
      plain: String(item.plain ?? ''),
      gap: String(item.gap ?? ''),
      notes: String(item.notes ?? ''),
      shader: String(item.shader ?? 'hermite'),
      enabled: item.enabled !== false,
      generative: item.generative === true,
      generationDisabled: item.generation_disabled === true,
      published: item.published === true,
      requirements: ((item.requirements ?? []) as Array<Record<string, unknown>>).map((req) => ({
        name: String(req.name),
        met: req.met === true,
        detail: String(req.detail ?? ''),
      })),
      scores: ((item.scores ?? []) as Array<Record<string, unknown>>).map((score) => ({
        layerId: String(score.layer_id),
        sourceId: String(score.source_id),
        variable: String(score.variable),
        heldOutFrames: Number(score.held_out_frames ?? 0),
        improvementOverReversedFlow: Number(score.improvement_over_reversed_flow ?? 0),
        improvementOverCrossfade: Number(score.improvement_over_crossfade ?? 0),
        improvementOverAdvection: Number(score.improvement_over_advection ?? 0),
        midpointMaePercent: Number(score.midpoint_mae_percent ?? 0),
        midpointSsim: optional(score.midpoint_ssim),
        midpointSharpnessRatio: optional(score.midpoint_sharpness_ratio),
        midpointSpectralRatioError: optional(score.midpoint_spectral_ratio_error),
        midpointMaeGrew: optional(score.midpoint_mae_grew),
        midpointMaeDecayed: optional(score.midpoint_mae_decayed),
        applied: Object.fromEntries(
          Object.entries((score.applied ?? {}) as Record<string, unknown>).map(([name, on]) => [name, on === true]),
        ),
        reducedToDefault: score.reduced_to_default === true,
      })),
    }))
    return {
      methods,
      defaultMethod: String(payload.default_method ?? DEFAULT_INTERPOLATION_METHOD),
      notices: (payload.notices ?? []).map(String),
      error: null,
    }
  } catch (error) {
    if ((error as Error).name === 'AbortError') return { methods: [], defaultMethod: DEFAULT_INTERPOLATION_METHOD, notices: [], error: 'aborted' }
    return { methods: [], defaultMethod: DEFAULT_INTERPOLATION_METHOD, notices: [], error: `the interpolation bench could not be read: ${(error as Error).message}` }
  }
}

export function layerFlowUrl(
  layer: LayerItem,
  request: RasterRequest & { from: string; to: string },
  texture: FlowTextureName = 'motion',
  method: string = DEFAULT_INTERPOLATION_METHOD,
): string {
  const params = new URLSearchParams({
    from: request.from,
    to: request.to,
    south: request.south.toFixed(5),
    west: request.west.toFixed(5),
    north: request.north.toFixed(5),
    east: request.east.toFixed(5),
    width: String(Math.min(MAX_RENDER_PIXELS, Math.max(1, Math.round(request.widthPx)))),
    height: String(Math.min(MAX_RENDER_PIXELS, Math.max(1, Math.round(request.heightPx)))),
    crs: RASTER_CRS,
    texture,
    method,
  })
  return `${prefix}/layers/${encodeURIComponent(layer.id)}/flow?${params}`
}

/** Fetch one pair's motion texture. ``absent: true`` (a 404) is the disclosed
 *  crossfade fallback, not an error; anything else unusable is an error and
 *  equally falls back to the crossfade - never to an invented motion field. */
export async function loadLayerFlow(
  layer: LayerItem,
  request: RasterRequest & { from: string; to: string },
  signal?: AbortSignal,
  method: string = DEFAULT_INTERPOLATION_METHOD,
): Promise<{ flow: FlowTexture | null; absent: boolean; error: string | null }> {
  const fetchTexture = async (texture: FlowTextureName): Promise<{ objectUrl: string; scale: number; frameFrom: string | null; frameTo: string | null; method: string | null; shader: string | null } | 'absent' | { error: string }> => {
    const response = await fetch(layerFlowUrl(layer, request, texture, method), { signal, headers: { Accept: 'image/png,image/*' } })
    if (response.status === 404) return 'absent'
    if (!response.ok) return { error: `motion texture request returned ${response.status}` }
    const scale = Number(response.headers.get('X-Weather-Flow-Scale'))
    if (response.headers.get('X-Weather-Image-Basis') !== 'derived_motion' || !Number.isFinite(scale) || scale <= 0) {
      return { error: 'the motion texture carried no derived-motion provenance, so it is not used' }
    }
    const blob = await response.blob()
    if (blob.size === 0 || typeof URL.createObjectURL !== 'function') return { error: 'motion texture body unusable' }
    return {
      objectUrl: URL.createObjectURL(blob),
      scale,
      frameFrom: response.headers.get('X-Weather-Frame-From'),
      frameTo: response.headers.get('X-Weather-Frame-To'),
      method: response.headers.get('X-Weather-Interpolation-Method'),
      shader: response.headers.get('X-Weather-Flow-Shader'),
    }
  }
  try {
    const motion = await fetchTexture('motion')
    if (motion === 'absent') return { flow: null, absent: true, error: null }
    if ('error' in motion) return { flow: null, absent: false, error: motion.error }
    // The Hermite tangents are an upgrade, not a requirement: an artifact
    // predating them answers 404 and the shader advects linearly - one honest
    // rung down, never an invented curve.
    let tangents: { objectUrl: string; scale: number } | null = null
    const fetched = await fetchTexture('tangents').catch(() => 'absent' as const)
    if (fetched !== 'absent' && !('error' in fetched)) tangents = { objectUrl: fetched.objectUrl, scale: fetched.scale }
    // These two suffixes exist for exactly one shader each, unlike the
    // tangents which every method's artifact carries. So they are fetched only
    // when the server says it served a method with that shader - the server
    // refuses them by name for every other method, so asking on every pair
    // would be a guaranteed 404 per frame pair. Absent either way means the
    // shader falls back to symmetric fusion with no envelope, never to a
    // reliability or a development term the client made up.
    const served = motion.shader ?? ''
    let visibility: { objectUrl: string } | null = null
    if (served === 'visibility') {
      const visibilityFetched = await fetchTexture('visibility').catch(() => 'absent' as const)
      if (visibilityFetched !== 'absent' && !('error' in visibilityFetched)) {
        visibility = { objectUrl: visibilityFetched.objectUrl }
      }
    }
    let residual: { objectUrl: string; scale: number } | null = null
    if (served === 'residual-advection') {
      const residualFetched = await fetchTexture('residual').catch(() => 'absent' as const)
      if (residualFetched !== 'absent' && !('error' in residualFetched)) {
        residual = { objectUrl: residualFetched.objectUrl, scale: residualFetched.scale }
      }
    }
    return {
      flow: {
        objectUrl: motion.objectUrl,
        scalePixels: motion.scale,
        tangentsUrl: tangents?.objectUrl ?? null,
        tangentsScalePixels: tangents?.scale ?? 0,
        visibilityUrl: visibility?.objectUrl ?? null,
        residualUrl: residual?.objectUrl ?? null,
        residualScalePixels: residual?.scale ?? 0,
        frameFrom: motion.frameFrom ?? request.from,
        frameTo: motion.frameTo ?? request.to,
        request,
        // What the server says it served, not what was asked for.
        method: motion.method ?? method,
        shader: motion.shader ?? 'hermite',
      },
      absent: false,
      error: null,
    }
  } catch (error) {
    if ((error as Error).name === 'AbortError') return { flow: null, absent: false, error: 'aborted' }
    return { flow: null, absent: false, error: `motion texture request failed: ${(error as Error).message}` }
  }
}

/** Every object URL a FlowTexture holds, for revocation on eviction. */
export function flowObjectUrls(flow: FlowTexture): string[] {
  return [flow.objectUrl, flow.tangentsUrl, flow.visibilityUrl, flow.residualUrl].filter(
    (url): url is string => !!url,
  )
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
  if (basis === 'published_artifact' && group === 'satellite') {
    // The satellite group's one published-artifact member is the cloud mask
    // this experiment renders itself; the four provider composites stay
    // live_proxy. Saying “rendered live by the provider” here would
    // attribute our own pixels to NOAA.
    return 'Published artifact: this layer\u2019s evidence passed ingest, QC and atomic publication. Its imagery is drawn by this experiment from stored NOAA cloud-mask values at their stored cells - nearest-neighbor, never smoothed - not fetched from a provider.'
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
export async function loadStory(location: LocationPoint, timeline: TimelineResponse | null, product: string | undefined, signal?: AbortSignal, options: NormalizeOptions = {}): Promise<StoryStep[]> {
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
    const result = await loadPoint(location, candidate.iso, product, signal, options)
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

/** Which frame of a layer answers `at` QUIETLY, or null if none may.

 *  Nearest wins, but only inside the layer's own declared tolerance. Outside it
 *  the answer is null: a frame beyond the tolerance may still be drawn, but
 *  only through `resolveLayerFrame`'s fallback path, whose every frame carries
 *  a mandatory visible disclosure — an undisclosed older frame is how a
 *  six-minute radar sweep ends up presented as the weather an hour later. */
export function resolveFrame(layer: LayerItem, at: Date): ResolvedFrame | null {
  const best = nearestFrame(layer, at)
  if (!best) return null
  const tolerance = layer.staleness_tolerance_seconds
  // A layer that did not declare a tolerance does not get an assumed one.
  if (typeof tolerance !== 'number' || Math.abs(best.offsetSeconds) > tolerance) return null
  return best
}

/** The published frame closest to `at`, with no tolerance applied. Used by
 *  the drawer and ribbon to say how far away the nearest evidence is, and by
 *  the fallback resolver below — never drawn without its disclosure. */
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

function asFrame(time: string, targetMs: number): ResolvedFrame {
  return { time, offsetSeconds: Math.round((new Date(time).getTime() - targetMs) / 1000) }
}

/** The latest published frame at or before `at`, or null when none is. */
export function previousFrame(layer: LayerItem, at: Date): ResolvedFrame | null {
  const target = at.getTime()
  let best: { time: string; stamp: number } | null = null
  for (const time of layer.times ?? []) {
    const stamp = new Date(time).getTime()
    if (Number.isNaN(stamp) || stamp > target) continue
    if (!best || stamp > best.stamp) best = { time, stamp }
  }
  return best ? asFrame(best.time, target) : null
}

/** The earliest published frame at or after `at`, or null when none is. */
export function nextFrame(layer: LayerItem, at: Date): ResolvedFrame | null {
  const target = at.getTime()
  let best: { time: string; stamp: number } | null = null
  for (const time of layer.times ?? []) {
    const stamp = new Date(time).getTime()
    if (Number.isNaN(stamp) || stamp < target) continue
    if (!best || stamp < best.stamp) best = { time, stamp }
  }
  return best ? asFrame(best.time, target) : null
}

/** What one layer resolves to for a requested instant, under the
 *  owner-approved fallback rules (change frame-fallback-and-viewport-layout).
 *
 *  `exact` is the quiet case: the nearest frame inside the layer's declared
 *  tolerance, drawn as before. Beyond the tolerance the layer falls back —
 *  previous-only for observed groups, and never for an observed instant after
 *  the session reference; nearest either way for forecast groups — and every
 *  fallback is `snapped`, which the map MUST disclose visibly. `blend` is the
 *  opt-in display composite of a forecast layer's two neighbouring frames;
 *  it exists only for imagery and is display derivation, never evidence.
 *  `none` names why nothing may be drawn, keeping the nearest frame so the
 *  reader can still jump to the evidence. */
export type FrameResolution =
  | { kind: 'exact'; frame: ResolvedFrame }
  | { kind: 'snapped'; frame: ResolvedFrame; direction: 'previous' | 'nearest' }
  | { kind: 'blend'; previous: ResolvedFrame; next: ResolvedFrame; fraction: number }
  | { kind: 'none'; reason: string; nearest: ResolvedFrame | null }

/** Groups whose frames are observations or issuances: falling forward would
 *  show evidence of something that had not yet happened at the requested
 *  instant. An undeclared group fails toward the stricter rule. */
function isObservedGroup(layer: LayerItem): boolean {
  const group = layerGroup(layer)
  return group === 'satellite' || group === 'observation' || group === 'alert' || group === 'unknown'
}

/** The `layer.frames[]` entry declaring `time`'s run, or undefined when the
 *  layer carries no `frames[]` at all (an older API). */
function frameEntry(layer: LayerItem, time: string): import('./types').LayerFrame | undefined {
  return layer.frames?.find((frame) => frame.valid_time === time)
}

/** Whether a previous/next pair may be interpolated for display (task 4.3):
 *  refused only when BOTH frames declare a non-null `run_time` and the two
 *  differ — a short cycle's join, which is evidence from two runs and never
 *  drawn as one continuous series. Either side unknown (`null`, or no
 *  `frames[]` published at all) does not refuse: there is nothing to compare
 *  and every existing frame-fallback scenario stays exactly as it was. */
function sameRunOrUnknown(layer: LayerItem, previousTime: string, nextTime: string): boolean {
  const previousRun = frameEntry(layer, previousTime)?.run_time ?? null
  const nextRun = frameEntry(layer, nextTime)?.run_time ?? null
  if (previousRun === null || nextRun === null) return true
  return previousRun === nextRun
}

export function resolveLayerFrame(layer: LayerItem, at: Date, opts: { interpolate: boolean; reference: Date }): FrameResolution {
  if ((layer.times?.length ?? 0) === 0) return { kind: 'none', reason: 'this layer published no frames', nearest: null }
  const observed = isObservedGroup(layer)
  // A forecast layer under the display-interpolation setting composites its
  // two neighbouring frames whenever the instant sits strictly between them —
  // including inside the tolerance, where the fraction is simply near an end
  // — but never across a run change: two frames from different runs are two
  // pieces of evidence, and the disclosed nearest frame is drawn instead.
  if (opts.interpolate && !observed) {
    const previous = previousFrame(layer, at)
    const next = nextFrame(layer, at)
    if (previous && next && previous.time !== next.time && sameRunOrUnknown(layer, previous.time, next.time)) {
      const prevMs = new Date(previous.time).getTime()
      const nextMs = new Date(next.time).getTime()
      return { kind: 'blend', previous, next, fraction: (at.getTime() - prevMs) / (nextMs - prevMs) }
    }
  }
  const exact = resolveFrame(layer, at)
  if (exact) return { kind: 'exact', frame: exact }
  if (observed) {
    // The tolerance check above keeps its published meaning even a hair past
    // the reference; only the fallback path refuses future instants.
    if (at.getTime() > opts.reference.getTime()) {
      return { kind: 'none', reason: 'observed imagery has no frames for future instants', nearest: nearestFrame(layer, at) }
    }
    const previous = previousFrame(layer, at)
    if (!previous) return { kind: 'none', reason: 'no earlier frame exists in this window', nearest: nearestFrame(layer, at) }
    return { kind: 'snapped', frame: previous, direction: 'previous' }
  }
  const nearest = nearestFrame(layer, at)
  if (!nearest) return { kind: 'none', reason: 'this layer published no readable frames', nearest: null }
  return { kind: 'snapped', frame: nearest, direction: 'nearest' }
}

/** The frames a resolution permits drawing: none, one, or a blend pair. */
export function drawableFrames(resolution: FrameResolution): ResolvedFrame[] {
  if (resolution.kind === 'exact' || resolution.kind === 'snapped') return [resolution.frame]
  if (resolution.kind === 'blend') return [resolution.previous, resolution.next]
  return []
}

/** A time on the St. John's clock, for disclosure sentences. */
export function stJohnsTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-CA', { timeZone: 'America/St_Johns', hour: '2-digit', minute: '2-digit' })
}

/** A time in Newfoundland local clock, Unknown when absent or unreadable. */
export function nlTime(iso: string | null): string {
  if (!iso) return 'Unknown'
  const stamp = new Date(iso)
  if (Number.isNaN(stamp.getTime())) return 'Unknown'
  return stamp.toLocaleTimeString('en-CA', { timeZone: 'America/St_Johns', hour: '2-digit', minute: '2-digit' })
}

/** One decimal for display, and nothing else changed. Presentational only —
 *  the retrieved value is what travels in provenance — and it deliberately
 *  does not collapse null, because "no value was returned" must never read
 *  as a number. */
export function reading(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

/** The one disclosure sentence for a resolution, reused verbatim by the
 *  on-map note, the drawer row and the text alternative so the three can
 *  never disagree. Exact resolutions return null: they carry no note. */
export function describeResolution(resolution: FrameResolution): string | null {
  if (resolution.kind === 'exact') return null
  if (resolution.kind === 'snapped') {
    return `showing ${stJohnsTime(resolution.frame.time)} NT (${describeOffset(resolution.frame.offsetSeconds)} than the selected time)`
  }
  if (resolution.kind === 'blend') {
    return `display compositing of the ${stJohnsTime(resolution.previous.time)} and ${stJohnsTime(resolution.next.time)} NT frames — display only, not evidence`
  }
  return `not shown — ${resolution.reason}`
}

/** Sorted unique epoch-ms instants of every visible layer's published frames
 *  inside the window: the axis the scrubber snaps onto when display
 *  interpolation is off. Empty when nothing is active or nothing published. */
export function unionFrameInstants(layers: LayerItem[], selections: Array<{ id: string; visible: boolean }>, windowStartMs: number, windowEndMs: number): number[] {
  const visible = new Set(selections.filter((entry) => entry.visible).map((entry) => entry.id))
  const instants = new Set<number>()
  for (const layer of layers) {
    if (!visible.has(layer.id)) continue
    for (const time of layer.times ?? []) {
      const stamp = new Date(time).getTime()
      if (!Number.isNaN(stamp) && stamp >= windowStartMs && stamp <= windowEndMs) instants.add(stamp)
    }
  }
  return [...instants].sort((a, b) => a - b)
}

/** The tick colours for published-frame markers on the timeline. Chosen to
 *  stay apart on the dock's dark ground and in the light theme, and to avoid
 *  the orange the selection thumb already owns. */
export const LAYER_TICK_COLORS = ['#4fc3f7', '#7ed957', '#ff6f91', '#c792ea', '#ffd166', '#4dd0c4', '#ff9f6e', '#9fa8da'] as const

/** A layer's marker colour: its position in the retrieved layer list into
 *  the palette. Stable under toggling - turning one layer off never
 *  recolours another - and stable across renders, since the order is the
 *  API's. An unknown layer takes the first colour rather than none. */
export function layerTickColor(layerId: string, layers: LayerItem[]): string {
  const index = layers.findIndex((layer) => layer.id === layerId)
  return LAYER_TICK_COLORS[(index < 0 ? 0 : index) % LAYER_TICK_COLORS.length]
}

export interface FrameMarker {
  /** The published instant, epoch ms. */
  ms: number
  time: string
  /** Every active layer publishing this instant, in retrieved layer order.
   *  `runTime` is `layer.frames[]`'s declared run time for this instant, when
   *  the layer published one — `undefined` when the layer carries no
   *  `frames[]` at all (an older API), `null` when it declared the frame's
   *  run time as unknown. Read by the rail for the run label and the
   *  run-change marker (task 4.3). */
  layers: Array<{ id: string; title: string; color: string; runTime?: string | null }>
}

export interface FrameMarkers {
  markers: FrameMarker[]
  /** Titles of active layers that published no readable frame axis. Named
   *  out loud rather than left silently absent from the rail. */
  axisless: string[]
}

/** The published frames of the active visible layers inside the window,
 *  grouped by instant: one marker per instant, carrying every layer that
 *  published it, so a frame two layers share is one target rather than two
 *  ticks on top of each other.
 *
 *  Purely a view of what `/layers` returned. Nothing here invents an
 *  instant: a layer with no `times` contributes no ticks and is reported in
 *  `axisless` instead. */
export function frameMarkers(
  layers: LayerItem[],
  selections: Array<{ id: string; visible: boolean }>,
  windowStartMs: number,
  windowEndMs: number,
): FrameMarkers {
  const visible = new Set(selections.filter((entry) => entry.visible).map((entry) => entry.id))
  const byInstant = new Map<number, FrameMarker>()
  const axisless: string[] = []
  for (const layer of layers) {
    if (!visible.has(layer.id)) continue
    const color = layerTickColor(layer.id, layers)
    let published = 0
    for (const time of layer.times ?? []) {
      const stamp = new Date(time).getTime()
      if (Number.isNaN(stamp)) continue
      published += 1
      if (stamp < windowStartMs || stamp > windowEndMs) continue
      // `undefined` when the layer publishes no `frames[]` at all (an older
      // API); `null` when it declared this frame's run as unknown. The two
      // are kept apart so a run-change marker is never drawn from a layer
      // that never said anything about runs.
      const runTime = layer.frames ? (frameEntry(layer, time)?.run_time ?? null) : undefined
      const existing = byInstant.get(stamp)
      if (existing) existing.layers.push({ id: layer.id, title: layer.title, color, runTime })
      else byInstant.set(stamp, { ms: stamp, time, layers: [{ id: layer.id, title: layer.title, color, runTime }] })
    }
    if (published === 0) axisless.push(layer.title)
  }
  return { markers: [...byInstant.values()].sort((a, b) => a.ms - b.ms), axisless }
}

/** The member of `instants` closest to `rawMs`, ties resolving earlier.
 *  Identity when the list is empty, so a caller never invents an instant. */
export function snapInstant(instants: number[], rawMs: number): number {
  let best: number | null = null
  for (const instant of instants) {
    if (best === null || Math.abs(instant - rawMs) < Math.abs(best - rawMs)) best = instant
  }
  return best ?? rawMs
}

/** The neighbouring member of `instants` in `direction`, for keyboard
 *  movement across the snap axis. Stays put at the ends. */
export function stepInstant(instants: number[], currentMs: number, direction: 1 | -1): number {
  if (instants.length === 0) return currentMs
  if (direction === 1) {
    for (const instant of instants) if (instant > currentMs) return instant
    return currentMs
  }
  for (let index = instants.length - 1; index >= 0; index -= 1) {
    if (instants[index] < currentMs) return instants[index]
  }
  return currentMs
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
