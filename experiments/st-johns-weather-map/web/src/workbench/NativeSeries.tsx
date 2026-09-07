import { useCallback, useEffect, useRef, useState } from 'react'
import { attributionOf, type ApiEvidenceField } from '../api'
import type { LocationPoint, ServedFieldValue } from '../types'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'
import { EVIDENCE_CLASS_LABELS } from '../evidenceClass'

interface Selector { id: string; source_id: string; field: string; run: string }
interface Selection { latitude: number; longitude: number; start: string; end: string; selectors: Selector[]; page_size: number }
interface Row { selector_id: string; source_id: string; field: string; requested_run: string; availability: 'available' | 'checked_empty' | 'unknown' | 'unavailable'; reason: string | null; samples: ApiEvidenceField[] }
export interface NativeSeriesResponse {
  selection: Selection
  snapshot: { id: string; selected_at: string; expires_at: string; change_token: string; identities: unknown[] }
  series: Row[]; next_cursor: string | null; complete: boolean; notices: string[]
}
function selectionKey(value: Selection): string {
  return JSON.stringify({ latitude: value.latitude, longitude: value.longitude, start: new Date(value.start).toISOString(), end: new Date(value.end).toISOString(),
    selectors: value.selectors.map((s) => ({ id: s.id, source_id: s.source_id, field: s.field, run: s.run })), page_size: value.page_size })
}
const endpoint = '/api/experiments/weather/v0/point/series'
async function post(path: string, body: unknown, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body), signal })
  const value = await response.json()
  if (!response.ok) throw new Error(`${value?.detail?.code ?? response.status}: ${value?.detail?.message ?? 'Series request failed'}`)
  return value
}
function readResponse(value: unknown): NativeSeriesResponse {
  if (!value || typeof value !== 'object') throw new Error('Series response is unreadable')
  const body = value as NativeSeriesResponse
  if (!body.selection || !Array.isArray(body.selection.selectors) || !body.snapshot || typeof body.snapshot.id !== 'string'
    || typeof body.snapshot.change_token !== 'string' || !Number.isFinite(Date.parse(body.snapshot.expires_at))
    || !Array.isArray(body.series) || typeof body.complete !== 'boolean'
    || !(body.next_cursor === null || typeof body.next_cursor === 'string') || !Array.isArray(body.notices)) throw new Error('Series response is unreadable')
  for (const row of body.series) {
    const selector = body.selection.selectors.find((item) => item.id === row.selector_id)
    if (!selector || selector.source_id !== row.source_id || selector.field !== row.field || !Array.isArray(row.samples)
      || !['available', 'checked_empty', 'unknown', 'unavailable'].includes(row.availability)) throw new Error('Series identity is unreadable')
    for (const sample of row.samples) {
      if (sample.key !== row.field || sample.provenance?.source_id !== row.source_id
        || typeof sample.provenance.valid_time !== 'string' || !Number.isFinite(Date.parse(sample.provenance.valid_time))
        || Date.parse(sample.provenance.valid_time) < Date.parse(body.selection.start) || Date.parse(sample.provenance.valid_time) >= Date.parse(body.selection.end)) throw new Error('Native reading identity is unreadable')
    }
  }
  return body
}
function appendPage(previous: NativeSeriesResponse, page: NativeSeriesResponse): NativeSeriesResponse {
  if (page.snapshot.id !== previous.snapshot.id || page.snapshot.expires_at !== previous.snapshot.expires_at
      || selectionKey(page.selection) !== selectionKey(previous.selection)) throw new Error('Continuation changed the selection')
  const rows = previous.series.map((row) => ({ ...row, samples: [...row.samples] }))
  for (const row of page.series) {
    const existing = rows.find((item) => item.selector_id === row.selector_id)
    if (existing) existing.samples.push(...row.samples)
    else rows.push(row)
  }
  return { ...page, series: rows }
}
interface Props {
  location: LocationPoint; instant: number; fields: ServedFieldValue[]; runs: Record<string, string>; enabled: boolean; focusReady?: boolean; selectionMoving?: boolean
  onLatest: (source: string) => void
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}

