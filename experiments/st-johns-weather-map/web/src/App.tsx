import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ALL_CLOUD_BANDS, type CloudBand, type CloudBands, DEFAULT_INTERPOLATION_METHOD, type InterpolationMethodItem, cloudBandOf, filterCloudLayers, frameMarkers, loadAstronomy, loadCatalog, loadLayers, loadMethods, loadPoint, loadProfile, loadSourceStatus, loadSpaceWeather, loadStory, loadTimeline, nlTime, pointProductFor, reading, snapInstant, stepInstant, stJohnsTime, unionFrameInstants } from './api'
import { advanceClock, fasterSpeed, slowerSpeed, type PlaybackDirection, type PlaybackSpeed } from './playback'
import { stationCoverage, stations, unavailableSnapshot } from './fixtures'
import { MapPanel, type MapEvidenceRow } from './MapPanel'
import { ModeChip } from './ModeChip'
import { StoryFlyout } from './StoryFlyout'
import { TimelineDock } from './TimelineDock'
import { useTheme } from './theme'
import type {
  AppMode, CatalogSource, CloudLayerReading, DataSource, EvidenceSnapshot, FallbackMode, FieldAttribution, FieldDataMode,
  LayerItem, LayerSelection, LocationPoint, ProfileResponse, SourceStatusItem, StoryStep, TimelineResponse, AstronomyResponse,
  SpaceWeatherReading, SpaceWeatherResponse, SpaceWeatherSeries,
} from './types'

/** The evidence window, in minutes from the session reference instant. */
const BACK_MINUTES = 3 * 60
const FORWARD_MINUTES = 24 * 60

/** Scrub resolution. Five minutes is finer than the fastest layer published
 *  (radar, every six), so no layer's frames are unreachable between steps. */
const SCRUB_STEP_MINUTES = 5

/** The key the interpolation preference persists under. A per-viewer display
 *  convenience only; nothing evidential lives in browser storage. */
const INTERPOLATE_STORAGE_KEY = 'weather-interpolate-forecast'
const METHOD_STORAGE_KEY = 'weather-interpolation-method'

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

/** The freshness suffix a space-weather card shows. Stale is said out loud —
 *  an old planetary reading shown as current would misdate the sky. */
function staleSuffix(freshness: { status: string; age_seconds: number | null }): string {
  if (freshness.status !== 'stale') return ''
  const age = freshness.age_seconds
  return age === null ? ' · stale' : ` · stale, ${age < 5400 ? `${Math.round(age / 60)} min` : `${(age / 3600).toFixed(1)} h`} old`
}

/** The newest observed Kp reading that actually carries a value, or null.
 *  Readings arrive in feed order (ascending time); a trailing gap stays a gap. */
function latestKpReading(series: SpaceWeatherSeries | undefined): SpaceWeatherReading | null {
  if (!series?.available) return null
  for (let index = series.readings.length - 1; index >= 0; index -= 1) {
    if (series.readings[index].value !== null) return series.readings[index]
  }
  return null
}

/** The maximum forecast Kp inside the evidence window, with the provider's own
 *  per-value status. Null when no forecast value falls in the window — never
 *  the window-less maximum standing in for it. */
function maxForecastKp(series: SpaceWeatherSeries | undefined, windowStartMs: number, windowEndMs: number): SpaceWeatherReading | null {
  if (!series?.available) return null
  let best: SpaceWeatherReading | null = null
  for (const item of series.readings) {
    const stamp = new Date(item.time).getTime()
    if (Number.isNaN(stamp) || stamp < windowStartMs || stamp > windowEndMs || item.value === null) continue
    if (!best || item.value > (best.value ?? -Infinity)) best = item
  }
  return best
}

