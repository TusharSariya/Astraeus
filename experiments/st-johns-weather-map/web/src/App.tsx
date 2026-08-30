import { useCallback, useEffect, useMemo, useState } from 'react'
import { ALL_CLOUD_BANDS, type CloudBand, type CloudBands, cloudBandOf, describeOffset, filterCloudLayers, groupLayers, loadCatalog, loadLayers, loadPoint, loadProfile, loadSourceStatus, loadStory, loadTimeline, pointProductFor, resolveFrame } from './api'
import { stationCoverage, stations, unavailableSnapshot } from './fixtures'
import { MapPanel, type MapEvidenceRow } from './MapPanel'
import type {
  AppMode, CatalogSource, CloudLayerReading, DataSource, EvidenceSnapshot, FallbackMode, FieldAttribution, FieldDataMode,
  LayerItem, LayerSelection, LocationPoint, ProfileResponse, ResolvedFrame, SourceStatusItem, StoryStep, TimelineResponse,
} from './types'

/** The evidence window, in minutes from the session reference instant. */
const BACK_MINUTES = 3 * 60
const FORWARD_MINUTES = 24 * 60

/** Scrub resolution. Five minutes is finer than the fastest layer published
 *  (radar, every six), so no layer's frames are unreachable between steps. */
const SCRUB_STEP_MINUTES = 5

/** Text alternative for a coverage row, so the ribbon is not graphics-only. */
function coverageDescription(layer: LayerItem, frameCount: number, current: ResolvedFrame | null): string {
  if (frameCount === 0) return `${layer.title} published no frames in this window.`
  const where = current ? `the selected time resolves to a frame ${describeOffset(current.offsetSeconds)}` : 'the selected time has no frame within this layer\u2019s tolerance'
  return `${layer.title}: ${frameCount} published frame${frameCount === 1 ? '' : 's'}; ${where}.`
}

/** The scrubber offset in words, at the minute. A jump to a radar frame lands
 *  on -10 min, and a badge that rounded that to "Now (0h)" claimed an instant
 *  the reader had not chosen. Whole hours keep the short "+3h" form. */
function describeScrubOffset(minutes: number): string {
  const sign = minutes < 0 ? '-' : '+'
  const magnitude = Math.abs(minutes)
  const hours = Math.floor(magnitude / 60)
  const rest = magnitude % 60
  if (rest === 0) return `${sign}${hours}h`
  if (hours === 0) return `${sign}${rest} min`
  return `${sign}${hours} h ${rest} min`
}

const badgeCopy: Record<FallbackMode, string> = {
  consensus: 'Experimental consensus',
  hrdps: 'HRDPS primary · consensus unavailable',
  rdps: 'RDPS fallback',
  unavailable: 'Forecast unavailable · evidence only',
}

const dataPathCopy: Record<DataSource, string> = {
  loading: 'Checking API',
  live: 'Live API',
  mixed: 'Mixed live and fixture',
  fixture: 'Development fixture',
  unavailable: 'Unavailable',
}

const bannerCopy: Record<Exclude<DataSource, 'live'>, string> = {
  loading: 'CHECKING API · NO EVIDENCE SHOWN YET',
  mixed: 'MIXED EVIDENCE · SOME FIELDS ARE NOT LIVE',
  fixture: 'DEVELOPMENT FIXTURE · NOT LIVE EVIDENCE',
  unavailable: 'NO LIVE EVIDENCE RETRIEVED',
}

function ModeChip({ mode }: { mode: FieldDataMode | undefined }) {
  if (!mode || mode === 'live') return null
  const copy = mode === 'fixture' ? 'fixture value' : mode === 'mixed' ? 'mixed provenance' : 'not declared live'
  return <em className={`mode-chip ${mode}`}>{copy}</em>
}

/** "derived · MetPy" beside any value the API says it computed rather than
 *  read, with the API's own derivation sentence as the tooltip. */
function derivedChip(attribution: FieldAttribution | undefined): string | null {
  if (!attribution?.derivation) return null
  return /metpy/i.test(attribution.derivation) ? 'derived \u00b7 MetPy' : 'derived'
}

/** Who produced a shown number. Rendered only beside a value that exists: an
 *  Unknown has no source to credit, and the tag must not suggest one. */
function SourceTag({ attribution }: { attribution: FieldAttribution | undefined }) {
  if (!attribution) return null
  return <em className="source-tag" title={`${attribution.provider} \u00b7 ${attribution.product ?? 'product not named'}`}>{attribution.sourceId ?? attribution.product ?? attribution.provider}</em>
}

function Metric({ label, value, detail, detailTitle, mode, source, controls }: { label: string; value: string; detail?: string; detailTitle?: string; mode?: FieldDataMode; source?: FieldAttribution; controls?: React.ReactNode }) {
  return (
    <article className="metric">
      <span>{label}</span>
      {controls}
      <strong>{value}</strong>
      {detail && <small title={detailTitle}>{detail}</small>}
      <span className="metric-tags"><SourceTag attribution={source} /><ModeChip mode={mode} /></span>
    </article>
  )
}

function FieldControl({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field-control"><span>{label}</span>{children}</label>
}

/** Options a selector can honestly offer. An empty list stays disabled and says why. */
function EvidenceSelect({ options, value, onChange, emptyReason, label }: {
  options: Array<{ value: string; label: string; disabled?: boolean; title?: string }>
  value: string
  onChange: (value: string) => void
  emptyReason: string
  label: string
}) {
  if (options.length === 0) return <select disabled aria-label={label}><option>{emptyReason}</option></select>
  return (
    <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled} title={option.title}>{option.label}</option>)}
    </select>
  )
}

/** Verified against the running API's OpenAPI document: `/point` accepts
 *  `latitude`, `longitude`, `valid_time`, `product` and three fixture-mode
 *  freshness switches; `/profile` accepts `latitude`, `longitude` and
 *  `valid_time`. Neither takes a run, member or level, and an unrecognised
 *  query parameter is ignored with a 200 rather than rejected — so a request
 *  carrying one would look successful and come back unnarrowed. */
const PROVENANCE_ONLY_REASON = 'Read-only: the point request has no run, member or level parameter, so choosing here could not change what is fetched. These are the values the response reported.'

/** A field the API publishes in provenance but has no request parameter for.
 *  It reads out what came back and stays disabled, because a control that
 *  accepts a choice and then discards it is a lie about what was requested —
 *  which is the one thing this interface must never do. */
function ProvenanceReadout({ label, values, emptyReason }: {
  label: string
  values: string[]
  emptyReason: string
}) {
  return (
    <>
      <select disabled aria-label={label} aria-describedby={`${label.toLowerCase()}-readonly`}>
        {values.length === 0 ? <option>{emptyReason}</option> : values.map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
      <small className="control-readonly" id={`${label.toLowerCase()}-readonly`}>{PROVENANCE_ONLY_REASON}</small>
    </>
  )
}

/** One decimal for display, and nothing else changed.
 *
 *  Observation sources report already-rounded values, so this was invisible
 *  until the gridded models published: a sampled HRDPS cell carries the float
 *  it was stored as, and 17.27401733398437 rendered raw overflowed the panel it
 *  sits in. The rounding is presentational only - the retrieved value is what
 *  travels in provenance and what /point returns - and it deliberately does not
 *  collapse null, because "no value was returned" must never read as a number.
 */
function reading(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter((value) => value.trim().length > 0))]
}