/** Owned by App so switching stage/dock does not discard a finite selection. */
export function useNativeSeries(props: Props) {
  const { location, instant, runs, fields, enabled, focusReady = true, selectionMoving = false } = props
  const [first, setFirst] = useState('eccc-hrdps|temperature_2m')
  const [second, setSecond] = useState('eccc-hrdps|total_cloud_opacity')
  const [compare, setCompare] = useState(false)
  const [hours, setHours] = useState(3)
  const [data, setData] = useState<NativeSeriesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expired, setExpired] = useState(false)
  const active = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const lastStarted = useRef<string | null>(null)
  const selectors = [first, second].map((key, i): Selector => {
    const [source_id, field] = key.split('|')
    return { id: String(i), source_id, field, run: runs[source_id] ?? 'latest' }
  })
  const selection: Selection = { latitude: location.latitude, longitude: location.longitude,
    start: new Date(instant).toISOString(), end: new Date(instant + hours * 3600000).toISOString(), selectors, page_size: 12 }
  const signature = selectionKey(selection)
  const read = useCallback(async (request: unknown, append = false) => {
    active.current?.abort()
    const controller = new AbortController(); active.current = controller
    const version = ++generation.current
    setBusy(true); setError(null); setCheck(null)
    try {
      const page = readResponse(await post(endpoint, request, controller.signal))
      if (version !== generation.current) return
      // Coordinates and selectors are verified, not trusted from a late response.
      if (selectionKey(page.selection) !== signature) throw new Error('Response changed the requested Focus or selectors')
      if (append) {
        if (!data) throw new Error('Continuation has no original selection')
        setData(appendPage(data, page))
      } else setData(page)
      setExpired(Date.parse(page.snapshot.expires_at) <= Date.now())
    } catch (failure) {
      if (version === generation.current && !controller.signal.aborted) setError(String(failure))
    } finally { if (version === generation.current) setBusy(false) }
  }, [signature, data])
  const latestRead = useRef(read); latestRead.current = read
  useEffect(() => {
    if (!focusReady || selectionMoving) {
      active.current?.abort(); generation.current++; lastStarted.current = null
      setData(null); setError(null); setCheck(null); setBusy(false)
      return
    }
    if (lastStarted.current !== signature) {
      active.current?.abort(); generation.current++
      setData(null); setError(null); setCheck(null); setExpired(false); setBusy(false)
      if (enabled) { lastStarted.current = signature; void latestRead.current(JSON.parse(signature)) }
    }
  }, [signature, enabled, focusReady, selectionMoving])
  useEffect(() => () => { active.current?.abort(); generation.current++; lastStarted.current = null }, [])
  useEffect(() => {
    if (!data) return
    const timer = setTimeout(() => { setExpired(true); setCheck(null) }, Math.max(0, Date.parse(data.snapshot.expires_at) - Date.now()))
    return () => clearTimeout(timer)
  }, [data])
  async function checkChanges() {
    if (!data || expired) return
    active.current?.abort()
    const controller = new AbortController(); active.current = controller
    const version = ++generation.current
    setBusy(true); setCheck(null)
    try {
      const result = await post(`${endpoint}/changes`, { change_token: data.snapshot.change_token }, controller.signal) as { snapshot_id: string; state: string; reason: string }
      if (version !== generation.current) return
      if (result.snapshot_id !== data.snapshot.id || !['unchanged', 'changed', 'unknown'].includes(result.state)) throw new Error('Unreadable change check')
      setCheck(`${result.state}: ${result.reason}`)
    } catch (failure) { if (version === generation.current && !controller.signal.aborted) setCheck(`unknown: ${String(failure)}`) }
    finally { if (version === generation.current) setBusy(false) }
  }
  const options = new Map([[first, first.replace('|', ' · ')], [second, second.replace('|', ' · ')]])
  for (const field of fields) if (field.attribution.sourceId && field.attribution.fieldKey) {
    const key = `${field.attribution.sourceId}|${field.attribution.fieldKey}`
    options.set(key, key.replace('|', ' · '))
  }
  const select = (label: string, value: string, setter: (value: string) => void) => <label>{label}<select value={value} onChange={(event) => setter(event.target.value)}>{[...options].map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
  return <section className="native-series" aria-label="Native Series">
    <div className="series-controls"><button aria-pressed={!compare} onClick={() => setCompare(false)}>Overview</button><button aria-pressed={compare} onClick={() => setCompare(true)}>Temporary Compare</button>
      {select('Series A', first, setFirst)}{compare && select('Series B', second, setSecond)}
      <label>Window from Focus<select value={hours} onChange={(event) => setHours(Number(event.target.value))}>{[1, 3, 6, 12].map((n) => <option key={n} value={n}>{n} hours</option>)}</select></label>
      <button disabled={busy || !focusReady || selectionMoving} onClick={() => void read(selection)}>Refresh Series</button>
      <button disabled={busy || !data || expired} onClick={() => void checkChanges()}>Check for changes</button>
    </div>
    <p>Native samples only. Separate value axes preserve each field’s units; spaces between samples are not interpolated. Compare is temporary.</p>
    {selectors.filter((s) => s.run !== 'latest').map((s) => <p key={s.id}>Pinned {s.source_id}: {s.run}. <button onClick={() => props.onLatest(s.source_id)}>Use Latest available for {s.source_id}</button></p>)}
    <div role="status">{selectionMoving && <p>Pause playback to read native Series for this selection.</p>}{!focusReady && <p>Focus is awaiting registered geometry; no point values are shown.</p>}{busy && 'Reading selected native evidence…'}{error && <p>Read failed; no replacement was applied. {error}</p>}{check && <p>{check}</p>}{expired && <p>Selection expired. Refresh Series to read again.</p>}</div>
    {data && <p>Selected {data.snapshot.selected_at} · Fixed expiry {data.snapshot.expires_at}{!data.complete && ' · More native samples available'}</p>}
    {data && !expired && <>{data.series.map((row) => <NativeTrack key={row.selector_id} row={row} start={instant} end={instant + hours * 3600000} onInspect={props.onInspect} />)}
      {data.next_cursor && <button disabled={busy} onClick={() => void read({ cursor: data.next_cursor }, true)}>Load next native samples</button>}
      {data.notices.map((notice) => <p key={notice}>{notice}</p>)}
    </>}
  </section>
}
function NativeTrack({ row, start, end, onInspect }: { row: Row; start: number; end: number; onInspect: Props['onInspect'] }) {
  const readings = row.samples.map((sample) => ({ sample, a: attributionOf(sample) }))
  const numeric = readings.filter(({ sample, a }) => typeof sample.value === 'number' && Number.isFinite(sample.value)
    && a && a.evidenceClass !== 'unrecognised' && !a.derivationRefused && !a.provenanceUnmodelled && !a.uncatalogued)
  const units = new Set(numeric.map(({ sample }) => sample.provenance?.normalized_units))
  const values = numeric.map(({ sample }) => Number(sample.value))
  const min = Math.min(...values), max = Math.max(...values)
  return <section className="native-track"><h3>{row.field} · {row.source_id}</h3><p>{row.availability}: {row.reason}</p>
    {values.length > 0 && units.size === 1 && typeof [...units][0] === 'string' && <figure><svg viewBox="0 0 720 160" role="img" aria-label={`${row.field} native samples; exact values and times in the following table`}>
      <path d="M65 12V125H700" fill="none" stroke="currentColor" />
      <text x="0" y="22">{max.toPrecision(4)}</text><text x="0" y="118">{min.toPrecision(4)}</text>
      {numeric.map(({ sample, a }, i) => <circle key={i} cx={65 + 630 * (Date.parse(a!.validTime!) - start) / (end - start)} cy={max === min ? 68 : 115 - 95 * (Number(sample.value) - min) / (max - min)} r="4" fill="currentColor" />)}
      <text x="65" y="150">{new Date(start).toISOString().slice(11, 16)} UTC</text><text x="620" y="150">{new Date(end).toISOString().slice(11, 16)} UTC</text>
    </svg><figcaption>{String([...units][0])} · Discrete native points, no connecting interpolation</figcaption></figure>}
    <details><summary>Native values, gaps and run identity · {readings.length} readings</summary><table><caption>Exact native readings</caption><thead><tr><th scope="col">Native time</th><th scope="col">Value / absence</th><th scope="col">Run / identity</th><th scope="col">Evidence</th></tr></thead><tbody>
      {readings.map(({ sample, a }, i) => {
        const allowed = a && a.evidenceClass !== 'unrecognised' && !a.derivationRefused && !a.provenanceUnmodelled && !a.uncatalogued
        const text = allowed && sample.value !== null ? String(sample.value) : 'Unavailable'
        return <tr key={i}><th scope="row">{a?.validTime}</th><td>{text} {sample.provenance?.normalized_units as string}<small>{a?.qualityFlags.join(', ')}</small></td><td>{a?.runTime ?? 'No run supplied'}<small>{String(sample.provenance?.data_mode ?? 'Mode unknown')} · {a?.phase ?? 'Phase not supplied'} · {a?.member ? `Member ${a.member}` : a?.ensemble ? JSON.stringify(a.ensemble) : 'No ensemble identity'}</small></td><td>{a && <><EvidenceGlyph kind={a.evidenceClass} />{EVIDENCE_CLASS_LABELS[a.evidenceClass]}</>}<button onClick={(event) => onInspect({ key: `series:${row.selector_id}:${i}:${a?.validTime}`, label: row.field, text, attribution: a ?? undefined }, event.currentTarget)}>Inspect {row.field} at {a?.validTime}</button></td></tr>
      })}
    </tbody></table></details>
  </section>
}