const fogCopy: Record<EvidenceSnapshot['fogRisk'], string> = {
  evidence_present: 'Fog evidence present',
  not_indicated: 'Fog not indicated by available evidence',
  unknown: 'Fog evidence unknown',
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
    { label: 'Jet-level wind', value: snapshot.upperAir.jet200Kmh === null && snapshot.upperAir.jet300Kmh === null ? 'Unknown — no upper-air wind value was returned' : `${snapshot.upperAir.jet200Kmh === null ? 'unknown' : Math.round(snapshot.upperAir.jet200Kmh)} / ${snapshot.upperAir.jet300Kmh === null ? 'unknown' : Math.round(snapshot.upperAir.jet300Kmh)} km/h at 200/300 hPa — strong jet flow degrades astronomical seeing${sourced(snapshot, 'wind_speed_200hPa')}` },
    { label: 'Precipitable water', value: snapshot.upperAir.precipitableWaterKgM2 === null ? 'Unknown — no precipitable water value was returned' : `${snapshot.upperAir.precipitableWaterKgM2.toFixed(1)} kg/m² of column moisture — more degrades sky transparency${sourced(snapshot, 'precipitable_water')}` },
    { label: 'Aurora probability', value: snapshot.auroraProbabilityPct === null ? 'Unknown — no aurora probability value was returned' : `${Math.round(snapshot.auroraProbabilityPct)}% — OVATION model nowcast at the sampled grid cell, not an observation${sourced(snapshot, 'aurora_probability')}` },
    { label: 'Valid time', value: snapshot.validAt ?? 'Unknown — no valid time was returned' },
  ]
}

