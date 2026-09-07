import { SourceTag, sourceAttributes } from './SourceTag'
import { useCallback, useEffect, useRef, useState } from 'react'
import { attributionOf, type ApiEvidenceField } from '../api'
import type { LocationPoint, ServedFieldValue } from '../types'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'
import { resolveFamily } from '../fieldFamily'
import { EVIDENCE_CLASS_LABELS } from '../evidenceClass'

interface Selector { id: string; source_id: string; field: string; run: string }
interface Selection { latitude: number; longitude: number; start: string; end: string; selectors: Selector[]; page_size: number }
interface RunChoice { id: string; run_time: string }
export interface NativeSeriesRow { selectable_runs?: RunChoice[]; run_inventory_reason?: string; selector_id: string; source_id: string; field: string; requested_run: string; availability: 'available' | 'checked_empty' | 'unknown' | 'unavailable'; reason: string | null; samples: ApiEvidenceField[] }
export interface NativeSeriesResponse {
  selection: Selection
  snapshot: { id: string; selected_at: string; expires_at: string; change_token: string; identities: unknown[] }
  series: NativeSeriesRow[]; next_cursor: string | null; complete: boolean; notices: string[]
}
export type SharedSeriesSelection = Pick<NativeSeriesResponse, 'selection' | 'snapshot' | 'series' | 'complete'> & { expired: boolean; families?: Record<string, string[]> }
export function selectedEvidence(evidence: InspectedEvidence, snapshot: NativeSeriesResponse['snapshot']): InspectedEvidence {
  return { ...evidence, key: `native:${snapshot.id}:${evidence.key}`, details: { ...evidence.details, 'Finite native selection': { id: snapshot.id, selected_at: snapshot.selected_at, expires_at: snapshot.expires_at } } }
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
    if (!selector || selector.source_id !== row.source_id || selector.field !== row.field || selector.run !== row.requested_run || !Array.isArray(row.samples)
      || !['available', 'checked_empty', 'unknown', 'unavailable'].includes(row.availability)) throw new Error('Series identity is unreadable')
    if (row.selectable_runs !== undefined && (!Array.isArray(row.selectable_runs) || row.selectable_runs.length > 2 || !row.selectable_runs.every((run) => run && typeof run.id === 'string' && run.id.length > 0 && typeof run.run_time === 'string' && Number.isFinite(Date.parse(run.run_time))))) throw new Error('Run inventory is unreadable')
    const pinned = row.selectable_runs?.find((run) => run.id === selector.run)
    for (const sample of row.samples) {
      if (selector.run !== 'latest' && (!pinned || Date.parse(typeof sample.provenance?.run_time === 'string' ? sample.provenance.run_time : '') !== Date.parse(pinned.run_time))) throw new Error('Reading does not match the pinned run')
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
  jumpTo?: { field: string; source: string; revision: number } | null
  location: LocationPoint; instant: number; fields: ServedFieldValue[]; runs: Record<string, string>; enabled: boolean; focusReady?: boolean; selectionMoving?: boolean
  onLatest: (source: string) => void
  onRun?: (source: string, run: string) => void
  onEvidence?: (selection: SharedSeriesSelection | null) => void
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
}

/** Owned by App so switching stage/dock does not discard a finite selection. */
export function useNativeSeries(props: Props) {
  const { location, instant, runs, fields, enabled, focusReady = true, selectionMoving = false } = props
  const [first, setFirst] = useState('eccc-hrdps|temperature_2m')
  const [second, setSecond] = useState('eccc-hrdps|total_cloud_opacity')
  const [compare, setCompare] = useState(false)
  const [runPair, setRunPair] = useState<{ source: string; field: string; runs: RunChoice[] } | null>(null)
  const [hours, setHours] = useState(3)
  const [inventoryRows, setInventoryRows] = useState<NativeSeriesRow[]>([])
  const [data, setData] = useState<NativeSeriesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [expired, setExpired] = useState(false)
  const active = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const lastStarted = useRef<string | null>(null)
  useEffect(() => { if (props.jumpTo) { setFirst(`${props.jumpTo.source}|${props.jumpTo.field}`); setRunPair(null); setCompare(false) } }, [props.jumpTo])
  const selectors = [first, second].map((key, i): Selector => {
    const [source_id, field] = key.split('|')
    return runPair ? { id: String(i), source_id: runPair.source, field: runPair.field, run: runPair.runs[i].id } : { id: String(i), source_id, field, run: runs[source_id] ?? 'latest' }
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
      setInventoryRows((current) => [...new Map([...current, ...page.series].filter((row) => selection.selectors.some((selector) => selector.source_id === row.source_id)).map((row) => [row.source_id, row])).values()])
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
  useEffect(() => {
    props.onEvidence?.(data ? { selection: data.selection, snapshot: data.snapshot, families: Object.fromEntries(data.series.map((row) => [row.selector_id, [...new Set(row.samples.map((sample) => resolveFamily(sample.family)))]])), series: expired ? data.series.map((row) => ({ ...row, samples: [] })) : data.series, complete: data.complete, expired } : null)
  }, [data, expired, props.onEvidence])
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
  const select = (label: string, value: string, setter: (value: string) => void) => <label>{label}<select value={value} onChange={(event) => { setRunPair(null); setter(event.target.value) }}>{[...options].map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
  const runInventories = new Map<string, { choices: RunChoice[]; reason: string }>()
  for (const row of inventoryRows) runInventories.set(row.source_id, { choices: row.selectable_runs ?? [], reason: row.run_inventory_reason ?? 'Selectable runs are not supplied by this reader' })
  const firstSource = first.split('|')[0]
  const pairChoices = runInventories.get(firstSource)?.choices ?? []
  return <section className="native-series" aria-label="Native Series">
    <div className="series-controls"><button aria-pressed={!compare} onClick={() => setCompare(false)}>Overview</button><button aria-pressed={compare} onClick={() => setCompare(true)}>Temporary Compare</button>
      {!runPair && <>{select('Series A', first, setFirst)}{compare && select('Series B', second, setSecond)}</>}
      <label>Window from Focus<select data-inspector-return value={hours} onChange={(event) => setHours(Number(event.target.value))}>{[1, 3, 6, 12].map((n) => <option key={n} value={n}>{n} hours</option>)}</select></label>
      <button disabled={busy || !focusReady || selectionMoving} onClick={() => void read(selection)}>Refresh Series</button>
      <button disabled={busy || !data || expired} onClick={() => void checkChanges()}>Check for changes</button>
    </div>
    {props.onRun && <div className="series-run-controls" aria-label="Source run selection">{[...runInventories].map(([source, inventory]) => {
      const pinned = runs[source], previous = inventory.choices[1]
      return <div key={source}><label>Browsing run for {source}<select disabled={expired || selectionMoving} value={pinned ?? 'latest'} onChange={(event) => event.target.value === 'latest' ? props.onLatest(source) : props.onRun?.(source, event.target.value)}>
        <option value="latest">Latest available</option>
        {previous && <option value={previous.id}>Previous · {previous.id} · {previous.run_time}</option>}
        {pinned && pinned !== previous?.id && <option value={pinned}>Pinned · {pinned}{inventory.choices.some((run) => run.id === pinned) ? '' : ' · Run no longer available in this inventory'}</option>}
      </select></label><p>{inventory.reason}</p>{!previous && <p>No named previous run is established by this inventory.</p>}</div>
    })}</div>}
    {compare && !runPair && <button disabled={busy || expired || pairChoices.length !== 2} onClick={() => setRunPair({ source: firstSource, field: first.split('|')[1], runs: pairChoices })}>Compare latest and previous runs of Series A</button>}
    {runPair && <p>Temporary same-field comparison · {runPair.field} · {runPair.source} · {runPair.runs.map((run) => run.id).join(' / ')}. Map and Activity are unchanged. <button onClick={() => setRunPair(null)}>Stop run comparison</button></p>}
    <p>Native samples only. Separate value axes preserve each field’s units; spaces between samples are not interpolated. Compare is temporary.</p>
    {!runPair && selectors.filter((s) => s.run !== 'latest').map((s) => <p key={s.id}>Pinned {s.source_id}: {s.run}. <button onClick={() => props.onLatest(s.source_id)}>Use Latest available for {s.source_id}</button></p>)}
    <div role="status">{selectionMoving && <p>Pause playback to read native Series for this selection.</p>}{!focusReady && <p>Focus is awaiting registered geometry; no point values are shown.</p>}{busy && 'Reading selected native evidence…'}{error && <p>Read failed; no replacement was applied. {error}</p>}{check && <p>{check}</p>}{expired && <p>Selection expired. Refresh Series to read again.</p>}</div>
    {data && <p>Selected {data.snapshot.selected_at} · Fixed expiry {data.snapshot.expires_at}{!data.complete && ' · More native samples available'}</p>}
    {data && !expired && <>{runPair && compare && <RunOverlay rows={data.series} start={instant} end={instant + hours * 3600000} />}{data.series.map((row) => <NativeTrack hidePlot={Boolean(runPair && compare)} key={row.selector_id} row={row} start={instant} end={instant + hours * 3600000} onInspect={(evidence, opener) => props.onInspect(selectedEvidence(evidence, data.snapshot), opener)} />)}
      {data.next_cursor && <button disabled={busy} onClick={() => void read({ cursor: data.next_cursor }, true)}>Load next native samples</button>}
      {data.notices.map((notice) => <p key={notice}>{notice}</p>)}
    </>}
  </section>
}
export function NativeTrack({ row, start, end, onInspect, hidePlot = false }: { hidePlot?: boolean; row: NativeSeriesRow; start: number; end: number; onInspect: Props['onInspect'] }) {
  const readings = row.samples.map((sample) => ({ sample, a: attributionOf(sample) }))
  const numeric = readings.filter(({ sample, a }) => typeof sample.value === 'number' && Number.isFinite(sample.value)
    && a && a.evidenceClass !== 'unrecognised' && !a.derivationRefused && !a.provenanceUnmodelled && !a.uncatalogued)
  const units = new Set(numeric.map(({ sample }) => sample.provenance?.normalized_units))
  const values = numeric.map(({ sample }) => Number(sample.value))
  const min = Math.min(...values), max = Math.max(...values)
  return <section className="native-track"><h3>{row.field} · <SourceTag id={row.source_id} /> · {row.requested_run}</h3><p>{row.availability}: {row.reason}</p>
    {!hidePlot && values.length > 0 && units.size === 1 && typeof [...units][0] === 'string' && <figure><svg viewBox="0 0 720 160" role="img" aria-label={`${row.field} native samples; exact values and times in the following table`}>
      <path d="M65 12V125H700" fill="none" stroke="currentColor" />
      <text x="0" y="22">{max.toPrecision(4)}</text><text x="0" y="118">{min.toPrecision(4)}</text>
      <g className="native-samples" {...sourceAttributes(row.source_id)}>{numeric.map(({ sample, a }, i) => <circle key={i} cx={65 + 630 * (Date.parse(a!.validTime!) - start) / (end - start)} cy={max === min ? 68 : 115 - 95 * (Number(sample.value) - min) / (max - min)} r="4" fill="currentColor" />)}</g>
      <text x="65" y="150">{new Date(start).toISOString().slice(11, 16)} UTC</text><text x="620" y="150">{new Date(end).toISOString().slice(11, 16)} UTC</text>
    </svg><figcaption>{String([...units][0])} · Discrete native points, no connecting interpolation</figcaption></figure>}
    <details><summary>Native values, gaps and run identity · {readings.length} readings</summary><table><caption>Exact native readings</caption><thead><tr><th scope="col">Native time</th><th scope="col">Value / absence</th><th scope="col">Run / identity</th><th scope="col">Evidence</th></tr></thead><tbody>
      {readings.map(({ sample, a }, i) => {
        const allowed = a && a.evidenceClass !== 'unrecognised' && !a.derivationRefused && !a.provenanceUnmodelled && !a.uncatalogued
        const text = allowed && sample.value !== null ? String(sample.value) : 'Unavailable'
        return <tr key={i}><th scope="row">{a?.validTime}</th><td>{text} {sample.provenance?.normalized_units as string}<small>{a?.qualityFlags.join(', ')}</small></td><td>{a?.runTime ?? 'No run supplied'}<small>{String(sample.provenance?.data_mode ?? 'Mode unknown')} · {a?.phase ?? 'Phase not supplied'} · {a?.member ? `Member ${a.member}` : a?.ensemble ? JSON.stringify(a.ensemble) : 'No ensemble identity'}</small></td><td>{a && <><EvidenceGlyph kind={a.evidenceClass} />{EVIDENCE_CLASS_LABELS[a.evidenceClass]}</>}<button aria-label={`Inspect ${row.field} at ${a?.validTime} from ${row.source_id}, run ${a?.runTime ?? row.requested_run}, track ${row.selector_id}`} onClick={(event) => onInspect({ key: `series:${row.selector_id}:${i}:${a?.validTime}`, label: row.field, text, attribution: a ?? undefined }, event.currentTarget)}>Inspect {row.field} at {a?.validTime}</button></td></tr>
      })}
    </tbody></table></details>
  </section>
}

function RunOverlay({ rows, start, end }: { rows: NativeSeriesRow[]; start: number; end: number }) {
  if (rows.length !== 2 || rows[0].source_id !== rows[1].source_id || rows[0].field !== rows[1].field) return null
  const points = rows.flatMap((row, series) => row.samples.flatMap((sample) => {
    const a = attributionOf(sample)
    return typeof sample.value === 'number' && Number.isFinite(sample.value) && a && a.evidenceClass !== 'unrecognised' && !a.derivationRefused && !a.provenanceUnmodelled && !a.uncatalogued ? [{ series, sample, time: Date.parse(a.validTime!) }] : []
  }))
  const units = new Set(points.map(({ sample }) => sample.provenance?.normalized_units))
  if (!points.length || units.size !== 1 || typeof [...units][0] !== 'string') return <p>Run overlay unavailable: no compatible numeric native readings. Each run retains its own table.</p>
  const min = Math.min(...points.map(({ sample }) => Number(sample.value))), max = Math.max(...points.map(({ sample }) => Number(sample.value)))
  return <figure><svg viewBox="0 0 720 160" role="img" aria-label="Same-field run overlay; circles for run A, squares for run B; exact native readings in the following tables">
    <path d="M65 12V125H700" fill="none" stroke="currentColor" /><text x="0" y="22">{max.toPrecision(4)}</text><text x="0" y="118">{min.toPrecision(4)}</text>
    <g className="native-samples" {...sourceAttributes(rows[0].source_id)}>{points.map(({ series, sample, time }, index) => {
      const x = 65 + 630 * (time - start) / (end - start), y = max === min ? 68 : 115 - 95 * (Number(sample.value) - min) / (max - min)
      return series === 0 ? <circle key={index} cx={x} cy={y} r="4" fill="currentColor" /> : <rect key={index} x={x - 5} y={y - 5} width="10" height="10" fill="none" stroke="currentColor" />
    })}</g><text x="65" y="150">{new Date(start).toISOString().slice(11, 16)} UTC</text><text x="620" y="150">{new Date(end).toISOString().slice(11, 16)} UTC</text>
  </svg><figcaption>{String([...units][0])} · Run A (filled circles): {rows[0].requested_run}; Run B (open squares): {rows[1].requested_run}. Native gaps remain empty; no difference is calculated.</figcaption></figure>
}