/** One reported cloud layer in words: the cover code as the API served it and
 *  the base above ground in metres, each Unknown when it did not come back.
 *  Layers are shown in provider order and never sorted into strata. */
function cloudLayerText(layer: CloudLayerReading): string {
  const cover = layer.coverCode ?? (layer.coverPct === null ? 'cover Unknown' : `${Math.round(layer.coverPct)}%`)
  const base = layer.baseM === null ? 'base Unknown' : `${Math.round(layer.baseM)} m`
  return `${cover} · ${base}`
}

function cloudLayersText(layers: CloudLayerReading[]): string | null {
  if (layers.length === 0) return null
  return layers.map(cloudLayerText).join('  |  ')
}

/** The metric's own rendering of the layers under the band filter. A layer
 *  with no base cannot be placed in a band, is never hidden, and says so;
 *  the text alternative (`evidenceRows`) keeps the plain wording. */
function cloudLayersMetricText(layers: CloudLayerReading[]): string | null {
  if (layers.length === 0) return null
  return layers.map((layer) => (cloudBandOf(layer) === null && layer.baseM === null ? `${cloudLayerText(layer)} — not filterable` : cloudLayerText(layer))).join('  |  ')
}

const CLOUD_LAYERS_DETAIL = 'As reported, in provider order (cover code · base AGL); not bucketed into strata'

/** The band buttons' labels, each printing the aviation-convention bounds it
 *  filters by. The ceilings are the metres the API declares (1,981.2 m and
 *  6,096 m); the feet are the convention's own words. */
const CLOUD_BAND_LABELS: Record<CloudBand, string> = {
  low: 'Low · <6,500 ft',
  middle: 'Middle · 6,500–20,000 ft',
  high: 'High · ≥20,000 ft',
}
const CLOUD_BAND_ORDER: CloudBand[] = ['low', 'middle', 'high']

/** A view filter over the as-reported layers, and only that: it hides rows
 *  whose declared base falls outside the bands left on, computes nothing per
 *  band, and never hides a layer with no base. The strata metric beside it
 *  is untouched by it. */
function CloudBandFilter({ bands, onChange }: { bands: CloudBands; onChange: (next: CloudBands) => void }) {
  return (
    <div className="cloud-bands" role="group" aria-label="Cloud layer bands">
      {CLOUD_BAND_ORDER.map((band) => (
        <button
          key={band}
          type="button"
          aria-pressed={bands[band]}
          className={bands[band] ? 'on' : 'off'}
          title="View filter by reported base height. Hides layers outside the bands left on; nothing is computed per band."
          onClick={() => onChange({ ...bands, [band]: !bands[band] })}
        >
          {CLOUD_BAND_LABELS[band]}
        </button>
      ))}
    </div>
  )
}

const fogCopy: Record<EvidenceSnapshot['fogRisk'], string> = {
  evidence_present: 'Fog evidence present',
  not_indicated: 'Fog not indicated by available evidence',
  unknown: 'Fog evidence unknown',
}

/** The accessible name of one story card. Every reading is named with its unit
 *  and an absent one is spoken as Unknown, so the card carries the same evidence
 *  by ear as by eye — a silently skipped field would read as a value not worth
 *  mentioning rather than one that was never returned. */
function storyCardLabel(item: StoryStep): string {
  const readings = [
    `temperature ${reading(item.temperatureC) === null ? 'unknown' : `${reading(item.temperatureC)} °C`}`,
    `dew point ${reading(item.dewPointC) === null ? 'unknown' : `${reading(item.dewPointC)} °C`}`,
    `precipitation probability ${item.precipPct === null ? 'unknown' : `${item.precipPct}%`}`,
    `wind ${item.windKmh === null ? 'unknown' : `${item.windKmh} km/h`}`,
  ]
  return `Scrub to ${item.time}. ${item.label}. ${readings.join(', ')}.`
}

/** The source suffix for a text-alternative row, or nothing for an Unknown. */
function sourced(snapshot: EvidenceSnapshot, field: string): string {
  const source = snapshot.fieldSources[field]
  return source ? ` (${source.sourceId ?? source.product ?? source.provider})` : ''
}

function evidenceRows(snapshot: EvidenceSnapshot, humidityGap: string): MapEvidenceRow[] {
  const direction = snapshot.windDirectionDeg === null ? 'direction Unknown' : `from ${Math.round(snapshot.windDirectionDeg)}°`
  return [
    { label: 'Temperature', value: reading(snapshot.temperatureC) === null ? 'Unknown — no temperature value was returned' : `${reading(snapshot.temperatureC)} °C${sourced(snapshot, 'temperature')}` },
    { label: 'Dew point', value: reading(snapshot.dewPointC) === null ? 'Unknown — no dew point value was returned' : `${reading(snapshot.dewPointC)} °C${sourced(snapshot, 'dew_point')}` },
    { label: 'Humidity', value: snapshot.relativeHumidityPct === null ? 'Unknown — no relative humidity value was returned' : `${Math.round(snapshot.relativeHumidityPct)}% · ${humidityGap}${sourced(snapshot, 'relative_humidity')}` },
    { label: 'Wind and gust', value: snapshot.windKmh === null && snapshot.gustKmh === null ? 'Unknown — no wind value was returned' : `${snapshot.windKmh ?? 'unknown'} / ${snapshot.gustKmh ?? 'unknown'} km/h, ${direction}${sourced(snapshot, 'wind_speed')}` },
    { label: 'Pressure', value: snapshot.pressureHpa === null ? 'Unknown — no mean sea level pressure value was returned' : `${snapshot.pressureHpa.toFixed(1)} hPa${sourced(snapshot, 'mean_sea_level_pressure')}` },
    { label: 'Total cloud', value: snapshot.totalCloudPct === null ? 'Unknown — no total cloud value was returned' : `${Math.round(snapshot.totalCloudPct)}%${sourced(snapshot, 'total_cloud')}` },
    { label: 'Cloud layers', value: cloudLayersText(snapshot.cloudLayers) === null ? 'Unknown — no cloud layer was returned' : `${cloudLayersText(snapshot.cloudLayers)}, as reported and not bucketed into strata${sourced(snapshot, 'cloud_layer_1_cover_code')}` },
    { label: 'Visibility', value: snapshot.visibilityKm === null ? 'Unknown — no visibility value in a recognised unit was returned' : `${snapshot.visibilityKm.toFixed(1)} km${sourced(snapshot, 'visibility')}` },
    { label: 'Fog', value: `${fogCopy[snapshot.fogRisk]}${snapshot.fogRisk === 'unknown' ? '' : sourced(snapshot, 'fog_state')}` },
    { label: 'Valid time', value: snapshot.validAt ?? 'Unknown — no valid time was returned' },
  ]
}

