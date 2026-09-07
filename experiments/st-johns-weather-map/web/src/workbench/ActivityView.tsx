import { resolveEvidenceClass } from '../evidenceClass'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiEvidenceField } from '../api'
import type { LayerSelection, LocationPoint } from '../types'
import { EvidenceGlyph, type InspectedEvidence } from './EvidenceInspector'
import { ReturnedValue } from './ReturnedValue'
import { SourceTag } from './SourceTag'

const ORDER = ['running', 'astronomy', 'aurora', 'landscape_photography'] as const
const TITLES = ['Running', 'Astronomy', 'Aurora', 'Landscape photography']
const STATES: Record<string, string> = { unresolved: '◇ Unresolved', stopped: '■ Stopped', unchecked: '? Unchecked', unscorable: '▧ Unscorable', outside_window: '◷ Outside window', scored: '● Scored' }
const ENDPOINT = '/api/experiments/weather/v0/verdicts'
const STORAGE = 'astraeus-activity-overrides-v1'
interface Criterion {
  name: string; field: string; curve?: string; comparison?: string; outcome: string; reason: string | null; loss: number | null
  weight_declared: number | null; evaluated_weight: number | null; weight_held: number | null
  input: { evidence: ApiEvidenceField | null; reason: string | null; skipped: unknown[]; fell_to_next_source: boolean }
  threshold_defaults: Record<string, number>; thresholds_in_force: Record<string, number>
}
export interface ActivityVerdict {
  profile_id: string; profile_version?: number; title?: string; unavailable?: string; state?: string; score?: number | null
  tier?: string; limiting_criterion?: string | null; hard_stops?: Criterion[]; criteria?: Criterion[]
  coverage?: { declared: number; reachable: number; evaluated: number | null; floor: number }
  window?: { current?: { start: string; end: string } | null; next?: { start: string; end: string } | null; intervals: Array<{ start: string; end: string }>; unresolved_fields?: string[] }
  saved_stack?: Array<{ id: string; opacity: number }>; thresholds?: Record<string, { default: number; units: string }>
  [key: string]: unknown
}
interface Focus { latitude: number; longitude: number; valid_time: string; site_id: string | null }
interface Current { focus: Focus; verdicts: ActivityVerdict[]; notices: string[] }
interface Cache { expires_at: string; computed_at: string; state: string; key: string }
export interface ActivityResponse extends Current { cache: Cache; refusal?: { code: string }; input_identity: string }
interface Strip { focus: Focus; cells: Current[]; cache: Cache; next_start: string | null; complete: boolean; resolution_seconds: number | null; notices: string[]; queried_times: string[]; end: string }
interface Props {
  location: LocationPoint; instant: number; siteId: string | null; enabled: boolean; moving?: boolean; focusReady?: boolean; windowEnd?: number
  onInspect: (evidence: InspectedEvidence, opener: HTMLButtonElement) => void
  onInstant: (instant: number) => void; onStack: (stack: LayerSelection[]) => void
  onSeries: (field: string, source: string) => void
  onEvidence: (response: ActivityResponse | null) => void
}
function storedOverrides(): Record<string, number> {
  try {
    const fromUrl = new URLSearchParams(window.location.search).getAll('override')
    const value: unknown = fromUrl.length ? Object.fromEntries(fromUrl.map(item => { const [name, value] = item.split(':'); return [name, Number(value)] })) : JSON.parse(localStorage.getItem(STORAGE) ?? '{}')
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return Object.fromEntries(Object.entries(value).slice(0, 100).filter(([name, value]) => /^[a-z][a-z0-9_]*$/.test(name) && typeof value === 'number' && Number.isFinite(value)))
  } catch { return {} }
}
function sameFocus(a: Focus, b: Focus) { return a.latitude === b.latitude && a.longitude === b.longitude && Date.parse(a.valid_time) === Date.parse(b.valid_time) && a.site_id === b.site_id }
async function request(focus: Focus, overrides: Record<string, number>, signal: AbortSignal, refresh: boolean, end?: string): Promise<ActivityResponse | Strip> {
  const query = new URLSearchParams({ latitude: String(focus.latitude), longitude: String(focus.longitude), valid_time: focus.valid_time })
  if (focus.site_id) query.set('site_id', focus.site_id)
  if (end) query.set('end', end)
  if (refresh) query.set('refresh', 'true')
  for (const [key, value] of Object.entries(overrides)) query.append('override', `${key}:${value}`)
  const response = await fetch(`${ENDPOINT}${end ? '/series' : ''}?${query}`, { signal, headers: { Accept: 'application/json' } })
  const body = await response.json()
  if (!response.ok) throw new Error(`${body?.detail?.code ?? response.status}: ${body?.detail?.message ?? 'Activity request failed'}`)
  if (body.refusal) throw new Error(`Evaluator refused: ${body.refusal.code}`)
  if (!body.focus || !sameFocus(body.focus, focus) || !body.cache || !Number.isFinite(Date.parse(body.cache.expires_at))) throw new Error('Activity response identity or expiry is invalid')
  const rows = end ? body.cells?.flatMap((cell: Current) => cell.verdicts) : body.verdicts
  if (!Array.isArray(rows) || rows.some((row: ActivityVerdict) => !ORDER.includes(row.profile_id as typeof ORDER[number]) || (!row.unavailable && (!STATES[row.state ?? ''] || !Array.isArray(row.hard_stops) || !Array.isArray(row.criteria) || !row.coverage || !row.window || !Array.isArray(row.saved_stack))))) throw new Error('Activity verdict is unreadable')
  for (const row of rows) if (row.score !== null && row.score !== undefined && (!['scored', 'outside_window'].includes(row.state ?? '') || !Number.isInteger(row.score) || row.score < 0 || row.score > 100)) throw new Error('Activity returned an invalid score/state')
  if (end && (!Array.isArray(body.cells) || body.cells.some((cell: Current) => cell.focus.latitude !== focus.latitude || cell.focus.longitude !== focus.longitude || Date.parse(cell.focus.valid_time) < Date.parse(focus.valid_time) || Date.parse(cell.focus.valid_time) >= Date.parse(end)))) throw new Error('Strip cell is outside its requested Focus window')
  return body
}
export function activityEvidence(key: string, response: ActivityResponse | null): InspectedEvidence {
  const [, pid, name] = key.split(':')
  const row = response?.verdicts.find(row => row.profile_id === pid)
  const criterion = [...(row?.hard_stops ?? []), ...(row?.criteria ?? [])].find(row => row.name === name)
  return { key, label: `${TITLES[ORDER.indexOf(pid as typeof ORDER[number])] ?? pid}${name ? ` · ${name}` : ''}`, text: row ? criterion?.reason ?? criterion?.outcome ?? row.state ?? row.unavailable ?? 'Unavailable' : 'Activity selection expired or changed; old values are withheld. Refresh explicitly.', details: row ? { 'Exact Focus': response?.focus, 'Finite cache': response?.cache, ...(criterion ? { 'Selected criterion': criterion, 'Profile version': row.profile_version, 'Method': row.method, 'Method version': row.method_version, 'Override provenance': row.overrides, 'Coverage': row.coverage, 'Applicability': row.applicability } : { 'Returned verdict': row }) } : { 'Selection unavailable': true } }
}
const percent = (value: number | null | undefined) => value == null ? 'Not evaluated' : `${Math.round(value * 100)}%`