export default function App() {
  const { theme, setTheme } = useTheme()
  const [mode, setMode] = useState<AppMode>('simple')
  const [location, setLocation] = useState<LocationPoint>(stations[0])
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot>(unavailableSnapshot)
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  // One reference instant for the whole session. Recomputing `now` on every
  // render would slide every layer's resolved frame under the reader.
  const [reference] = useState<Date>(() => new Date())
  // The selected instant, exact to the millisecond. The reference carries the
  // seconds of the moment the page loaded, so a whole-minute offset could
  // never land exactly on a published frame timestamp; snapping and frame
  // jumps set the exact epoch instant instead.
  const [selectedMs, setSelectedMs] = useState<number>(reference.getTime())
  // Owner-approved display setting: composite forecast imagery between its
  // two neighbouring frames. Off by default; a per-viewer convenience only,
  // so the stored value is read best-effort and never trusted as evidence.
  const [interpolate, setInterpolate] = useState<boolean>(() => {
    try { return localStorage.getItem(INTERPOLATE_STORAGE_KEY) === 'true' } catch { return false }
  })
  // Which interpolation method the map draws with. A per-viewer display
  // choice, stored best-effort like the interpolation toggle; the registry
  // that says which methods exist is the server's, so a stored id the server
  // no longer publishes falls back to the default rather than 404ing.
  const [method, setMethod] = useState<string>(() => {
    try { return localStorage.getItem(METHOD_STORAGE_KEY) || DEFAULT_INTERPOLATION_METHOD } catch { return DEFAULT_INTERPOLATION_METHOD }
  })
  const [methods, setMethods] = useState<InterpolationMethodItem[]>([])
  const [methodNotices, setMethodNotices] = useState<string[]>([])
  const [methodError, setMethodError] = useState<string | null>(null)
  // The transport: a clock over the same selected instant the scrubber
  // moves. It resolves frames by exactly the rules a scrub does.
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<PlaybackSpeed>(1)
  const [direction, setDirection] = useState<PlaybackDirection>(1)
  const [storyOpen, setStoryOpen] = useState(false)
  const storyToggleRef = useRef<HTMLButtonElement | null>(null)
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
  const [astronomy, setAstronomy] = useState<AstronomyResponse | null>(null)
  const [astronomyNotice, setAstronomyNotice] = useState<string | null>(null)
  const [spaceWeather, setSpaceWeather] = useState<SpaceWeatherResponse | null>(null)
  const [spaceWeatherNotice, setSpaceWeatherNotice] = useState<string | null>(null)
  const [story, setStory] = useState<StoryStep[]>([])
  const [provider, setProvider] = useState('')
  const [sourceStatuses, setSourceStatuses] = useState<SourceStatusItem[] | null>(null)
  const [sourceStatusError, setSourceStatusError] = useState<string | null>(null)
  // All three bands on = the full as-reported list. Local view state only; it
  // reaches no request and derives no value.
  const [cloudBands, setCloudBands] = useState<CloudBands>(ALL_CLOUD_BANDS)

  /** The instant the reader is asking about, exact. The badge and headings
   *  speak in whole minutes; the frames and requests use the instant itself. */
  const validTime = useMemo(() => new Date(selectedMs), [selectedMs])
  const offsetMinutes = useMemo(() => Math.round((selectedMs - reference.getTime()) / 60_000), [selectedMs, reference])
  const scrubOffset = useMemo(() => describeScrubOffset(offsetMinutes), [offsetMinutes])
  const windowStartMs = useMemo(() => reference.getTime() - BACK_MINUTES * 60_000, [reference])
  const windowEndMs = useMemo(() => reference.getTime() + FORWARD_MINUTES * 60_000, [reference])

  const validTimeIso = useMemo(() => {
    if (selectedMs === reference.getTime()) return undefined
    return validTime.toISOString().replace(/\.\d{3}Z$/, 'Z')
  }, [selectedMs, reference, validTime])

  // The axis a scrub snaps onto when display interpolation is off: the union
  // of the active visible layers' published frame instants in the window.
  // Empty (free five-minute scrubbing) when interpolation is on or nothing
  // active publishes a frame. Toggling a layer changes this axis but never
  // moves the current selection — only a scrub action snaps.
  const snapInstants = useMemo(
    () => (interpolate ? [] : unionFrameInstants(layers, selections, windowStartMs, windowEndMs)),
    [interpolate, layers, selections, windowStartMs, windowEndMs],
  )
  const snapping = snapInstants.length > 0
  const clampMs = useCallback((ms: number) => Math.max(windowStartMs, Math.min(windowEndMs, ms)), [windowStartMs, windowEndMs])

  /** A hand on the timeline stops the transport: playback and a scrub must
   *  never fight over the same clock. */
  const pausePlayback = useCallback(() => setPlaying(false), [])

  /** Every scrub-shaped selection routes through here: slider drags, quick
   *  jumps and story cards, so all of them obey the same snap rule. */
  const selectMinutes = useCallback((rawMinutes: number) => {
    pausePlayback()
    const target = reference.getTime() + rawMinutes * 60_000
    if (snapInstants.length > 0) {
      setSelectedMs(clampMs(snapInstant(snapInstants, target)))
      return
    }
    const rounded = Math.round(rawMinutes / SCRUB_STEP_MINUTES) * SCRUB_STEP_MINUTES
    setSelectedMs(clampMs(reference.getTime() + rounded * 60_000))
  }, [reference, snapInstants, clampMs, pausePlayback])

  const onScrubKeyDown = useCallback((event: React.KeyboardEvent<HTMLInputElement>) => {
    const step = (towards: 1 | -1, minutes: number) => {
      event.preventDefault()
      pausePlayback()
      if (snapInstants.length > 0) setSelectedMs(clampMs(stepInstant(snapInstants, selectedMs, towards)))
      else setSelectedMs(clampMs(selectedMs + towards * minutes * 60_000))
    }
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowUp': step(1, SCRUB_STEP_MINUTES); break
      case 'ArrowLeft':
      case 'ArrowDown': step(-1, SCRUB_STEP_MINUTES); break
      case 'PageUp': step(1, 60); break
      case 'PageDown': step(-1, 60); break
      case 'Home': event.preventDefault(); pausePlayback(); setSelectedMs(snapInstants.length > 0 ? snapInstants[0] : windowStartMs); break
      case 'End': event.preventDefault(); pausePlayback(); setSelectedMs(snapInstants.length > 0 ? snapInstants[snapInstants.length - 1] : windowEndMs); break
      default: break
    }
  }, [snapInstants, selectedMs, clampMs, windowStartMs, windowEndMs, pausePlayback])

  const scrubValueText = `${scrubOffset} — ${stJohnsTime(validTime.toISOString())} NT${snapping ? ', snapped to the nearest published frame' : ''}`

  // The playback clock. Each animation frame advances the selected instant
  // by the wall-clock time since the previous frame, so a backgrounded tab
  // (which gets no frames at all) resumes where it left off instead of
  // jumping by however long it was hidden.
  useEffect(() => {
    if (!playing) return
    let frame = 0
    let last: number | null = null
    const tick = (now: number) => {
      const elapsedSeconds = last === null ? 0 : (now - last) / 1000
      last = now
      if (elapsedSeconds > 0) {
        setSelectedMs((current) => advanceClock({
          ms: current, elapsedSeconds, speedMinutesPerSecond: speed, direction, windowStartMs, windowEndMs,
        }))
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed, direction, windowStartMs, windowEndMs])

  // Published frames of the active layers: the ticks under the scrubber and
  // the jump targets. Exactly what /layers returned, never an invented
  // instant; a layer with no time axis is named rather than left out.
  const markers = useMemo(
    () => frameMarkers(layers, selections, windowStartMs, windowEndMs),
    [layers, selections, windowStartMs, windowEndMs],
  )

  const selectMethod = useCallback((methodId: string) => {
    setMethod(methodId)
    try { localStorage.setItem(METHOD_STORAGE_KEY, methodId) } catch { /* display preference only */ }
  }, [])

  // The bench, read once. A stored method the server no longer publishes is
  // dropped back to the default rather than left asking for fields that do
  // not exist - the map would fall to a crossfade and say so, but silently
  // asking for a method nobody offers is not a state worth keeping.
  useEffect(() => {
    const controller = new AbortController()
    loadMethods(controller.signal).then((result) => {
      if (result.error === 'aborted') return
      setMethods(result.methods)
      setMethodNotices(result.notices)
      setMethodError(result.error)
      setMethod((current) => (result.methods.some((item) => item.id === current) ? current : result.defaultMethod))
    }).catch(() => undefined)
    return () => controller.abort()
  }, [])

  const toggleInterpolate = useCallback(() => {
    setInterpolate((previous) => {
      const next = !previous
      try { localStorage.setItem(INTERPOLATE_STORAGE_KEY, String(next)) } catch { /* display preference only */ }
      return next
    })
  }, [])

  const closeStory = useCallback(() => {
    setStoryOpen(false)
    storyToggleRef.current?.focus()
  }, [])

  const toggleLayer = useCallback((layerId: string) => {
    setSelections((previous) => previous.some((entry) => entry.id === layerId)
      ? previous.filter((entry) => entry.id !== layerId)
      : [...previous, { id: layerId, visible: true, opacity: 0.85 }])
  }, [])

  const setLayerOpacity = useCallback((layerId: string, opacity: number) => {
    setSelections((previous) => previous.map((entry) => (entry.id === layerId ? { ...entry, opacity } : entry)))
  }, [])

  // A layer row asked for the scrubber to go to its nearest frame. The exact
  // instant is kept — it IS a published frame time — and only clamped to the
  // window; the row will say so in its own words if that moved it.
  const jumpToTime = useCallback((date: Date) => {
    pausePlayback()
    setSelectedMs(clampMs(date.getTime()))
  }, [clampMs, pausePlayback])

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
    // Computed darkness/moon geometry. Fail-closed like everything else: a
    // failure keeps the reason and no band is drawn, because an empty band
    // would read as "no darkness tonight".
    loadAstronomy(controller.signal).then((result) => {
      setAstronomy(result.astronomy)
      setAstronomyNotice(result.error)
    }).catch(() => undefined)
    // Planetary space weather (Kp, Bz). Fail-closed like astronomy: a failure
    // keeps the reason and no card shows a number, because a Kp of zero on an
    // outage would be an invented reading.
    loadSpaceWeather(controller.signal).then((result) => {
      setSpaceWeather(result.spaceWeather)
      setSpaceWeatherNotice(result.error)
    }).catch(() => undefined)
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

  // Shared between the two layouts: in simple mode these live inside the
  // scrollable right strip, in expert mode they keep their full-width rows.
  const masthead = (
    <header className="masthead">
      <div className="wordmark"><span>WX//47°N</span><h1>Avalon Evidence Desk</h1></div>
      <div className="experimental"><i /> experimental · not operational guidance</div>
      <div className="theme-switch" role="group" aria-label="Colour theme">
        <button type="button" aria-pressed={theme === 'light'} onClick={() => setTheme('light')}><span aria-hidden="true">☀</span> Light</button>
        <button type="button" aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}><span aria-hidden="true">◐</span> Dark</button>
      </div>
      <nav className="mode-switch" aria-label="Interface mode">
        <button aria-pressed={mode === 'simple'} onClick={() => setMode('simple')}>Brief</button>
        <button aria-pressed={mode === 'expert'} onClick={() => setMode('expert')}>Workbench</button>
      </nav>
    </header>
  )

  const locationStrip = (
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
  )

  const modelStrip = (
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
  )

  const sourceErrorLine = sourceError
    ? <p className="source-error" role="status">{sourceError}. No previous point evidence is being shown.</p>
    : null

  const fallbackBadge = (
        <section className={`fallback-badge evidence-surface ${snapshot.mode}`} aria-label="Forecast selection">
          <span className="signal-bars" aria-hidden="true"><i /><i /><i /></span>
          <div><small>Selected forecast</small><strong>{selectionLabel}</strong></div>
          {snapshot.validAt ? <time dateTime={snapshot.validAt}>Valid {new Date(snapshot.validAt).toLocaleString('en-CA', { timeZone: 'America/St_Johns', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' })}</time> : <span className="unknown-time">Valid time unknown</span>}
        </section>
  )

  const stripFooter = (
    <div className="strip-footer">
      <span>POC // St. John’s · Avalon · Grand Banks</span>
      <p>Experimental evidence display. Not a calibrated probability, warning service, or navigation product.</p>
    </div>
  )

  return (
    <div className={`workbench ${mode === 'simple' ? 'app-shell' : ''} ${dataSource === 'fixture' ? 'fixture-mode' : ''}`}>
      {dataSource !== 'live' && <div className={`fixture-watermark ${dataSource}`} role="status">{bannerCopy[dataSource]}</div>}
      {masthead}

      <main className={mode === 'simple' ? 'app-main' : undefined}>
        {mode === 'simple' ? (
          <div className="viewport-grid">
            <div className="map-stage">
              <MapPanel
                label="Avalon / upstream Atlantic"
                field={mapField}
                selected={location}
                onSelect={setLocation}
                validTime={validTime}
                reference={reference}
                interpolate={interpolate}
                interpolationMethod={method}
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
                theme={theme}
              />
              {storyOpen && (
                <StoryFlyout
                  astronomy={astronomy}
                  astronomyNotice={astronomyNotice}
                  windowStartMs={windowStartMs}
                  windowEndMs={windowEndMs}
                  layers={layers}
                  selections={selections}
                  onToggleLayer={toggleLayer}
                  validTime={validTime}
                  reference={reference}
                  timelineNotice={timelineNotice}
                  story={story}
                  offsetMinutes={offsetMinutes}
                  onSelectOffsetHours={(offsetHours) => selectMinutes(offsetHours * 60)}
                  onClose={closeStory}
                />
              )}
            </div>
            <TimelineDock
              offsetMinutes={offsetMinutes}
              scrubOffset={scrubOffset}
              validClock={stJohnsTime(validTime.toISOString())}
              backMinutes={BACK_MINUTES}
              forwardMinutes={FORWARD_MINUTES}
              snapping={snapping}
              ariaValueText={scrubValueText}
              onScrubMinutes={selectMinutes}
              onScrubKeyDown={onScrubKeyDown}
              onQuickJump={(offsetHours) => selectMinutes(offsetHours * 60)}
              windowStartMs={windowStartMs}
              windowEndMs={windowEndMs}
              markers={markers}
              onJumpToInstant={(ms) => jumpToTime(new Date(ms))}
              playing={playing}
              speed={speed}
              direction={direction}
              onTogglePlay={() => setPlaying((on) => !on)}
              onFaster={() => setSpeed(fasterSpeed)}
              onSlower={() => setSpeed(slowerSpeed)}
              onToggleDirection={() => setDirection((towards) => (towards === 1 ? -1 : 1))}
              interpolate={interpolate}
              onToggleInterpolate={toggleInterpolate}
              methods={methods}
              method={method}
              onSelectMethod={selectMethod}
              methodNotices={methodNotices}
              methodError={methodError}
              storyOpen={storyOpen}
              onToggleStory={() => setStoryOpen((open) => !open)}
              storyToggleRef={storyToggleRef}
            />
            <aside className="conditions-strip" aria-label="Evidence point, models and conditions">
              {locationStrip}
              <details className="model-details">
                <summary>Forecast model · {selectedProduct ?? 'Consensus (BLEND)'}</summary>
                {modelStrip}
              </details>
              {sourceErrorLine}
              {fallbackBadge}
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
                    : [snapshot.cloud.low, snapshot.cloud.middle, snapshot.cloud.high]
                        .map((pct) => (pct === null ? 'Unknown' : `${Math.round(pct)}%`)).join(' · ')}
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
                <Metric
                  label="Jet-level wind"
                  value={snapshot.upperAir.jet200Kmh === null && snapshot.upperAir.jet300Kmh === null
                    ? 'Unknown'
                    : [snapshot.upperAir.jet200Kmh, snapshot.upperAir.jet300Kmh].map((v) => (v === null ? 'Unknown' : `${Math.round(v)} km/h`)).join(' · ')}
                  detail={snapshot.upperAir.jet200Kmh === null && snapshot.upperAir.jet300Kmh === null
                    ? 'No upper-air wind returned'
                    : 'At 200 · 300 hPa — strong jet flow degrades astronomical seeing'}
                  mode={snapshot.fieldModes.wind_speed_200hPa ?? snapshot.fieldModes.wind_speed_300hPa}
                  source={snapshot.fieldSources.wind_speed_200hPa ?? snapshot.fieldSources.wind_speed_300hPa}
                />
                <Metric
                  label="Precipitable water"
                  value={snapshot.upperAir.precipitableWaterKgM2 === null ? 'Unknown' : `${snapshot.upperAir.precipitableWaterKgM2.toFixed(1)} kg/m²`}
                  detail={snapshot.upperAir.precipitableWaterKgM2 === null ? 'No precipitable water returned' : 'Column moisture — more degrades sky transparency'}
                  mode={snapshot.fieldModes.precipitable_water}
                  source={snapshot.upperAir.precipitableWaterKgM2 === null ? undefined : snapshot.fieldSources.precipitable_water}
                />
              </div>
              <div className="marine-rule">
                <span>Offshore</span>
                <strong>{snapshot.marine.waveHeightM === null ? 'Unavailable' : `${snapshot.marine.waveHeightM} m seas`}</strong>
                <p>
                  {snapshot.marine.sstC === null ? 'SST Unavailable' : `SST ${snapshot.marine.sstC}°C`} · {snapshot.marine.tide}
                  {snapshot.marine.waveHeightM === null && snapshot.marine.sstC === null && ' · No marine field was returned for this point.'}
                </p>
              </div>
              <div className="tonight">
                <h3>Tonight <small>computed geometry, JPL DE442</small></h3>
                {astronomy === null
                  ? <p className="unwired-notice" role="status">Astronomy unavailable: {astronomyNotice ?? 'astronomy was not read'}</p>
                  : (
                    <div className="metric-grid">
                      <Metric
                        label="Astronomical darkness"
                        value={astronomy.twilight_bands.some((band) => band.kind === 'night')
                          ? astronomy.twilight_bands.filter((band) => band.kind === 'night').map((band) => `${nlTime(band.start)}–${nlTime(band.end)}`).join(', ')
                          : 'None in this window'}
                        detail="Sun below −18° · Newfoundland time"
                      />
                      <Metric
                        label="Moon"
                        value={`${astronomy.moon.rise === null ? 'no rise' : `rises ${nlTime(astronomy.moon.rise)}`} · ${astronomy.moon.set === null ? 'no set' : `sets ${nlTime(astronomy.moon.set)}`}`}
                        detail={`${Math.round(astronomy.moon.illuminated_fraction * 100)}% illuminated, ${astronomy.moon.phase_deg < 180 ? 'waxing' : 'waning'}`}
                      />
                      <Metric
                        label="Milky Way core"
                        value={astronomy.milky_way_core.windows.length === 0
                          ? 'No geometric window'
                          : astronomy.milky_way_core.windows.map((band) => `${nlTime(band.start)}–${nlTime(band.end)}`).join(', ')}
                        detail={`Peaks at ${astronomy.milky_way_core.max_altitude_deg}° · ${astronomy.milky_way_core.caption}`}
                        detailTitle={astronomy.milky_way_core.caption}
                      />
                    </div>
                  )}
              </div>
              <div className="tonight space-weather">
                <h3>Space weather <small>NOAA SWPC · planetary indices, not local readings</small></h3>
                {spaceWeather === null
                  ? <p className="unwired-notice" role="status">Space weather unavailable: {spaceWeatherNotice ?? 'space weather was not read'}</p>
                  : (() => {
                    const observed = latestKpReading(spaceWeather.kp_observed)
                    const forecast = maxForecastKp(spaceWeather.kp_forecast, windowStartMs, windowEndMs)
                    const wind = spaceWeather.solar_wind
                    return (
                      <div className="metric-grid">
                        <Metric
                          label="Kp observed"
                          value={observed === null || observed.value === null ? 'Unknown' : observed.value.toFixed(2)}
                          detail={observed === null
                            ? spaceWeather.kp_observed.notices[0] ?? 'No observed Kp value was returned'
                            : `Planetary K index at ${nlTime(observed.time)} NT${staleSuffix(spaceWeather.kp_observed.freshness)}`}
                        />
                        <Metric
                          label="Kp forecast max"
                          value={forecast === null || forecast.value === null ? 'Unknown' : forecast.value.toFixed(2)}
                          detail={forecast === null
                            ? (spaceWeather.kp_forecast.available
                              ? 'No forecast Kp value falls inside this window'
                              : spaceWeather.kp_forecast.notices[0] ?? 'No forecast series is available')
                            : `provider status: ${forecast.status ?? 'undeclared'} · at ${nlTime(forecast.time)} NT — NOAA guidance: photographable at St. John's from about Kp 4-5`}
                          detailTitle="The status label (observed | estimated | predicted) is the provider's own, per value."
                        />
                        <Metric
                          label="Solar wind Bz"
                          value={wind.available && wind.bz_gsm_nt !== null ? `${wind.bz_gsm_nt.toFixed(1)} nT` : 'Unknown'}
                          detail={wind.available && wind.bz_gsm_nt !== null
                            ? `measured ${wind.measured_at ? `${nlTime(wind.measured_at)} NT` : 'at an unknown instant'}${staleSuffix(wind.freshness)} — southward (negative) Bz is the aurora tripwire`
                            : wind.notices[0] ?? 'No Bz value was returned'}
                        />
                      </div>
                    )
                  })()}
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
              {stripFooter}
            </aside>
          </div>
        ) : (
          <>
            {locationStrip}
            {modelStrip}
            {sourceErrorLine}
            {fallbackBadge}
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
                  aria-valuetext={scrubValueText}
                  type="range"
                  min={-BACK_MINUTES}
                  max={FORWARD_MINUTES}
                  step={1}
                  value={offsetMinutes}
                  onChange={(e) => selectMinutes(Number(e.target.value))}
                  onKeyDown={onScrubKeyDown}
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
                reference={reference}
                interpolate={interpolate}
                interpolationMethod={method}
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
                theme={theme}
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
          </>
        )}
      </main>
      {mode === 'expert' && <footer><span>POC // St. John’s · Avalon · Grand Banks</span><p>Experimental evidence display. Not a calibrated probability, warning service, or navigation product.</p></footer>}
    </div>
  )
}