export default function App() {
  const [mode, setMode] = useState<AppMode>('simple')
  const [location, setLocation] = useState<LocationPoint>(stations[0])
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot>(unavailableSnapshot)
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [offsetMinutes, setOffsetMinutes] = useState<number>(0)
  // One reference instant for the whole session. Recomputing `now` on every
  // render would slide every layer's resolved frame under the reader.
  const [reference] = useState<Date>(() => new Date())
  const [dataSource, setDataSource] = useState<DataSource>('loading')
  const [sourceError, setSourceError] = useState('')
  const [locationNotice, setLocationNotice] = useState('Location stays off until you ask for it.')
  const [coordinateLat, setCoordinateLat] = useState('47.6186')
  const [coordinateLon, setCoordinateLon] = useState('-52.7519')
  const [coordinateError, setCoordinateError] = useState('')
  const [catalog, setCatalog] = useState<CatalogSource[]>([])
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [layers, setLayers] = useState<LayerItem[]>([])
  const [layerNotices, setLayerNotices] = useState<string[]>([])
  const [layersError, setLayersError] = useState<string | null>(null)
  const [layersLoading, setLayersLoading] = useState(true)
  const [selections, setSelections] = useState<LayerSelection[]>([])
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null)
  const [timelineNotice, setTimelineNotice] = useState<string | null>(null)
  const [story, setStory] = useState<StoryStep[]>([])
  const [provider, setProvider] = useState('')
  const [sourceStatuses, setSourceStatuses] = useState<SourceStatusItem[] | null>(null)
  const [sourceStatusError, setSourceStatusError] = useState<string | null>(null)
  // All three bands on = the full as-reported list. Local view state only; it
  // reaches no request and derives no value.
  const [cloudBands, setCloudBands] = useState<CloudBands>(ALL_CLOUD_BANDS)

  /** The instant the reader is asking about. Minute resolution, because radar
   *  publishes every six minutes and lightning every ten: rounding to the hour
   *  made those layers unscrubbable at the cadence they actually have. */
  const validTime = useMemo(() => new Date(reference.getTime() + offsetMinutes * 60_000), [reference, offsetMinutes])
  const scrubOffset = useMemo(() => describeScrubOffset(offsetMinutes), [offsetMinutes])
  const windowStartMs = useMemo(() => reference.getTime() - BACK_MINUTES * 60_000, [reference])
  const windowEndMs = useMemo(() => reference.getTime() + FORWARD_MINUTES * 60_000, [reference])

  const validTimeIso = useMemo(() => {
    if (offsetMinutes === 0) return undefined
    return validTime.toISOString().replace(/\.\d{3}Z$/, 'Z')
  }, [offsetMinutes, validTime])

  const toggleLayer = useCallback((layerId: string) => {
    setSelections((previous) => previous.some((entry) => entry.id === layerId)
      ? previous.filter((entry) => entry.id !== layerId)
      : [...previous, { id: layerId, visible: true, opacity: 0.85 }])
  }, [])

  const setLayerOpacity = useCallback((layerId: string, opacity: number) => {
    setSelections((previous) => previous.map((entry) => (entry.id === layerId ? { ...entry, opacity } : entry)))
  }, [])

  // A layer row asked for the scrubber to go to its nearest frame. The offset
  // is kept at the minute so a 6-minute radar sweep is reachable exactly;
  // outside the window it is clamped, and the row will say so in its own words.
  const jumpToTime = useCallback((date: Date) => {
    const minutes = Math.round((date.getTime() - reference.getTime()) / 60_000)
    setOffsetMinutes(Math.max(-BACK_MINUTES, Math.min(FORWARD_MINUTES, minutes)))
  }, [reference])

  useEffect(() => {
    const controller = new AbortController()
    loadCatalog(controller.signal).then((result) => {
      setCatalog(result.sources)
      setCatalogError(result.error)
    }).catch(() => undefined)
    loadLayers(controller.signal).then((result) => {
      setLayers(result.layers)
      setLayerNotices(result.notices)
      setLayersError(result.error)
      setLayersLoading(false)
    }).catch(() => undefined)
    // The timeline names which hours carry evidence, so it gets the same
    // fail-closed reading as every other fetch: an unavailable one is kept, but
    // its hours are not presented as coverage and the reason is shown.
    loadTimeline(controller.signal).then((result) => {
      setTimeline(result.timeline)
      setTimelineNotice(result.error)
    }).catch(() => undefined)
    // Station markers are drawn from a hardcoded picker list, so this is the
    // only thing that can say whether anything has actually been ingested for
    // one. Until it answers, every station reads as coverage unknown.
    loadSourceStatus(controller.signal).then((result) => {
      setSourceStatuses(result.statuses)
      setSourceStatusError(result.error)
    }).catch(() => undefined)
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setDataSource('loading')
    setSourceError('')
    setSnapshot(unavailableSnapshot)

    loadPoint(location, validTimeIso, selectedProduct ?? undefined, controller.signal).then((result) => {
      setSnapshot(result.snapshot)
      setDataSource(result.source)
      setSourceError(result.error ?? '')
    }).catch(() => undefined)

    if (mode === 'expert') {
      loadProfile(location, validTimeIso, controller.signal).then((prof) => {
        setProfile(prof)
      }).catch(() => undefined)
    }

    return () => controller.abort()
  }, [location, validTimeIso, mode, selectedProduct])

  // The story is assembled from the hours the timeline says are published, one
  // real /point response per card. Hours that return nothing are simply absent;
  // nothing is interpolated between the cards that remain.
  useEffect(() => {
    const controller = new AbortController()
    setStory([])
    if (!timeline) return () => controller.abort()
    loadStory(location, timeline, selectedProduct ?? undefined, controller.signal)
      .then((steps) => setStory(steps))
      .catch(() => undefined)
    return () => controller.abort()
  }, [location, timeline, selectedProduct])

  const humidityGap = useMemo(() => snapshot.temperatureC !== null && snapshot.dewPointC !== null
    ? `${(snapshot.temperatureC - snapshot.dewPointC).toFixed(1)}° dew-point depression`
    : 'Unknown', [snapshot])

  // Only sources `/point` will accept as a `product` are offered. The old
  // predicate was `state === 'active'`, which the registry never emits by
  // design, so every model button was permanently dead beside a fully
  // implemented endpoint. A source the endpoint has no parameter value for is
  // not rendered as a disabled affordance either; it is simply not a control.
  const forecastSources = useMemo(
    () => catalog.filter((source) => source.forecast_horizon !== 'observation' && pointProductFor(source) !== null),
    [catalog],
  )
  const providers = useMemo(() => unique(catalog.map((source) => source.producer)), [catalog])
  /** The model row grouped by producer, producers in catalogue order and each
   *  producer's sources in catalogue order. BLEND stays first and ungrouped. */
  const forecastSourcesByProducer = useMemo(() => {
    const groups: Array<{ producer: string; sources: CatalogSource[] }> = []
    forecastSources.forEach((source) => {
      const group = groups.find((entry) => entry.producer === source.producer)
      if (group) group.sources.push(source)
      else groups.push({ producer: source.producer, sources: [source] })
    })
    return groups
  }, [forecastSources])
  const productSources = useMemo(() => (provider ? forecastSources.filter((source) => source.producer === provider) : forecastSources), [forecastSources, provider])
  const runs = useMemo(() => unique(snapshot.provenance.map((row) => row.run)), [snapshot])
  const members = useMemo(() => unique(snapshot.provenance.map((row) => row.member ?? '')), [snapshot])
  const levels = useMemo(() => unique(snapshot.provenance.map((row) => row.level)), [snapshot])
  const mapEvidence = useMemo(() => evidenceRows(snapshot, humidityGap), [snapshot, humidityGap])
  const shownCloudLayers = useMemo(() => filterCloudLayers(snapshot.cloudLayers, cloudBands), [snapshot.cloudLayers, cloudBands])
  const anyBandOff = !cloudBands.low || !cloudBands.middle || !cloudBands.high
  const stationOptions = useMemo(() => stations.map((station) => ({ station, coverage: stationCoverage(station, sourceStatuses) })), [sourceStatuses])
  /** The picker's groups, in the words the marker and the text alternative
   *  use. A station whose coverage could not be read is neither live nor a
   *  bare place to query, so it gets its own group rather than either claim. */
  const stationGroups = useMemo(() => {
    const groups: Array<{ label: string; entries: typeof stationOptions }> = [
      { label: 'Live ingested source', entries: stationOptions.filter(({ coverage }) => coverage.state === 'live') },
      { label: 'Live-source coverage unknown', entries: stationOptions.filter(({ coverage }) => coverage.state === 'unknown') },
      { label: 'No ingested source (place to query)', entries: stationOptions.filter(({ coverage }) => coverage.state !== 'live' && coverage.state !== 'unknown') },
    ]
    return groups.filter(({ entries }) => entries.length > 0)
  }, [stationOptions])
  const groupedLayers = useMemo(() => groupLayers(layers), [layers])
  const stationCoverageNotice = useMemo(() => {
    if (sourceStatusError) return `Live-source coverage unknown: ${sourceStatusError}. No station is being shown as live.`
    if (sourceStatuses === null) return 'Checking which stations have a live ingested source…'
    const live = stationOptions.filter(({ coverage }) => coverage.state === 'live').length
    return `A live ingested source stands behind ${live} of ${stationOptions.length} stations; the rest are places you can query, not stations reporting to this deployment.`
  }, [sourceStatusError, sourceStatuses, stationOptions])

  // The header names the product the response answered with, in the response's
  // own badge. It used to be inferred from the first temperature field, which
  // on the blended response is the METAR observation, so it contradicted the
  // API's own `selection.badge`. With no badge yet (loading, outage) the mode
  // label stands in, and a requested product is shown as requested, not answered.
  const selectionLabel = snapshot.selectionBadge
    ?? (selectedProduct === null ? badgeCopy[snapshot.mode] : `${selectedProduct} requested \u00b7 ${badgeCopy[snapshot.mode]}`)

  /** What this deployment has actually ingested for a model, from
   *  `/sources/status` and `/timeline`. The registry's cadence and horizon
   *  prose is provider documentation and moves to the tooltip, labelled so. */
  const coverageOf = useCallback((source: CatalogSource): { text: string; unavailable: boolean } => {
    if (sourceStatuses === null) return { text: sourceStatusError ? 'ingestion status unreadable' : 'checking ingestion\u2026', unavailable: false }
    const status = sourceStatuses.find((row) => row.source_id === source.id)
    if (!status || status.data_mode !== 'live') return { text: 'nothing ingested', unavailable: true }
    if (!timeline || timeline.data_mode === 'unavailable') return { text: 'ingested; published hours unavailable', unavailable: false }
    const product = (pointProductFor(source) ?? '').toLowerCase()
    const hours = timeline.items
      .filter((item) => item.available_products.some((token) => token === source.id || token.toLowerCase() === product))
      .map((item) => new Date(item.valid_time_utc).getTime())
      .filter((stamp) => !Number.isNaN(stamp))
    if (hours.length === 0) return { text: 'ingested; no hour in this window', unavailable: false }
    const lead = Math.round((Math.max(...hours) - reference.getTime()) / 3600_000)
    return { text: `covers to ${lead >= 0 ? '+' : ''}${lead} h`, unavailable: false }
  }, [sourceStatuses, sourceStatusError, timeline, reference])

  const requestGps = () => {
    if (!navigator.geolocation) {
      setLocationNotice(`Location is not available in this browser. ${location.name} remains selected. Use coordinates, a station, or the map.`)
      return
    }
    setLocationNotice('Waiting for browser permission…')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocation({ id: 'gps', name: 'Your selected position', latitude: coords.latitude, longitude: coords.longitude, kind: 'map' })
        setLocationNotice('Location used for this session only. It was not sent until you approved.')
      },
      (error) => {
        const retained = `${location.name} remains selected.`
        if (error.code === error.PERMISSION_DENIED) setLocationNotice(`Location permission was denied. ${retained} Use coordinates, a station, or the map.`)
        else if (error.code === error.POSITION_UNAVAILABLE) setLocationNotice(`Your position could not be determined. ${retained} Use coordinates, a station, or the map.`)
        else setLocationNotice(`The location request timed out. ${retained} Use coordinates, a station, or the map.`)
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    )
  }

  const submitCoordinates = (event: React.FormEvent) => {
    event.preventDefault()
    const latitude = Number(coordinateLat)
    const longitude = Number(coordinateLon)
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 || !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      setCoordinateError('Enter latitude from -90 to 90 and longitude from -180 to 180.')
      return
    }
    setCoordinateError('')
    setLocation({ id: `coordinates-${latitude}-${longitude}`, name: `Coordinates ${latitude.toFixed(3)}, ${longitude.toFixed(3)}`, latitude, longitude, kind: 'map' })
  }

  const mapField = dataSource === 'live' ? 'Response-backed evidence points'
    : dataSource === 'mixed' ? 'Mixed live and fixture evidence points'
      : dataSource === 'fixture' ? 'Development fixture evidence points'
        : dataSource === 'loading' ? 'Checking the API for evidence points'
          : 'No response-backed evidence points'

  return (
    <div className={`workbench ${dataSource === 'fixture' ? 'fixture-mode' : ''}`}>
      {dataSource !== 'live' && <div className={`fixture-watermark ${dataSource}`} role="status">{bannerCopy[dataSource]}</div>}
      <header className="masthead">
        <div className="wordmark"><span>WX//47°N</span><h1>Avalon Evidence Desk</h1></div>
        <div className="experimental"><i /> experimental · not operational guidance</div>
        <nav className="mode-switch" aria-label="Interface mode">
          <button aria-pressed={mode === 'simple'} onClick={() => setMode('simple')}>Brief</button>
          <button aria-pressed={mode === 'expert'} onClick={() => setMode('expert')}>Workbench</button>
        </nav>
      </header>

      <main>
        <section className="location-strip" aria-label="Place and data status">
          <div><span className="eyebrow">Evidence point</span><h2>{location.name}</h2><code>{location.latitude.toFixed(3)} / {location.longitude.toFixed(3)}</code></div>
          {/* A picker, not a coverage claim. Every option carries whether a live
              ingested source stands behind it, in the same words the map marker
              and the map's text alternative use. */}
          <label className="station-picker"><span>Station or buoy</span><select value={stations.some((s) => s.id === location.id) ? location.id : ''} onChange={(event) => {
            const next = stations.find((station) => station.id === event.target.value)
            if (next) setLocation(next)
          }}><option value="" disabled>Custom map point</option>{stationGroups.map(({ label, entries }) => (
            <optgroup key={label} label={label}>
              {entries.map(({ station, coverage }) => (
                <option key={station.id} value={station.id}>{station.name} — {coverage.short}</option>
              ))}
            </optgroup>
          ))}</select><small role="status">{stationCoverageNotice}</small></label>
          <div className="gps-block"><button className="locate" onClick={requestGps}>Use my location</button><small role="status">{locationNotice}</small></div>
          <form className="coordinate-entry" onSubmit={submitCoordinates} aria-label="Enter coordinates">
            <label>Latitude<input aria-label="Latitude" inputMode="decimal" value={coordinateLat} onChange={(event) => setCoordinateLat(event.target.value)} /></label>
            <label>Longitude<input aria-label="Longitude" inputMode="decimal" value={coordinateLon} onChange={(event) => setCoordinateLon(event.target.value)} /></label>
            <button type="submit">Go</button>
            {coordinateError && <small role="alert">{coordinateError}</small>}
          </form>
          <div className={`source-state ${dataSource}`}><span>Data path</span><strong>{dataPathCopy[dataSource]}</strong></div>
        </section>

        <section className="model-strip" aria-label="Forecast models">
          <span className="eyebrow">Forecast model</span>
          {/* Plain pressed buttons, not a radiogroup: a radiogroup promises
              arrow-key movement between its radios, which was never wired. */}
          <div className="model-buttons" aria-label="Select forecast model">
            <button type="button" aria-pressed={selectedProduct === null} className={selectedProduct === null ? 'active' : ''} onClick={() => setSelectedProduct(null)}>
              <span className="model-badge">BLEND</span>
              <strong>Consensus</strong>
              <small>API selection</small>
            </button>
            {forecastSourcesByProducer.map(({ producer, sources }) => (
              // One group per producer, labelled once, so the strip reads as
              // "ECCC: HRDPS RDPS REPS / NOAA: GFS" rather than a flat run of
              // cards. Still one scrolling row: the group is a flex item too.
              <div key={producer} className="model-group" role="group" aria-label={producer}>
                <span className="model-group-label">{producer}</span>
                {sources.map((source) => {
                  // Every button here names a product the endpoint accepts, so it is
                  // pressable — including one with nothing ingested, because the
                  // API's reason for having nothing is worth reading. Whether the
                  // product has an artifact covering this point and hour is the
                  // API's answer, shown below, not a prediction made here.
                  const product = pointProductFor(source) as string
                  const coverage = coverageOf(source)
                  return (
                    <button
                      key={source.id}
                      type="button"
                      aria-pressed={selectedProduct === product}
                      title={`${source.role} \u00b7 ${source.cadence} \u00b7 ${source.forecast_horizon} (provider documentation, not verified here)`}
                      className={`${selectedProduct === product ? 'active' : ''}${coverage.unavailable ? ' model-unavailable' : ''}`}
                      onClick={() => setSelectedProduct(product)}
                    >
                      <span className="model-badge">{source.producer}</span>
                      <strong>{product}</strong>
                      <small>{coverage.text}</small>
                    </button>
                  )
                })}
              </div>
            ))}
            {forecastSources.length === 0 && (
              <p className="model-empty" role="status">
                {catalogError ? `No catalog: ${catalogError}. No model can be offered.` : 'No catalogued forecast product is one the point endpoint accepts, so no model can be offered.'}
              </p>
            )}
          </div>
        </section>

        {sourceError && <p className="source-error" role="status">{sourceError}. No previous point evidence is being shown.</p>}

        <section className={`fallback-badge evidence-surface ${snapshot.mode}`} aria-label="Forecast selection">
          <span className="signal-bars" aria-hidden="true"><i /><i /><i /></span>
          <div><small>Selected forecast</small><strong>{selectionLabel}</strong></div>
          {snapshot.validAt ? <time dateTime={snapshot.validAt}>Valid {new Date(snapshot.validAt).toLocaleString('en-CA', { timeZone: 'America/St_Johns', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })}</time> : <span className="unknown-time">Valid time unknown</span>}
        </section>

        {mode === 'simple' ? (
          <div className="simple-grid">
            <MapPanel
              label="Avalon / upstream Atlantic"
              field={mapField}
              selected={location}
              onSelect={setLocation}
              validTime={validTime}
              fixtureMode={dataSource === 'fixture'}
              layers={layers}
              layersError={layersError}
              layersLoading={layersLoading}
              selections={selections}
              onToggleLayer={toggleLayer}
              onSetOpacity={setLayerOpacity}
              onJumpToTime={jumpToTime}
              layerNotices={layerNotices}
              evidence={mapEvidence}
              sourceStatuses={sourceStatuses}
            />
            <section className="conditions evidence-surface" aria-labelledby="conditions-title">
              <div className="section-head">
                <span>01</span>
                <div>
                  <small>{offsetMinutes === 0 ? 'At the evidence point' : offsetMinutes < 0 ? `Past observation (${scrubOffset})` : `Forecast horizon (${scrubOffset})`}</small>
                  <h2 id="conditions-title">{offsetMinutes === 0 ? 'Now on the headland' : offsetMinutes < 0 ? `${scrubOffset.slice(1)} ago on the headland` : `${scrubOffset} forecast on the headland`}</h2>
                </div>
              </div>
              <div className="hero-reading">
                {snapshot.temperatureC === null
                  ? <strong className="hero-unknown">Unknown</strong>
                  : <strong>{reading(snapshot.temperatureC)}<sup>°C</sup></strong>}
                <p>
                  {snapshot.temperatureC === null
                    ? 'No temperature value was returned for this point and hour.'
                    : offsetMinutes === 0 ? snapshot.precipitation : offsetMinutes < 0 ? `Past observation at ${scrubOffset}` : `Model guidance at ${scrubOffset}`}
                  {snapshot.temperatureC !== null && <><br /><SourceTag attribution={snapshot.fieldSources.temperature} /></>}
                </p>
              </div>
              <div className="metric-grid">
                <Metric
                  label="Humidity"
                  value={snapshot.relativeHumidityPct === null ? 'Unknown' : `${Math.round(snapshot.relativeHumidityPct)}%`}
                  detail={[humidityGap, derivedChip(snapshot.fieldSources.relative_humidity)].filter(Boolean).join(' \u00b7 ')}
                  detailTitle={snapshot.fieldSources.relative_humidity?.derivation ?? undefined}
                  mode={snapshot.fieldModes.relative_humidity}
                  source={snapshot.relativeHumidityPct === null ? undefined : snapshot.fieldSources.relative_humidity}
                />
                <Metric
                  label="Dew point"
                  value={reading(snapshot.dewPointC) === null ? 'Unknown' : `${reading(snapshot.dewPointC)}°C`}
                  detail={snapshot.dewPointC === null ? 'No dew point value returned' : derivedChip(snapshot.fieldSources.dew_point) ?? 'Provider field'}
                  detailTitle={snapshot.fieldSources.dew_point?.derivation ?? undefined}
                  mode={snapshot.fieldModes.dew_point}
                  source={snapshot.dewPointC === null ? undefined : snapshot.fieldSources.dew_point}
                />
                {/* Direction is a field of its own, so it is shown when it came
                    back and called Unknown when it did not — the old detail
                    printed "direction unavailable" unconditionally. */}
                <Metric
                  label="Wind / gust"
                  value={snapshot.windKmh === null && snapshot.gustKmh === null ? 'Unknown' : `${snapshot.windKmh ?? 'Unknown'} / ${snapshot.gustKmh ?? 'Unknown'}`}
                  detail={[
                    'km/h',
                    snapshot.windDirectionDeg === null ? 'direction Unknown' : `from ${Math.round(snapshot.windDirectionDeg)}°`,
                    derivedChip(snapshot.fieldSources.wind_speed) ?? derivedChip(snapshot.fieldSources.wind_direction) ?? (snapshot.windKmh === null ? null : 'Provider field'),
                  ].filter(Boolean).join(' \u00b7 ')}
                  detailTitle={snapshot.fieldSources.wind_speed?.derivation ?? snapshot.fieldSources.wind_direction?.derivation ?? undefined}
                  mode={snapshot.fieldModes.wind_speed}
                  source={snapshot.windKmh === null && snapshot.gustKmh === null ? undefined : snapshot.fieldSources.wind_speed ?? snapshot.fieldSources.wind_gust}
                />
                <Metric
                  label="Visibility"
                  value={snapshot.visibilityKm === null ? 'Unknown' : `${snapshot.visibilityKm.toFixed(1)} km`}
                  detail={snapshot.visibilityKm === null ? 'No visibility value in a recognised unit returned' : 'Converted from the declared unit'}
                  mode={snapshot.fieldModes.visibility}
                  source={snapshot.visibilityKm === null ? undefined : snapshot.fieldSources.visibility}
                />
                {/* Fog is its own field with its own lineage: the API derives
                    it from the present-weather group and says so. The value
                    is the API's category verbatim; a source is credited only
                    when the response carried a fog_state to credit. */}
                <Metric
                  label="Fog"
                  value={fogCopy[snapshot.fogRisk]}
                  detail={snapshot.fieldSources.fog_state?.derivation ? 'derived from the present-weather group' : snapshot.fogRisk === 'unknown' ? 'No fog evidence returned' : 'API category'}
                  detailTitle={snapshot.fieldSources.fog_state?.derivation ?? undefined}
                  mode={snapshot.fieldModes.fog_state}
                  source={snapshot.fieldSources.fog_state}
                />
                {/* The band buttons are a view filter over the list below and
                    nothing more. They hide rows by the base the report gave;
                    they never compute a per-band value, never hide a layer
                    whose base is unknown, and leave "Cloud L / M / H" as the
                    API returned it. */}
                <Metric
                  label="Cloud layers"
                  controls={snapshot.cloudLayers.length > 0 ? <CloudBandFilter bands={cloudBands} onChange={setCloudBands} /> : undefined}
                  value={snapshot.cloudLayers.length === 0
                    ? 'Unknown'
                    : cloudLayersMetricText(shownCloudLayers) ?? 'No reported layer in the bands left on'}
                  detail={snapshot.cloudLayers.length === 0
                    ? 'No cloud layer returned'
                    : anyBandOff
                      ? `${shownCloudLayers.length} of ${snapshot.cloudLayers.length} reported layers shown · view filter, not a classification`
                      : CLOUD_LAYERS_DETAIL}
                  mode={snapshot.fieldModes.cloud_layer_1_cover_code}
                  source={snapshot.cloudLayers.length === 0 ? undefined : snapshot.fieldSources.cloud_layer_1_cover_code}
                />
                <Metric
                  label="Cloud L / M / H"
                  value={snapshot.cloud.low === null && snapshot.cloud.middle === null && snapshot.cloud.high === null
                    ? 'Unknown'
                    : `${snapshot.cloud.low ?? 'Unknown'} · ${snapshot.cloud.middle ?? 'Unknown'} · ${snapshot.cloud.high ?? 'Unknown'}%`}
                  detail={snapshot.cloud.low === null && snapshot.cloud.middle === null && snapshot.cloud.high === null ? 'No cloud strata returned' : 'Separate strata'}
                  mode={snapshot.fieldModes.cloud_low}
                  source={snapshot.cloud.low === null && snapshot.cloud.middle === null && snapshot.cloud.high === null ? undefined : snapshot.fieldSources.cloud_low ?? snapshot.fieldSources.cloud_middle ?? snapshot.fieldSources.cloud_high}
                />
                <Metric
                  label="Total cloud"
                  value={snapshot.totalCloudPct === null ? 'Unknown' : `${Math.round(snapshot.totalCloudPct)}%`}
                  detail={snapshot.totalCloudPct === null ? 'No total cloud value returned' : 'Whole-sky cover, not a stratum'}
                  mode={snapshot.fieldModes.total_cloud}
                  source={snapshot.totalCloudPct === null ? undefined : snapshot.fieldSources.total_cloud}
                />
                <Metric
                  label="MSLP"
                  value={snapshot.pressureHpa === null ? 'Unknown' : `${snapshot.pressureHpa.toFixed(1)} hPa`}
                  detail={snapshot.pressureHpa === null ? 'No mean sea level pressure returned' : 'Mean sea level pressure'}
                  mode={snapshot.fieldModes.mean_sea_level_pressure}
                  source={snapshot.pressureHpa === null ? undefined : snapshot.fieldSources.mean_sea_level_pressure}
                />
                <Metric label="AQHI" value={snapshot.aqhi === null ? 'Unknown' : String(snapshot.aqhi)} detail={snapshot.aqhi === null ? 'Health risk unavailable' : snapshot.aqhi <= 3 ? 'Low health risk' : snapshot.aqhi <= 6 ? 'Moderate health risk' : 'Elevated health risk'} mode={snapshot.fieldModes.aqhi} source={snapshot.aqhi === null ? undefined : snapshot.fieldSources.aqhi} />
              </div>
              <div className="marine-rule">
                <span>Offshore</span>
                <strong>{snapshot.marine.waveHeightM === null ? 'Unavailable' : `${snapshot.marine.waveHeightM} m seas`}</strong>
                <p>
                  {snapshot.marine.sstC === null ? 'SST Unavailable' : `SST ${snapshot.marine.sstC}°C`} · {snapshot.marine.tide}
                  {snapshot.marine.waveHeightM === null && snapshot.marine.sstC === null && ' · No marine field was returned for this point.'}
                </p>
              </div>
              <div className="warning">
                <span>{dataSource === 'fixture' ? 'Fixture hazard example' : 'Hazard evidence'}</span>
                <strong>{snapshot.warnings[0] ?? 'Hazard feed unavailable'}</strong>
                {snapshot.warnings.length > 1 && <ul className="warning-list">{snapshot.warnings.slice(1).map((text) => <li key={text}>{text}</li>)}</ul>}
                <small>{snapshot.warnings.length === 0
                  ? 'No alert evidence was returned. Absence here is not an all-clear; check the issuing authority.'
                  : 'Always check the issuing authority before decisions.'}</small>
              </div>
            </section>
            <section className="story evidence-surface" aria-labelledby="story-title">
              <div className="story-head-row">
                <div className="section-head">
                  <span>02</span>
                  <div><small>Scrub timeline (-3h to +24h)</small><h2 id="story-title">Weather story</h2></div>
                </div>
                <div className="story-scrubber-badge">
                  <span>Valid Hour:</span>
                  <strong>{offsetMinutes === 0 ? 'Now (0h)' : offsetMinutes < 0 ? `${scrubOffset} (Past)` : `${scrubOffset} (Forecast)`}</strong>
                </div>
              </div>

              <div className="timeline-scrubber-controls">
                <div className="scrubber-bar-wrapper">
                  <div className="scrubber-labels">
                    <span>-3h (Past)</span>
                    <span>-1h</span>
                    <span className="scrubber-now">Now (0h)</span>
                    <span>+6h</span>
                    <span>+12h</span>
                    <span>+18h</span>
                    <span>+24h (Forecast)</span>
                  </div>
                  <input
                    aria-label="Valid timeline scrubber"
                    type="range"
                    min={-BACK_MINUTES}
                    max={FORWARD_MINUTES}
                    step={SCRUB_STEP_MINUTES}
                    value={offsetMinutes}
                    onChange={(e) => setOffsetMinutes(Number(e.target.value))}
                    className="timeline-slider"
                  />
                </div>
                <div className="scrubber-quick-jumps">
                  {[-3, -1, 0, 3, 6, 12, 18, 24].map((offset) => (
                    <button key={offset} type="button" className={offsetMinutes === offset * 60 ? 'active' : ''} onClick={() => setOffsetMinutes(offset * 60)}>
                      {offset === 0 ? 'Now' : offset > 0 ? `+${offset}h` : `${offset}h`}
                    </button>
                  ))}
                </div>
              </div>

              <div className="coverage-ribbon" aria-label="Published frames per layer across the window">
                {layers.length === 0
                  ? <p className="coverage-empty">No layer is published, so there are no frames to show.</p>
                  : groupedLayers.map(({ group, label, rows }) => (
                    // The same groups, order and headings as the layer drawer.
                    // Rows keep the API's order inside each group.
                    <section key={group} className="coverage-group" role="group" aria-labelledby={`coverage-group-${group}`}>
                      <h4 id={`coverage-group-${group}`}>{label} · {rows.length} layer{rows.length === 1 ? '' : 's'}</h4>
                      {group === 'satellite' && <p className="coverage-group-note">observed imagery: frames exist only for the past</p>}
                      {rows.map((layer) => {
                        const frames = (layer.times ?? [])
                          .map((time) => new Date(time).getTime())
                          .filter((stamp) => !Number.isNaN(stamp))
                        const on = selections.some((entry) => entry.id === layer.id && entry.visible)
                        const current = resolveFrame(layer, validTime)
                        return (
                          <div key={layer.id} className={`coverage-row ${on ? 'on' : 'off'}`}>
                            <button type="button" className="coverage-label" aria-pressed={on} onClick={() => toggleLayer(layer.id)}>
                              {layer.title}
                            </button>
                            <div className="coverage-track" role="img" aria-label={coverageDescription(layer, frames.length, current)}>
                              {frames.map((stamp) => {
                                const fraction = (stamp - windowStartMs) / (windowEndMs - windowStartMs)
                                if (fraction < 0 || fraction > 1) return null
                                return <i key={stamp} className="coverage-frame" style={{ left: `${fraction * 100}%` }} />
                              })}
                            </div>
                            <span className="coverage-count">
                              {frames.length === 0 ? 'no frames' : current ? describeOffset(current.offsetSeconds) : 'no frame here'}
                            </span>
                          </div>
                        )
                      })}
                    </section>
                  ))}
              </div>

              {/* The hours in the story come from /timeline. If that response did
                  not declare a usable mode, it is said here rather than letting
                  its hours read as coverage. */}
              {timelineNotice && <p className="unwired-notice" role="status">Published-hour coverage unavailable: {timelineNotice}. No story card is built from it.</p>}

              {story.length > 0 ? (
                <div className="story-track">
                  {story.map((item, index) => (
                    // A real <button>, not a div wearing role="button": Enter,
                    // Space, focus order and the button role all come for free
                    // and cannot drift apart. Its readings are laid out for the
                    // eye, so the accessible name restates them in order with
                    // their units — including every Unknown, which is the
                    // reading that matters most and the easiest one to lose.
                    <button
                      key={item.time}
                      type="button"
                      style={{ '--step': index } as React.CSSProperties}
                      className={`story-card ${item.offset * 60 === offsetMinutes ? 'active-hour' : ''}`}
                      onClick={() => setOffsetMinutes(item.offset * 60)}
                      aria-pressed={item.offset * 60 === offsetMinutes}
                      aria-label={storyCardLabel(item)}
                    >
                      <time>{item.time}</time>
                      <span className="temp">{reading(item.temperatureC) === null ? 'Unknown' : `${reading(item.temperatureC)}°`}</span>
                      <strong>{item.label}</strong>
                      <ModeChip mode={item.dataMode} />
                      {/* Spans, not a <dl>: a button may only contain phrasing
                          content, and the button flattens list semantics into
                          its accessible name regardless. */}
                      <span className="story-readings">
                        <span><span className="story-key">Dew</span><span className="story-value">{reading(item.dewPointC) === null ? 'Unknown' : `${reading(item.dewPointC)}°`}</span></span>
                        <span><span className="story-key">Rain</span><span className="story-value">{item.precipPct === null ? 'Unknown' : `${item.precipPct}%`}</span></span>
                        <span><span className="story-key">Wind</span><span className="story-value">{item.windKmh === null ? 'Unknown' : item.windKmh}</span></span>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="evidence-unavailable">24-hour narrative unavailable from this point response. No forecast story has been inferred.</p>
              )}
            </section>
          </div>
        ) : (
          <div className="expert-layout">
            <aside className="expert-controls" aria-label="Evidence controls">
              <div className="section-head"><span>EX</span><div><small>Native evidence</small><h2>Field selector</h2></div></div>
              <p className="unwired-notice">Every option below comes from a response. A selector with no returned options stays disabled and says why. Provider, product and variable change what is requested; run, member and level are read-only, because the point request has no parameter for them.</p>
              <FieldControl label="Provider">
                <EvidenceSelect
                  label="Provider"
                  value={provider}
                  onChange={(value) => { setProvider(value); setSelectedProduct(null) }}
                  emptyReason={catalogError ? `Catalog unavailable: ${catalogError}` : 'No provider in catalog response'}
                  options={providers.length > 0 ? [{ value: '', label: 'All providers in catalog' }, ...providers.map((name) => ({ value: name, label: name }))] : []}
                />
              </FieldControl>
              <FieldControl label="Product">
                <EvidenceSelect
                  label="Product"
                  value={selectedProduct ?? ''}
                  onChange={(value) => setSelectedProduct(value === '' ? null : value)}
                  emptyReason={catalogError ? `Catalog unavailable: ${catalogError}` : 'No catalogued product is accepted by the point endpoint'}
                  options={productSources.length > 0 ? [{ value: '', label: 'Consensus (API selection)' }, ...productSources.map((source) => ({
                    value: pointProductFor(source) as string,
                    label: `${pointProductFor(source)} — ${source.product}`,
                    title: `${source.role} · registry state: ${source.state}`,
                  }))] : []}
                />
              </FieldControl>
              <FieldControl label="Run">
                <ProvenanceReadout label="Run" values={runs} emptyReason="No run time in returned provenance" />
              </FieldControl>
              <FieldControl label="Variable">
                <EvidenceSelect
                  label="Variable"
                  value={''}
                  onChange={(value) => { if (value !== '') toggleLayer(value) }}
                  emptyReason={layersLoading ? 'Loading published layers…' : layersError ? `Layers unavailable: ${layersError}` : 'No layer published by the API'}
                  options={layers.length > 0 ? [{ value: '', label: 'Add a layer to the stack' }, ...layers.map((layer) => ({ value: layer.id, label: `${selections.some((entry) => entry.id === layer.id) ? '✓ ' : ''}${layer.title} (${layer.units})`, title: layer.semantics }))] : []}
                />
              </FieldControl>
              <div className="control-pair">
                <FieldControl label="Member">
                  <ProvenanceReadout label="Member" values={members} emptyReason="No ensemble member in returned provenance" />
                </FieldControl>
                <FieldControl label="Level">
                  <ProvenanceReadout label="Level" values={levels} emptyReason="No vertical level in returned provenance" />
                </FieldControl>
              </div>
              <FieldControl label={`Valid time (${scrubOffset})`}>
                <input
                  aria-label="Valid forecast time"
                  type="range"
                  min={-BACK_MINUTES}
                  max={FORWARD_MINUTES}
                  step={SCRUB_STEP_MINUTES}
                  value={offsetMinutes}
                  onChange={(e) => setOffsetMinutes(Number(e.target.value))}
                />
              </FieldControl>
              <p className="one-raster-note"><i /> Layers draw only response-backed values, each at the frame it published. Nothing is drawn where a layer has no frame.</p>
            </aside>
            <div className="comparison single" aria-label="Evidence map and comparison status">
              <MapPanel
                label="Pane A · point evidence"
                field={mapField}
                comparison="Product shown in provenance"
                selected={location}
                onSelect={setLocation}
                validTime={validTime}
                fixtureMode={dataSource === 'fixture'}
                layers={layers}
                layersError={layersError}
                layersLoading={layersLoading}
                selections={selections}
                onToggleLayer={toggleLayer}
                onSetOpacity={setLayerOpacity}
                onJumpToTime={jumpToTime}
                layerNotices={layerNotices}
                evidence={mapEvidence}
                sourceStatuses={sourceStatuses}
              />
              <section className="comparison-unavailable"><strong>Pane B unavailable</strong><p>No second response-backed field is loaded. Comparison is not inferred.</p></section>
            </div>
            <section className="analysis-tray evidence-surface" aria-label="Expert analysis panels">
              <details><summary>Humidity & cloud profile</summary>
                {profile && profile.levels.length > 0 ? (
                  <table aria-label="Atmospheric sounding levels at evidence point">
                    <thead>
                      <tr>
                        <th scope="col">Level</th>
                        <th scope="col">Temp (°C)</th>
                        <th scope="col">Dew (°C)</th>
                        <th scope="col">RH (%)</th>
                        <th scope="col">Wind (m/s)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {profile.levels.map((lvl) => (
                        <tr key={lvl.pressure_hpa}>
                          <th scope="row">{lvl.pressure_hpa} hPa</th>
                          <td>{lvl.temperature_c !== null ? `${lvl.temperature_c}°C` : 'Unknown'}</td>
                          <td>{lvl.dew_point_c !== null ? `${lvl.dew_point_c}°C` : 'Unknown'}</td>
                          <td>{lvl.relative_humidity_pct !== null ? `${lvl.relative_humidity_pct}%` : 'Unknown'}</td>
                          <td>{lvl.wind_speed_ms !== null ? `${lvl.wind_speed_ms} m/s` : 'Unknown'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p>Profile visualization is not wired. No vertical values are synthesized.</p>
                )}
              </details>
              <details><summary>Skew-T / log-pressure</summary><p>Unavailable until a validated numeric profile response is loaded.</p></details>
              <details><summary>Drawn cross-section</summary><p>Drawing and cross-section requests are not wired in this slice.</p></details>
              <details open><summary>Provenance</summary><table><caption>Provenance returned for the selected point</caption><thead><tr><th scope="col">Provider / product</th><th scope="col">Run</th><th scope="col">Role</th><th scope="col">Freshness</th><th scope="col">Data mode</th><th scope="col">Derivation</th></tr></thead><tbody>{snapshot.provenance.map((row) => <tr key={`${row.provider}-${row.product}`}><th scope="row">{row.provider} / {row.product}</th><td>{row.run}</td><td>{row.role}</td><td>{row.freshness}</td><td>{row.dataMode}</td><td>{row.derivations.length === 0 ? 'Provider values' : row.derivations.join('; ')}</td></tr>)}</tbody></table>{snapshot.provenance.length === 0 && <p>No provenance is available.</p>}</details>
            </section>
          </div>
        )}
      </main>
      <footer><span>POC // St. John’s · Avalon · Grand Banks</span><p>Experimental evidence display. Not a calibrated probability, warning service, or navigation product.</p></footer>
    </div>
  )
}