/** App owns this hook so stage/dock remounts preserve selection and expanded lane. */
export function useActivity(props: Props) {
  const { location, instant, siteId, enabled, moving = false, focusReady = true } = props
  const focus: Focus = { latitude: location.latitude, longitude: location.longitude, valid_time: new Date(instant).toISOString(), site_id: siteId }
  const key = JSON.stringify(focus)
  const [overrides, setOverrides] = useState(storedOverrides)
  const [data, setData] = useState<ActivityResponse | null>(null)
  const [strip, setStrip] = useState<Strip | null>(null)
  const [hours, setHours] = useState(6)
  const [definitions, setDefinitions] = useState<Record<string, Pick<ActivityVerdict, 'thresholds' | 'profile_version'>>>({})
  const [error, setError] = useState(''); const [stripError, setStripError] = useState('')
  const [busy, setBusy] = useState(false); const [stripBusy, setStripBusy] = useState(false)
  const [expired, setExpired] = useState(false); const [stripExpired, setStripExpired] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const controller = useRef<AbortController | null>(null)
  const stripController = useRef<AbortController | null>(null)
  const last = useRef<string | null>(null)
  const overridesKey = JSON.stringify(overrides)
  const current = !expired && !moving && data && sameFocus(data.focus, focus) ? data : null
  const currentStrip = !stripExpired && !moving && strip && sameFocus(strip.focus, focus) ? strip : null
  const load = useCallback(async (refresh = false) => {
    controller.current?.abort(); const active = new AbortController(); controller.current = active
    setBusy(true); setError(''); setData(null); setExpired(false)
    try { const result = await request(JSON.parse(key), JSON.parse(overridesKey), active.signal, refresh) as ActivityResponse; if (!active.signal.aborted) { setData(result); setDefinitions(previous => ({ ...previous, ...Object.fromEntries(result.verdicts.filter(row => row.thresholds).map(row => [row.profile_id, { thresholds: row.thresholds, profile_version: row.profile_version }])) })) } }
    catch (error) { if (!active.signal.aborted) setError(error instanceof Error ? error.message : 'Activity unavailable') }
    finally { if (!active.signal.aborted) setBusy(false) }
  }, [key, overridesKey])
  useEffect(() => {
    if (moving || !focusReady) { controller.current?.abort(); stripController.current?.abort(); last.current = null; return }
    const identity = key + overridesKey
    if (!enabled || last.current === identity) return
    last.current = identity; setStrip(null); setStripError(''); stripController.current?.abort(); void load()
  }, [enabled, moving, focusReady, key, overridesKey, load])
  useEffect(() => () => { controller.current?.abort(); stripController.current?.abort(); last.current = null }, [])
  useEffect(() => { if (!data) return; const timer = window.setTimeout(() => setExpired(true), Math.max(0, Date.parse(data.cache.expires_at) - Date.now())); return () => window.clearTimeout(timer) }, [data])
  useEffect(() => { if (!strip) return; const timer = window.setTimeout(() => setStripExpired(true), Math.max(0, Date.parse(strip.cache.expires_at) - Date.now())); return () => window.clearTimeout(timer) }, [strip])
  useEffect(() => { props.onEvidence(current) }, [current, props.onEvidence])
  const loadStrip = async (next = false) => {
    stripController.current?.abort(); const active = new AbortController(); stripController.current = active
    setStripBusy(true); setStripError(''); setStripExpired(false)
    const start = next && currentStrip?.next_start ? currentStrip.next_start : focus.valid_time
    const end = next && currentStrip ? currentStrip.end : new Date(Math.min(instant + hours * 3600000, props.windowEnd ?? Infinity)).toISOString()
    if (!next) setStrip(null)
    try {
      const page = await request({ ...focus, valid_time: start }, overrides, active.signal, false, end) as Strip
      if (!active.signal.aborted) setStrip(previous => next && previous ? { ...page, focus: previous.focus, cells: [...previous.cells, ...page.cells], queried_times: [...previous.queried_times, ...page.queried_times], cache: Date.parse(previous.cache.expires_at) < Date.parse(page.cache.expires_at) ? previous.cache : page.cache } : page)
    } catch (error) { if (!active.signal.aborted) setStripError(error instanceof Error ? error.message : 'Strip unavailable') }
    finally { if (!active.signal.aborted) setStripBusy(false) }
  }
  const inspect = (pid: string, name: string | undefined, opener: HTMLButtonElement) => props.onInspect(activityEvidence(`activity:${pid}${name ? `:${name}` : ''}`, current), opener)
  return <div className="activity-view">
    <div className="activity-toolbar"><h3 tabIndex={-1} data-inspector-return>Activity at Focus</h3><button disabled={busy || moving || !focusReady} onClick={() => { setStrip(null); stripController.current?.abort(); void load(true) }}>Refresh Activity</button><label htmlFor="activity-strip-window">Native strip window<select id="activity-strip-window" value={hours} onChange={event => { stripController.current?.abort(); setStrip(null); setStripBusy(false); setHours(Number(event.target.value)) }}>{[1,3,6,12,24].map(value => <option key={value} value={value}>{value} hours from Focus</option>)}</select></label><button disabled={stripBusy || moving || !focusReady} onClick={() => void loadStrip()}>Read native strip</button></div>
    <p role="status" aria-atomic="true">{busy ? 'Reading selected-time evidence…' : expired ? 'Activity expired. Refresh explicitly to read current evidence.' : error || (current ? `Computed ${current.cache.computed_at} · Expires ${current.cache.expires_at} · Cache ${current.cache.state}` : 'Activity not read at this Focus.')}</p>
    <p>Experimental profile evidence. Scores are not probabilities or safety clearance. Active budgets are staged; intended field gaps remain disclosed.</p>
    {(stripError || stripExpired || stripBusy) && <p role="status">{stripBusy ? 'Reading bounded native cells…' : stripExpired ? 'Strip expired; cells are withheld.' : stripError}</p>}
    {currentStrip && <p>Native strip step: {currentStrip.resolution_seconds ? `${currentStrip.resolution_seconds / 3600} hours` : 'Unavailable'}. Gaps stay empty. {currentStrip.complete ? 'Bounded read complete.' : `Unqueried from ${currentStrip.next_start}.`} {currentStrip.next_start && <button disabled={stripBusy} onClick={() => void loadStrip(true)}>Read next native cells</button>}</p>}
    <div className="activity-lanes">{ORDER.map((pid, index) => {
      const row = current?.verdicts.find(row => row.profile_id === pid)
      const definition = row?.thresholds ? row : definitions[pid]
      const open = expanded === pid
      return <section className="activity-lane" data-state={row?.state ?? 'unavailable'} key={pid}>
        <div className="activity-summary"><div><h4><button aria-expanded={open} aria-controls={`activity-${pid}`} onClick={() => setExpanded(open ? null : pid)}>{TITLES[index]}</button></h4><p className="activity-state">{STATES[row?.state ?? ''] ?? '◇ Unavailable'}</p><p>{row?.score != null ? row.tier === 'planning' ? 'Planning score band' : `${row.score} / 100` : row?.unavailable ?? 'Score withheld'}</p>{row?.tier === 'planning' && row.score != null && <meter min={0} max={100} value={row.score} aria-label={`${TITLES[index]} planning score band`} />}</div>
          <div><p>Limiting: {row?.limiting_criterion ?? 'Not available'}</p><p>Coverage {percent(row?.coverage?.evaluated)} · Reachable {percent(row?.coverage?.reachable)} · Floor {percent(row?.coverage?.floor)}</p><p>{row?.window?.current ? 'Geometric window ends' : 'Next geometric window'}: {row?.window?.current?.end ?? row?.window?.next?.start ?? row?.window?.intervals.find(interval => Date.parse(interval.start) > instant)?.start ?? (row?.window?.unresolved_fields?.length ? `Unresolved: ${row.window.unresolved_fields.join(', ')}` : 'None returned')}</p>{Array.isArray(row?.site_inputs) && row.site_inputs.some(input => input.state === 'no_site') && <p>Needs a site for {row.site_inputs.filter(input => input.state === 'no_site').map(input => input.field).join(', ')}</p>}{row?.tier === 'planning' && <p>Unavailable fields: {[...(row.hard_stops ?? []), ...(row.criteria ?? [])].filter(item => item.outcome === 'unknown').map(item => item.field).join(', ') || 'None in this returned evaluation'}</p>}</div>
          <div className="activity-strip" style={currentStrip?.resolution_seconds ? { gridTemplateColumns: `repeat(${Math.ceil((Date.parse(currentStrip.end) - instant) / (currentStrip.resolution_seconds * 1000))}, minmax(100px, 1fr))` } : undefined}>{currentStrip?.cells.map(cell => { const verdict = cell.verdicts.find(row => row.profile_id === pid); if (verdict?.issued === false) return null; return <button key={cell.focus.valid_time} style={{ gridColumn: currentStrip.resolution_seconds ? Math.floor((Date.parse(cell.focus.valid_time) - instant) / (currentStrip.resolution_seconds * 1000)) + 1 : undefined, background: verdict?.score == null ? undefined : `color-mix(in srgb, var(--bench-accent) ${Math.round(verdict.score * .25)}%, var(--bench-panel))` }} data-state={verdict?.state ?? 'unavailable'} onClick={() => props.onInstant(Date.parse(cell.focus.valid_time))} title={`${verdict?.state ?? 'unavailable'} · ${verdict?.tier === 'planning' ? 'Planning band' : verdict?.score ?? 'Score withheld'} · Limiting: ${verdict?.limiting_criterion ?? 'Unavailable'}`} aria-label={`${TITLES[index]} at ${cell.focus.valid_time}: ${verdict?.state ?? 'unavailable'}`}><time>{cell.focus.valid_time.slice(11, 16)} UTC</time><span>{STATES[verdict?.state ?? ''] ?? '◇ Unavailable'}</span>{typeof verdict?.resolution_seconds === 'number' && <small>{verdict.resolution_seconds / 3600}h step</small>}{verdict?.score != null && (verdict.tier === 'planning' ? <meter min={0} max={100} value={verdict.score} aria-label="Planning score band" /> : <span>{verdict.score}</span>)}</button> })}{!currentStrip && <p>Native strip not read</p>}{currentStrip && <div className="activity-windows"><WindowBand intervals={row?.window?.intervals ?? []} unresolved={row?.window?.unresolved_fields ?? []} start={instant} end={Date.parse(currentStrip.end)} title={TITLES[index]} /></div>}</div>
        </div>
        {open && <div id={`activity-${pid}`} className="activity-expanded">{row && !row.unavailable ? <>
          <button onClick={event => inspect(pid, undefined, event.currentTarget)}>Inspect {TITLES[index]} verdict</button>
          <button onClick={() => props.onStack([...(row.saved_stack ?? [])].reverse().map(entry => ({ ...entry, visible: true })))}>Load {TITLES[index]} Map stack</button>
          <h5>Hard stops</h5>{row.hard_stops?.length ? <Criteria rows={row.hard_stops} pid={pid} inspect={inspect} onSeries={props.onSeries} /> : <p>No hard stops declared in this profile.</p>}
          <h5>Graded criteria</h5>{row.criteria?.length ? <Criteria rows={row.criteria} pid={pid} inspect={inspect} onSeries={props.onSeries} /> : <p>Grading was prevented. See the hard-stop evidence.</p>}
          <details><summary>Profile version, intended weights, exclusions and applicability</summary><ReturnedValue value={{ version: row.profile_version, intended_weights: row.intended_weights, active_weights: row.active_weights, admission_residuals: row.admission_residuals, blocked_fields: row.blocked_fields, applicability: row.applicability, site_inputs: row.site_inputs, window: row.window, quality: row.quality, freshness: row.freshness }} /></details>

        </> : <p>{row?.unavailable ?? error ?? 'No server verdict available.'}</p>}{definition?.thresholds && <>          <details><summary>{TITLES[index]} threshold overrides</summary><p>Named anchors use their declared units. The server validates curve order. Defaults remain recorded with every verdict.</p><form onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const next = { ...overrides }; for (const name of Object.keys(definition.thresholds ?? {})) { const raw = String(form.get(name) ?? '').trim(); if (raw === '') delete next[name]; else { const value = Number(raw); if (!Number.isFinite(value)) { setNotice('Enter finite threshold values.'); return }; next[name] = value } }; setOverrides(next); try { localStorage.setItem(STORAGE, JSON.stringify(next)); setNotice('Overrides saved in this browser and submitted for server validation.') } catch { setNotice('Browser storage unavailable; overrides apply to this session.') } }}>
            {Object.entries(definition.thresholds ?? {}).map(([name, threshold]) => <label key={`${name}:${overrides[name] ?? ''}`} htmlFor={`override-${name}`}>{name} · {threshold.units} · Default {threshold.default}<input id={`override-${name}`} name={name} type="number" step="any" defaultValue={overrides[name] ?? ''} placeholder="Use default" /></label>)}<button>Apply {TITLES[index]} overrides</button></form></details></>}</div>}
      </section>
    })}</div>
    <div className="activity-toolbar"><button onClick={() => { setOverrides({}); try { localStorage.removeItem(STORAGE) } catch { /* session still clears */ }; setNotice('Profile defaults restored.') }}>Restore all profile defaults</button><button onClick={async () => { const url = new URL(window.location.href); url.searchParams.delete('override'); for (const [name, value] of Object.entries(overrides)) url.searchParams.append('override', `${name}:${value}`); try { await navigator.clipboard.writeText(url.href); setNotice('Copied Activity link with explicit overrides.') } catch { setNotice(`Share link: ${url.href}`) } }}>Share with overrides</button></div>
    {notice && <p role="status">{notice}</p>}{current?.notices.map(notice => <p key={notice}>{notice}</p>)}
  </div>
}
function Criteria({ rows, pid, inspect, onSeries }: { rows: Criterion[]; pid: string; inspect: (pid: string, name: string, opener: HTMLButtonElement) => void; onSeries: Props['onSeries'] }) {
  return <div className="activity-table"><table><caption>{pid} returned criterion evidence</caption><thead><tr><th scope="col">Criterion / source</th><th scope="col">Native value</th><th scope="col">Curve / thresholds</th><th scope="col">Outcome</th><th scope="col">Weight held</th><th scope="col">Evidence</th></tr></thead><tbody>{rows.map(row => {
    const provenance = row.input.evidence?.provenance
    const source = typeof provenance?.source_id === 'string' ? provenance.source_id : null
    const value = row.input.evidence?.value
    return <tr key={row.name}><th scope="row"><EvidenceGlyph kind={resolveEvidenceClass(provenance?.evidence_class)} />{row.name}<small>{row.field} · <SourceTag id={source} /></small></th><td>{typeof value === 'number' ? `${value} ${String(provenance?.normalized_units ?? '')}` : 'Not returned'}</td><td>{row.curve ?? 'Declared comparison'} {row.comparison ?? ''}<ul>{Object.entries(row.thresholds_in_force).map(([name, value]) => <li key={name}>{name}: {value} {String(provenance?.normalized_units ?? '')}</li>)}</ul></td><td>{row.outcome} · {row.reason ?? 'Returned curve/comparison'}{row.input.fell_to_next_source && <p>Fell to next eligible source</p>}</td><td>{percent(row.weight_held)}</td><td><button onClick={event => inspect(pid, row.name, event.currentTarget)}>Inspect {pid} {row.name}</button>{source && ['eccc-hrdps','eccc-rdps','eccc-gdps','noaa-gfs'].includes(source) && <button onClick={() => onSeries(row.field, source)}>Open {pid} {row.name} in Series</button>}</td></tr>
  })}</tbody></table></div>
}

function WindowBand({ intervals, unresolved, start, end, title }: { intervals: Array<{ start: string; end: string }>; unresolved: string[]; start: number; end: number; title: string }) {
  if (unresolved.length) return <small>Window unresolved: {unresolved.join(', ')}</small>
  const description = intervals.length ? intervals.map(interval => `${interval.start} to ${interval.end}`).join('; ') : 'No geometric interval returned'
  return <><svg viewBox="0 0 100 4" preserveAspectRatio="none" role="img" aria-label={`${title} geometric window band: ${description}`}><title>{description}</title>{intervals.map((interval, index) => { const x = Math.max(0, Math.min(100, 100 * (Date.parse(interval.start) - start) / (end - start))); const right = Math.max(0, Math.min(100, 100 * (Date.parse(interval.end) - start) / (end - start))); return <rect key={index} x={x} y={0} width={Math.max(0, right - x)} height={4} fill="currentColor" /> })}</svg><small>Geometric window band</small></>
}
